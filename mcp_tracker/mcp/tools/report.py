"""Issue report MCP tools (read-only)."""

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import PageParam, PerPageParam, ReportID
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from mcp_tracker.tracker.proto.types.reports import Report


def register_report_tools(_settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register issue report read tools."""

    @mcp.tool(
        title="Get Report",
        description="Read an issue report ('отчёт', an export of issues to "
        "xlsx/csv/xml) by id: its name, status and what it exports. The file itself "
        "is downloaded in Tracker's web interface only.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def report_get(
        ctx: Context[AppContext],
        report_id: ReportID,
    ) -> Report:
        return await ctx.request_context.lifespan_context.reports.report_get(
            report_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Find Reports",
        description="List the organization's issue reports ('отчёты', exports of "
        "issues to a file), newest first, optionally by one author; returns "
        "`{values, hits, pages}`.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def reports_find(
        ctx: Context[AppContext],
        author: Annotated[
            str | None,
            Field(description="Login or uid of the user who created the reports."),
        ] = None,
        page: PageParam = 1,
        per_page: PerPageParam = 50,
    ) -> PaginatedResult[Report]:
        app = ctx.request_context.lifespan_context
        auth = get_yandex_auth(ctx)
        # Tracker filters by uid only: a login answers no reports at all.
        if author is not None and not author.isdigit():
            user = await app.users.user_get(author, auth=auth)
            if user is None:
                raise TrackerError(f"User `{author}` not found.")
            author = str(user.uid)
        return await app.reports.reports_find(
            author=author, per_page=per_page, page=page, auth=auth
        )
