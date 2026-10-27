"""Dashboard MCP tools (read-only)."""

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import DashboardID
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.dashboards import Dashboard
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult


def register_dashboard_tools(_settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register dashboard read tools."""

    @mcp.tool(
        title="Get Dashboard",
        description="Read a Yandex Tracker dashboard ('дашборд') by id: its name, "
        "layout, owner and the ids and titles of its widgets.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def dashboard_get(
        ctx: Context[AppContext],
        dashboard_id: DashboardID,
    ) -> Dashboard:
        return await ctx.request_context.lifespan_context.dashboards.dashboard_get(
            dashboard_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get All Dashboards",
        description="List the dashboards ('дашборды') of the Yandex Tracker "
        "organization with their owners, newest first; returns `{values, hits, "
        "pages}`. Widgets are listed by dashboard_get only.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def dashboards_get_all(
        ctx: Context[AppContext],
    ) -> PaginatedResult[Dashboard]:
        return await ctx.request_context.lifespan_context.dashboards.dashboards_list(
            auth=get_yandex_auth(ctx)
        )
