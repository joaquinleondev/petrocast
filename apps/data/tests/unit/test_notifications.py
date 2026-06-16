import urllib.error
import urllib.request

from petrocast_data.resources import WebhookNotificationResource


class _FakeResponse:
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


def test_notify_noops_when_url_unset():
    assert WebhookNotificationResource(webhook_url=None).notify({"a": 1}) is False
    assert WebhookNotificationResource(webhook_url="").notify({"a": 1}) is False
    assert WebhookNotificationResource(webhook_url="   ").notify({"a": 1}) is False


def test_notify_noops_for_non_http_scheme():
    assert WebhookNotificationResource(webhook_url="ftp://host/x").notify({"a": 1}) is False
    assert WebhookNotificationResource(webhook_url="file:///etc/passwd").notify({"a": 1}) is False


def test_notify_posts_json_when_url_set(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    sent = WebhookNotificationResource(
        webhook_url="https://hooks.example/abc", timeout_seconds=7
    ).notify({"event": "quality_block", "failed_checks": []})

    assert sent is True
    assert captured["url"] == "https://hooks.example/abc"
    assert captured["method"] == "POST"
    assert b"quality_block" in captured["body"]  # type: ignore[operator]
    assert captured["timeout"] == 7


def test_notify_swallows_transport_errors(monkeypatch):
    def boom(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    # A notification failure must never propagate and mask the quality failure.
    assert WebhookNotificationResource(webhook_url="https://hooks.example/x").notify({}) is False
