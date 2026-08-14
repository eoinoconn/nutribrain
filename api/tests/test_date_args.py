"""Tests for MCP-04/05: effective local timezone resolution (app/mcp/date_args.py).

Covers `resolve_effective_local_tz`'s precedence (explicit local_tz argument
wins, otherwise falls back to the account's configured timezone,
`app_settings.local_timezone`, EC-06) and its rejection of invalid IANA
timezone names. The account default is read via a short-lived session
opened inside `resolve_effective_local_tz` itself, so `session_scope` is
patched to reuse the test's transactional `db_session` fixture.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

from app.db import AppSettings
from app.domain.errors import InvalidTimezoneError
from app.mcp import date_args as date_args_module
from app.mcp.date_args import resolve_effective_local_tz


def _patch_session_scope(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(date_args_module, "session_scope", fake_session_scope)


def _set_account_tz(db_session: Session, local_timezone: str) -> None:
    db_session.merge(AppSettings(id=1, local_timezone=local_timezone))
    db_session.flush()


def test_explicit_local_tz_wins_over_account_default() -> None:
    assert resolve_effective_local_tz("Europe/Dublin") == "Europe/Dublin"


def test_omitted_local_tz_falls_back_to_account_default(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_session_scope(monkeypatch, db_session)
    _set_account_tz(db_session, "Europe/Dublin")

    assert resolve_effective_local_tz(None) == "Europe/Dublin"


def test_invalid_explicit_local_tz_raises_invalid_timezone_error() -> None:
    with pytest.raises(InvalidTimezoneError):
        resolve_effective_local_tz("Not/A_Real_Zone")


def test_invalid_account_default_raises_invalid_timezone_error(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_session_scope(monkeypatch, db_session)
    _set_account_tz(db_session, "Not/A_Real_Zone")

    with pytest.raises(InvalidTimezoneError):
        resolve_effective_local_tz(None)
