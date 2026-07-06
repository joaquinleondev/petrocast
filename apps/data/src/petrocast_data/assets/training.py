"""Partitioned Dagster assets for recurrent model retraining (F3-19)."""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import dagster as dg
import pandas as pd
from petrocast_ml import (
    CandidateNotApprovedError,
    FeatureKind,
    MlSettings,
    ModelRegistry,
    RunMetadata,
    TrainableModel,
    TrainingRequest,
    TrainingResult,
    create_registry_client,
    create_tracking_client,
    promote_champion,
    record_training_run,
    register_candidate,
    validate_feature_frame,
)
from petrocast_ml.evaluation import EVALUATION_FILE, evaluate
from petrocast_ml.features import CONTRACT_SCHEMA
from petrocast_ml.training import TARGET_COLUMN, build_training_dataset, save_training_artifact
from petrocast_ml.training.artifact import load_booster
from petrocast_ml.training.pipeline import train
from psycopg.connection import Connection

from petrocast_data.assets.features import (
    FEATURE_ASSET_KEY,
    FEATURE_BACKFILL_POLICY,
    FEATURE_MODEL_PATH,
    FEATURE_MONTHLY_PARTITIONS,
    _feature_config_hash,
    _feature_dbt_vars,
    feature_dbt_assets,
)
from petrocast_data.settings import DataSettings, get_settings

TRAINING_ASSET_KEY = dg.AssetKey(["ml", "training_candidate"])
EVALUATION_ASSET_KEY = dg.AssetKey(["ml", "model_evaluation"])
PROMOTION_ASSET_KEY = dg.AssetKey(["ml", "champion_promotion"])
TRAINING_HORIZONS = (1, 2, 3)

_FEATURE_QUERY = """
select
    well_id,
    as_of_date,
    oil_prod_m3_lag_1m,
    oil_prod_m3_lag_2m,
    oil_prod_m3_lag_3m,
    oil_prod_m3_lag_6m,
    oil_prod_m3_lag_12m,
    oil_prod_m3_roll_mean_3m,
    oil_prod_m3_roll_mean_6m,
    oil_prod_m3_roll_mean_12m,
    oil_prod_m3_roll_std_6m,
    oil_prod_m3_roll_std_12m,
    oil_prod_m3_trend_6m,
    oil_prod_m3_trend_12m,
    months_with_history,
    well_age_months,
    months_since_last_observed,
    zero_months_12m,
    last_observed_month,
    basin,
    field,
    resource_type
from features.well_features
where as_of_date <= %s
order by as_of_date, well_id
"""

_PRODUCTION_QUERY = """
select well_id, production_month, oil_prod_m3
from gold.fact_production
order by production_month, well_id
"""


@dataclass(frozen=True, slots=True)
class TrainingCandidate:
    """Serializable handoff from training to evaluation."""

    request: TrainingRequest
    artifact_dir: Path
    metrics: dict[str, float]
    training_rows: int
    dataset_rows: int
    wells: int


@dataclass(frozen=True, slots=True)
class EvaluatedCandidate:
    """Tracked candidate ready for registry registration and promotion."""

    run_id: str
    as_of_date: date
    gates_passed: bool
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Registry version promoted to the stable champion alias."""

    run_id: str
    version: str
    alias: str
    as_of_date: date


def _query_frame(
    settings: DataSettings,
    query: str,
    parameters: tuple[object, ...] = (),
) -> pd.DataFrame:
    with (
        Connection.connect(settings.psycopg_dsn) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(query, parameters)
        rows = cursor.fetchall()
        if cursor.description is None:
            raise RuntimeError("training query returned no column description")
        columns = [column.name for column in cursor.description]
    return pd.DataFrame(rows, columns=columns)


def load_training_frames(
    settings: DataSettings,
    *,
    as_of_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and normalize persisted features plus Gold production history."""
    features = _query_frame(settings, _FEATURE_QUERY, (as_of_date,))
    production = _query_frame(settings, _PRODUCTION_QUERY)
    if features.empty:
        raise ValueError(f"no persisted features available through {as_of_date}")
    if production.empty:
        raise ValueError("gold.fact_production is empty")

    for column in ("as_of_date", "last_observed_month"):
        features[column] = pd.to_datetime(features[column])
    for column, kind in CONTRACT_SCHEMA.items():
        if kind is FeatureKind.NUMERIC:
            features[column] = pd.to_numeric(features[column])
    features["well_id"] = features["well_id"].astype("string")
    features = validate_feature_frame(features)

    production["well_id"] = production["well_id"].astype("string")
    production["production_month"] = pd.to_datetime(production["production_month"])
    production["oil_prod_m3"] = pd.to_numeric(production["oil_prod_m3"])
    return features, production


