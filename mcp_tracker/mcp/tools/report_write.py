"""Issue report write MCP tools (conditionally registered based on read-only mode)."""

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import ReportID
from mcp_tracker.mcp.tools._access import queue_checks_needed
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.reports import Report, ReportFormat, ReportSort


def register_report_write_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register issue report write tools (not registered in read-only mode)."""

    @mcp.tool(
        title="Create Report",
        description="Create an issue report ('отчёт', 'выгрузка'): Tracker exports "
        "the issues a query matches to an xlsx, csv or xml file. The API returns no "
        "file - it is downloaded in Tracker's web interface; to read issues here use "
        "issues_find.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def report_create(
        ctx: Context[AppContext],
        summary: Annotated[str, Field(min_length=1, description="Report name.")],
        format: Annotated[ReportFormat, Field(description="File format.")],
        fields: Annotated[
            list[str],
            Field(
                min_length=1,
                description="Issue field keys, one column each, e.g. "
                "['key', 'summary', 'status', 'assignee'].",
            ),
        ],
        query: Annotated[
            str | None,
            Field(description="Issues to export, in the Tracker query language."),
        ] = None,
        filter: Annotated[
            dict[str, Any] | None,
            Field(
                description="Issues to export as field values, e.g. "
                "{'queue': 'TREK', 'assignee': 'empty()'}."
            ),
        ] = None,
        filter_id: Annotated[
            int | None, Field(description="Id of a saved filter to export.")
        ] = None,
        sorts: Annotated[
            list[ReportSort] | None, Field(description="Row order.")
        ] = None,
    ) -> Report:
        if sum(value is not None for value in (query, filter, filter_id)) != 1:
            raise TrackerError("Pass exactly one of `query`, `filter`, `filter_id`.")
        # The query may match issues anywhere, which this server cannot check.
        if queue_checks_needed(settings, write=False):
            raise TrackerError(
                "A report may export issues of any queue, and this server may read "
                "only some queues; refusing."
            )
        return await ctx.request_context.lifespan_context.reports.report_create(
            summary,
            format=format,
            fields=fields,
            query=query,
            filter=filter,
            filter_id=filter_id,
            sorts=sorts,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Delete Report",
        description="Delete an issue report ('отчёт') of Yandex Tracker by id, with "
        "its file.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def report_delete(
        ctx: Context[AppContext],
        report_id: ReportID,
    ) -> None:
        await ctx.request_context.lifespan_context.reports.report_delete(
            report_id, auth=get_yandex_auth(ctx)
        )
