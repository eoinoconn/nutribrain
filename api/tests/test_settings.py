"""Tests for EC-06: settings domain (get_settings, update_settings).

Covers:
- no row yet: get_settings lazily creates the singleton with default 'UTC'
- update_settings persists a new timezone and returns it
- update_settings rejects an invalid IANA timezone name
- get_settings after update_settings returns the persisted value
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db import AppSettings
from app.domain.errors import InvalidTimezoneError
from app.domain.settings import get_settings, update_settings


class TestGetSettings:
    def test_no_row_yet_returns_default_utc(self, db_session: Session) -> None:
        result = get_settings(db_session)
        assert result.local_timezone == "UTC"

    def test_lazily_creates_the_singleton_row(self, db_session: Session) -> None:
        get_settings(db_session)
        row = db_session.get(AppSettings, 1)
        assert row is not None
        assert row.local_timezone == "UTC"


class TestUpdateSettings:
    def test_update_persists_new_timezone(self, db_session: Session) -> None:
        result = update_settings(db_session, local_timezone="America/New_York")
        assert result.local_timezone == "America/New_York"

        row = db_session.get(AppSettings, 1)
        assert row is not None
        assert row.local_timezone == "America/New_York"

    def test_get_after_update_returns_persisted_value(self, db_session: Session) -> None:
        update_settings(db_session, local_timezone="Europe/Dublin")
        result = get_settings(db_session)
        assert result.local_timezone == "Europe/Dublin"

    def test_invalid_timezone_raises(self, db_session: Session) -> None:
        with pytest.raises(InvalidTimezoneError):
            update_settings(db_session, local_timezone="Not/A_Timezone")
