from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.domain import parse_local_date
from app.main import mcp


@pytest.mark.asyncio
async def test_mcp_lists_full_tool_surface_with_descriptions_and_schemas() -> None:
    tools = await mcp.list_tools()

    tool_names = {tool.name for tool in tools}
    assert tool_names == {
        "log_meal",
        "log_template",
        "add_food",
        "update_food",
        "delete_food",
        "merge_food",
        "create_template",
        "update_template",
        "delete_template",
        "set_target",
        "set_favorite_food",
        "delete_meal",
        "delete_meal_item",
        "update_meal",
        "update_meal_item",
        "copy_meal",
        "get_day",
        "get_range",
        "find_food",
        "find_foods",
        "find_meal",
        "list_templates",
        "get_target",
        "sync_intervals",
    }

    for tool in tools:
        assert tool.description is not None
        assert tool.description.strip() != ""
        assert tool.parameters["type"] == "object"
        assert isinstance(tool.parameters.get("properties"), dict)


@pytest.mark.asyncio
async def test_add_food_numeric_fields_advertise_plain_number_schema() -> None:
    """Decimal input fields must advertise a plain `number` type, not pydantic's
    default `anyOf: [{type: number}, {type: string, pattern: ...}]` union for
    Decimal — that union costs ~60-70 tokens per field on every tool listing
    versus ~10 for a plain number (see NumericDecimal in tools_write.py)."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    properties = tools["add_food"].parameters["properties"]

    required_numeric_fields = ["serving_size", "calories", "protein_g", "carbs_g", "fat_g"]
    for field_name in required_numeric_fields:
        schema = properties[field_name]
        assert schema == {"type": "number"}, f"{field_name} schema: {schema}"

    optional_numeric_fields = ["fiber_g", "sat_fat_g", "sodium_mg", "density_g_per_ml"]
    for field_name in optional_numeric_fields:
        schema = properties[field_name]
        assert "anyOf" in schema, f"{field_name} schema: {schema}"
        # Optional fields legitimately anyOf over [number, null] (the None
        # union), but must never contain a string branch (the Decimal union
        # this change eliminates).
        for branch in schema["anyOf"]:
            assert branch["type"] != "string", f"{field_name} schema: {schema}"


@pytest.mark.asyncio
async def test_get_day_accepts_today_token_via_shared_parser(db_session: Session) -> None:
    _ = db_session
    expected_today = parse_local_date("today", local_tz="UTC", now=datetime.now(UTC))

    result = await mcp.call_tool("get_day", {"day": "today", "local_tz": "UTC"})

    assert result.is_error is False
    payload = result.structured_content
    assert payload is not None
    assert payload["result"]["date"] == expected_today.isoformat()
