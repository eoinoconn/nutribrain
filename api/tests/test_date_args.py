"""Tests for MCP-04/05: effective local timezone resolution (app/mcp/date_args.py).

Covers `resolve_effective_local_tz`'s precedence (explicit local_tz argument
wins, otherwise falls back to the server's configured default `settings.tz`)
and its rejection of invalid IANA timezone names.
"""

from __future__ import annotations

import pytest

from app import settings as settings_module
from app.domain.errors import InvalidTimezoneError
from app.mcp.date_args import resolve_effective_local_tz


def test_explicit_local_tz_wins_over_config_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.settings, "tz", "UTC")

    assert resolve_effective_local_tz("Europe/Dublin") == "Europe/Dublin"


def test_omitted_local_tz_falls_back_to_config_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.settings, "tz", "Europe/Dublin")

    assert resolve_effective_local_tz(None) == "Europe/Dublin"


def test_invalid_explicit_local_tz_raises_invalid_timezone_error() -> None:
    with pytest.raises(InvalidTimezoneError):
        resolve_effective_local_tz("Not/A_Real_Zone")


def test_invalid_config_default_raises_invalid_timezone_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings_module.settings, "tz", "Not/A_Real_Zone")

    with pytest.raises(InvalidTimezoneError):
        resolve_effective_local_tz(None)
