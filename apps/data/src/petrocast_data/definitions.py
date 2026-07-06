import dagster as dg
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource

from petrocast_data.assets.dbt import (
    DBT_PROJECT_DIR,
    dbt_smoke_assets,
    gold_dbt_assets,
    silver_dbt_assets,
)
from petrocast_data.assets.dlt import petrocast_bronze_dlt_assets, petrocast_smoke_dlt_assets
from petrocast_data.assets.features import feature_dbt_assets
from petrocast_data.assets.training import (
    ml_champion_promotion,
    ml_model_evaluation,
    ml_training_candidate,
    retraining_job,
)
from petrocast_data.assets.warehouse import warehouse_schemas_ready
from petrocast_data.resources import WebhookNotificationResource
from petrocast_data.schedules import retraining_schedule
from petrocast_data.sensors import quality_block_notification

defs = dg.Definitions(
    assets=[
        warehouse_schemas_ready,
        petrocast_smoke_dlt_assets,
        petrocast_bronze_dlt_assets,
        dbt_smoke_assets,
        silver_dbt_assets,
        gold_dbt_assets,
        feature_dbt_assets,
        ml_training_candidate,
        ml_model_evaluation,
        ml_champion_promotion,
    ],
    jobs=[retraining_job],
    schedules=[retraining_schedule],
    sensors=[quality_block_notification],
    resources={
        "dbt": DbtCliResource(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR),
        "dlt": DagsterDltResource(),
        # Lazy EnvVar: unset in CI/local (the sensor no-ops), the real URL is
        # injected via PETROCAST_NOTIFICATION_WEBHOOK_URL in deployed environments.
        "webhook": WebhookNotificationResource(
            webhook_url=dg.EnvVar("PETROCAST_NOTIFICATION_WEBHOOK_URL"),
        ),
    },
)
