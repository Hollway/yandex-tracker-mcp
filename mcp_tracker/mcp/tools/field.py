"""Global field and metadata MCP tools (read-only)."""

import asyncio
from collections.abc import Sequence
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import FieldID, IssueID
from mcp_tracker.mcp.tools._access import (
    check_fetched_issue_access,
    check_issue_access,
    check_queue_access,
    queue_of_key,
)
from mcp_tracker.mcp.tools._field_lookup import (
    CATALOG_BY_VALUE_TYPE,
    CATALOG_FIELDS,
    FieldRow,
    FieldValue,
    FieldValues,
    field_rows,
    find_field,
    fixed_options,
    free_value_error,
    match_rows,
    select_values,
    value_type,
    values_hint,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.fields import (
    FieldCategory,
    FieldLanguage,
    GlobalField,
)
from mcp_tracker.tracker.proto.types.issue_types import IssueType
from mcp_tracker.tracker.proto.types.priorities import Priority
from mcp_tracker.tracker.proto.types.resolutions import Resolution
from mcp_tracker.tracker.proto.types.statuses import Status


def register_field_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register global field and metadata tools (all read-only)."""

    @mcp.tool(
        title="Get Global Fields",
        description="Get all global fields available in Yandex Tracker that can be used in issues",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def get_global_fields(
        ctx: Context[AppContext],
    ) -> list[GlobalField]:
        return await ctx.request_context.lifespan_context.fields.get_global_fields(
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Field",
        description="Get one issue field ('поле задачи') of the Yandex Tracker "
        "organization by its id: name, type, category, drop-down values and the "
        "current `version`. A queue's local field is read with queue_get_fields.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def field_get(
        ctx: Context[AppContext],
        field_id: FieldID,
    ) -> GlobalField:
        return await ctx.request_context.lifespan_context.fields.field_get(
            field_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Field Categories",
        description="List the categories ('категории полей') that group the issue "
        "fields of the Yandex Tracker organization, with their ids and versions.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def fields_get_categories(
        ctx: Context[AppContext],
    ) -> list[FieldCategory]:
        return await ctx.request_context.lifespan_context.fields.fields_get_categories(
            auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Find Fields",
        description="Find an issue field ('поле задачи') by the name a user says, in "
        "Russian or English, or by part of its id; `queue` adds its local fields. A "
        "row gives the `id` for `fields` of issue_create / issue_update, the "
        "issues_find query name and how values are given. No row: ask, never "
        "substitute a similar field.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def fields_find(
        ctx: Context[AppContext],
        query: Annotated[
            str | None,
            Field(
                description="Part of the field name, in any language, or of its id. "
                "Without it, only the local fields of `queue` are listed."
            ),
        ] = None,
        queue: Annotated[
            str | None,
            Field(description="Queue key, e.g. 'SOMEPROJECT': adds its local fields."),
        ] = None,
    ) -> list[FieldRow]:
        if query is None and queue is None:
            raise TrackerError(
                "Pass `query`, `queue` or both; get_global_fields lists every field."
            )
        if queue is not None:
            check_queue_access(settings, queue)
            # The local fields of `sap` answer 404: the path wants the key as is.
            queue = queue.upper()

        app = ctx.request_context.lifespan_context
        auth = get_yandex_auth(ctx)

        # Names come in the `Accept-Language` language: both are read so that
        # a field is found by either, and `ql_name` uses the English one.
        async def global_fields(language: FieldLanguage) -> Sequence[GlobalField]:
            if query is None:
                return []
            return await app.fields.get_global_fields(language=language, auth=auth)

        async def local_fields(language: FieldLanguage) -> Sequence[GlobalField]:
            if queue is None:
                return []
            return await app.queues.queues_get_local_fields(
                queue, language=language, auth=auth
            )

        global_ru, global_en, local_ru, local_en = await asyncio.gather(
            global_fields("ru"),
            global_fields("en"),
            local_fields("ru"),
            local_fields("en"),
        )
        entities = settings.tracker_entities_enabled
        rows = field_rows(
            global_ru, global_en, queue=None, entities_enabled=entities
        ) + field_rows(
            local_ru,
            local_en,
            queue=queue,
            entities_enabled=entities,
        )
        keys = {f.id: f.key for f in [*global_ru, *local_ru]}
        return match_rows(rows, keys, query)

    async def field_definition(
        app: AppContext, field_id: str, queue: str | None, auth: YandexAuth | None
    ) -> GlobalField:
        """A field by its id or key: a global one, else a local one of `queue`."""
        if "--" not in field_id:
            found = find_field(
                await app.fields.get_global_fields(language="ru", auth=auth), field_id
            )
            if found is not None:
                return found
        if queue is not None:
            found = find_field(
                await app.queues.queues_get_local_fields(
                    queue, language="ru", auth=auth
                ),
                field_id,
            )
            if found is not None:
                return found
            raise TrackerError(
                f"No issue field `{field_id}` in queue {queue}; find it with fields_find."
            )
        if "--" in field_id:
            raise TrackerError(
                f"`{field_id}` is a local field: pass the `queue` it belongs to."
            )
        raise TrackerError(
            f"No issue field `{field_id}`; find it with fields_find, and pass "
            "`queue` for a local field."
        )

    async def catalog_values(
        app: AppContext,
        catalog: str,
        field_id: str,
        queue: str | None,
        issue_type: str | None,
        auth: YandexAuth | None,
    ) -> list[FieldValue]:
        if catalog == "priority":
            # The API lists them by id; by weight, the next level up is the
            # next row.
            priorities = await app.fields.get_priorities(auth=auth)
            return [
                FieldValue(
                    id=str(priority.id),
                    key=priority.key,
                    display=priority.name,
                    order=priority.order,
                )
                for priority in sorted(priorities, key=lambda p: p.order)
            ]

        if catalog in ("type", "resolution"):
            if queue is None:
                catalogue = (
                    await app.fields.get_issue_types(auth=auth)
                    if catalog == "type"
                    else await app.fields.get_resolutions(auth=auth)
                )
                return [
                    FieldValue(id=str(item.id), key=item.key, display=item.name)
                    for item in catalogue
                ]
            configs = (
                await app.queues.queue_get(
                    queue, expand=["issueTypesConfig"], auth=auth
                )
            ).issueTypesConfig or []
            values: dict[str, FieldValue] = {}
            if catalog == "type":
                for config in configs:
                    ref = config.issueType
                    if ref is not None and ref.key is not None:
                        values.setdefault(
                            ref.key,
                            FieldValue(
                                id=str(ref.id), key=ref.key, display=ref.display
                            ),
                        )
                return list(values.values())
            # The resolutions of the issue's own type when there is one, else
            # those of every type of the queue.
            own = [c for c in configs if c.issueType and c.issueType.key == issue_type]
            for config in own or configs:
                for resolution in config.resolutions or []:
                    values.setdefault(
                        resolution.key,
                        FieldValue(
                            id=str(resolution.id),
                            key=resolution.key,
                            display=resolution.display or resolution.name,
                        ),
                    )
            return list(values.values())

        if queue is None:
            raise TrackerError(
                f"The values of `{field_id}` belong to a queue: pass `queue` or "
                "`issue_id`."
            )
        if catalog == "components":
            return [
                FieldValue(id=str(component.id), display=component.name)
                for component in await app.queues.queues_get_components(
                    queue, auth=auth
                )
            ]
        return [
            FieldValue(
                id=str(version.id),
                display=version.name,
                archived=version.archived or None,
            )
            for version in await app.queues.queues_get_versions(queue, auth=auth)
        ]

    @mcp.tool(
        title="Get Field Values",
        description="List the values an issue field ('поле задачи') accepts: "
        "drop-down options, priorities, issue types, resolutions, components or "
        "versions, for a new issue in `queue` or an existing `issue_id`. Write a "
        "value's `key`, else its `id`. Not listed: ask, never guess. People, "
        "statuses, sprints and issues have their own tools, named in the error.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def field_get_values(
        ctx: Context[AppContext],
        field: Annotated[
            str,
            Field(
                description="Field id from fields_find (a local field: its id or "
                "key, with `queue`), or one of priority, type, resolution, "
                "components, fixVersions, affectedVersions."
            ),
        ],
        queue: Annotated[
            str | None,
            Field(
                description="Queue key of a new issue, e.g. 'SOMEPROJECT'. Needed "
                "for components, versions and local fields; narrows types and "
                "resolutions to the queue's."
            ),
        ] = None,
        issue_id: Annotated[
            str | None,
            Field(
                description="Key of an existing issue, instead of `queue`: "
                "resolutions are then those of its issue type."
            ),
        ] = None,
        query: Annotated[
            str | None,
            Field(description="Text the value's key or name contains."),
        ] = None,
        limit: Annotated[
            int,
            Field(ge=1, le=500, description="Most values to return."),
        ] = 50,
    ) -> FieldValues:
        if queue is not None and issue_id is not None:
            raise TrackerError(
                "Pass `queue` for a new issue or `issue_id` for an existing one, "
                "not both."
            )
        app = ctx.request_context.lifespan_context
        auth = get_yandex_auth(ctx)

        issue_type: str | None = None
        if issue_id is not None:
            # The issue is read anyway, so an internal id is checked by the key
            # it comes back under.
            if queue_of_key(issue_id) is not None:
                check_issue_access(settings, issue_id)
            issue = await app.issues.issue_get(issue_id, auth=auth)
            check_fetched_issue_access(settings, issue_id, issue.key)
            queue = queue_of_key(issue.key or issue_id)
            issue_type = issue.type.key if issue.type else None
        elif queue is not None:
            check_queue_access(settings, queue)
            queue = queue.upper()

        catalog = field if field in CATALOG_FIELDS else None
        if catalog is None:
            definition = await field_definition(app, field, queue, auth)
            catalog = CATALOG_BY_VALUE_TYPE.get(value_type(definition) or "")
            if catalog is None:
                options = fixed_options(definition)
                if options is None:
                    raise free_value_error(
                        field,
                        values_hint(
                            definition,
                            entities_enabled=settings.tracker_entities_enabled,
                        ),
                    )
                values = [
                    FieldValue(key=option, display=str(option)) for option in options
                ]
                return select_values(field, values, query, limit)

        values = await catalog_values(app, catalog, field, queue, issue_type, auth)
        return select_values(field, values, query, limit)

    @mcp.tool(
        title="Get Statuses",
        description="Get all statuses available in Yandex Tracker that can be used in issues",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def get_statuses(
        ctx: Context[AppContext],
    ) -> list[Status]:
        return await ctx.request_context.lifespan_context.fields.get_statuses(
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Issue Types",
        description="Get all issue types available in Yandex Tracker that can be used when creating or updating issues",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def get_issue_types(
        ctx: Context[AppContext],
    ) -> list[IssueType]:
        return await ctx.request_context.lifespan_context.fields.get_issue_types(
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Priorities",
        description="Get the issue priority levels of Yandex Tracker - trivial, minor, "
        "normal, critical, blocker and whatever else the organization configured - "
        "with the `id` and `key` that `issue_create` and `issue_update` accept in "
        "`priority`. The list is organization-wide: a queue may still reject a "
        "priority it does not use.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def get_priorities(
        ctx: Context[AppContext],
    ) -> list[Priority]:
        return await ctx.request_context.lifespan_context.fields.get_priorities(
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Resolutions",
        description="Get all resolutions available in Yandex Tracker that can be used when closing issues",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def get_resolutions(
        ctx: Context[AppContext],
    ) -> list[Resolution]:
        return await ctx.request_context.lifespan_context.fields.get_resolutions(
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Issue URL",
        description="Get a Yandex Tracker issue url by its id",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_url(
        issue_id: IssueID,
    ) -> str:
        return f"https://tracker.yandex.ru/{issue_id}"