def ml_settings_from_data(settings: DataSettings) -> MlSettings:
    """Map Dagster configuration onto the shared ML package contract."""
    return MlSettings(
        mlflow_tracking_uri=settings.mlflow_tracking_uri,
        mlflow_experiment_name=settings.mlflow_experiment_name,
        mlflow_model_name=settings.mlflow_model_name,
        mlflow_model_alias=settings.mlflow_model_alias,
    )


def build_candidate(
    features: pd.DataFrame,
    production: pd.DataFrame,
    *,
    as_of_date: date,
    features_version: str,
    artifact_dir: Path,
) -> TrainingCandidate:
    """Build the supervised dataset, train the model and persist its artifact."""
    dataset = build_training_dataset(features, production, horizons=TRAINING_HORIZONS)
    request = TrainingRequest(
        as_of_date=as_of_date,
        features_version=features_version,
        horizon=max(TRAINING_HORIZONS),
    )
    result = train(dataset, dataset[TARGET_COLUMN], request=request)
    saved_dir = save_training_artifact(
        result,
        request=request,
        dataset=dataset,
        output_dir=artifact_dir,
    )
    return TrainingCandidate(
        request=request,
        artifact_dir=saved_dir,
        metrics=dict(result.metrics),
        training_rows=result.training_rows,
        dataset_rows=len(dataset),
        wells=int(dataset["well_id"].nunique()),
    )


def evaluate_and_track_candidate(
    candidate: TrainingCandidate,
    features: pd.DataFrame,
    production: pd.DataFrame,
    *,
    settings: DataSettings,
) -> EvaluatedCandidate:
    """Evaluate gates and record the complete candidate run in MLflow."""
    dataset = build_training_dataset(features, production, horizons=TRAINING_HORIZONS)
    result = TrainingResult(
        model=cast(TrainableModel, load_booster(candidate.artifact_dir)),
        metrics=candidate.metrics,
        training_rows=candidate.training_rows,
    )
    report = evaluate(
        result.model,
        dataset,
        production,
        request=candidate.request,
    )
    (candidate.artifact_dir / EVALUATION_FILE).write_text(
        json.dumps(report.to_dict(), indent=2),
        encoding="utf-8",
    )
    run_id = record_training_run(
        create_tracking_client(ml_settings_from_data(settings)),
        request=candidate.request,
        result=result,
        dataset=dataset,
        run_metadata=RunMetadata(
            as_of_date=candidate.request.as_of_date,
            features_version=candidate.request.features_version,
            git_commit=settings.git_sha,
        ),
        artifact_dir=candidate.artifact_dir,
        evaluation=report,
    )
    return EvaluatedCandidate(
        run_id=run_id,
        as_of_date=candidate.request.as_of_date,
        gates_passed=report.gates_passed,
        metrics=report.to_mlflow_metrics(),
    )


def register_and_promote_candidate(
    candidate: EvaluatedCandidate,
    *,
    settings: DataSettings,
    registry: ModelRegistry | None = None,
) -> PromotionResult:
    """Register a candidate and move champion only after successful gates."""
    ml_settings = ml_settings_from_data(settings)
    resolved_registry = registry or create_registry_client(ml_settings)
    version = register_candidate(
        resolved_registry,
        run_id=candidate.run_id,
        settings=ml_settings,
    )
    if not candidate.gates_passed:
        raise CandidateNotApprovedError(
            f"model {version.name} version {version.version} did not pass quality gates"
        )
    champion = promote_champion(
        resolved_registry,
        version=version.version,
        settings=ml_settings,
    )
    return PromotionResult(
        run_id=candidate.run_id,
        version=champion.version,
        alias=ml_settings.mlflow_model_alias,
        as_of_date=candidate.as_of_date,
    )


def _trigger_source(context: dg.AssetExecutionContext) -> str:
    return str(context.run_tags.get("petrocast/trigger", "manual"))


