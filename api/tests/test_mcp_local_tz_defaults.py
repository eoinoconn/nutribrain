"""Tests for MCP-04: effective local timezone defaulting on the six MCP tools
that previously required `local_tz` (log_meal, log_template, get_day,
get_range, set_target, get_target).

Exercised end-to-end via ``mcp.call_tool`` with the relevant module's
``run_with_session`` monkeypatched to run against the transactional
``db_session`` fixture, mirroring the pattern in test_mcp_write_tools.py and
test_mcp_sync_tool.py. The account's effective-default timezone
(``app_settings.local_timezone``, EC-06) is resolved by
``app.mcp.date_args.resolve_effective_local_tz`` via its own short-lived
session, so that module's ``session_scope`` is patched too, to reuse the same
transactional ``db_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

import app.mcp.date_args as date_args_module
import app.mcp.tools_read as tools_read_module
import app.mcp.tools_write as tools_write_module
from app.db import AppSettings, Food, QuantityUnit, Template, TemplateItem
from app.main import mcp


def _patch_run_with_session(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    def fake_run_with_session(operation, /, *args, **kwargs):
        return operation(db_session, *args, **kwargs)

    monkeypatch.setattr(tools_read_module, "run_with_session", fake_run_with_session)
    monkeypatch.setattr(tools_write_module, "run_with_session", fake_run_with_session)

    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(date_args_module, "session_scope", fake_session_scope)


@pytest.fixture(autouse=True)
def _default_tz(db_session: Session) -> None:
    db_session.merge(AppSettings(id=1, local_timezone="Europe/Dublin"))
    db_session.flush()


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
async def test_invalid_account_default_local_tz_returns_domain_error_envelope(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    _patch_run_with_session(monkeypatch, db_session)
    db_session.merge(AppSettings(id=1, local_timezone="Not/A_Real_Zone"))
    db_session.flush()

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
