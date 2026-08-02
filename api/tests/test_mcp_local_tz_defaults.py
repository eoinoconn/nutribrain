"""Tests for MCP-04: effective local timezone defaulting on the six MCP tools
that previously required `local_tz` (log_meal, log_template, get_day,
get_range, set_target, get_target).

Exercised end-to-end via ``mcp.call_tool`` with the relevant module's
``run_with_session`` monkeypatched to run against the transactional
``db_session`` fixture, mirroring the pattern in test_mcp_write_tools.py and
test_mcp_sync_tool.py.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

import app.mcp.tools_read as tools_read_module
import app.mcp.tools_write as tools_write_module
from app import settings as settings_module
from app.db import Food, QuantityUnit, Template, TemplateItem
from app.main import mcp


def _patch_run_with_session(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    def fake_run_with_session(operation, /, *args, **kwargs):
        return operation(db_session, *args, **kwargs)

    monkeypatch.setattr(tools_read_module, "run_with_session", fake_run_with_session)
    monkeypatch.setattr(tools_write_module, "run_with_session", fake_run_with_session)


@pytest.fixture(autouse=True)
def _default_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.settings, "tz", "Europe/Dublin")


@pytest.mark.asyncio
async def test_get_day_tool_omits_local_tz_and_day(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("get_day", {})

    assert result.is_error is False


@pytest.mark.asyncio
async def test_get_range_tool_omits_local_tz_and_dates(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("get_range", {})

    assert result.is_error is False
    payload = result.structured_content["result"]
    # Defaulting both from_date and to_date to today collapses to a
    # single-day range.
    assert len(payload["periods"]) == 1


@pytest.mark.asyncio
async def test_get_target_tool_omits_local_tz_and_day(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("get_target", {})

    assert result.is_error is False


@pytest.mark.asyncio
async def test_set_target_tool_omits_local_tz(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool(
        "set_target",
        {
            "base_calories": 2200,
            "protein_g": 150,
            "carbs_g": 220,
            "fat_g": 70,
            "effective_from": "today",
        },
    )

    assert result.is_error is False


@pytest.mark.asyncio
async def test_log_meal_tool_omits_local_tz(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool(
        "log_meal",
        {
            "items": [
                {
                    "name": "Ad-hoc",
                    "quantity": "100",
                    "quantity_unit": "g",
                    "calories": "100",
                    "protein_g": "1",
                    "carbs_g": "1",
                    "fat_g": "1",
                }
            ],
        },
    )

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["local_tz"] == "Europe/Dublin"


@pytest.mark.asyncio
async def test_log_template_tool_omits_local_tz(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    make_food: Callable[..., Food],
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    food = make_food()
    template = Template(name="Test Template")
    db_session.add(template)
    db_session.flush()
    db_session.add(
        TemplateItem(
            template_id=template.id,
            name="Item",
            quantity=100,
            quantity_unit=QuantityUnit.g,
            food_id=food.id,
        )
    )
    db_session.flush()

    result = await mcp.call_tool("log_template", {"template_id": template.id})

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["local_tz"] == "Europe/Dublin"


@pytest.mark.asyncio
async def test_invalid_local_tz_returns_domain_error_envelope(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool("get_day", {"local_tz": "Not/A_Real_Zone"})

    payload = result.structured_content["result"]
    assert payload["error"] == "invalid_timezone"


@pytest.mark.asyncio
async def test_invalid_config_default_local_tz_returns_domain_error_envelope(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)
    monkeypatch.setattr(settings_module.settings, "tz", "Not/A_Real_Zone")

    result = await mcp.call_tool("get_day", {})

    payload = result.structured_content["result"]
    assert payload["error"] == "invalid_timezone"


@pytest.mark.asyncio
async def test_explicit_local_tz_still_overrides_config_default(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)

    result = await mcp.call_tool(
        "log_meal",
        {
            "items": [
                {
                    "name": "Ad-hoc",
                    "quantity": "100",
                    "quantity_unit": "g",
                    "calories": "100",
                    "protein_g": "1",
                    "carbs_g": "1",
                    "fat_g": "1",
                }
            ],
            "local_tz": "America/New_York",
        },
    )

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["local_tz"] == "America/New_York"
