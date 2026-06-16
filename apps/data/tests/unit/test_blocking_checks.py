"""F2-18 contract: the Silver quality tests must be BLOCKING asset checks.

dagster-dbt 0.29 emits each dbt test as a Dagster asset check and marks it
``blocking=True`` when the dbt test severity is ``error`` (the default). A
blocking check that fails holds back the downstream Gold assets in the same run.
This test pins that contract so a future change (e.g. flipping a test to
``severity: warn``) cannot silently disable the quality gate.

Requires the dbt manifest (``dbt parse``); skipped otherwise, and run in CI after
the parse step.
"""

import pytest

from petrocast_data.assets.dbt import DBT_MANIFEST

pytestmark = pytest.mark.skipif(
    not DBT_MANIFEST.exists(),
    reason="dbt manifest not built (run `dbt parse`); exercised in CI after parse",
)


def _silver_check_specs():
    from petrocast_data.assets.dbt import silver_dbt_assets

    specs = getattr(silver_dbt_assets, "check_specs", None)
    if specs is None:  # pragma: no cover - API fallback across dagster versions
        specs = silver_dbt_assets.check_specs_by_output_name.values()
    return list(specs)


def test_silver_production_quality_checks_are_blocking():
    specs = [s for s in _silver_check_specs() if s.asset_key.path[-1] == "silver_production"]
    assert specs, "expected dbt tests on silver_production to map to asset checks"

    blocking = [s for s in specs if s.blocking]
    non_blocking = [s for s in specs if not s.blocking]

    # The integrity/validity dimensions (not_null, accepted_range, uniqueness,
    # completeness) gate Gold, so they must be blocking.
    assert blocking, "expected blocking quality checks on silver_production"
    # The only non-blocking check is freshness (recency, severity: warn).
    assert all(
        "recency" in s.name for s in non_blocking
    ), f"unexpected non-blocking checks on silver_production: {[s.name for s in non_blocking]}"


def test_recency_check_is_non_blocking():
    recency = [s for s in _silver_check_specs() if "recency" in s.name]
    assert recency, "expected a recency (freshness) check on silver_production"
    assert all(not s.blocking for s in recency), "freshness should warn, not block (ADR-0025)"
