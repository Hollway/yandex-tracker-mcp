"""Queue-related MCP tools (read-only)."""

import asyncio
import datetime
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import (
    AutoactionIDParam,
    LocalFieldKey,
    MacroIDParam,
    PageOrAllParam,
    PerPageParam,
    QueueID,
    TriggerIDParam,
)
from mcp_tracker.mcp.tools._access import check_queue_access, is_queue_allowed
from mcp_tracker.mcp.tools._ai_access import is_ai_restricted
from mcp_tracker.mcp.tools._pagination import collect_pages
from mcp_tracker.mcp.utils import get_yandex_auth, set_non_needed_fields_null
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.fields import GlobalField, LocalField
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from mcp_tracker.tracker.proto.types.queue_automation import (
    QueueAutoaction,
    QueueAutoactionRun,
    QueueAutoactionRunIssue,
    QueueMacro,
    QueueTriggerLog,
)
from mcp_tracker.tracker.proto.types.queues import (
    Queue,
    QueueExpandOption,
    QueueFieldsEnum,
    QueueTrigger,
    QueueVersion,
)
from mcp_tracker.tracker.proto.types.refs import IssueTypeReference

# `expand` sections that are lists, and so can meaningfully come back empty.
EXPAND_SECTIONS = frozenset(
    {"projects", "components", "versions", "types", "workflows", "fields"}
)


