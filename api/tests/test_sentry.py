"""Tests for optional Sentry integration (T-033)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.sentry import _before_send, init_sentry


class TestBeforeSend:
    """Verify scrubbing removes request bodies and auth headers."""

    def test_strips_request_body(self) -> None:
        event = {"request": {"url": "/api/foods", "data": '{"name": "Rice"}'}}
        result = _before_send(event, {})
        assert result is not None
        assert "data" not in result["request"]

    def test_strips_authorization_header_dict(self) -> None:
        event = {
            "request": {
                "url": "/api/foods",
                "headers": {"Authorization": "******", "Content-Type": "application/json"},
            }
        }
        result = _before_send(event, {})
        assert result is not None
        headers = result["request"]["headers"]
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_strips_authorization_header_list(self) -> None:
        event = {
            "request": {
                "url": "/api/foods",
                "headers": [
                    ("Authorization", "******"),
                    ("Content-Type", "application/json"),
                ],
            }
        }
        result = _before_send(event, {})
        assert result is not None
        headers = result["request"]["headers"]
        assert ("Authorization", "******") not in headers
        assert ("Content-Type", "application/json") in headers

    def test_no_request_key_passes_through(self) -> None:
        event = {"exception": {"values": [{"type": "ValueError"}]}}
        result = _before_send(event, {})
        assert result == event


class TestInitSentry:
    """Verify init_sentry is a no-op when DSN is absent."""

    def test_noop_when_dsn_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app import settings as settings_module

        monkeypatch.setattr(settings_module.settings, "sentry_dsn", None)

        with patch("app.sentry.sentry_sdk.init") as mock_init:
            init_sentry()
            mock_init.assert_not_called()

    def test_calls_init_when_dsn_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app import settings as settings_module

        monkeypatch.setattr(settings_module.settings, "sentry_dsn", "https://key@sentry.io/123")

        with patch("app.sentry.sentry_sdk.init") as mock_init:
            init_sentry()
            mock_init.assert_called_once()
            call_kwargs = mock_init.call_args[1]
            assert call_kwargs["dsn"] == "https://key@sentry.io/123"
            assert call_kwargs["send_default_pii"] is False
            assert call_kwargs["before_send"] is _before_send
