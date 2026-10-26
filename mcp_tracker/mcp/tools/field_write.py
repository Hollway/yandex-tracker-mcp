"""Write tools for the organization's issue fields and their categories.

Registered with the catalogue tools (writable server and
TRACKER_WORKFLOWS_WRITE_ENABLED), for the same reason: a field is shared by
every queue of the organization. An update is refused on a server limited to
some queues, a create is not. The API cannot delete a field or a category
(405, verified 2026-10-26).
"""

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import (
    CategoryID,
    CategoryUpdateID,
    ContainerParam,
    FieldID,
    FieldOrderParam,
    FieldTypeParam,
    HiddenParam,
    OptionsParam,
    ReadonlyParam,
    VisibleParam,
)
from mcp_tracker.mcp.tools._access import queue_checks_needed
from mcp_tracker.mcp.tools.catalog_write import (
    DescriptionParam,
    DescriptionUpdateParam,
    NameEnParam,
    NameOptionalParam,
    NameParam,
    _both,
    _name,
    _require_change,
    _version,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.fields import FieldCategory, GlobalField

NewFieldID = Annotated[
    str,
    Field(
        description="Id of the new field, e.g. 'releaseNotes': Latin letters "
        "and digits, starting with a lowercase letter. It cannot be changed later."
    ),
]
FieldVersionParam = Annotated[
    int | None,
    Field(
        description="Version to update (optimistic locking), the `version` "
        "field_get shows. Omit to update the current one."
    ),
]
CategoryOrderParam = Annotated[
    int,
    Field(description="Display weight: a category with a lower one is shown higher."),
]
CategoryOrderUpdateParam = Annotated[
    int | None,
    Field(
        description="Display weight: a category with a lower one is shown "
        "higher. Omit to keep it."
    ),
]
CategoryVersionParam = Annotated[
    int | None,
    Field(
        description="Version to update (optimistic locking), the `version` "
        "fields_get_categories shows. Omit to update the current one."
    ),
]


def has_user_options(field: GlobalField) -> bool:
    """Whether a new drop-down list of this field is a list of users - the
    kind Tracker wants the list written as."""
    provider = field.optionsProvider
    if provider is not None and provider.type:
        return provider.type == "FixedUserListOptionsProvider"
    return field.schema_ is not None and field.schema_.type == "user"


def register_field_write_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register the issue field and field category write tools (writable server
    and tracker_workflows_write_enabled)."""

    def check_update_allowed(kind: str) -> None:
        if queue_checks_needed(settings, write=True):
            raise TrackerError(
                f"A {kind} is shared by every queue of the organization, and this "
                f"server may change only some queues; refusing."
            )

    @mcp.tool(
        title="Create Field",
        description="Create an issue field ('поле задачи') in the Yandex Tracker "
        "organization, available to every queue, and return it. A field cannot be "
        "deleted; queue_create_local_field adds one to a single queue.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def field_create(
        ctx: Context[AppContext],
        field_id: NewFieldID,
        name: NameParam,
        category: CategoryID,
        type: FieldTypeParam,
        name_en: NameEnParam = None,
        description: DescriptionParam = None,
        order: FieldOrderParam = None,
        readonly: ReadonlyParam = None,
        visible: VisibleParam = None,
        hidden: HiddenParam = None,
        container: ContainerParam = None,
        options: OptionsParam = None,
    ) -> GlobalField:
        return await ctx.request_context.lifespan_context.fields.field_create(
            field_id=field_id,
            name=_both(name, name_en),
            category=category,
            type=type,
            description=description,
            order=order,
            readonly=readonly,
            visible=visible,
            hidden=hidden,
            container=container,
            options=options,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Field",
        description="Change the name, description, category, drop-down values or "
        "display flags of a Yandex Tracker issue field ('поле задачи') and return "
        "it; omitted settings keep their value. The change shows in every queue, "
        "so a server limited to some queues refuses it.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def field_update(
        ctx: Context[AppContext],
        field_id: FieldID,
        name: NameOptionalParam = None,
        name_en: NameEnParam = None,
        description: DescriptionUpdateParam = None,
        category: CategoryUpdateID = None,
        order: FieldOrderParam = None,
        readonly: ReadonlyParam = None,
        visible: VisibleParam = None,
        hidden: HiddenParam = None,
        options: OptionsParam = None,
        version: FieldVersionParam = None,
    ) -> GlobalField:
        check_update_allowed("field")
        localized = _name(name, name_en)
        _require_change(
            "field",
            name=localized,
            description=description,
            category=category,
            order=order,
            readonly=readonly,
            visible=visible,
            hidden=hidden,
            options=options,
        )
        fields = ctx.request_context.lifespan_context.fields
        auth = get_yandex_auth(ctx)
        user_options = False
        if version is None or options is not None:
            # A new drop-down list is written as the kind the field has, which
            # only a read tells.
            current = await fields.field_get(field_id, auth=auth)
            if version is None:
                version = _version("field", field_id, current.version)
            user_options = has_user_options(current)
        return await fields.field_update(
            field_id,
            version=version,
            name=localized,
            description=description,
            category=category,
            order=order,
            readonly=readonly,
            visible=visible,
            hidden=hidden,
            options=options,
            user_options=user_options,
            auth=auth,
        )

    @mcp.tool(
        title="Create Field Category",
        description="Create a category ('категория полей') that groups issue fields "
        "in the Yandex Tracker organization, and return it. A category cannot be "
        "deleted.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def field_create_category(
        ctx: Context[AppContext],
        name: NameParam,
        order: CategoryOrderParam,
        name_en: NameEnParam = None,
        description: DescriptionParam = None,
    ) -> FieldCategory:
        return await ctx.request_context.lifespan_context.fields.field_category_create(
            name=_both(name, name_en),
            order=order,
            description=description,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Field Category",
        description="Change the name, description or order of a Yandex Tracker "
        "field category ('категория полей') and return it; omitted settings keep "
        "their value. A server limited to some queues refuses it.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def field_update_category(
        ctx: Context[AppContext],
        category_id: CategoryID,
        name: NameOptionalParam = None,
        name_en: NameEnParam = None,
        description: DescriptionUpdateParam = None,
        order: CategoryOrderUpdateParam = None,
        version: CategoryVersionParam = None,
    ) -> FieldCategory:
        check_update_allowed("field category")
        localized = _name(name, name_en)
        _require_change(
            "field category", name=localized, description=description, order=order
        )
        fields = ctx.request_context.lifespan_context.fields
        auth = get_yandex_auth(ctx)
        if version is None:
            current = await fields.field_category_get(category_id, auth=auth)
            version = _version("field category", category_id, current.version)
        return await fields.field_category_update(
            category_id,
            version=version,
            name=localized,
            description=description,
            order=order,
            auth=auth,
        )
