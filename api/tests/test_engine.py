"""Engine-configuration tests (T-013).

These lock the G6 Neon connection-pool settings (``docs/decisions.md``) so a
future refactor cannot silently drop ``pool_pre_ping`` or widen the pool, which
would reintroduce stale-connection 500s against Neon's scale-to-zero endpoints.
The settings are asserted against the built engine rather than the source text.
"""

from sqlalchemy.pool import QueuePool

from app.db import engine
from app.db.engine import POOL_PRE_PING, POOL_RECYCLE_SECONDS, POOL_SIZE


def test_g6_pool_constants() -> None:
    assert POOL_PRE_PING is True
    assert POOL_RECYCLE_SECONDS == 300
    assert POOL_SIZE == 2


def test_engine_applies_g6_settings() -> None:
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool._pre_ping is True
    assert pool._recycle == 300
    assert pool.size() == 2
