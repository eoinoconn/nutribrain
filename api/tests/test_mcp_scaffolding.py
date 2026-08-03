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
        "create_template",
        "update_template",
        "delete_template",
        "set_target",
        "set_favorite_food",
        "delete_meal",
        "delete_meal_item",
        "get_day",
        "get_range",
        "find_food",
        "find_foods",
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
async def test_get_day_accepts_today_token_via_shared_parser(db_session: Session) -> None:
    _ = db_session
    expected_today = parse_local_date("today", local_tz="UTC", now=datetime.now(UTC))

    result = await mcp.call_tool("get_day", {"day": "today", "local_tz": "UTC"})

    assert result.is_error is False
    payload = result.structured_content
    assert payload is not None
    assert payload["result"]["date"] == expected_today.isoformat()
