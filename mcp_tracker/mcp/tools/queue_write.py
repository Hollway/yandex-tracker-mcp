"""Queue write MCP tools (conditionally registered based on read-only mode)."""

import datetime
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import (
    MacroBodyParam,
    MacroIDParam,
    MacroIssueUpdateParam,
    QueueID,
    QueueIssueTypeParam,
    TriggerActionsParam,
    TriggerActionsUpdateParam,
    TriggerActiveParam,
    TriggerConditionsParam,
    TriggerIDParam,
    TriggerNameParam,
    WorkflowID,
)
from mcp_tracker.mcp.tools._access import (
    check_queue_access,
    check_version_access,
    queue_checks_needed,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import (
    FieldClearConflict,
    MacroEmptyUpdate,
    TriggerEmptyUpdate,
)
from mcp_tracker.tracker.proto.types.queue_automation import (
    QueueAutoaction,
    QueueIssueTypeConfigInput,
    QueueMacro,
)
from mcp_tracker.tracker.proto.types.queues import (
    Queue,
    QueueIssueTypeConfig,
    QueueTrigger,
    QueueVersion,
)
from mcp_tracker.tracker.proto.types.workflows import Workflow, WorkflowAction


def register_queue_write_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register queue write tools (not registered in read-only mode)."""

    @mcp.tool(
        title="Create Queue Version",
        description="Create a new version in a Yandex Tracker queue.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_create_version(
        ctx: Context[AppContext],
        queue_id: QueueID,
        name: Annotated[str, Field(description="Version name")],
        description: Annotated[
            str | None,
            Field(description="Optional version description"),
        ] = None,
        start_date: Annotated[
            datetime.date | None,
            Field(description="Optional version start date in YYYY-MM-DD format"),
        ] = None,
        due_date: Annotated[
            datetime.date | None,
            Field(description="Optional version due date in YYYY-MM-DD format"),
        ] = None,
    ) -> QueueVersion:
        check_queue_access(settings, queue_id, write=True)
        return await ctx.request_context.lifespan_context.queues.queue_create_version(
            queue_id,
            name=name,
            description=description,
            start_date=start_date,
            due_date=due_date,
            auth=get_yandex_auth(ctx),
        )

    VersionIDParam = Annotated[
        int, Field(description="Version `id` from queue_get_versions.")
    ]

    @mcp.tool(
        title="Update Queue Version",
        description="Rename a version of a Yandex Tracker queue or change its "
        "description or dates. Only the arguments passed change.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_update_version(
        ctx: Context[AppContext],
        version_id: VersionIDParam,
        name: Annotated[str | None, Field(description="New name.")] = None,
        description: Annotated[
            str | None, Field(description="New description.")
        ] = None,
        start_date: Annotated[
            datetime.date | None, Field(description="New start date, YYYY-MM-DD.")
        ] = None,
        due_date: Annotated[
            datetime.date | None, Field(description="New due date, YYYY-MM-DD.")
        ] = None,
    ) -> QueueVersion:
        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)

        # The id names no queue: read the version for it only when there is a
        # restriction to check.
        if queue_checks_needed(settings, write=True):
            current = await queues.queue_get_version(version_id, auth=auth)
            check_version_access(settings, current, write=True)

        return await queues.queue_update_version(
            version_id,
            name=name,
            description=description,
            start_date=start_date,
            due_date=due_date,
            auth=auth,
        )

    @mcp.tool(
        title="Delete Queue Version",
        description="Permanently delete a version of a Yandex Tracker queue. Issues "
        "that had it in their fix or affected versions lose it.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def queue_delete_version(
        ctx: Context[AppContext],
        version_id: VersionIDParam,
    ) -> None:
        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)

        if queue_checks_needed(settings, write=True):
            current = await queues.queue_get_version(version_id, auth=auth)
            check_version_access(settings, current, write=True)

        await queues.queue_delete_version(version_id, auth=auth)

    @mcp.tool(
        title="Create Queue Trigger",
        description="Create an automation trigger in a Yandex Tracker queue "
        "('триггер'): when its conditions hold for an issue event, its actions run "
        "(change status or fields, comment, move, checklist, HTTP request, create "
        "an issue). It fires on real issues as soon as it is active.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_create_trigger(
        ctx: Context[AppContext],
        queue_id: QueueID,
        name: TriggerNameParam,
        actions: TriggerActionsParam,
        conditions: TriggerConditionsParam = None,
        active: TriggerActiveParam = None,
    ) -> QueueTrigger:
        check_queue_access(settings, queue_id, write=True)
        return await ctx.request_context.lifespan_context.queues.queue_create_trigger(
            queue_id,
            name=name,
            actions=actions,
            conditions=conditions,
            active=active,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Queue Trigger",
        description="Change an automation trigger of a Yandex Tracker queue "
        "('триггер'): rename it, replace its actions or conditions, move it in the "
        "order, or switch it off with active=false - the API has no trigger "
        "delete. Only the arguments passed change.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_update_trigger(
        ctx: Context[AppContext],
        queue_id: QueueID,
        trigger_id: TriggerIDParam,
        name: Annotated[str | None, Field(description="New trigger name.")] = None,
        actions: TriggerActionsUpdateParam = None,
        conditions: TriggerConditionsParam = None,
        active: TriggerActiveParam = None,
        before: Annotated[
            int | None,
            Field(description="Id of the trigger to place this one before."),
        ] = None,
        version: Annotated[
            int | None,
            Field(
                description="The trigger's `version` from queue_get_trigger, to "
                "refuse the change if it was edited since; omitted, the current "
                "version is read and used."
            ),
        ] = None,
    ) -> QueueTrigger:
        check_queue_access(settings, queue_id, write=True)
        if (name, actions, conditions, active, before) == (None,) * 5:
            raise TriggerEmptyUpdate()

        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)
        if version is None:
            current = await queues.queue_get_trigger(queue_id, trigger_id, auth=auth)
            if current.version is None:
                raise TrackerError(
                    f"Trigger `{trigger_id}` came back without a `version`; pass "
                    f"it explicitly."
                )
            version = current.version

        return await queues.queue_update_trigger(
            queue_id,
            trigger_id,
            version=version,
            name=name,
            actions=actions,
            conditions=conditions,
            active=active,
            before=before,
            auth=auth,
        )

    @mcp.tool(
        title="Create Queue Autoaction",
        description="Create an autoaction in a Yandex Tracker queue "
        "('автодействие'): on a schedule, its actions run on every issue its "
        "filter or query selects. Pass `filter` or `query`. It changes real issues "
        "from its first launch.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_create_autoaction(
        ctx: Context[AppContext],
        queue_id: QueueID,
        name: Annotated[str, Field(description="Autoaction name.")],
        actions: Annotated[
            list[dict[str, Any]],
            Field(
                description="What to do with each selected issue, as trigger "
                'actions: {"type": "Transition", "status": {"key": "needInfo"}}, '
                '{"type": "Update", "update": {"priority": {"set": "critical"}}}, '
                '"CreateComment", "Webhook", "CalculateFormula".'
            ),
        ],
        filter: Annotated[
            dict[str, Any] | None,
            Field(
                description="Issues to act on, as field key -> accepted values, "
                'e.g. {"status": ["inProgress"], "priority": ["critical"]}.'
            ),
        ] = None,
        query: Annotated[
            str | None,
            Field(
                description="Issues to act on, as a query in the Tracker query "
                'language, e.g. \'"Status": "In progress"\'.'
            ),
        ] = None,
        active: Annotated[
            bool | None, Field(description="false creates it switched off.")
        ] = None,
        enable_notifications: Annotated[
            bool | None,
            Field(description="Whether its changes send notifications."),
        ] = None,
        interval_millis: Annotated[
            int | None,
            Field(
                description="How often it runs, in milliseconds; hourly "
                "(3600000) when omitted.",
                ge=1,
            ),
        ] = None,
        calendar_id: Annotated[
            int | None,
            Field(description="Id of the work schedule it runs within."),
        ] = None,
    ) -> QueueAutoaction:
        check_queue_access(settings, queue_id, write=True)
        if filter is None and query is None:
            raise TrackerError(
                "An autoaction needs `filter` or `query` to select the issues it "
                "acts on."
            )
        return (
            await ctx.request_context.lifespan_context.queues.queue_create_autoaction(
                queue_id,
                name=name,
                actions=actions,
                filter=filter,
                query=query,
                active=active,
                enable_notifications=enable_notifications,
                interval_millis=interval_millis,
                calendar_id=calendar_id,
                auth=get_yandex_auth(ctx),
            )
        )

    @mcp.tool(
        title="Create Queue Macro",
        description="Create a macro in a Yandex Tracker queue ('макрос'): a "
        "comment and field changes a user applies to an issue in one click.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_create_macro(
        ctx: Context[AppContext],
        queue_id: QueueID,
        name: Annotated[str, Field(description="Macro name.")],
        body: MacroBodyParam = None,
        issue_update: MacroIssueUpdateParam = None,
    ) -> QueueMacro:
        check_queue_access(settings, queue_id, write=True)
        return await ctx.request_context.lifespan_context.queues.queue_create_macro(
            queue_id,
            name=name,
            body=body,
            issue_update=issue_update,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Queue Macro",
        description="Change a macro of a Yandex Tracker queue ('макрос'): its "
        "name, the comment it posts or the field changes it makes. Only the "
        "arguments passed change; `issue_update` replaces all the field changes.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_update_macro(
        ctx: Context[AppContext],
        queue_id: QueueID,
        macro_id: MacroIDParam,
        name: Annotated[str | None, Field(description="New macro name.")] = None,
        body: MacroBodyParam = None,
        issue_update: MacroIssueUpdateParam = None,
        clear_body: Annotated[
            bool, Field(description="Remove the comment the macro posts.")
        ] = False,
    ) -> QueueMacro:
        check_queue_access(settings, queue_id, write=True)
        if clear_body and body is not None:
            raise FieldClearConflict("body")
        if name is None and body is None and issue_update is None and not clear_body:
            raise MacroEmptyUpdate()

        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)
        # The reference lists `name` as required on the update too, so an
        # update that keeps the name sends the current one.
        if name is None:
            current = await queues.queue_get_macro(queue_id, macro_id, auth=auth)
            if current.name is None:
                raise TrackerError(
                    f"Macro `{macro_id}` came back without a name; pass `name`."
                )
            name = current.name

        return await queues.queue_update_macro(
            queue_id,
            macro_id,
            name=name,
            body=body,
            issue_update=issue_update,
            clear_body=clear_body,
            auth=auth,
        )

    @mcp.tool(
        title="Delete Queue Macro",
        description="Permanently delete a macro of a Yandex Tracker queue "
        "('макрос'). Issues it was applied to keep their changes.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def queue_delete_macro(
        ctx: Context[AppContext],
        queue_id: QueueID,
        macro_id: MacroIDParam,
    ) -> None:
        check_queue_access(settings, queue_id, write=True)
        await ctx.request_context.lifespan_context.queues.queue_delete_macro(
            queue_id, macro_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Create Queue",
        description="Create a Yandex Tracker queue ('очередь') with its owner, "
        "default issue type and priority, and the issue types it allows with "
        "their workflow and resolutions. Needs queue-creation rights; a key "
        "outside the server's queue allow-list is refused.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_create(
        ctx: Context[AppContext],
        key: Annotated[
            str,
            Field(
                description="Queue key: Latin letters, unique in the organization, "
                "e.g. 'DESIGN'. It prefixes every issue key and cannot change."
            ),
        ],
        name: Annotated[str, Field(description="Queue name.")],
        lead: Annotated[str, Field(description="Owner's login or user id.")],
        default_type: Annotated[
            str,
            Field(
                description="Key of the issue type new issues get, e.g. 'task'; "
                "must be one of `issue_types_config`."
            ),
        ],
        default_priority: Annotated[
            str, Field(description="Priority key new issues get, e.g. 'normal'.")
        ],
        issue_types_config: Annotated[
            list[QueueIssueTypeConfigInput],
            Field(
                min_length=1,
                description="The issue types the queue allows, each with its "
                "workflow and resolutions.",
            ),
        ],
    ) -> Queue:
        check_queue_access(settings, key, write=True)
        return await ctx.request_context.lifespan_context.queues.queue_create(
            key=key,
            name=name,
            lead=lead,
            default_type=default_type,
            default_priority=default_priority,
            issue_types_config=issue_types_config,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Delete Queue",
        description="Delete a Yandex Tracker queue ('очередь') with all its "
        "issues. An administrator can bring it back with queue_restore.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def queue_delete(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> None:
        check_queue_access(settings, queue_id, write=True)
        await ctx.request_context.lifespan_context.queues.queue_delete(
            queue_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Restore Queue",
        description="Restore a deleted Yandex Tracker queue ('очередь') with its "
        "issues and return it. Only an organization administrator may.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def queue_restore(
        ctx: Context[AppContext],
        queue_id: QueueID,
    ) -> Queue:
        check_queue_access(settings, queue_id, write=True)
        return await ctx.request_context.lifespan_context.queues.queue_restore(
            queue_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Set Queue Issue Type Workflow",
        description="Add an issue type to a Yandex Tracker queue or change the "
        "workflow ('рабочий процесс') it follows. Existing issues of the type "
        "move to the new workflow and may sit in a status it lacks - the UI asks "
        "for a status mapping, the API was not tried with one.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def queue_set_issue_type_workflow(
        ctx: Context[AppContext],
        queue_id: QueueID,
        issue_type: QueueIssueTypeParam,
        workflow_id: WorkflowID,
        resolutions: Annotated[
            list[str] | None,
            Field(
                description="Resolution keys the type can close with. Omitted: "
                "the type keeps its own, a new type gets those the workflow's "
                "transitions set. Tracker refuses a list missing one of those."
            ),
        ] = None,
        make_default: Annotated[
            bool, Field(description="Also make it the queue's default issue type.")
        ] = False,
    ) -> Queue:
        check_queue_access(settings, queue_id, write=True)
        context = ctx.request_context.lifespan_context
        auth = get_yandex_auth(ctx)

        queue = await context.queues.queue_get_fresh(
            queue_id, expand=["issueTypesConfig"], auth=auth
        )
        config = _config_inputs(queue_id, queue.issueTypesConfig or [])
        existing = next((c for c in config if c.issue_type == issue_type), None)

        if resolutions is None:
            if existing is not None:
                resolutions = list(existing.resolutions)
            else:
                workflow = await context.workflows.workflow_get(workflow_id, auth=auth)
                resolutions = _workflow_resolutions(workflow) or ["fixed"]

        entry = QueueIssueTypeConfigInput(
            issue_type=issue_type, workflow=workflow_id, resolutions=resolutions
        )
        if existing is None:
            config.append(entry)
        else:
            config = [entry if c is existing else c for c in config]

        return await context.queues.queue_update_issue_types_config(
            queue_id,
            issue_types_config=config,
            default_type=issue_type if make_default else None,
            auth=auth,
        )

    @mcp.tool(
        title="Remove Queue Issue Type",
        description="Remove an issue type from a Yandex Tracker queue, so new "
        "issues of it can no longer be created there. The queue's default type "
        "is refused unless `new_default_type` names one that stays.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def queue_remove_issue_type(
        ctx: Context[AppContext],
        queue_id: QueueID,
        issue_type: QueueIssueTypeParam,
        new_default_type: Annotated[
            str | None,
            Field(
                description="Key of a remaining issue type to make the default; "
                "required when removing the current default."
            ),
        ] = None,
    ) -> Queue:
        check_queue_access(settings, queue_id, write=True)
        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)

        queue = await queues.queue_get_fresh(
            queue_id, expand=["issueTypesConfig"], auth=auth
        )
        config = _config_inputs(queue_id, queue.issueTypesConfig or [])
        keys = [c.issue_type for c in config]
        if issue_type not in keys:
            raise TrackerError(
                f"Queue `{queue_id}` has no issue type `{issue_type}`; its types "
                f"are {keys}."
            )

        remaining = [c for c in config if c.issue_type != issue_type]
        default = queue.defaultType.key if queue.defaultType is not None else None
        if new_default_type is not None:
            if new_default_type not in {c.issue_type for c in remaining}:
                raise TrackerError(
                    f"`new_default_type` must be one of the types that stay: "
                    f"{[c.issue_type for c in remaining]}."
                )
        elif default is None or default == issue_type:
            raise TrackerError(
                f"`{issue_type}` is the default issue type of queue `{queue_id}`: "
                f"pass `new_default_type`, one of "
                f"{[c.issue_type for c in remaining]}."
            )

        return await queues.queue_update_issue_types_config(
            queue_id,
            issue_types_config=remaining,
            default_type=new_default_type,
            auth=auth,
        )


def _config_inputs(
    queue_id: str, config: list[QueueIssueTypeConfig]
) -> list[QueueIssueTypeConfigInput]:
    """The queue's `issueTypesConfig` in the form the PATCH sends back.

    The PATCH replaces the whole list, so an entry that cannot be rebuilt would
    be dropped - such a queue is refused rather than half-written.
    """
    inputs: list[QueueIssueTypeConfigInput] = []
    for item in config:
        type_key = item.issueType.key if item.issueType is not None else None
        workflow = item.workflow.id if item.workflow is not None else None
        if type_key is None or workflow is None:
            raise TrackerError(
                f"An issue type of queue `{queue_id}` came back without its key or "
                f"workflow, so the list cannot be written back safely; refusing."
            )
        inputs.append(
            QueueIssueTypeConfigInput(
                issue_type=type_key,
                workflow=workflow,
                resolutions=[r.key for r in item.resolutions or []],
            )
        )
    return inputs


def _workflow_resolutions(workflow: Workflow) -> list[str]:
    """The resolution keys a workflow's transitions set, in order of appearance."""
    actions: list[WorkflowAction] = []
    if workflow.initial_action is not None:
        actions.append(workflow.initial_action)
    for step in workflow.steps:
        actions.extend(step.actions or [])
        if step.meta_action is not None:
            actions.append(step.meta_action)

    keys: list[str] = []
    for action in actions:
        for function in action.post_functions or []:
            if function.get("type") != "SetResolutionFunction":
                continue
            resolution = function.get("resolution")
            key = resolution.get("key") if isinstance(resolution, dict) else None
            if isinstance(key, str) and key not in keys:
                keys.append(key)
    return keys
