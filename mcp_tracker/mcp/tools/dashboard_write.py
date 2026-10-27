"""Dashboard write MCP tools (conditionally registered based on read-only mode)."""

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import DashboardID
from mcp_tracker.mcp.tools._access import queue_checks_needed
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.dashboards import (
    CycleTimeBucket,
    CycleTimeLines,
    CycleTimeMode,
    CycleTimeWidget,
    CycleTimeWidgetInput,
    Dashboard,
    DashboardLayout,
)

StatusKeys = Annotated[
    list[str] | None, Field(description="Status keys, e.g. ['open'].")
]


def register_dashboard_write_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register dashboard write tools (not registered in read-only mode)."""

    @mcp.tool(
        title="Create Dashboard",
        description="Create an empty Yandex Tracker dashboard ('дашборд') and return "
        "it with its id; dashboard_add_cycle_time_widget puts a chart on it.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def dashboard_create(
        ctx: Context[AppContext],
        name: Annotated[str, Field(min_length=1, description="Dashboard name.")],
        layout: Annotated[
            DashboardLayout | None,
            Field(
                description="How widgets are arranged; Tracker's default is one column."
            ),
        ] = None,
        owner: Annotated[
            str | None,
            Field(description="Owner's login or uid; omit for the token's owner."),
        ] = None,
    ) -> Dashboard:
        return await ctx.request_context.lifespan_context.dashboards.dashboard_create(
            name, layout=layout, owner=owner, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Delete Dashboard",
        description="Delete a Yandex Tracker dashboard ('дашборд') with all its "
        "widgets. It cannot be restored.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def dashboard_delete(
        ctx: Context[AppContext],
        dashboard_id: DashboardID,
    ) -> None:
        await ctx.request_context.lifespan_context.dashboards.dashboard_delete(
            dashboard_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Add Cycle Time Widget",
        description="Add a 'Время цикла' (cycle time) chart to a Yandex Tracker "
        "dashboard: how long the issues a query matches take between statuses. "
        "The only widget kind the API can create.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def dashboard_add_cycle_time_widget(
        ctx: Context[AppContext],
        dashboard_id: DashboardID,
        description: Annotated[str, Field(min_length=1, description="Widget title.")],
        query: Annotated[
            str | None,
            Field(description="Issues to chart, in the Tracker query language."),
        ] = None,
        filter: Annotated[
            dict[str, Any] | None,
            Field(
                description="Issues to chart as field values, e.g. {'queue': 'TEST'}."
            ),
        ] = None,
        filter_id: Annotated[
            int | None, Field(description="Id of a saved filter to chart.")
        ] = None,
        from_statuses: Annotated[
            list[str] | None,
            Field(
                description="Status keys the cycle starts after; default: the "
                "first status in the issue's history."
            ),
        ] = None,
        to_statuses: Annotated[
            list[str] | None,
            Field(
                description="Status keys the cycle ends in (the latest one reached "
                "counts); default: the issue's last status."
            ),
        ] = None,
        excluded_statuses: StatusKeys = None,
        included_statuses: StatusKeys = None,
        bucket: Annotated[
            CycleTimeBucket | None,
            Field(description="Date grouping; Tracker's default is 7 days."),
        ] = None,
        lines: Annotated[
            CycleTimeLines | None, Field(description="Lines to draw.")
        ] = None,
        calendar_id: Annotated[
            int | None,
            Field(description="Work calendar id, to count working time only."),
        ] = None,
        start: Annotated[
            str | None,
            Field(
                description="Period start as a formula, e.g. 'now()-2w'; default two years."
            ),
        ] = None,
        end: Annotated[
            str | None,
            Field(
                description="Period end as a formula, e.g. 'now()-2d'; default now()."
            ),
        ] = None,
        mode: Annotated[
            CycleTimeMode | None,
            Field(
                description="'common-lines-and-points' adds a dot per issue, "
                "'status-lines' draws the lines per status."
            ),
        ] = None,
    ) -> CycleTimeWidget:
        if sum(value is not None for value in (query, filter, filter_id)) != 1:
            raise TrackerError("Pass exactly one of `query`, `filter`, `filter_id`.")
        # The query may match issues anywhere, which this server cannot check.
        if queue_checks_needed(settings, write=False):
            raise TrackerError(
                "A widget may chart issues of any queue, and this server may read "
                "only some queues; refusing."
            )
        widget = CycleTimeWidgetInput(
            description=description,
            query=query,
            filter=filter,
            filter_id=filter_id,
            from_statuses=from_statuses,
            to_statuses=to_statuses,
            excluded_statuses=excluded_statuses,
            included_statuses=included_statuses,
            bucket=bucket,
            lines=lines,
            calendar_id=calendar_id,
            start=start,
            end=end,
            mode=mode,
        )
        return await ctx.request_context.lifespan_context.dashboards.dashboard_add_cycle_time_widget(
            dashboard_id, widget, auth=get_yandex_auth(ctx)
        )
