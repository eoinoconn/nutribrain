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
from app.db import Food, Meal
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


@pytest.mark.asyncio
async def test_delete_food_tool_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_food: Callable[..., Food],
) -> None:
    food = make_food(name="Old Food")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("delete_food", {"food_id": food.id})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["id"] == food.id
    db_session.refresh(food)
    assert food.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_food_tool_not_found(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("delete_food", {"food_id": 999999})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["error"] == "food_not_found"


@pytest.mark.asyncio
async def test_merge_food_tool_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_food: Callable[..., Food],
    make_meal: Callable[..., Meal],
    make_meal_item,
) -> None:
    from_food = make_food(name="Duplicate Yogurt")
    into_food = make_food(name="GetPRO")
    meal = make_meal()
    item = make_meal_item(food=from_food, meal_id=meal.id)
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("merge_food", {"from_id": from_food.id, "into_id": into_food.id})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["reassigned_count"] == 1
    assert payload["into_food"]["id"] == into_food.id
    assert payload["from_food"]["id"] == from_food.id
    db_session.refresh(item)
    assert item.food_id == into_food.id


@pytest.mark.asyncio
async def test_merge_food_tool_not_found(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_food: Callable[..., Food],
) -> None:
    from_food = make_food(name="Duplicate Yogurt")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("merge_food", {"from_id": from_food.id, "into_id": 999999})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["error"] == "food_not_found"


@pytest.mark.asyncio
async def test_merge_food_tool_self_merge_error(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_food: Callable[..., Food],
) -> None:
    food = make_food(name="GetPRO")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("merge_food", {"from_id": food.id, "into_id": food.id})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["error"] == "food_merge_same_food"


@pytest.mark.asyncio
async def test_add_food_tool_accepts_numeric_strings_for_decimal_fields(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    """The advertised schema for Decimal fields is now a plain `number`
    (see NumericDecimal in tools_write.py), but the underlying Decimal
    validator is untouched, so numeric strings — the precision-preserving
    form some callers use to avoid float round-tripping — must still be
    accepted at runtime even though the schema no longer advertises them."""
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool(
        "add_food",
        {
            "name": "String Decimal Oats",
            "serving_size": "100",
            "serving_unit": "g",
            "calories": "389.5",
            "protein_g": "16.7",
            "carbs_g": "66.3",
            "fat_g": "6.9",
        },
    )

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["calories"] == "389.5"
    assert payload["protein_g"] == "16.7"


@pytest.mark.asyncio
async def test_log_meal_tool_food_linked_item_name_omitted(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_food: Callable[..., Food],
) -> None:
    """MCP-09: items[].name is optional on food-linked items."""
    food = make_food(name="Oats")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool(
        "log_meal",
        {
            "items": [
                {
                    "quantity": 50,
                    "quantity_unit": "g",
                    "food_id": food.id,
                    # name omitted entirely
                }
            ]
        },
    )

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["items"][0]["food_id"] == food.id
    assert payload["items"][0]["name"] == "Oats"


@pytest.mark.asyncio
async def test_log_meal_tool_adhoc_item_name_omitted_raises(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    """MCP-09: an ad-hoc item (no food_id) with no name is a clear domain error."""
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool(
        "log_meal",
        {
            "items": [
                {
                    "quantity": 100,
                    "quantity_unit": "g",
                    "calories": 150,
                    "protein_g": 5,
                    "carbs_g": 25,
                    "fat_g": 4,
                    # No food_id, no name
                }
            ]
        },
    )

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["error"] == "adhoc_item_name_required"


@pytest.mark.asyncio
async def test_create_template_tool_food_linked_item_name_omitted(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_food: Callable[..., Food],
) -> None:
    """MCP-09: items[].name is optional on food-linked template items."""
    food = make_food(name="Oats")
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool(
        "create_template",
        {
            "name": "Morning Oats",
            "items": [
                {
                    "quantity": 80,
                    "quantity_unit": "g",
                    "food_id": food.id,
                    # name omitted entirely
                }
            ],
        },
    )

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["items"][0]["food_id"] == food.id
    assert payload["items"][0]["name"] == "Oats"
