"""Queue component MCP tools (read-only)."""

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import (
    ComponentID,
    PermissionGroupParam,
    PermissionUserParam,
)
from mcp_tracker.mcp.tools._access import (
    check_component_access,
    queue_checks_needed,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.permissions import SubjectPermissions


def register_component_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register queue component tools (all read-only)."""

    @mcp.tool(
        title="Get Component",
        description="Get one Yandex Tracker queue component (in russian - "
        "'компонент') by its numeric id, with `queue`, `lead`, `assignAuto` and the "
        "`version` that `component_update` takes. Ids come from "
        "`queue_get_components` or an issue's `components` field.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def component_get(
        ctx: Context[AppContext],
        component_id: ComponentID,
    ) -> Component:
        component = await ctx.request_context.lifespan_context.components.component_get(
            component_id,
            auth=get_yandex_auth(ctx),
        )
        # The id names no queue, so the check runs on what came back.
        check_component_access(settings, component)
        return component


def register_component_admin_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register the component permission reads (``TRACKER_ADMIN_ENABLED``)."""

    async def check_permissions_access(
        ctx: Context[AppContext], component_id: int
    ) -> None:
        """Under a queue restriction, read the component for its queue - the
        id names none."""
        if queue_checks_needed(settings, write=False):
            component = (
                await ctx.request_context.lifespan_context.components.component_get(
                    component_id, auth=get_yandex_auth(ctx)
                )
            )
            check_component_access(settings, component)

    @mcp.tool(
        title="Get Component User Permissions",
        description="Get the permissions one user has on a Yandex Tracker queue "
        "component ('права на компонент'), each with the grant it comes through.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def component_get_user_permissions(
        ctx: Context[AppContext],
        component_id: ComponentID,
        user: PermissionUserParam,
    ) -> SubjectPermissions:
        await check_permissions_access(ctx, component_id)
        components = ctx.request_context.lifespan_context.components
        return await components.component_get_user_permissions(
            component_id, user, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Component Group Permissions",
        description="Get the permissions one user group has on a Yandex Tracker "
        "queue component ('права группы на компонент'), each with the grant it "
        "comes through.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def component_get_group_permissions(
        ctx: Context[AppContext],
        component_id: ComponentID,
        group_id: PermissionGroupParam,
    ) -> SubjectPermissions:
        await check_permissions_access(ctx, component_id)
        components = ctx.request_context.lifespan_context.components
        return await components.component_get_group_permissions(
            component_id, group_id, auth=get_yandex_auth(ctx)
        )
