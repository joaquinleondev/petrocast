"""Dagster resources for the data stack."""

import json
import urllib.error
import urllib.request
from typing import Any

from dagster import ConfigurableResource, get_dagster_logger


# ConfigurableResource is generic over the value it provides; a self-providing
# resource subclasses it bare (dagster's documented idiom), which trips strict
# mypy's disallow_any_generics — the only reason for the ignore here.
class WebhookNotificationResource(ConfigurableResource):  # type: ignore[type-arg]
    """Posts a JSON payload to an operator-configured webhook (Slack/email/etc.).

    Used by the quality-block sensor (F2-18, ADR-0025) to notify when a blocking
    data-quality check fails and Gold is held back. It **no-ops when no URL is
    configured**, so the exact same wiring runs in CI and local environments
    (where the webhook is unset) without erroring, and a notification failure is
    swallowed so it never masks the original quality failure.
    """

    webhook_url: str | None = None
    timeout_seconds: int = 10

    def notify(self, payload: dict[str, Any]) -> bool:
        """POST ``payload`` as JSON. Return True if sent, False if no-op/failed."""
        url = (self.webhook_url or "").strip()
        if not url:
            return False
        if not url.startswith(("http://", "https://")):
            get_dagster_logger().warning(
                "notification webhook url is set but not http(s); skipping notification"
            )
            return False
        data = json.dumps(payload).encode("utf-8")
        # Scheme is validated to http(s) above, so the urllib audit (S310) is satisfied.
        request = urllib.request.Request(  # noqa: S310
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds):  # noqa: S310
                return True
        except (urllib.error.URLError, TimeoutError) as exc:
            get_dagster_logger().warning("failed to POST quality notification: %s", exc)
            return False