@dg.asset(
    key=TRAINING_ASSET_KEY,
    deps=[FEATURE_ASSET_KEY],
    partitions_def=FEATURE_MONTHLY_PARTITIONS,
    backfill_policy=FEATURE_BACKFILL_POLICY,
    group_name="ml",
)
def ml_training_candidate(
    context: dg.AssetExecutionContext,
) -> dg.Output[TrainingCandidate]:
    """Train one candidate from persisted point-in-time feature snapshots."""
    as_of_date = date.fromisoformat(context.partition_key)
    settings = get_settings()
    features, production = load_training_frames(settings, as_of_date=as_of_date)
    features_version = _feature_config_hash(
        _feature_dbt_vars(context.partition_key),
        FEATURE_MODEL_PATH,
    )
    candidate = build_candidate(
        features,
        production,
        as_of_date=as_of_date,
        features_version=features_version,
        artifact_dir=settings.ml_artifact_dir / context.partition_key / context.run_id,
    )
    return dg.Output(
        candidate,
        metadata={
            "as_of_date": context.partition_key,
            "trigger": _trigger_source(context),
            "dataset_rows": candidate.dataset_rows,
            "wells": candidate.wells,
            "features_version": features_version,
            "artifact_dir": str(candidate.artifact_dir),
        },
    )


@dg.asset(
    key=EVALUATION_ASSET_KEY,
    ins={"ml_training_candidate": dg.AssetIn(key=TRAINING_ASSET_KEY)},
    partitions_def=FEATURE_MONTHLY_PARTITIONS,
    backfill_policy=FEATURE_BACKFILL_POLICY,
    group_name="ml",
)
def ml_model_evaluation(
    context: dg.AssetExecutionContext,
    ml_training_candidate: TrainingCandidate,
) -> dg.Output[EvaluatedCandidate]:
    """Backtest the candidate, apply gates and persist the MLflow run."""
    settings = get_settings()
    features, production = load_training_frames(
        settings,
        as_of_date=ml_training_candidate.request.as_of_date,
    )
    evaluated = evaluate_and_track_candidate(
        ml_training_candidate,
        features,
        production,
        settings=settings,
    )
    return dg.Output(
        evaluated,
        metadata={
            "as_of_date": evaluated.as_of_date.isoformat(),
            "trigger": _trigger_source(context),
            "mlflow_run_id": evaluated.run_id,
            "gates_passed": evaluated.gates_passed,
            "metrics": dg.MetadataValue.json(cast(dict[str, Any], evaluated.metrics)),
        },
    )


@dg.asset(
    key=PROMOTION_ASSET_KEY,
    ins={"ml_model_evaluation": dg.AssetIn(key=EVALUATION_ASSET_KEY)},
    partitions_def=FEATURE_MONTHLY_PARTITIONS,
    backfill_policy=FEATURE_BACKFILL_POLICY,
    group_name="ml",
)
def ml_champion_promotion(
    context: dg.AssetExecutionContext,
    ml_model_evaluation: EvaluatedCandidate,
) -> dg.Output[PromotionResult]:
    """Register the evaluated model and atomically promote the champion alias."""
    try:
        result = register_and_promote_candidate(
            ml_model_evaluation,
            settings=get_settings(),
        )
    except CandidateNotApprovedError as error:
        raise dg.Failure(
            description=str(error),
            metadata={
                "as_of_date": ml_model_evaluation.as_of_date.isoformat(),
                "mlflow_run_id": ml_model_evaluation.run_id,
                "promotion_status": "blocked_by_quality_gates",
            },
            allow_retries=False,
        ) from error
    return dg.Output(
        result,
        metadata={
            "as_of_date": result.as_of_date.isoformat(),
            "trigger": _trigger_source(context),
            "mlflow_run_id": result.run_id,
            "model_version": result.version,
            "alias": result.alias,
            "promotion_status": "promoted",
        },
    )


retraining_job = dg.define_asset_job(
    name="retraining_job",
    selection=dg.AssetSelection.assets(
        feature_dbt_assets,
        ml_training_candidate,
        ml_model_evaluation,
        ml_champion_promotion,
    ),
    description="Materialize features, train, evaluate and promote one monthly candidate.",
)


__all__ = [
    "EVALUATION_ASSET_KEY",
    "PROMOTION_ASSET_KEY",
    "TRAINING_ASSET_KEY",
    "EvaluatedCandidate",
    "PromotionResult",
    "TrainingCandidate",
    "build_candidate",
    "evaluate_and_track_candidate",
    "load_training_frames",
    "ml_champion_promotion",
    "ml_model_evaluation",
    "ml_training_candidate",
    "register_and_promote_candidate",
    "retraining_job",
]
