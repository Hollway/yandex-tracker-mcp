"""Write tools for the organization's catalogue: issue statuses, resolutions,
issue types and priorities.

Registered on a writable server with TRACKER_WORKFLOWS_WRITE_ENABLED - these
are what workflows are built from, and each one is shared by every queue of
the organization. That is also why an update is refused on a server limited
to some queues (TRACKER_LIMIT_QUEUES / TRACKER_READ_ONLY_QUEUES): renaming a
status renames it in queues the server may not touch. A create is not - a new
object is used nowhere until a workflow or a queue takes it up. The API has no
call that deletes any of them.
"""

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.tools._access import queue_checks_needed
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import (
    CatalogEmptyUpdate,
    CatalogNameEnWithoutName,
)
from mcp_tracker.tracker.proto.types.issue_types import IssueType
from mcp_tracker.tracker.proto.types.priorities import Priority
from mcp_tracker.tracker.proto.types.resolutions import Resolution
from mcp_tracker.tracker.proto.types.statuses import Status, StatusType
from mcp_tracker.tracker.proto.types.workflows import LocalizedText

KeyParam = Annotated[
    str,
    Field(
        description="Key, e.g. 'inReview': Latin letters, starting with a "
        "lowercase one. It cannot be changed later."
    ),
]
NameParam = Annotated[str, Field(description="Name in Russian.")]
NameOptionalParam = Annotated[
    str | None, Field(description="Name in Russian. Omit to keep it.")
]
NameEnParam = Annotated[
    str | None,
    Field(
        description="Name in English; defaults to `name`, and is written only "
        "together with it."
    ),
]
DescriptionParam = Annotated[str | None, Field(description="Description.")]
DescriptionUpdateParam = Annotated[
    str | None, Field(description="Description. Omit to keep it.")
]
OrderParam = Annotated[
    int | None,
    Field(description="Display weight, which sets the position in lists."),
]
StatusTypeParam = Annotated[
    StatusType,
    Field(description="Status type - what boards, filters and reports take it for."),
]
StatusTypeOptionalParam = Annotated[
    StatusType | None,
    Field(
        description="Status type - what boards, filters and reports take it for. "
        "Omit to keep it."
    ),
]
VersionParam = Annotated[
    int | None,
    Field(
        description="Version to update (optimistic locking), the `version` its "
        "get_* listing shows. Omit to update the current one."
    ),
]
StatusID = Annotated[
    str, Field(description="Status key, e.g. 'inProgress', or its numeric id.")
]
ResolutionID = Annotated[
    str, Field(description="Resolution key, e.g. 'fixed', or its numeric id.")
]
IssueTypeID = Annotated[
    str, Field(description="Issue type key, e.g. 'bug', or its numeric id.")
]
PriorityID = Annotated[
    str, Field(description="Priority key, e.g. 'critical', or its numeric id.")
]


def _both(name: str, name_en: str | None) -> LocalizedText:
    """The name as Tracker writes it - both languages at once."""
    return LocalizedText(ru=name, en=name_en or name)


def _name(name: str | None, name_en: str | None) -> LocalizedText | None:
    """The name of an update, if it changes."""
    if name is None:
        if name_en is not None:
            raise CatalogNameEnWithoutName()
        return None
    return _both(name, name_en)


def _require_change(kind: str, **values: Any) -> None:
    """Refuse an update that passes nothing to change - before the read of
    the current version, which it would waste."""
    if all(v is None for v in values.values()):
        raise CatalogEmptyUpdate(kind, tuple(values))


def _version(kind: str, object_id: str, version: int | None) -> int:
    if version is None:
        raise TrackerError(
            f"The {kind} '{object_id}' came back without a version, so it cannot "
            f"be updated; pass `version`."
        )
    return version


