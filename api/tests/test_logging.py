"""Tests for structured logging (T-032).

Asserts the redaction processor strips Authorization header values from log events.
"""

from __future__ import annotations

from app.logging import _redact_authorization


class TestRedactAuthorization:
    def test_redacts_authorization_key(self) -> None:
        event: dict[str, object] = {
            "event": "request_received",
            "authorization": "******",
        }
        result = _redact_authorization(None, "info", event)
        assert result["authorization"] == "[REDACTED]"

    def test_redacts_auth_header_key(self) -> None:
        event: dict[str, object] = {
            "event": "request_received",
            "auth_header": "******",
        }
        result = _redact_authorization(None, "info", event)
        assert result["auth_header"] == "[REDACTED]"

    def test_redacts_nested_headers_dict(self) -> None:
        event: dict[str, object] = {
            "event": "request_received",
            "headers": {"Authorization": "******", "Content-Type": "application/json"},
        }
        result = _redact_authorization(None, "info", event)
        assert result["headers"]["Authorization"] == "[REDACTED]"  # type: ignore[index]
        assert result["headers"]["Content-Type"] == "application/json"  # type: ignore[index]

    def test_leaves_non_auth_keys_untouched(self) -> None:
        event: dict[str, object] = {
            "event": "meal_logged",
            "meal_id": 42,
            "method": "POST",
        }
        result = _redact_authorization(None, "info", event)
        assert result["meal_id"] == 42
        assert result["method"] == "POST"

    def test_handles_empty_event(self) -> None:
        event: dict[str, object] = {"event": "something"}
        result = _redact_authorization(None, "info", event)
        assert result == {"event": "something"}

    def test_case_insensitive_key_matching(self) -> None:
        event: dict[str, object] = {
            "event": "test",
            "Authorization": "******",
        }
        result = _redact_authorization(None, "info", event)
        assert result["Authorization"] == "[REDACTED]"
