"""Tests for MCP write tool adapters in app/mcp/tools_write.py.

These exercise the tool functions (not the domain functions directly) via
``mcp.call_tool``, with ``app.mcp.tools_write.run_with_session`` monkeypatched
to run against the transactional ``db_session`` fixture instead of opening a
genuinely-committing ``session_scope()`` (mirrors the pattern in
test_mcp_sync_tool.py).

The tool layer applies its own default handling on top of the domain layer's
sentinel semantics (see ``_NOTES_UNSET`` / ``_FOOD_ID_UNSET`` in
tools_write.py), so these must go through the tool, not call the domain
function directly — a domain-layer test alone would not catch a tool that
forwards a plain `None` default and silently clears a field the caller never
mentioned.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

import app.mcp.tools_write as tools_write_module
from app.db import Meal
from app.main import mcp


def _patch_run_with_session(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    def fake_run_with_session(operation, /, *args, **kwargs):
        return operation(db_session, *args, **kwargs)

    monkeypatch.setattr(tools_write_module, "run_with_session", fake_run_with_session)


@pytest.mark.asyncio
async def test_update_meal_tool_omitting_notes_leaves_existing_notes_untouched(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_meal: Callable[..., Meal],
) -> None:
    meal = make_meal(notes="keep me")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("update_meal", {"meal_id": meal.id, "meal_type": "dinner"})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["meal_type"] == "dinner"
    assert payload["notes"] == "keep me"


@pytest.mark.asyncio
async def test_update_meal_tool_explicit_null_notes_clears(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_meal: Callable[..., Meal],
) -> None:
    meal = make_meal(notes="clear me")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("update_meal", {"meal_id": meal.id, "notes": None})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["notes"] is None
