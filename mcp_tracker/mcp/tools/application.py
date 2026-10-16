"""External application tools (read-only)."""

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.issues import ExternalApplication


def register_application_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register external application tools."""

    @mcp.tool(
        title="Get External Applications",
        description="List the applications a Yandex Tracker issue can be linked to "
        "(a repository host, a wiki, a CRM, ...): their `id` is the `origin` that "
        "issue_add_remote_link takes.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def applications_get_all(
        ctx: Context[AppContext],
    ) -> list[ExternalApplication]:
        return await ctx.request_context.lifespan_context.issues.applications_list(
            auth=get_yandex_auth(ctx)
        )
