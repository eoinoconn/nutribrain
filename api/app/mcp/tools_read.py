"""MCP read tools."""

from __future__ import annotations

from datetime import date
from typing import Literal, cast

from fastmcp import FastMCP

from app.api.foods import FoodSearchResponse
from app.domain import get_day, get_effective_target, get_range, list_templates, search_foods
from app.domain.dto import DayResponse, EffectiveTarget, RangeResponse, TemplateResponse
from app.domain.errors import DomainError
from app.domain.foods import FoodSearchResult
from app.mcp._tool_common import capture_domain_error, run_with_session
from app.mcp.date_args import resolve_date_arg, resolve_date_range_args
from app.mcp.serializers import (
    DayModel,
    EffectiveTargetModel,
    RangeModel,
    TemplateModel,
    ToolErrorResponse,
    serialize_day,
    serialize_effective_target,
    serialize_food_search_result,
    serialize_range,
    serialize_template,
)

type GetDayResult = DayModel | ToolErrorResponse
type GetRangeResult = RangeModel | ToolErrorResponse
type FindFoodResult = list[FoodSearchResponse] | ToolErrorResponse
type ListTemplatesResult = list[TemplateModel] | ToolErrorResponse
type GetTargetResult = EffectiveTargetModel | ToolErrorResponse | None


def register_read_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_day",
        description="Get one day summary by date token (today/yesterday) or ISO date.",
    )
    def get_day_tool(day: str, local_tz: str) -> GetDayResult:
        resolved = resolve_date_arg(day, local_tz=local_tz)
        try:
            result = cast(DayResponse, run_with_session(get_day, day=resolved))
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_day(result)

    @mcp.tool(
        name="get_range",
        description=(
            "Get day or week range totals using date tokens or ISO dates. "
            "Granularity is one of day/week."
        ),
    )
    def get_range_tool(
        from_date: str,
        to_date: str,
        local_tz: str,
        granularity: Literal["day", "week"] = "day",
    ) -> GetRangeResult:
        start, end = resolve_date_range_args(
            from_value=from_date,
            to_value=to_date,
            local_tz=local_tz,
        )
        try:
            result = cast(
                RangeResponse,
                run_with_session(
                    get_range,
                    from_date=start,
                    to_date=end,
                    granularity=granularity,
                ),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_range(result)

    @mcp.tool(
        name="find_food",
        description=(
            "Search foods with favorite marker and usage metadata for resolution decisions. "
            "Use this before guessing between multiple similar foods."
        ),
    )
    def find_food_tool(query: str, limit: int = 20) -> FindFoodResult:
        try:
            result = cast(
                list[FoodSearchResult],
                run_with_session(search_foods, query=query, limit=limit),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return [serialize_food_search_result(item) for item in result]

    @mcp.tool(name="list_templates", description="List all non-deleted templates with full items.")
    def list_templates_tool() -> ListTemplatesResult:
        try:
            result = cast(list[TemplateResponse], run_with_session(list_templates))
        except DomainError as exc:
            return capture_domain_error(exc)
        return [serialize_template(item) for item in result]

    @mcp.tool(
        name="get_target",
        description="Get effective target for one day using date token or ISO date.",
    )
    def get_target_tool(day: str | date, local_tz: str) -> GetTargetResult:
        resolved = resolve_date_arg(day, local_tz=local_tz)
        try:
            result = cast(
                EffectiveTarget | None,
                run_with_session(get_effective_target, day=resolved),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        if result is None:
            return None
        return serialize_effective_target(result)
