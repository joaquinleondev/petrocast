"""Dagster sensors for the data stack.

F2-18 (ADR-0025) — operational consequence of a quality block. The dbt quality
tests on ``silver_production`` are emitted by dagster-dbt as **blocking** asset
checks (any test at the dbt-default ``severity: error``). When one fails, the
Silver run fails and the downstream Gold assets are skipped in the same run, so
Gold is never overwritten with bad data. This sensor turns that failure into a
notification so the Data Owner can act, instead of the block being silent.
"""

from typing import Any

from dagster import (
    DagsterEventType,
    DefaultSensorStatus,
    RunFailureSensorContext,
    run_failure_sensor,
)

from petrocast_data.resources import WebhookNotificationResource


def collect_failed_checks(context: RunFailureSensorContext) -> list[dict[str, str]]:
    """Return the failed asset checks recorded in the failed run (empty if none).

    A run can fail for reasons other than a quality block (e.g. an ingestion
    error); in that case this returns ``[]`` and the notification is a generic
    run failure rather than a quality block.
    """
    records = context.instance.get_records_for_run(
        context.dagster_run.run_id,
        of_type=DagsterEventType.ASSET_CHECK_EVALUATION,
    ).records
    failed: list[dict[str, str]] = []
    for record in records:
        dagster_event = record.event_log_entry.dagster_event
        if dagster_event is None:
            continue
        evaluation = dagster_event.event_specific_data
        if getattr(evaluation, "passed", True):
            continue
        asset_key = getattr(evaluation, "asset_key", None)
        failed.append(
            {
                "asset": asset_key.to_user_string() if asset_key is not None else "unknown",
                "check": str(getattr(evaluation, "check_name", "unknown")),
                "severity": str(getattr(evaluation, "severity", "")),
            }
        )
    return failed


@run_failure_sensor(
    name="quality_block_notification",
    description=(
        "Notifies via webhook when a Dagster run fails. When the failure is a "
        "blocking data-quality check (F2-18), the payload lists the failed checks "
        "so the Data Owner can act on the held-back Gold promotion (ADR-0025)."
    ),
    default_status=DefaultSensorStatus.RUNNING,
)
def quality_block_notification(
    context: RunFailureSensorContext,
    webhook: WebhookNotificationResource,
) -> None:
    failed_checks = collect_failed_checks(context)
    payload: dict[str, Any] = {
        "event": "quality_block" if failed_checks else "run_failure",
        "run_id": context.dagster_run.run_id,
        "job": context.dagster_run.job_name,
        "message": str(context.failure_event.message),
        "failed_checks": failed_checks,
    }
    sent = webhook.notify(payload)
    context.log.info(
        "quality_block_notification fired: failed_checks=%d webhook_sent=%s",
        len(failed_checks),
        sent,
    )
