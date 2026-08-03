"""MCP read tools."""

from __future__ import annotations

from datetime import date
from typing import Literal, cast

from fastmcp import FastMCP

from app.api.foods import FoodSearchResponse
from app.domain import (
    find_foods,
    find_meal,
    get_day,
    get_effective_target,
    get_range,
    list_templates,
    search_foods,
)
from app.domain.dto import (
    DayResponse,
    EffectiveTarget,
    MealItemMatch,
    RangeResponse,
    TemplateResponse,
)
from app.domain.errors import DomainError
from app.domain.foods import FindFoodsResult, FoodSearchResult
from app.mcp._tool_common import capture_domain_error, run_with_session
from app.mcp.date_args import (
    resolve_date_arg,
    resolve_date_range_args,
    resolve_effective_local_tz,
)
from app.mcp.serializers import (
    DayModel,
    EffectiveTargetModel,
    FindFoodsResultModel,
    MealItemMatchModel,
    RangeModel,
    TemplateModel,
    ToolErrorResponse,
    serialize_day,
    serialize_effective_target,
    serialize_find_foods_result,
    serialize_food_search_result,
    serialize_meal_item_match,
    serialize_range,
    serialize_template,
)

type GetDayResult = DayModel | ToolErrorResponse
type GetRangeResult = RangeModel | ToolErrorResponse
type FindFoodResult = list[FoodSearchResponse] | ToolErrorResponse
type FindFoodsToolResult = list[FindFoodsResultModel] | ToolErrorResponse
type FindMealResult = list[MealItemMatchModel] | ToolErrorResponse
type ListTemplatesResult = list[TemplateModel] | ToolErrorResponse
type GetTargetResult = EffectiveTargetModel | ToolErrorResponse | None


def register_read_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_day",
        description=(
            "Get one day summary by date token (today/yesterday) or ISO date. "
            "day defaults to today. local_tz defaults to the server's configured "
            "timezone when omitted."
        ),
    )
    def get_day_tool(day: str | None = None, local_tz: str | None = None) -> GetDayResult:
        try:
            tz = resolve_effective_local_tz(local_tz)
            resolved = resolve_date_arg(day if day is not None else "today", local_tz=tz)
            result = cast(DayResponse, run_with_session(get_day, day=resolved))
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_day(result)

    @mcp.tool(
        name="get_range",
        description=(
            "Get day or week range totals using date tokens or ISO dates. "
            "Granularity is one of day/week. from_date/to_date default to today. "
            "local_tz defaults to the server's configured timezone when omitted."
        ),
    )
    def get_range_tool(
        from_date: str | None = None,
        to_date: str | None = None,
        local_tz: str | None = None,
        granularity: Literal["day", "week"] = "day",
    ) -> GetRangeResult:
        try:
            tz = resolve_effective_local_tz(local_tz)
            start, end = resolve_date_range_args(
                from_value=from_date if from_date is not None else "today",
                to_value=to_date if to_date is not None else "today",
                local_tz=tz,
            )
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
            "Use this before guessing between multiple similar foods. Resolving several item "
            "names at once (e.g. every item in a meal)? Use find_foods instead of one call per "
            "name."
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

    @mcp.tool(
        name="find_foods",
        description=(
            "Batch food search: resolve several item names in one round-trip instead of "
            "calling find_food once per item. Each result carries its originating query "
            'alongside its own candidate list, e.g. {"query": "bagel", "candidates": [...]}, '
            "so results stay attributable per input item. limit applies per query, not "
            "globally. An empty queries list returns an empty list; a query with no matches "
            "still appears with an empty candidates list."
        ),
    )
    def find_foods_tool(queries: list[str], limit: int = 20) -> FindFoodsToolResult:
        try:
            result = cast(
                list[FindFoodsResult],
                run_with_session(find_foods, queries=queries, limit=limit),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return [serialize_find_foods_result(item) for item in result]

    @mcp.tool(
        name="find_meal",
        description=(
            "Search logged meal items by name, most-recent-first. Use this for "
            "'when did I last have X' instead of walking get_day one day at a "
            "time. Each result carries meal_id/item_id and computed macros, so "
            "it can feed directly into copy_meal or update_meal_item."
        ),
    )
    def find_meal_tool(
        query: str,
        since: date | None = None,
        limit: int = 20,
    ) -> FindMealResult:
        try:
            result = cast(
                list[MealItemMatch],
                run_with_session(find_meal, query=query, since=since, limit=limit),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return [serialize_meal_item_match(item) for item in result]

    @mcp.tool(name="list_templates", description="List all non-deleted templates with full items.")
    def list_templates_tool() -> ListTemplatesResult:
        try:
            result = cast(list[TemplateResponse], run_with_session(list_templates))
        except DomainError as exc:
            return capture_domain_error(exc)
        return [serialize_template(item) for item in result]

    @mcp.tool(
        name="get_target",
        description=(
            "Get effective target for one day using date token or ISO date. "
            "day defaults to today. local_tz defaults to the server's configured "
            "timezone when omitted."
        ),
    )
    def get_target_tool(
        day: str | date | None = None, local_tz: str | None = None
    ) -> GetTargetResult:
        try:
            tz = resolve_effective_local_tz(local_tz)
            resolved = resolve_date_arg(day if day is not None else "today", local_tz=tz)
            result = cast(
                EffectiveTarget | None,
                run_with_session(get_effective_target, day=resolved),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        if result is None:
            return None
        return serialize_effective_target(result)