def register_catalog_write_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register the status, resolution, issue type and priority write tools
    (writable server and tracker_workflows_write_enabled)."""

    def check_update_allowed(kind: str) -> None:
        if queue_checks_needed(settings, write=True):
            raise TrackerError(
                f"A {kind} is shared by every queue of the organization, and this "
                f"server may change only some queues; refusing."
            )

    @mcp.tool(
        title="Create Status",
        description="Create an issue status ('статус задачи') in the Yandex Tracker "
        "organization's catalogue, for workflows to use, and return it. Statuses "
        "are shared by all queues and cannot be deleted.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def status_create(
        ctx: Context[AppContext],
        key: KeyParam,
        name: NameParam,
        type: StatusTypeParam,
        name_en: NameEnParam = None,
        description: DescriptionParam = None,
        order: OrderParam = None,
    ) -> Status:
        return await ctx.request_context.lifespan_context.fields.status_create(
            key=key,
            name=_both(name, name_en),
            type=type,
            description=description,
            order=order,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Status",
        description="Change the name, description, order or type of a Yandex "
        "Tracker issue status ('статус задачи') and return it; omitted fields keep "
        "their value. The change shows in every queue, so a server limited to "
        "some queues refuses it.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def status_update(
        ctx: Context[AppContext],
        status_id: StatusID,
        name: NameOptionalParam = None,
        name_en: NameEnParam = None,
        description: DescriptionUpdateParam = None,
        order: OrderParam = None,
        type: StatusTypeOptionalParam = None,
        version: VersionParam = None,
    ) -> Status:
        check_update_allowed("status")
        localized = _name(name, name_en)
        _require_change(
            "status", name=localized, description=description, order=order, type=type
        )
        fields = ctx.request_context.lifespan_context.fields
        auth = get_yandex_auth(ctx)
        if version is None:
            version = (await fields.status_get(status_id, auth=auth)).version
        return await fields.status_update(
            status_id,
            version=version,
            name=localized,
            description=description,
            order=order,
            type=type,
            auth=auth,
        )

    @mcp.tool(
        title="Create Resolution",
        description="Create a resolution ('резолюция') - why an issue was closed - "
        "in the Yandex Tracker organization's catalogue, and return it. "
        "Resolutions are shared by all queues and cannot be deleted.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def resolution_create(
        ctx: Context[AppContext],
        key: KeyParam,
        name: NameParam,
        name_en: NameEnParam = None,
        description: DescriptionParam = None,
        order: OrderParam = None,
    ) -> Resolution:
        return await ctx.request_context.lifespan_context.fields.resolution_create(
            key=key,
            name=_both(name, name_en),
            description=description,
            order=order,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Resolution",
        description="Change the name, description or order of a Yandex Tracker "
        "resolution ('резолюция') and return it; omitted fields keep their value. "
        "The change shows in every queue, so a server limited to some queues "
        "refuses it.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def resolution_update(
        ctx: Context[AppContext],
        resolution_id: ResolutionID,
        name: NameOptionalParam = None,
        name_en: NameEnParam = None,
        description: DescriptionUpdateParam = None,
        order: OrderParam = None,
        version: VersionParam = None,
    ) -> Resolution:
        check_update_allowed("resolution")
        localized = _name(name, name_en)
        _require_change(
            "resolution", name=localized, description=description, order=order
        )
        fields = ctx.request_context.lifespan_context.fields
        auth = get_yandex_auth(ctx)
        if version is None:
            current = await fields.resolution_get(resolution_id, auth=auth)
            version = _version("resolution", resolution_id, current.version)
        return await fields.resolution_update(
            resolution_id,
            version=version,
            name=localized,
            description=description,
            order=order,
            auth=auth,
        )

    @mcp.tool(
        title="Create Issue Type",
        description="Create an issue type ('тип задачи') in the Yandex Tracker "
        "organization's catalogue and return it. Issue types are shared by all "
        "queues and cannot be deleted.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_type_create(
        ctx: Context[AppContext],
        key: KeyParam,
        name: NameParam,
        name_en: NameEnParam = None,
        description: DescriptionParam = None,
    ) -> IssueType:
        return await ctx.request_context.lifespan_context.fields.issue_type_create(
            key=key,
            name=_both(name, name_en),
            description=description,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Issue Type",
        description="Change the name or description of a Yandex Tracker issue type "
        "('тип задачи') and return it; omitted fields keep their value. The change "
        "shows in every queue, so a server limited to some queues refuses it.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_type_update(
        ctx: Context[AppContext],
        issue_type_id: IssueTypeID,
        name: NameOptionalParam = None,
        name_en: NameEnParam = None,
        description: DescriptionUpdateParam = None,
        version: VersionParam = None,
    ) -> IssueType:
        check_update_allowed("issue type")
        localized = _name(name, name_en)
        _require_change("issue type", name=localized, description=description)
        fields = ctx.request_context.lifespan_context.fields
        auth = get_yandex_auth(ctx)
        if version is None:
            version = (await fields.issue_type_get(issue_type_id, auth=auth)).version
        return await fields.issue_type_update(
            issue_type_id,
            version=version,
            name=localized,
            description=description,
            auth=auth,
        )

    @mcp.tool(
        title="Create Priority",
        description="Create an issue priority ('приоритет') in the Yandex Tracker "
        "organization's catalogue and return it. Priorities are shared by all "
        "queues and cannot be deleted; the API cannot set a priority's icon.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def priority_create(
        ctx: Context[AppContext],
        key: KeyParam,
        name: NameParam,
        name_en: NameEnParam = None,
        description: DescriptionParam = None,
        order: OrderParam = None,
    ) -> Priority:
        return await ctx.request_context.lifespan_context.fields.priority_create(
            key=key,
            name=_both(name, name_en),
            description=description,
            order=order,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Priority",
        description="Change the name, description or order of a Yandex Tracker "
        "issue priority ('приоритет') and return it; omitted fields keep their "
        "value. The change shows in every queue, so a server limited to some "
        "queues refuses it.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def priority_update(
        ctx: Context[AppContext],
        priority_id: PriorityID,
        name: NameOptionalParam = None,
        name_en: NameEnParam = None,
        description: DescriptionUpdateParam = None,
        order: OrderParam = None,
        version: VersionParam = None,
    ) -> Priority:
        check_update_allowed("priority")
        localized = _name(name, name_en)
        _require_change(
            "priority", name=localized, description=description, order=order
        )
        fields = ctx.request_context.lifespan_context.fields
        auth = get_yandex_auth(ctx)
        if version is None:
            version = (await fields.priority_get(priority_id, auth=auth)).version
        return await fields.priority_update(
            priority_id,
            version=version,
            name=localized,
            description=description,
            order=order,
            auth=auth,
        )
