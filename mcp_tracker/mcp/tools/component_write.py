"""Queue component write MCP tools (conditionally registered based on read-only mode)."""

from typing import Annotated

from mcp.server.mcpserver import (
    AcceptedElicitation,
    Context,
    Elicit,
    ElicitationResult,
    MCPServer,
    Resolve,
)
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import (
    ComponentAssignAutoParam,
    ComponentClearLeadParam,
    ComponentDescriptionParam,
    ComponentID,
    ComponentLeadParam,
    ComponentNameOptionalParam,
    ComponentNameParam,
    ComponentVersionParam,
    QueueID,
)
from mcp_tracker.mcp.tools._access import (
    check_component_access,
    check_queue_access,
    queue_checks_needed,
)
from mcp_tracker.mcp.tools.issue_write import _can_ask
from mcp_tracker.mcp.tools.queue_write import (
    PermissionsConfirmation,
    _describe_change,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import PermissionsEmptyUpdate
from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.permissions import (
    PermissionChange,
    QueuePermissions,
)


def _component_permission_changes(
    create: PermissionChange | None,
    read: PermissionChange | None,
    write: PermissionChange | None,
    grant: PermissionChange | None,
) -> dict[str, PermissionChange]:
    actions = {"create": create, "read": read, "write": write, "grant": grant}
    changes = {k: v for k, v in actions.items() if v is not None}
    if not changes:
        raise PermissionsEmptyUpdate("`create`, `read`, `write` or `grant`")
    return changes


def register_component_write_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register queue component write tools (not registered in read-only mode)."""

    async def check_component(ctx: Context[AppContext], component_id: int) -> None:
        """The write check of a component known by id: its queue is read only
        when a queue restriction applies."""
        if queue_checks_needed(settings, write=True):
            component = (
                await ctx.request_context.lifespan_context.components.component_get(
                    component_id, auth=get_yandex_auth(ctx)
                )
            )
            check_component_access(settings, component, write=True)

    async def confirm_component_permissions(
        ctx: Context[AppContext],
        component_id: int,
        create: PermissionChange | None = None,
        read: PermissionChange | None = None,
        write: PermissionChange | None = None,
        grant: PermissionChange | None = None,
    ) -> PermissionsConfirmation | Elicit[PermissionsConfirmation]:
        """Ask the user to confirm a change of a component's permissions where
        the client can be asked; the checks run first, so the user is not asked
        about a change the tool would refuse anyway."""
        changes = _component_permission_changes(create, read, write, grant)
        await check_component(ctx, component_id)
        if not _can_ask(ctx):
            return PermissionsConfirmation(confirm=True)
        summary = "; ".join(_describe_change(a, c) for a, c in changes.items())
        return Elicit(
            f"Change the permissions of component {component_id}: {summary}. Proceed?",
            PermissionsConfirmation,
        )

    @mcp.tool(
        title="Create Component",
        description="Create a component (in russian - 'компонент') in a Yandex "
        "Tracker queue - a label grouping the queue's issues by product, process or "
        "owner; `lead` is a user login.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def component_create(
        ctx: Context[AppContext],
        queue_id: QueueID,
        name: ComponentNameParam,
        description: ComponentDescriptionParam = None,
        lead: ComponentLeadParam = None,
        assign_auto: ComponentAssignAutoParam = None,
    ) -> Component:
        check_queue_access(settings, queue_id, write=True)
        return await ctx.request_context.lifespan_context.components.component_create(
            queue_id,
            name=name,
            description=description,
            lead=lead,
            assign_auto=assign_auto,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Component",
        description="Change the name, description, lead or auto-assign flag of a "
        "Yandex Tracker queue component (in russian - 'компонент'); omitted fields "
        "keep their value, `clear_lead` removes the lead.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def component_update(
        ctx: Context[AppContext],
        component_id: ComponentID,
        name: ComponentNameOptionalParam = None,
        description: ComponentDescriptionParam = None,
        lead: ComponentLeadParam = None,
        assign_auto: ComponentAssignAutoParam = None,
        clear_lead: ComponentClearLeadParam = False,
        version: ComponentVersionParam = None,
    ) -> Component:
        components = ctx.request_context.lifespan_context.components
        auth = get_yandex_auth(ctx)

        # One read at most, for the version and/or the queue to check.
        if version is None or queue_checks_needed(settings, write=True):
            component = await components.component_get(component_id, auth=auth)
            check_component_access(settings, component, write=True)
            if version is None:
                version = component.version

        return await components.component_update(
            component_id,
            version=version,
            name=name,
            description=description,
            lead=lead,
            assign_auto=assign_auto,
            clear_lead=clear_lead,
            auth=auth,
        )

    @mcp.tool(
        title="Delete Component",
        description="Delete a Yandex Tracker queue component (in russian - "
        "'компонент') by its numeric id. Cannot be undone.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def component_delete(
        ctx: Context[AppContext],
        component_id: ComponentID,
    ) -> None:
        components = ctx.request_context.lifespan_context.components
        auth = get_yandex_auth(ctx)

        # Read the component only when there is a queue restriction to check.
        if queue_checks_needed(settings, write=True):
            component = await components.component_get(component_id, auth=auth)
            check_component_access(settings, component, write=True)

        await components.component_delete(component_id, auth=auth)

    @mcp.tool(
        title="Update Component Permissions",
        description="Grant or revoke the permissions of a Yandex Tracker queue "
        "component ('права доступа к компоненту') for users, groups and roles, and "
        "return them all. The first change restricts a component nobody had "
        "restricted; the user confirms where the client can ask.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def component_update_permissions(
        ctx: Context[AppContext],
        component_id: ComponentID,
        confirmation: Annotated[
            ElicitationResult[PermissionsConfirmation],
            Resolve(confirm_component_permissions),
        ],
        create: Annotated[
            PermissionChange | None,
            Field(description="Who may create issues with it; omit to keep it."),
        ] = None,
        read: Annotated[
            PermissionChange | None,
            Field(description="Who may read its issues; omit to keep it."),
        ] = None,
        write: Annotated[
            PermissionChange | None,
            Field(description="Who may change its issues; omit to keep it."),
        ] = None,
        grant: Annotated[
            PermissionChange | None,
            Field(description="Who may change its permissions; omit to keep it."),
        ] = None,
        version: Annotated[
            int | None,
            Field(
                description="`version` of the component's permissions (not of the "
                "component), to refuse the change if they were edited since; "
                "omitted, the current one is read and used."
            ),
        ] = None,
    ) -> QueuePermissions:
        changes = _component_permission_changes(create, read, write, grant)
        await check_component(ctx, component_id)
        if not (
            isinstance(confirmation, AcceptedElicitation) and confirmation.data.confirm
        ):
            raise TrackerError("The permissions change was cancelled by the user.")
        components = ctx.request_context.lifespan_context.components
        auth = get_yandex_auth(ctx)
        if version is None:
            current = await components.component_get_permissions(
                component_id, auth=auth
            )
            if current.version is None:
                raise TrackerError(
                    f"The permissions of component `{component_id}` came back "
                    f"without a `version`; pass it explicitly."
                )
            version = current.version
        return await components.component_update_permissions(
            component_id, changes, version=version, auth=auth
        )
