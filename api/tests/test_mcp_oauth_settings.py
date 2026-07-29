"""Tests for the fail-loudly gating logic around the MCP OAuth settings (F-103).

See `docs/features/mcp_oauth.md` F-103 and `app.main._validate_startup_settings`.
The four settings (`google_oauth_client_id`, `google_oauth_client_secret`,
`mcp_allowed_email`, `mcp_public_base_url`) are optional so most local dev/test
environments (with none of them set) keep working, but a half-configured set
must fail startup loudly rather than silently leaving `/mcp` OAuth half-wired.
"""

from __future__ import annotations

import pytest

from app import settings as settings_module
from app.main import _validate_startup_settings

_OAUTH_FIELDS = (
    "google_oauth_client_id",
    "google_oauth_client_secret",
    "mcp_allowed_email",
    "mcp_public_base_url",
)


def _clear_oauth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for field in _OAUTH_FIELDS:
        monkeypatch.setattr(settings_module.settings, field, None)


def test_all_oauth_settings_unset_does_not_fail_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_oauth_settings(monkeypatch)

    _validate_startup_settings()  # must not raise


def test_all_oauth_settings_set_does_not_fail_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_oauth_settings(monkeypatch)
    monkeypatch.setattr(settings_module.settings, "google_oauth_client_id", "client-id")
    monkeypatch.setattr(settings_module.settings, "google_oauth_client_secret", "client-secret")
    monkeypatch.setattr(settings_module.settings, "mcp_allowed_email", "me@example.com")
    monkeypatch.setattr(settings_module.settings, "mcp_public_base_url", "http://localhost:8000")

    _validate_startup_settings()  # must not raise


@pytest.mark.parametrize("missing_field", _OAUTH_FIELDS)
def test_partially_configured_oauth_settings_fail_startup(
    monkeypatch: pytest.MonkeyPatch, missing_field: str
) -> None:
    _clear_oauth_settings(monkeypatch)
    values = {
        "google_oauth_client_id": "client-id",
        "google_oauth_client_secret": "client-secret",
        "mcp_allowed_email": "me@example.com",
        "mcp_public_base_url": "http://localhost:8000",
    }
    del values[missing_field]
    for field, value in values.items():
        monkeypatch.setattr(settings_module.settings, field, value)

    with pytest.raises(RuntimeError, match="partially configured"):
        _validate_startup_settings()


def test_blank_string_counts_as_missing_for_partial_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_oauth_settings(monkeypatch)
    monkeypatch.setattr(settings_module.settings, "google_oauth_client_id", "client-id")
    monkeypatch.setattr(settings_module.settings, "google_oauth_client_secret", "client-secret")
    monkeypatch.setattr(settings_module.settings, "mcp_allowed_email", "me@example.com")
    monkeypatch.setattr(settings_module.settings, "mcp_public_base_url", "   ")

    with pytest.raises(RuntimeError, match="partially configured"):
        _validate_startup_settings()
