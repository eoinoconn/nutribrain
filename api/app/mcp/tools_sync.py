"""MCP sync tool (T-053, §4, §8)."""

from __future__ import annotations

from datetime import date
from typing import cast

from fastmcp import FastMCP

from app.domain import sync_intervals
from app.domain.dto import SyncIntervalsResult as SyncIntervalsDomainResult
from app.domain.errors import DomainError
from app.mcp._tool_common import capture_domain_error, run_with_session
from app.mcp.date_args import default_sync_window, resolve_date_range_args
from app.mcp.serializers import (
    SyncIntervalsResultModel,
    ToolErrorResponse,
    serialize_sync_result,
)

type SyncIntervalsResult = SyncIntervalsResultModel | ToolErrorResponse


def register_sync_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="sync_intervals",
        description=(
            "Sync calories-out for a date range. Date args accept today/yesterday/ISO; "
            "defaults to the last 7 days when omitted."
        ),
    )
    def sync_intervals_tool(
        local_tz: str,
        from_date: str | date | None = None,
        to_date: str | date | None = None,
    ) -> SyncIntervalsResult:
        if from_date is None or to_date is None:
            resolved_from, resolved_to = default_sync_window(local_tz=local_tz)
        else:
            resolved_from, resolved_to = resolve_date_range_args(
                from_value=from_date,
                to_value=to_date,
                local_tz=local_tz,
            )

        try:
            result = cast(
                SyncIntervalsDomainResult,
                run_with_session(sync_intervals, from_date=resolved_from, to_date=resolved_to),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_sync_result(result)
