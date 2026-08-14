"""Tests for MCP-13: list_templates summary mode.

Exercises the ``list_templates`` MCP tool adapter (not the domain function
directly) via ``mcp.call_tool``, with
``app.mcp.tools_read.run_with_session`` monkeypatched to run against the
transactional ``db_session`` fixture instead of opening a genuinely-committing
``session_scope()`` (mirrors the pattern in test_mcp_write_tools.py).

Covers:
* default call (``include_items`` omitted) returns id + name only, no
  ``items`` key populated with data (it is omitted / null).
* ``include_items=True`` returns full items exactly as before.
* a template with zero items behaves correctly in both modes.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

import app.mcp.tools_read as tools_read_module
from app.db import Food, Template, TemplateItem
from app.main import mcp


def _patch_run_with_session(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    def fake_run_with_session(operation, /, *args, **kwargs):
        return operation(db_session, *args, **kwargs)

    monkeypatch.setattr(tools_read_module, "run_with_session", fake_run_with_session)


@pytest.mark.asyncio
async def test_list_templates_default_omits_items(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_template: Callable[..., Template],
    make_template_item: Callable[..., TemplateItem],
    make_food: Callable[..., Food],
) -> None:
    food = make_food(name="Oats")
    template = make_template(name="Breakfast")
    make_template_item(template_id=template.id, food=food)
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("list_templates", {})

    assert result.is_error is False
    payload = result.structured_content["result"]
    match = next(t for t in payload if t["id"] == template.id)
    assert match["name"] == "Breakfast"
    assert match.get("items") is None


@pytest.mark.asyncio
async def test_list_templates_include_items_true_returns_full_items(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_template: Callable[..., Template],
    make_template_item: Callable[..., TemplateItem],
    make_food: Callable[..., Food],
) -> None:
    food = make_food(name="Oats")
    template = make_template(name="Breakfast")
    item = make_template_item(template_id=template.id, food=food, quantity=80)
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("list_templates", {"include_items": True})

    assert result.is_error is False
    payload = result.structured_content["result"]
    match = next(t for t in payload if t["id"] == template.id)
    assert match["items"] is not None
    assert len(match["items"]) == 1
    assert match["items"][0]["id"] == item.id
    assert match["items"][0]["food_id"] == food.id


@pytest.mark.asyncio
async def test_list_templates_empty_template_default_mode(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_template: Callable[..., Template],
) -> None:
    template = make_template(name="No Items")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("list_templates", {})

    assert result.is_error is False
    payload = result.structured_content["result"]
    match = next(t for t in payload if t["id"] == template.id)
    assert match.get("items") is None


@pytest.mark.asyncio
async def test_list_templates_empty_template_include_items_true(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_template: Callable[..., Template],
) -> None:
    template = make_template(name="No Items")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("list_templates", {"include_items": True})

    assert result.is_error is False
    payload = result.structured_content["result"]
    match = next(t for t in payload if t["id"] == template.id)
    assert match["items"] == []