def register_queue_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register queue-related tools (all read-only)."""

    @mcp.tool(
        title="Get All Queues",
        description="Find all Yandex Tracker queues available to the user (a queue is "
        "a project in some sense). `page` defaults to None and fetches ALL pages; pass "
        "a page number only when the result does not fit the context window.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queues_get_all(
        ctx: Context[AppContext, Request],
        fields: Annotated[
            list[QueueFieldsEnum] | None,
            Field(
                description="Fields to include in the response; omitting returns ALL "
                "of them (unlike project_find/portfolio_find/goal_find, which default "
                "to a small subset). key and name are usually enough.",
            ),
        ] = None,
        page: PageOrAllParam = None,
        per_page: PerPageParam = 100,
    ) -> PaginatedResult[Queue]:
        def allowed(queues: list[Queue]) -> list[Queue]:
            return [
                queue
                for queue in queues
                if queue.key is not None and is_queue_allowed(settings, queue.key)
            ]

        result = await collect_pages(
            lambda current_page: (
                ctx.request_context.lifespan_context.queues.queues_list(
                    per_page=per_page,
                    page=current_page,
                    auth=get_yandex_auth(ctx),
                )
            ),
            page=page,
            per_page=per_page,
            visible=allowed,
            restricted=bool(settings.tracker_limit_queues),
        )

        if fields is not None:
            set_non_needed_fields_null(result.values, {f.name for f in fields})

        return result

    @mcp.tool(
        title="Get Queue Local Field",
        description="Get one local field ('локальное поле') of a Yandex Tracker "
        "queue by its key. An issue write names the field by the `id` this "
        "returns ('<hash>--<key>'), not by the key.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_local_field(
        ctx: Context[AppContext],
        queue_id: QueueID,
        field_key: LocalFieldKey,
    ) -> LocalField:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queue_get_local_field(
            queue_id, field_key, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Queue Tags",
        description="Get all tags for a specific Yandex Tracker queue",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_tags(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> list[str]:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queues_get_tags(
            queue_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Queue Triggers",
        description="Get the automation triggers of a Yandex Tracker queue "
        "('триггеры'): conditions and actions, e.g. to explain why an issue changed "
        "status or assignee by itself - issue_get_changelog names the trigger that "
        "fired. Webhook credentials and headers are left out.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_triggers(
        ctx: Context[AppContext],
        queue_id: QueueID,
        active_only: Annotated[
            bool,
            Field(description="Leave out the triggers that are switched off."),
        ] = False,
    ) -> list[QueueTrigger]:
        check_queue_access(settings, queue_id)
        triggers = (
            await ctx.request_context.lifespan_context.queues.queues_get_triggers(
                queue_id,
                auth=get_yandex_auth(ctx),
            )
        )
        if active_only:
            triggers = [t for t in triggers if t.active is not False]
        return triggers

    @mcp.tool(
        title="Get Queue Versions",
        description="Get all versions for a specific Yandex Tracker queue",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_versions(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> list[QueueVersion]:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queues_get_versions(
            queue_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Queue Components",
        description="Get the components (in russian - 'компоненты') of a Yandex "
        "Tracker queue with lead, auto-assign flag and `version`. "
        "`queue_get_metadata` with expand=['components'] names them only (id and "
        "name); the id is what `issue_create` / `issue_update` take in `components`.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_components(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> list[Component]:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queues_get_components(
            queue_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Queue Workflows",
        description="Get the workflows (in russian - 'рабочие процессы') a Yandex "
        "Tracker queue runs: workflow id -> the issue types that follow it. "
        "`workflow_get` reads a workflow's statuses and transitions.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_workflows(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> dict[str, list[IssueTypeReference]]:
        check_queue_access(settings, queue_id)
        return (
            await ctx.request_context.lifespan_context.workflows.queues_get_workflows(
                queue_id,
                auth=get_yandex_auth(ctx),
            )
        )

    @mcp.tool(
        title="Get Queue Fields",
        description="Get the fields configured on a Yandex Tracker queue (in russian - "
        "'поля очереди'), its local ones included; `schema.required` marks the "
        "mandatory ones. Not the whole registry: system fields such as `parent` or "
        "`estimation` are settable without appearing here, and `get_global_fields` "
        "lists every organization field.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_fields(
        ctx: Context[AppContext],
        queue_id: QueueID,
        include_local_fields: Annotated[
            bool,
            Field(
                description="Whether to include queue-specific local fields in the response. "
                "When True, makes parallel requests to get both global and local fields."
            ),
        ] = True,
    ) -> list[GlobalField]:
        check_queue_access(settings, queue_id)

        auth = get_yandex_auth(ctx)
        queues = ctx.request_context.lifespan_context.queues

        if not include_local_fields:
            return await queues.queues_get_fields(queue_id, auth=auth)

        async with asyncio.TaskGroup() as tg:
            global_fields_task = tg.create_task(
                queues.queues_get_fields(queue_id, auth=auth)
            )
            local_fields_task = tg.create_task(
                queues.queues_get_local_fields(queue_id, auth=auth)
            )
        return global_fields_task.result() + local_fields_task.result()

    @mcp.tool(
        title="Get Queue Metadata",
        description="Get detailed metadata about a specific Yandex Tracker queue: "
        "name, description, default type and priority, plus the sections named in "
        "`expand` (issue types with their resolutions, workflows, team, ...). Use "
        "expand=['issueTypesConfig'] for the resolutions `issue_close` needs.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_metadata(
        ctx: Context[AppContext],
        queue_id: QueueID,
        expand: Annotated[
            list[QueueExpandOption] | None,
            Field(
                description="Optional list of fields to expand in the response. "
                "Available options: 'all', 'projects', 'components', 'versions', 'types', "
                "'team', 'workflows', 'fields', 'issueTypesConfig'. "
                "Use 'issueTypesConfig' to get available resolutions for each issue type. "
                "A requested section that the queue has nothing in comes back as an empty list."
            ),
        ] = None,
    ) -> Queue:
        check_queue_access(settings, queue_id)
        queue = await ctx.request_context.lifespan_context.queues.queue_get(
            queue_id,
            expand=expand,
            auth=get_yandex_auth(ctx),
        )

        # Tracker omits an expand section when the queue has nothing in it, which
        # reads the same as "expand did not work". Answer with an empty list so
        # the caller can tell the two apart.
        for option in expand or []:
            if option not in EXPAND_SECTIONS:
                continue
            if getattr(queue, option, None) is None:
                setattr(queue, option, [])

        return queue

    @mcp.tool(
        title="Get Queue Trigger",
        description="Get one automation trigger of a Yandex Tracker queue "
        "('триггер') with its conditions, actions and current `version`, which "
        "queue_update_trigger takes. Webhook credentials and headers are left out.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_trigger(
        ctx: Context[AppContext],
        queue_id: QueueID,
        trigger_id: TriggerIDParam,
    ) -> QueueTrigger:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queue_get_trigger(
            queue_id, trigger_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Queue Trigger Logs",
        description="Get the run log of a Yandex Tracker queue trigger's HTTP "
        "request (Webhook) actions: when it ran, for which issue, the request "
        "sent and the status code back. Only Webhook actions are logged; the "
        "latest 10 runs unless `limit` says otherwise.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_trigger_logs(
        ctx: Context[AppContext],
        queue_id: QueueID,
        trigger_id: TriggerIDParam,
        issue_id: Annotated[
            str | None,
            Field(description="Only the runs for this issue, e.g. 'QUEUE-123'."),
        ] = None,
        limit: Annotated[
            int | None,
            Field(
                description="How many runs, at most 100; 10 when omitted.",
                ge=1,
                le=100,
            ),
        ] = None,
        created_from: Annotated[
            datetime.datetime | None,
            Field(description="Only runs that started at or after this time."),
        ] = None,
        created_to: Annotated[
            datetime.datetime | None,
            Field(description="Only runs that started at or before this time."),
        ] = None,
    ) -> list[QueueTriggerLog]:
        check_queue_access(settings, queue_id)
        queues = ctx.request_context.lifespan_context.queues
        logs = await queues.queue_get_trigger_logs(
            queue_id,
            trigger_id,
            issue_id=issue_id,
            limit=limit,
            created_from=created_from,
            created_to=created_to,
            auth=get_yandex_auth(ctx),
        )
        # A request body is rendered from the issue it ran for, so a queue that
        # forbids AI tools its issues' content does not get it handed out here.
        if logs and await is_ai_restricted(ctx, settings, queue_id):
            for log in logs:
                if log.request is not None:
                    log.request.pop("body", None)
        return logs

    @mcp.tool(
        title="Get Queue Autoactions",
        description="Get the autoactions of a Yandex Tracker queue ('автодействия'): "
        "scheduled actions on the issues a filter or query selects, with their "
        "interval and last launch.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_autoactions(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> list[QueueAutoaction]:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queues_get_autoactions(
            queue_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Queue Autoaction",
        description="Get one autoaction of a Yandex Tracker queue ('автодействие'): "
        "its filter or query, actions, interval, calendar and last launch.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_autoaction(
        ctx: Context[AppContext],
        queue_id: QueueID,
        autoaction_id: AutoactionIDParam,
    ) -> QueueAutoaction:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queue_get_autoaction(
            queue_id, autoaction_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Queue Autoaction Logs",
        description="Get the launches of a Yandex Tracker queue autoaction "
        "('автодействие') with how many issues each found and changed; with "
        "`run_id`, the issues of that one launch and how each went. Only "
        "autoactions that update issues are logged.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_autoaction_logs(
        ctx: Context[AppContext],
        queue_id: QueueID,
        autoaction_id: AutoactionIDParam,
        run_id: Annotated[
            str | None,
            Field(
                description="A launch `id` from a call without it; returns the "
                "issues of that launch instead of the list of launches."
            ),
        ] = None,
    ) -> list[QueueAutoactionRun] | list[QueueAutoactionRunIssue]:
        check_queue_access(settings, queue_id)
        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)
        if run_id is None:
            return await queues.queue_get_autoaction_runs(
                queue_id, autoaction_id, auth=auth
            )

        issues = await queues.queue_get_autoaction_run(
            queue_id, autoaction_id, run_id, auth=auth
        )
        # `display` is the issue's summary - content a queue that forbids AI
        # tools does not hand out.
        if issues and await is_ai_restricted(ctx, settings, queue_id):
            for row in issues:
                if row.issueReference is not None:
                    row.issueReference.display = None
        return issues

    @mcp.tool(
        title="Get Queue Macros",
        description="Get the macros of a Yandex Tracker queue ('макросы'): the "
        "comment each posts and the issue fields it changes when applied.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_macros(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> list[QueueMacro]:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queues_get_macros(
            queue_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Queue Macro",
        description="Get one macro of a Yandex Tracker queue ('макрос'): its name, "
        "the comment it posts and the issue fields it changes.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def queue_get_macro(
        ctx: Context[AppContext],
        queue_id: QueueID,
        macro_id: MacroIDParam,
    ) -> QueueMacro:
        check_queue_access(settings, queue_id)
        return await ctx.request_context.lifespan_context.queues.queue_get_macro(
            queue_id, macro_id, auth=get_yandex_auth(ctx)
        )
