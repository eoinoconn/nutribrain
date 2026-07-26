"""Shared SQLAlchemy engine and session factory (T-013).

The db layer owns connection lifecycle so domain code can accept an injected
session without managing engines itself (see ``docs/style.md`` §1.1).

The engine is configured for Neon's free tier, which scales compute to zero
after a few minutes idle and closes every open connection when it does. The G6
pool settings (``docs/decisions.md``) keep SQLAlchemy from handing out a
connection that Neon has already killed:

* ``pool_pre_ping`` validates a connection on checkout, turning a suspended
  endpoint into a transparent reconnect instead of a 500;
* ``pool_recycle`` retires connections before Neon does;
* ``pool_size`` stays tiny because there is exactly one user.

There is deliberately no keep-alive ping; cold starts of a few hundred
milliseconds are accepted rather than holding compute awake around the clock.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

# G6 — Neon connection-pool settings (docs/decisions.md).
POOL_PRE_PING = True
POOL_RECYCLE_SECONDS = 300
POOL_SIZE = 2


def _create_engine() -> Engine:
    """Build the process-wide engine from ``DATABASE_URL``.

    ``DATABASE_URL`` should be Neon's **pooled** (``-pooler``) connection string
    so PgBouncer absorbs connection churn from scale-to-zero.
    """

    return create_engine(
        settings.database_url,
        pool_pre_ping=POOL_PRE_PING,
        pool_recycle=POOL_RECYCLE_SECONDS,
        pool_size=POOL_SIZE,
    )


engine: Engine = _create_engine()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield a session bound to the shared engine, closed on teardown.

    Suitable as a FastAPI dependency and as a context boundary for the cron
    worker. The domain layer receives the session but never owns its lifecycle.
    """

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
