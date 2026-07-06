"""Schedules for recurrent Petrocast data and ML jobs."""

from datetime import UTC, datetime

import dagster as dg

from petrocast_data.assets.training import retraining_job

RETRAINING_CRON = "0 6 5 * *"
RETRAINING_TIMEZONE = "UTC"


def partition_key_for_tick(scheduled_at: datetime) -> str:
    """Return the first day of the tick month as the training cutoff."""
    normalized = scheduled_at.astimezone(UTC)
    return normalized.date().replace(day=1).isoformat()


def retraining_run_request(context: dg.ScheduleEvaluationContext) -> dg.RunRequest:
    """Create one idempotent monthly request for the retraining partition."""
    scheduled_at = context.scheduled_execution_time
    if scheduled_at is None:
        raise ValueError("retraining schedule requires a scheduled execution time")
    partition_key = partition_key_for_tick(scheduled_at)
    return dg.RunRequest(
        run_key=f"retraining:{partition_key}",
        partition_key=partition_key,
        tags={
            "as_of_date": partition_key,
            "petrocast/trigger": "schedule",
        },
    )


retraining_schedule = dg.ScheduleDefinition(
    name="monthly_retraining_schedule",
    job=retraining_job,
    cron_schedule=RETRAINING_CRON,
    execution_timezone=RETRAINING_TIMEZONE,
    execution_fn=retraining_run_request,
    description="Retrain and promote the monthly candidate on day 5 at 06:00 UTC.",
)


__all__ = [
    "RETRAINING_CRON",
    "RETRAINING_TIMEZONE",
    "partition_key_for_tick",
    "retraining_run_request",
    "retraining_schedule",
]
