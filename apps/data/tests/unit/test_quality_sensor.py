"""F2-18: the quality-block sensor turns a failed run into a webhook notification.

These tests invoke the real sensor against a deliberately failing in-process run
(no Postgres, no dbt needed), covering both the no-op-without-webhook path and
the POST-when-configured path.
"""

import urllib.request

import dagster as dg

from petrocast_data.resources import WebhookNotificationResource
from petrocast_data.sensors import collect_failed_checks, quality_block_notification


@dg.op
def _boom_op() -> None:
    raise RuntimeError("boom")


@dg.job
def _failing_job() -> None:
    _boom_op()


def _failure_context(instance: dg.DagsterInstance, webhook: WebhookNotificationResource):
    result = _failing_job.execute_in_process(instance=instance, raise_on_error=False)
    failure_events = [
        record.event_log_entry.dagster_event
        for record in instance.get_records_for_run(result.run_id).records
        if record.event_log_entry.dagster_event is not None
        and record.event_log_entry.dagster_event.event_type == dg.DagsterEventType.RUN_FAILURE
    ]
    assert failure_events, "expected a RUN_FAILURE event for the failing job"
    return dg.build_run_status_sensor_context(
        sensor_name="quality_block_notification",
        dagster_instance=instance,
        dagster_run=result.dagster_run,
        dagster_event=failure_events[0],
        resources={"webhook": webhook},
    ).for_run_failure()


def test_collect_failed_checks_empty_when_no_checks():
    instance = dg.DagsterInstance.ephemeral()
    context = _failure_context(instance, WebhookNotificationResource(webhook_url=None))
    # A non-quality failure (no asset checks) must not crash and yields no checks.
    assert collect_failed_checks(context) == []


def test_sensor_noops_without_webhook():
    instance = dg.DagsterInstance.ephemeral()
    context = _failure_context(instance, WebhookNotificationResource(webhook_url=None))
    # Must run cleanly even with no webhook configured (the deployed default in CI).
    quality_block_notification(context)


def test_sensor_posts_payload_when_webhook_set(monkeypatch):
    posted: list[bytes] = []

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

    def fake_urlopen(request, timeout):
        posted.append(request.data)
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    instance = dg.DagsterInstance.ephemeral()
    context = _failure_context(
        instance, WebhookNotificationResource(webhook_url="https://hooks.example/x")
    )
    quality_block_notification(context)

    assert len(posted) == 1
    # No asset checks failed in this synthetic run -> generic run_failure event.
    assert b"run_failure" in posted[0]
