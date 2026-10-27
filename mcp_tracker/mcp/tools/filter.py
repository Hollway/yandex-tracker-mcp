"""Saved issue filter MCP tools (read-only).

A saved filter belongs to no queue, so TRACKER_LIMIT_QUEUES does not apply.
"""

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import FilterIDParam
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.filters import IssueFilter


def register_filter_tools(_settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register saved filter tools (all read-only)."""

    @mcp.tool(
        title="Get Saved Filter",
        description="Get a saved issue filter of Yandex Tracker ('фильтр') by id: "
        "name, conditions as `query` or `filter`, sorting, owner. issues_find "
        "with `filter_id` returns the issues it matches.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def filter_get(
        ctx: Context[AppContext],
        filter_id: FilterIDParam,
    ) -> IssueFilter:
        return await ctx.request_context.lifespan_context.issues.filter_get(
            filter_id, auth=get_yandex_auth(ctx)
        )
