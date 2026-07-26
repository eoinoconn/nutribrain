"""MCP sync tools.

T-050 scaffolds discovery, schema, and date parsing. The actual sync behavior
lands in T-061/T-062.
"""

from __future__ import annotations

from datetime import date

from fastmcp import FastMCP

from app.domain.errors import IntervalsUnavailableError
from app.mcp.date_args import default_sync_window, resolve_date_range_args
from app.mcp.serializers import (
    SyncIntervalsResultModel,
    ToolErrorResponse,
    serialize_domain_error,
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

        # The concrete integration is implemented in T-061.
        error = IntervalsUnavailableError(
            "Intervals sync is not implemented yet in this scaffold."
        )
        tool_error = serialize_domain_error(error)
        _ = (resolved_from, resolved_to)
        return tool_error
