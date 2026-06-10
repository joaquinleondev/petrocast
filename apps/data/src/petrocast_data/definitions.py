from pathlib import Path

import dagster as dg
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource

from petrocast_data.assets.dbt import DBT_PROJECT_DIR, dbt_smoke_assets
from petrocast_data.assets.dlt import petrocast_smoke_dlt_assets
from petrocast_data.assets.warehouse import warehouse_schemas_ready

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt"

defs = dg.Definitions(
    assets=[
        warehouse_schemas_ready,
        petrocast_smoke_dlt_assets,
        dbt_smoke_assets,
    ],
    resources={
        "dbt": DbtCliResource(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR),
        "dlt": DagsterDltResource(),
    },
)
