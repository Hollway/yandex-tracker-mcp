"""Saved issue filter write tools (conditionally registered based on read-only
mode).

A saved filter belongs to no queue, so TRACKER_LIMIT_QUEUES and
TRACKER_READ_ONLY_QUEUES do not apply to these tools - only TRACKER_READ_ONLY
does.
"""

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import (
    FilterColumnsParam,
    FilterConditionsParam,
    FilterIDParam,
    FilterQueryParam,
    FilterSortsParam,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.filters import IssueFilter


def register_filter_write_tools(
    _settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register saved filter write tools."""

    @mcp.tool(
        title="Create Saved Filter",
        description="Save an issue filter in Yandex Tracker ('фильтр') under a "
        "name, with its conditions as a `query` or as `filter` field values, and "
        "return it with its id. It is readable by every employee by default.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def filter_create(
        ctx: Context[AppContext],
        name: Annotated[str, Field(description="Filter name.")],
        query: FilterQueryParam = None,
        filter: FilterConditionsParam = None,
        sorts: FilterSortsParam = None,
        fields: FilterColumnsParam = None,
    ) -> IssueFilter:
        return await ctx.request_context.lifespan_context.issues.filter_create(
            name=name,
            query=query,
            filter=filter,
            sorts=sorts,
            fields=fields,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Saved Filter",
        description="Change a saved issue filter of Yandex Tracker ('фильтр'): "
        "rename it, replace its conditions, sorting or columns. Only the "
        "arguments passed change; new conditions replace the old ones whole.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def filter_update(
        ctx: Context[AppContext],
        filter_id: FilterIDParam,
        name: Annotated[str | None, Field(description="New filter name.")] = None,
        query: FilterQueryParam = None,
        filter: FilterConditionsParam = None,
        sorts: FilterSortsParam = None,
        fields: FilterColumnsParam = None,
    ) -> IssueFilter:
        return await ctx.request_context.lifespan_context.issues.filter_update(
            filter_id,
            name=name,
            query=query,
            filter=filter,
            sorts=sorts,
            fields=fields,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Delete Saved Filter",
        description="Permanently delete a saved issue filter of Yandex Tracker "
        "('фильтр') by id, for everyone it is shared with; there is no undo.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def filter_delete(
        ctx: Context[AppContext],
        filter_id: FilterIDParam,
    ) -> None:
        await ctx.request_context.lifespan_context.issues.filter_delete(
            filter_id, auth=get_yandex_auth(ctx)
        )
