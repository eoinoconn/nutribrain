"""Shared pytest harness for the API test suite (T-012).

Provides three things the persistence-dependent tests rely on:

* a **session-scoped, migrated database** — the Alembic chain is applied once per
  test session against ``DATABASE_URL`` (a Neon branch or the CI/local Postgres
  service);
* a **function-scoped transactional session** — every test runs inside a
  transaction that is rolled back on teardown, so tests never see each other's
  writes and can run in any order;
* a **frozen clock** — timezone and ``local_date`` logic is time-dependent and
  must be exercised deterministically.

Factory helpers from :mod:`tests.factories` are exposed as session-bound
fixtures so setup stays one line.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.db import Food, Meal, MealItem, Target, Template, TemplateItem
from app.settings import settings
from tests import factories

_API_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    """Alembic config pinned to this project regardless of the cwd.

    ``env.py`` supplies the URL from :mod:`app.settings`, so nothing here needs
    to know the connection string.
    """

    cfg = Config(str(_API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Session-scoped engine against a freshly migrated database.

    ``alembic upgrade head`` is idempotent, so this is safe whether the schema
    already exists (CI applies it in a prior step) or the database is empty.
    """

    command.upgrade(_alembic_config(), "head")
    eng = create_engine(settings.database_url)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Function-scoped session wrapped in a transaction rolled back on teardown.

    An outer transaction is opened on a dedicated connection and the session
    joins it in ``create_savepoint`` mode, so even ``session.commit()`` inside a
    test only releases a savepoint. Rolling the outer transaction back on
    teardown discards everything, keeping tests isolated and order-independent.
    """

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


class FrozenClock:
    """Deterministic, advanceable clock for time-dependent domain tests."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware instant")
        self._now = instant

    def now(self, tz: tzinfo = UTC) -> datetime:
        """Return the frozen instant in ``tz`` (UTC by default)."""

        return self._now.astimezone(tz)

    def advance(self, delta: timedelta) -> datetime:
        """Move the clock forward and return the new instant."""

        self._now += delta
        return self._now


# 2026-07-26 12:00 UTC — a fixed, unambiguous instant well away from any
# meal-type window or local-date boundary.
FROZEN_INSTANT = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def frozen_clock() -> FrozenClock:
    """A :class:`FrozenClock` pinned to :data:`FROZEN_INSTANT`."""

    return FrozenClock(FROZEN_INSTANT)


# --- Factory fixtures ------------------------------------------------------
# Each binds the corresponding factory to ``db_session`` so tests can create a
# fully-formed row in one line, e.g. ``make_food(name="Rice")``.


@pytest.fixture
def make_food(db_session: Session) -> Callable[..., Food]:
    return functools.partial(factories.create_food, db_session)


@pytest.fixture
def make_meal(db_session: Session) -> Callable[..., Meal]:
    return functools.partial(factories.create_meal, db_session)


@pytest.fixture
def make_meal_item(db_session: Session) -> Callable[..., MealItem]:
    return functools.partial(factories.create_meal_item, db_session)


@pytest.fixture
def make_template(db_session: Session) -> Callable[..., Template]:
    return functools.partial(factories.create_template, db_session)


@pytest.fixture
def make_template_item(db_session: Session) -> Callable[..., TemplateItem]:
    return functools.partial(factories.create_template_item, db_session)


@pytest.fixture
def make_target(db_session: Session) -> Callable[..., Target]:
    return functools.partial(factories.create_target, db_session)
