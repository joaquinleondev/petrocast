"""Offline training CLI (F3-13): train the baseline from CSV extracts.

Reads a contract-A feature extract and the raw production series (same layout
as apps/ml/tests/fixtures), builds the supervised dataset, trains the fixed
LightGBM baseline against a single-origin cutoff and writes the artifact.
Database-backed extraction arrives with the Dagster materialization (F3-12)
and the serving runtime (F3-18); this entrypoint keeps training runnable and
reproducible offline.
"""

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from petrocast_ml.training.artifact import save_training_artifact
from petrocast_ml.training.contracts import TrainingRequest
from petrocast_ml.training.dataset import TARGET_COLUMN, build_training_dataset
from petrocast_ml.training.pipeline import train


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m petrocast_ml.training",
        description="Train the baseline production forecasting model from CSVs.",
    )
    parser.add_argument("--features-csv", type=Path, required=True)
    parser.add_argument("--production-csv", type=Path, required=True)
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        required=True,
        help="single-origin evaluation cutoff (test split), e.g. 2026-01-01",
    )
    parser.add_argument(
        "--horizons",
        type=lambda raw: tuple(int(part) for part in raw.split(",")),
        default=(1, 2, 3),
        help="comma-separated horizons in months, e.g. 1,2,3",
    )
    parser.add_argument("--features-version", default="local-dev")
    parser.add_argument("--validation-cutoffs", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    well_features = pd.read_csv(
        args.features_csv,
        dtype={"well_id": str},
        parse_dates=["as_of_date", "last_observed_month"],
    )
    production = pd.read_csv(
        args.production_csv,
        dtype={"well_id": str},
        parse_dates=["production_month"],
    )

    dataset = build_training_dataset(well_features, production, horizons=args.horizons)
    request = TrainingRequest(
        as_of_date=args.as_of,
        features_version=args.features_version,
        horizon=max(args.horizons),
        validation_cutoffs=args.validation_cutoffs,
    )
    result = train(dataset, dataset[TARGET_COLUMN], request=request)
    artifact_dir = save_training_artifact(
        result, request=request, dataset=dataset, output_dir=args.output_dir
    )
    print(json.dumps({"artifact_dir": str(artifact_dir), "metrics": dict(result.metrics)}))


if __name__ == "__main__":
    main()
