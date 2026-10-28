"""Issue write MCP tools (conditionally registered based on read-only mode)."""

import datetime
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import (
    AcceptedElicitation,
    Context,
    Elicit,
    ElicitationResult,
    MCPServer,
    Resolve,
)
from mcp.types import ToolAnnotations
from mcp.types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import BaseModel, Field, create_model

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import (
    CommentReactionCommentIDParam,
    CommentReactionParam,
    IssueChecklistItemAssigneeParam,
    IssueChecklistItemCheckedParam,
    IssueChecklistItemClearAssigneeParam,
    IssueChecklistItemClearDeadlineParam,
    IssueChecklistItemDeadlineParam,
    IssueChecklistItemIDParam,
    IssueChecklistItemsParam,
    IssueChecklistItemTextParam,
    IssueComponentsParam,
    IssueComponentsUpdateParam,
    IssueFollowersParam,
    IssueFollowersUpdateParam,
    IssueID,
    IssueParentParam,
    IssueProjectParam,
    IssueSprintParam,
    IssueTagsParam,
    MarkupTypeParam,
)
from mcp_tracker.mcp.tools._access import (
    check_issue_access,
    check_issue_queue_access,
    check_queue_access,
    is_queue_allowed,
    queue_checks_needed,
    queue_of_key,
)
from mcp_tracker.mcp.tools._ai_access import (
    answer_hidden,
    hide_restricted_refs,
    restricted_issue,
)
from mcp_tracker.mcp.tools._files import (
    UploadFilenameParam,
    UploadFilePathParam,
    read_upload_file,
)
from mcp_tracker.mcp.tools._issue_access import check_issue
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.inputs import (
    ChecklistItemInput,
    IssuePriorityRef,
    IssueTypeRef,
)
from mcp_tracker.tracker.proto.types.issues import (
    BulkChange,
    BulkChangeFailure,
    BulkChangeReport,
    ChecklistItem,
    Issue,
    IssueAttachment,
    IssueComment,
    IssueLink,
    IssueLinkRelationship,
    IssueTransition,
    RemoteLink,
    Worklog,
)
from mcp_tracker.tracker.proto.types.templates import IssueTemplate


class IssueMoveOptions(BaseModel):
    """The boolean options of `issue_move`, as confirmed by the user."""

    notify: bool = Field(
        description="Notify users referenced in the issue's fields of the move.",
    )
    notify_author: bool = Field(
        description="Notify the issue author of the move.",
    )
    move_all_fields: bool = Field(
        description="Carry over versions, components and projects when matching "
        "ones exist in the target queue (otherwise they are cleared).",
    )
    initial_status: bool = Field(
        description="Reset the issue status to the initial value (use when the "
        "target queue has a different workflow).",
    )


def _prefilled(name: str, value: bool) -> tuple[type[bool], Any]:
    """A field definition for `create_model` seeded with the value the caller passed."""
    return (
        bool,
        Field(
            default=value, description=IssueMoveOptions.model_fields[name].description
        ),
    )


def _can_ask(ctx: Context[Any]) -> bool:
    """Whether the client can be asked a question: form elicitation, and a
    back-channel on a pre-2026-07-28 connection (see `confirm_move_options`)."""
    capabilities = ctx.client_capabilities
    elicitation = capabilities.elicitation if capabilities is not None else None
    supports_form = elicitation is not None and (
        elicitation.form is not None or elicitation.url is None
    )
    legacy = ctx.protocol_version not in MODERN_PROTOCOL_VERSIONS
    return supports_form and not (legacy and not ctx.session.can_send_request)


def _move_options_resolver(
    settings: Settings,
) -> Callable[..., Awaitable[IssueMoveOptions | Elicit[IssueMoveOptions]]]:
    """Build the resolver of `issue_move`'s `options` for the given settings.

    A resolver runs before the tool body, so the access checks are repeated here:
    an issue or queue the settings restrict is refused before the user is asked to
    confirm a move the body would reject anyway.
    """

    async def confirm_move_options(
        ctx: Context[AppContext],
        issue_id: str,
        queue: str,
        notify: bool,
        notify_author: bool,
        move_all_fields: bool,
        initial_status: bool,
    ) -> IssueMoveOptions | Elicit[IssueMoveOptions]:
        """Confirm the boolean options of `issue_move` with the user.

        When the client can be asked, the user is asked to confirm the options
        before the (irreversible) move. The form is seeded with the values passed
        by the caller so the user only adjusts what they need to. A client that
        cannot be asked gets those values without a round-trip - the SDK would
        otherwise answer the whole call with a JSON-RPC error, which is not a
        tool result the model can read:

        - no form elicitation: the SDK's own gate counts a bare `elicitation: {}`
          as form support and a url-only one as none, so the same rule is applied
          here - a url-only client returning `Elicit` would be refused with
          `MISSING_REQUIRED_CLIENT_CAPABILITY`;
        - a legacy (< 2026-07-28) connection without a back-channel: below
          2026-07-28 the question is a standalone server->client request, which
          the stateless / JSON-response streamable-http transport this server
          runs cannot deliver (`NoBackChannelError`). Modern connections carry
          the question in the tool result instead and are not affected.
        """
        await check_issue(ctx, settings, issue_id, write=True, ai=False)
        check_queue_access(settings, queue, write=True)

        if not _can_ask(ctx):
            return IssueMoveOptions(
                notify=notify,
                notify_author=notify_author,
                move_all_fields=move_all_fields,
                initial_status=initial_status,
            )

        schema = create_model(
            "IssueMoveOptions",
            __base__=IssueMoveOptions,
            notify=_prefilled("notify", notify),
            notify_author=_prefilled("notify_author", notify_author),
            move_all_fields=_prefilled("move_all_fields", move_all_fields),
            initial_status=_prefilled("initial_status", initial_status),
        )
        return Elicit(
            f"Confirm the options for moving issue {issue_id} to queue {queue}.",
            schema,
        )

    return confirm_move_options


def register_issue_write_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register issue write tools (not registered in read-only mode)."""

    @mcp.tool(
        title="Execute Issue Transition",
        description="Execute a status transition for a Yandex Tracker issue. Call "
        "`issue_get_transitions` first and pass one of the ids it returned - the API "
        "rejects anything else. Returns the transitions available in the new status.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_execute_transition(
        ctx: Context[AppContext],
        issue_id: IssueID,
        transition_id: Annotated[
            str,
            Field(
                description="The transition ID to execute. Must be one of the IDs returned by issue_get_transitions tool."
            ),
        ],
        comment: Annotated[
            str | None,
            Field(description="Optional comment to add when executing the transition."),
        ] = None,
        fields: Annotated[
            dict[str, str | int | list[str]] | None,
            Field(
                description="Optional dictionary of additional fields to set during the transition. "
                "Common fields include 'resolution' (e.g., 'fixed', 'wontFix') for closing issues, "
                "'assignee' for reassigning, etc."
            ),
        ] = None,
    ) -> list[IssueTransition]:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return (
            await ctx.request_context.lifespan_context.issues.issue_execute_transition(
                issue_id,
                transition_id,
                comment=comment,
                fields=fields,
                auth=get_yandex_auth(ctx),
            )
        )

    @mcp.tool(
        title="Close Issue",
        description="Close a Yandex Tracker issue with a resolution: finds a "
        "transition to a 'done' status and executes it. The resolution has to be one "
        "the issue's type allows - read the type with `issue_get`, then call "
        "`queue_get_metadata` with expand=['issueTypesConfig'] for the resolutions of "
        "that type. Returns the transitions available in the new (closed) status.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_close(
        ctx: Context[AppContext],
        issue_id: IssueID,
        resolution_id: Annotated[
            str,
            Field(
                description="The resolution ID to set when closing the issue. "
                "Must be one of the IDs returned by get_resolutions tool (e.g., 'fixed', 'wontFix', 'duplicate')."
            ),
        ],
        fields: Annotated[
            dict[str, str | int | list[str]] | None,
            Field(
                description="Optional dictionary of additional fields to set during the transition "
                "(e.g. 'assignee' for reassigning). Do NOT set 'resolution' here - use the dedicated "
                "resolution_id parameter instead."
            ),
        ] = None,
        comment: Annotated[
            str | None,
            Field(description="Optional comment to add when closing the issue."),
        ] = None,
    ) -> list[IssueTransition]:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return await ctx.request_context.lifespan_context.issues.issue_close(
            issue_id,
            resolution_id,
            comment=comment,
            fields=fields,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Create Issue",
        description="Create an issue (in russian - 'задача') in a Yandex Tracker "
        "queue, optionally from an issue template ('шаблон'), whose values and "
        "checklist fill what the arguments leave out. The returned `version` goes "
        "stale at once, as queue triggers bump it - re-read it with `issue_get`.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_create(
        ctx: Context[AppContext],
        queue: Annotated[
            str,
            Field(description="Queue key where to create the issue (e.g., 'MYQUEUE')"),
        ],
        summary: Annotated[
            str | None,
            Field(
                description="Issue title/summary; may be omitted only when the "
                "template sets one."
            ),
        ] = None,
        type: Annotated[
            IssueTypeRef | str | int | None,
            Field(
                description="Issue type: an object with 'id' (type ID) and/or 'key' "
                "(e.g., 'bug', 'task'), or the bare key/ID (from get_issue_types tool)."
            ),
        ] = None,
        description: Annotated[
            str | None, Field(description="Issue description (use markdown formatting)")
        ] = None,
        markup_type: MarkupTypeParam = "md",
        assignee: Annotated[
            str | int | None, Field(description="Assignee login or UID")
        ] = None,
        priority: Annotated[
            IssuePriorityRef | str | int | None,
            Field(
                description="Issue priority: an object with 'id' (priority ID) and/or 'key' "
                "(e.g., 'critical', 'normal'), or the bare key/ID (from get_priorities tool)."
            ),
        ] = None,
        parent: IssueParentParam = None,
        sprint: IssueSprintParam = None,
        followers: IssueFollowersParam = None,
        components: IssueComponentsParam = None,
        tags: IssueTagsParam = None,
        project: IssueProjectParam = None,
        fields: Annotated[
            dict[str, Any] | None,
            Field(
                description="Additional fields to set, for those without a dedicated "
                "parameter above. Field ids come from `queue_get_fields` "
                "(schema.required=true marks the mandatory ones) or "
                "`get_global_fields`, which also lists system fields such as `parent` "
                "or `estimation` that the queue listing may omit. Keys are Tracker's "
                "own camelCase ids, e.g. 'storyPoints'. An entry here overrides the "
                "dedicated parameter of the same name. Values are sent as-is: "
                "reference fields want numeric IDs as numbers or {'id': ...} objects, "
                "since a bare string may be read as a name."
            ),
        ] = None,
        template_id: Annotated[
            str | None,
            Field(
                description="Issue template id from `issue_templates_get_all`. Its "
                "field values fill what is not passed here, and its checklist is "
                "added to the new issue; it must belong to this queue or to none."
            ),
        ] = None,
    ) -> Issue:
        check_queue_access(settings, queue, write=True)
        app = ctx.request_context.lifespan_context
        auth = get_yandex_auth(ctx)

        checklist: list[ChecklistItemInput] = []
        if template_id is not None:
            template = await app.templates.get_issue_template(template_id, auth=auth)
            template_queue = template.queue.key if template.queue else None
            if template_queue is not None and template_queue.upper() != queue.upper():
                raise TrackerError(
                    f"Issue template `{template_id}` belongs to another queue; "
                    f"use one of queue `{queue}` or one bound to no queue."
                )
            # An argument passed here wins over the template's value for the field.
            passed = {
                "summary": summary,
                "type": type,
                "description": description,
                "assignee": assignee,
                "priority": priority,
                "parent": parent,
                "sprint": sprint,
                "followers": followers,
                "components": components,
                "tags": tags,
                "project": project,
            }
            prefilled = {
                key: _template_value(value)
                for key, value in (template.fieldTemplates or {}).items()
                if passed.get(key) is None and key not in (fields or {})
            }
            if summary is None and isinstance(prefilled.get("summary"), str):
                summary = prefilled.pop("summary")
            fields = {**prefilled, **(fields or {})} or None
            checklist = _template_checklist(template)

        if summary is None:
            raise TrackerError(
                "Pass `summary`, or a `template_id` whose template sets one."
            )

        issue = await app.issues.issue_create(
            queue=queue,
            summary=summary,
            type=type,
            description=description,
            markup_type=markup_type,
            assignee=assignee,
            priority=priority,
            parent=parent,
            sprint=sprint,
            followers=followers,
            components=components,
            tags=tags,
            project=project,
            auth=auth,
            fields=fields,
        )
        if checklist and issue.key:
            # Tracker takes no checklist in the create body.
            await app.issues.issue_add_checklist_items(
                issue.key, items=checklist, auth=auth
            )
        return await _issue_answer(ctx, settings, issue)

    @mcp.tool(
        title="Update Issue",
        description="Update an existing Yandex Tracker issue. Only the parameters you "
        "pass change; the rest stay as they are. Use `queue_get_fields` to discover "
        "the queue's fields. `version` is optional optimistic locking - pass one read "
        "moments earlier with `issue_get`, never the one `issue_create` returned, "
        "since triggers bump it right after creation.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_update(
        ctx: Context[AppContext],
        issue_id: IssueID,
        summary: Annotated[
            str | None,
            Field(description="New issue title/summary"),
        ] = None,
        description: Annotated[
            str | None,
            Field(description="New issue description (use markdown formatting)"),
        ] = None,
        markup_type: MarkupTypeParam = "md",
        parent: IssueParentParam = None,
        sprint: IssueSprintParam = None,
        type: Annotated[
            IssueTypeRef | str | int | None,
            Field(
                description="Issue type. Object with 'id' (type ID) and/or 'key' (type key like 'bug', 'task'), "
                "or the bare key/ID. "
                "Use `queue_get_metadata` tool with expand=['issueTypesConfig'] to get available issue types in this queue."
            ),
        ] = None,
        priority: Annotated[
            IssuePriorityRef | str | int | None,
            Field(
                description="Issue priority. Object with 'id' (priority ID) and/or 'key' "
                "(priority key like 'critical', 'normal'), or the bare key/ID. "
                "Use get_priorities to find available priorities."
            ),
        ] = None,
        assignee: Annotated[
            str | int | None,
            Field(description="New assignee login or UID"),
        ] = None,
        followers: IssueFollowersUpdateParam = None,
        components: IssueComponentsUpdateParam = None,
        project: IssueProjectParam = None,
        tags: IssueTagsParam = None,
        version: Annotated[
            int | None,
            Field(
                description="Issue version for optimistic locking: the change lands "
                "only if this is the issue's current version, otherwise the call fails "
                "with an editing conflict. Read it with `issue_get` right before "
                "updating, or omit it to update whatever the latest version is. The "
                "version `issue_create` returned is not safe here - triggers bump it "
                "right after creation."
            ),
        ] = None,
        fields: Annotated[
            dict[str, Any] | None,
            Field(
                description="Additional fields to update, for those without a "
                "dedicated parameter above. Field ids come from `queue_get_fields` or "
                "`get_global_fields`, which also lists system fields such as `parent` "
                "or `estimation` that the queue listing may omit. Keys are Tracker's "
                "own camelCase ids, e.g. 'storyPoints'. An entry here overrides the "
                "dedicated parameter of the same name, which is how a field is "
                "cleared: pass null (e.g. {'assignee': null}), since a dedicated "
                "parameter left unset is simply not sent. Values are sent as-is: "
                "reference fields want numeric IDs as numbers or {'id': ...} objects, "
                "since a bare string may be read as a name."
            ),
        ] = None,
    ) -> Issue:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        issue = await ctx.request_context.lifespan_context.issues.issue_update(
            issue_id,
            summary=summary,
            description=description,
            markup_type=markup_type,
            parent=parent,
            sprint=sprint,
            type=type,
            priority=priority,
            assignee=assignee,
            followers=followers,
            components=components,
            project=project,
            tags=tags,
            version=version,
            auth=get_yandex_auth(ctx),
            fields=fields,
        )
        return await _issue_answer(ctx, settings, issue)

    @mcp.tool(
        title="Add Worklog",
        description="Add a worklog entry (log spent time) to a Yandex Tracker issue",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_add_worklog(
        ctx: Context[AppContext],
        issue_id: IssueID,
        duration: Annotated[
            str,
            Field(
                description="Time spent in ISO-8601 duration format (e.g., 'PT1H30M').",
            ),
        ],
        comment: Annotated[
            str | None,
            Field(description="Optional comment to add to the worklog entry."),
        ] = None,
        start: Annotated[
            datetime.datetime | None,
            Field(
                description="When the work started; omitted, now. "
                "If timezone is not provided, UTC is assumed."
            ),
        ] = None,
    ) -> Worklog:
        hidden = await check_issue(ctx, settings, issue_id, write=True)

        worklog = await ctx.request_context.lifespan_context.issues.issue_add_worklog(
            issue_id,
            duration=duration,
            comment=comment,
            start=start,
            auth=get_yandex_auth(ctx),
        )
        return await _worklog_answer(ctx, settings, worklog, hidden)

    @mcp.tool(
        title="Update Worklog",
        description="Update a worklog entry (spent time record) in a Yandex Tracker issue",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_update_worklog(
        ctx: Context[AppContext],
        issue_id: IssueID,
        worklog_id: Annotated[
            int,
            Field(description="Worklog entry ID (integer)."),
        ],
        duration: Annotated[
            str | None,
            Field(
                description="New time spent in ISO-8601 duration format (e.g., 'PT1H30M').",
            ),
        ] = None,
        comment: Annotated[
            str | None,
            Field(description="New comment for the worklog entry."),
        ] = None,
        start: Annotated[
            datetime.datetime | None,
            Field(
                description="New start datetime for the worklog. "
                "If timezone is not provided, UTC is assumed."
            ),
        ] = None,
    ) -> Worklog:
        hidden = await check_issue(ctx, settings, issue_id, write=True)

        worklog = (
            await ctx.request_context.lifespan_context.issues.issue_update_worklog(
                issue_id,
                worklog_id,
                duration=duration,
                comment=comment,
                start=start,
                auth=get_yandex_auth(ctx),
            )
        )
        return await _worklog_answer(ctx, settings, worklog, hidden)

    @mcp.tool(
        title="Delete Worklog",
        description="Delete a worklog entry (spent time record) from a Yandex Tracker issue",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_delete_worklog(
        ctx: Context[AppContext],
        issue_id: IssueID,
        worklog_id: Annotated[
            int,
            Field(description="Worklog entry ID (integer)."),
        ],
    ) -> None:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return await ctx.request_context.lifespan_context.issues.issue_delete_worklog(
            issue_id,
            worklog_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Add Issue Comment",
        description="Add a comment to a Yandex Tracker issue. There is no "
        "`template_id` parameter: check `comment_templates_get_all` (with `queue` set) "
        "first and copy the template's `template` text into `text` and its summonees "
        "into the parameters below. To mention or call people so they get notified, "
        "use `summonees` - '@login' in the text notifies nobody.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_add_comment(
        ctx: Context[AppContext],
        issue_id: IssueID,
        text: Annotated[
            str,
            Field(description="Comment text (markdown supported by Tracker)."),
        ],
        summonees: Annotated[
            list[str] | None,
            Field(
                description="Users to summon (logins or IDs): they are invited to the "
                "discussion and notified. This is the API way to 'mention/call' "
                "someone in a Yandex Tracker comment."
            ),
        ] = None,
        maillist_summonees: Annotated[
            list[str] | None,
            Field(
                description="Optional list of mailing lists to summon (emails). "
                "Example: ['team@example.com']."
            ),
        ] = None,
        markup_type: Annotated[
            str | None,
            Field(
                description="Optional markup type for comment text. Use 'md' for YFM (markdown)."
            ),
        ] = None,
        is_add_to_followers: Annotated[
            bool,
            Field(
                description="Whether to add the comment author to issue followers. Default: true."
            ),
        ] = True,
        attachment_ids: Annotated[
            list[str] | None,
            Field(
                description="Files to attach to the comment: ids of temporary "
                "attachments from `attachment_create`. An id from "
                "issue_get_attachments is an attachment of the issue, not one of these."
            ),
        ] = None,
    ) -> IssueComment:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return await ctx.request_context.lifespan_context.issues.issue_add_comment(
            issue_id,
            text=text,
            summonees=summonees,
            maillist_summonees=maillist_summonees,
            markup_type=markup_type,
            is_add_to_followers=is_add_to_followers,
            attachment_ids=attachment_ids,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Issue Comment",
        description="Update an existing comment in a Yandex Tracker issue. To mention "
        "or call people, use `summonees`, not '@login' in the text.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_update_comment(
        ctx: Context[AppContext],
        issue_id: IssueID,
        comment_id: Annotated[
            int,
            Field(description="Comment ID (integer)."),
        ],
        text: Annotated[
            str,
            Field(description="New comment text (markdown supported by Tracker)."),
        ],
        summonees: Annotated[
            list[str] | None,
            Field(
                description="Users to summon (logins or IDs): they are invited to the "
                "discussion and notified. This is the API way to 'mention/call' "
                "someone in a Yandex Tracker comment."
            ),
        ] = None,
        maillist_summonees: Annotated[
            list[str] | None,
            Field(
                description="Optional list of mailing lists to summon (emails). "
                "Example: ['team@example.com']."
            ),
        ] = None,
        markup_type: Annotated[
            str | None,
            Field(
                description="Optional markup type for comment text. Use 'md' for YFM (markdown)."
            ),
        ] = None,
    ) -> IssueComment:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return await ctx.request_context.lifespan_context.issues.issue_update_comment(
            issue_id,
            comment_id,
            text=text,
            summonees=summonees,
            maillist_summonees=maillist_summonees,
            markup_type=markup_type,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Move Issue to Another Queue",
        description="Move a Yandex Tracker issue to a different queue. "
        "The issue will receive a new key in the target queue (e.g., TASKS-1 → NEWQUEUE-42). "
        "Returns the updated issue with its new key and queue.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_move(
        ctx: Context[AppContext],
        issue_id: IssueID,
        queue: Annotated[
            str,
            Field(description="Target queue key (e.g., 'MYQUEUE')"),
        ],
        options: Annotated[
            ElicitationResult[IssueMoveOptions],
            Resolve(_move_options_resolver(settings)),
        ],
        notify: Annotated[
            bool,
            Field(
                description="Whether users referenced in the issue's fields are notified "
                "of the change."
            ),
        ] = True,
        notify_author: Annotated[
            bool,
            Field(description="Whether the issue author is notified of the change."),
        ] = False,
        move_all_fields: Annotated[
            bool,
            Field(
                description="Whether to carry over the issue's versions, components and "
                "projects when matching ones exist in the target queue. When false, those "
                "fields are cleared."
            ),
        ] = False,
        initial_status: Annotated[
            bool,
            Field(
                description="Whether to reset the issue status to the initial value. "
                "Set this to true when moving to a queue with a different workflow. "
            ),
        ] = False,
    ) -> Issue:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)
        check_queue_access(settings, queue, write=True)

        # `options` is resolved before the body runs: either the values the user
        # confirmed through elicitation, or the ones passed by the caller when the
        # client cannot be asked (see `_move_options_resolver`).
        if not isinstance(options, AcceptedElicitation):
            raise TrackerError(
                f"Move of issue `{issue_id}` to queue `{queue}` was cancelled by the user."
            )

        issue = await ctx.request_context.lifespan_context.issues.issue_move(
            issue_id,
            queue,
            notify=options.data.notify,
            notify_author=options.data.notify_author,
            move_all_fields=options.data.move_all_fields,
            initial_status=options.data.initial_status,
            auth=get_yandex_auth(ctx),
        )
        return await _issue_answer(ctx, settings, issue)

    @mcp.tool(
        title="Delete Issue Comment",
        description="Delete a comment from a Yandex Tracker issue",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_delete_comment(
        ctx: Context[AppContext],
        issue_id: IssueID,
        comment_id: Annotated[
            int,
            Field(description="Comment ID (integer)."),
        ],
    ) -> None:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return await ctx.request_context.lifespan_context.issues.issue_delete_comment(
            issue_id,
            comment_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Add Comment Reaction",
        description="Put a reaction (like, heart, fire, ...) on a comment of a "
        "Yandex Tracker issue ('реакция') and return the comment with its "
        "reactions. A reaction you already put there is refused.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_add_comment_reaction(
        ctx: Context[AppContext],
        issue_id: IssueID,
        comment_id: CommentReactionCommentIDParam,
        reaction: CommentReactionParam,
    ) -> IssueComment:
        hidden = await check_issue(ctx, settings, issue_id, write=True)
        comment = await ctx.request_context.lifespan_context.issues.issue_add_comment_reaction(
            issue_id, comment_id, reaction, auth=get_yandex_auth(ctx)
        )
        return _comment_answer(comment, hidden)

    @mcp.tool(
        title="Delete Comment Reaction",
        description="Take your reaction off a comment of a Yandex Tracker issue "
        "('реакция') and return the comment with the reactions left. A reaction "
        "that is not there is refused.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_delete_comment_reaction(
        ctx: Context[AppContext],
        issue_id: IssueID,
        comment_id: CommentReactionCommentIDParam,
        reaction: CommentReactionParam,
    ) -> IssueComment:
        hidden = await check_issue(ctx, settings, issue_id, write=True)
        comment = await ctx.request_context.lifespan_context.issues.issue_delete_comment_reaction(
            issue_id, comment_id, reaction, auth=get_yandex_auth(ctx)
        )
        return _comment_answer(comment, hidden)

    @mcp.tool(
        title="Add Issue Remote Link",
        description="Link a Yandex Tracker issue to an object in another "
        "application, e.g. a pull request or a document. `origin` is an "
        "application `id` from applications_get_all. Wiki pages cannot be linked "
        "this way: Tracker refuses them with 403 for want of an X-Iam-Token header.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_add_remote_link(
        ctx: Context[AppContext],
        issue_id: IssueID,
        origin: Annotated[
            str,
            Field(description="Application `id` from applications_get_all."),
        ],
        key: Annotated[
            str,
            Field(description="The object's key in that application."),
        ],
        backlink: Annotated[
            bool,
            Field(description="Also create the mirror link in the other application."),
        ] = False,
    ) -> RemoteLink:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return await ctx.request_context.lifespan_context.issues.issue_add_remote_link(
            issue_id,
            origin=origin,
            key=key,
            backlink=backlink,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Delete Issue Remote Link",
        description="Delete a link from a Yandex Tracker issue to an object in "
        "another application; take the id from issue_get_remote_links.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def issue_delete_remote_link(
        ctx: Context[AppContext],
        issue_id: IssueID,
        link_id: Annotated[
            int,
            Field(description="Link `id` from issue_get_remote_links."),
        ],
    ) -> None:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        await ctx.request_context.lifespan_context.issues.issue_delete_remote_link(
            issue_id, link_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Delete Issue Attachment",
        description="Permanently delete a file attached to a Yandex Tracker issue "
        "('вложение'). It cannot be restored; take the id from "
        "issue_get_attachments.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def issue_delete_attachment(
        ctx: Context[AppContext],
        issue_id: IssueID,
        attachment_id: Annotated[
            str,
            Field(description="Attachment `id` from issue_get_attachments."),
        ],
    ) -> None:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        await ctx.request_context.lifespan_context.issues.issue_delete_attachment(
            issue_id, attachment_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Add Issue Link",
        description="Create a link between a Yandex Tracker issue and another issue. "
        "`relationship` reads from the current issue: 'depends on' means issue_id "
        "depends on the linked issue, 'is dependent by' is the reverse, 'relates' is a "
        "plain connection.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_add_link(
        ctx: Context[AppContext],
        issue_id: IssueID,
        relationship: Annotated[
            IssueLinkRelationship,
            Field(
                description="Link type describing how the current issue (issue_id) "
                "relates to the linked issue. 'is epic of'/'has epic' apply only to "
                "Epic-type issues."
            ),
        ],
        issue: Annotated[
            str,
            Field(description="ID or key of the issue to link to, e.g. 'TEST-123'."),
        ],
    ) -> IssueLink:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        link = await ctx.request_context.lifespan_context.issues.issue_add_link(
            issue_id,
            relationship=relationship,
            issue=issue,
            auth=get_yandex_auth(ctx),
        )
        await hide_restricted_refs(ctx, settings, link)
        return link

    @mcp.tool(
        title="Delete Issue Link",
        description="Delete a link between a Yandex Tracker issue and another issue. "
        "Use issue_get_links to retrieve the link IDs for an issue.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_delete_link(
        ctx: Context[AppContext],
        issue_id: IssueID,
        link_id: Annotated[
            int,
            Field(description="Link ID (integer) as returned by issue_get_links."),
        ],
    ) -> None:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        return await ctx.request_context.lifespan_context.issues.issue_delete_link(
            issue_id,
            link_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Add Issue Checklist Items",
        description="Add one or more items to the checklist of a Yandex Tracker issue. "
        "The checklist is created if the issue does not have one yet, and items are "
        "appended in the order given. Returns the issue's checklist after the items "
        "were added.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_add_checklist_items(
        ctx: Context[AppContext],
        issue_id: IssueID,
        items: IssueChecklistItemsParam,
    ) -> list[ChecklistItem]:
        hidden = await check_issue(ctx, settings, issue_id, write=True)

        checklist = (
            await ctx.request_context.lifespan_context.issues.issue_add_checklist_items(
                issue_id,
                items=items,
                auth=get_yandex_auth(ctx),
            )
        )
        return _checklist_answer(checklist, hidden)

    @mcp.tool(
        title="Update Issue Checklist Item",
        description="Update one checklist item of a Yandex Tracker issue - to check it "
        "off, rename it, or set an assignee or a deadline. Only the fields you pass "
        "change, and null leaves a field as it is: use `clear_assignee` / "
        "`clear_deadline` to remove a value. Item ids come from `issue_get_checklist`. "
        "Returns the whole checklist.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_update_checklist_item(
        ctx: Context[AppContext],
        issue_id: IssueID,
        checklist_item_id: IssueChecklistItemIDParam,
        text: IssueChecklistItemTextParam = None,
        checked: IssueChecklistItemCheckedParam = None,
        assignee: IssueChecklistItemAssigneeParam = None,
        deadline: IssueChecklistItemDeadlineParam = None,
        clear_assignee: IssueChecklistItemClearAssigneeParam = False,
        clear_deadline: IssueChecklistItemClearDeadlineParam = False,
    ) -> list[ChecklistItem]:
        hidden = await check_issue(ctx, settings, issue_id, write=True)

        checklist = await ctx.request_context.lifespan_context.issues.issue_update_checklist_item(
            issue_id,
            checklist_item_id,
            text=text,
            checked=checked,
            assignee=assignee,
            deadline=deadline,
            clear_assignee=clear_assignee,
            clear_deadline=clear_deadline,
            auth=get_yandex_auth(ctx),
        )
        return _checklist_answer(checklist, hidden)

    @mcp.tool(
        title="Delete Issue Checklist Item",
        description="Delete a single item from the checklist of a Yandex Tracker issue. "
        "Use issue_get_checklist to get the item IDs. Returns the issue's checklist "
        "after the deletion.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def issue_delete_checklist_item(
        ctx: Context[AppContext],
        issue_id: IssueID,
        checklist_item_id: IssueChecklistItemIDParam,
    ) -> list[ChecklistItem]:
        hidden = await check_issue(ctx, settings, issue_id, write=True)

        checklist = await ctx.request_context.lifespan_context.issues.issue_delete_checklist_item(
            issue_id,
            checklist_item_id,
            auth=get_yandex_auth(ctx),
        )
        return _checklist_answer(checklist, hidden)

    @mcp.tool(
        title="Delete Issue Checklist",
        description="Delete the whole checklist ('чеклист') of a Yandex Tracker "
        "issue, every item at once; issue_delete_checklist_item removes one item.",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=True
        ),
    )
    async def issue_delete_checklist(
        ctx: Context[AppContext],
        issue_id: IssueID,
    ) -> None:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        await ctx.request_context.lifespan_context.issues.issue_delete_checklist(
            issue_id, auth=get_yandex_auth(ctx)
        )


def register_issue_file_upload_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register the tools that read local files (`TRACKER_FILE_UPLOAD_ENABLED`).

    Registered only on a writable server with the flag on; `Settings` refuses the
    flag on anything but a local stdio server, since these tools read any file the
    server process can.
    """

    @mcp.tool(
        title="Attach File to Issue",
        description="Attach a file from the machine the server runs on to a Yandex "
        "Tracker issue ('вложение'), returning the attachment with its `id` (requires "
        "TRACKER_FILE_UPLOAD_ENABLED). To show an image in a description, embed "
        "`![name](/ajax/v2/attachments/<id>?inline=true)` - a file name or the API "
        "URL renders as a broken image.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_add_attachment(
        ctx: Context[AppContext],
        issue_id: IssueID,
        file_path: UploadFilePathParam,
        filename: UploadFilenameParam = None,
    ) -> IssueAttachment:
        await check_issue(ctx, settings, issue_id, write=True, ai=False)

        content, path = await read_upload_file(file_path)

        return await ctx.request_context.lifespan_context.issues.issue_add_attachment(
            issue_id,
            content=content,
            filename=filename or path.name,
            auth=get_yandex_auth(ctx),
        )


# The API's own cap on one bulk change.
MAX_BULK_ISSUES = 10_000

BulkIssuesParam = Annotated[
    list[str],
    Field(
        min_length=1,
        max_length=MAX_BULK_ISSUES,
        description="Issue keys, at most 10 000; each is checked against the queue "
        "restrictions.",
    ),
]

BulkValuesParam = Annotated[
    dict[str, Any] | None,
    Field(
        description="Fields to set, as in issue_update's `fields` map: keyed by field "
        '`id`; e.g. {"tags": {"add": ["x"]}}.'
    ),
]

BulkNotifyParam = Annotated[
    bool, Field(description="Notify the people in the issues' fields. Default: off.")
]


class BulkConfirmation(BaseModel):
    """The user's answer to a bulk change."""

    confirm: bool = Field(
        default=False, description="Yes - apply this change to all listed issues."
    )


def _bulk_question(
    ctx: Context[Any], what: str, count: int
) -> BulkConfirmation | Elicit[BulkConfirmation]:
    """Ask the user to confirm a bulk change, where the client can be asked.

    A client that cannot goes ahead: TRACKER_BULK_ENABLED, which the user set,
    is then the consent.
    """
    if not _can_ask(ctx):
        return BulkConfirmation(confirm=True)
    return Elicit(
        f"{what} for {count} issue(s). This cannot be undone. Proceed?",
        BulkConfirmation,
    )


def _template_value(value: Any) -> Any:
    """A template field value as a write takes it: a template answers with
    references as whole objects (`self`, `id`, `key`, `display`), and a write
    wants them by `id` (or `key`) alone."""
    if isinstance(value, list):
        return [_template_value(item) for item in value]
    if isinstance(value, dict):
        if "id" in value:
            return {"id": value["id"]}
        if "key" in value:
            return {"key": value["key"]}
    return value


def _template_checklist(template: IssueTemplate) -> list[ChecklistItemInput]:
    """The checklist of an issue template as items to add to an issue."""
    items = (template.model_extra or {}).get("checklistItems") or []
    checklist = []
    for item in items:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        assignee = item.get("assignee")
        if isinstance(assignee, dict):
            assignee = assignee.get("login") or assignee.get("id")
        checklist.append(
            ChecklistItemInput(
                text=item["text"], checked=item.get("checked"), assignee=assignee
            )
        )
    return checklist


def _check_bulk_keys(settings: Settings, issues: list[str]) -> None:
    """The write check of every issue of a bulk change by the queue its key
    names, which costs no request: a queue out of reach is refused at once."""
    for issue_id in issues:
        if queue_of_key(issue_id) is not None:
            check_issue_access(settings, issue_id, write=True)


async def _check_bulk_issues(
    ctx: Context[AppContext], settings: Settings, issues: list[str]
) -> None:
    """The write check of every issue of a bulk change against the queue it is
    in now.

    Tracker serves a moved issue under its old key too, so under the queue
    restrictions one search per thousand issues (`issues_find_by_keys`) gives
    the key each one is under now, and that queue is checked - up to 10 000
    issues are not read one by one. An internal id the search does not find is
    refused, as its queue cannot be known; an unknown key is left to Tracker,
    which reports it among the failures of the change.
    """
    _check_bulk_keys(settings, issues)
    if not queue_checks_needed(settings, write=True):
        return

    found = await ctx.request_context.lifespan_context.issues.issues_find_by_keys(
        issues, auth=get_yandex_auth(ctx)
    )
    current: dict[str, str] = {}
    for issue in found:
        if not issue.key:
            continue
        extra = issue.model_extra or {}
        for name in (issue.key, extra.get("id"), *(extra.get("aliases") or ())):
            if isinstance(name, str):
                current[name.upper()] = issue.key

    for issue_id in issues:
        queue = queue_of_key(current.get(issue_id.upper(), ""))
        if queue is not None:
            check_issue_queue_access(settings, issue_id, queue, write=True)
        elif queue_of_key(issue_id) is None:
            raise TrackerError(
                f"Issue `{issue_id}` was not found, so its queue cannot be "
                f"checked against the queue restrictions; refusing."
            )


def _bulk_failure_allowed(settings: Settings, failure: BulkChangeFailure) -> bool:
    """Whether a failed issue of a bulk change is in a queue the allow-list shows.

    The report is read by id, and a bulk change started elsewhere can span
    queues ``TRACKER_LIMIT_QUEUES`` hides.
    """
    if not settings.tracker_limit_queues:
        return True
    key = failure.issue.key if failure.issue is not None else None
    queue = queue_of_key(key) if key else None
    return queue is not None and is_queue_allowed(settings, queue)


def _bulk_resolvers(
    settings: Settings,
) -> dict[str, Callable[..., Awaitable[BulkConfirmation | Elicit[BulkConfirmation]]]]:
    """The confirmation resolvers of the bulk tools. A resolver runs before the
    tool body, so the access checks run here first: the user is not asked to
    confirm a change the body would refuse anyway. The search for the queues
    the issues are in now is made here only; the body repeats the free check
    by the keys."""

    async def confirm_update(
        ctx: Context[AppContext], issues: list[str], values: dict[str, Any]
    ) -> BulkConfirmation | Elicit[BulkConfirmation]:
        await _check_bulk_issues(ctx, settings, issues)
        return _bulk_question(ctx, f"Update fields {sorted(values)}", len(issues))

    async def confirm_transition(
        ctx: Context[AppContext], issues: list[str], transition: str
    ) -> BulkConfirmation | Elicit[BulkConfirmation]:
        await _check_bulk_issues(ctx, settings, issues)
        return _bulk_question(ctx, f"Run transition `{transition}`", len(issues))

    async def confirm_move(
        ctx: Context[AppContext], issues: list[str], queue: str
    ) -> BulkConfirmation | Elicit[BulkConfirmation]:
        await _check_bulk_issues(ctx, settings, issues)
        check_queue_access(settings, queue, write=True)
        return _bulk_question(ctx, f"Move to queue `{queue}`", len(issues))

    return {
        "update": confirm_update,
        "transition": confirm_transition,
        "move": confirm_move,
    }


def _confirmed(confirmation: ElicitationResult[BulkConfirmation], what: str) -> None:
    if not (
        isinstance(confirmation, AcceptedElicitation) and confirmation.data.confirm
    ):
        raise TrackerError(f"{what} was cancelled by the user.")


def register_issue_bulk_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register the bulk-change tools (`TRACKER_BULK_ENABLED`, writable server)."""

    resolvers = _bulk_resolvers(settings)

    @mcp.tool(
        title="Bulk Update Issues",
        description="Set the same fields on up to 10 000 Yandex Tracker issues at "
        "once ('массовое редактирование'). Irreversible and asynchronous: poll "
        "issues_get_bulk_change with the returned `id` (requires TRACKER_BULK_ENABLED).",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def issues_bulk_update(
        ctx: Context[AppContext],
        issues: BulkIssuesParam,
        values: Annotated[
            dict[str, Any],
            Field(
                description="Fields to set, keyed by field `id`, as in issue_update's "
                "`fields` map."
            ),
        ],
        confirmation: Annotated[
            ElicitationResult[BulkConfirmation], Resolve(resolvers["update"])
        ],
        notify: BulkNotifyParam = False,
    ) -> BulkChange:
        _check_bulk_keys(settings, issues)
        _confirmed(confirmation, "The bulk update")
        return await ctx.request_context.lifespan_context.issues.issues_bulk_update(
            issues, values=values, notify=notify, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Bulk Transition Issues",
        description="Run one status transition on up to 10 000 Yandex Tracker issues "
        "at once; a closing one needs `values` with a resolution. Irreversible and "
        "asynchronous: poll issues_get_bulk_change (requires TRACKER_BULK_ENABLED).",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def issues_bulk_transition(
        ctx: Context[AppContext],
        issues: BulkIssuesParam,
        transition: Annotated[
            str,
            Field(description="Transition `id` from issue_get_transitions."),
        ],
        confirmation: Annotated[
            ElicitationResult[BulkConfirmation], Resolve(resolvers["transition"])
        ],
        values: BulkValuesParam = None,
        notify: BulkNotifyParam = False,
    ) -> BulkChange:
        _check_bulk_keys(settings, issues)
        _confirmed(confirmation, "The bulk transition")
        return await ctx.request_context.lifespan_context.issues.issues_bulk_transition(
            issues,
            transition=transition,
            values=values,
            notify=notify,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Bulk Move Issues",
        description="Move up to 10 000 Yandex Tracker issues to another queue at "
        "once. Irreversible and asynchronous: poll issues_get_bulk_change "
        "(requires TRACKER_BULK_ENABLED).",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def issues_bulk_move(
        ctx: Context[AppContext],
        issues: BulkIssuesParam,
        queue: Annotated[str, Field(description="Key of the target queue.")],
        confirmation: Annotated[
            ElicitationResult[BulkConfirmation], Resolve(resolvers["move"])
        ],
        move_all_fields: Annotated[
            bool,
            Field(
                description="Keep versions, components and projects that exist in the "
                "target queue; by default they are cleared."
            ),
        ] = False,
        initial_status: Annotated[
            bool,
            Field(
                description="Reset the status to the target queue's initial one - "
                "needed when its workflow differs."
            ),
        ] = False,
        values: BulkValuesParam = None,
        notify: BulkNotifyParam = False,
    ) -> BulkChange:
        _check_bulk_keys(settings, issues)
        check_queue_access(settings, queue, write=True)
        _confirmed(confirmation, "The bulk move")
        return await ctx.request_context.lifespan_context.issues.issues_bulk_move(
            issues,
            queue=queue,
            values=values,
            move_all_fields=move_all_fields,
            initial_status=initial_status,
            notify=notify,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Bulk Change",
        description="Get the state of a bulk change by the `id` an issues_bulk_* tool "
        "returned; once it is final, also the issues it failed on and why (requires "
        "TRACKER_BULK_ENABLED).",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issues_get_bulk_change(
        ctx: Context[AppContext],
        bulk_change_id: Annotated[
            str, Field(description="The `id` an issues_bulk_* tool returned.")
        ],
    ) -> BulkChangeReport:
        issues = ctx.request_context.lifespan_context.issues
        auth = get_yandex_auth(ctx)
        change = await issues.bulk_change_get(bulk_change_id, auth=auth)

        failures = None
        incomplete = (
            change.total_issues is not None
            and change.total_completed_issues is not None
            and change.total_completed_issues < change.total_issues
        )
        if change.status in ("COMPLETE", "FAILED") and (
            incomplete or change.status == "FAILED"
        ):
            failures = await issues.bulk_change_get_failures(bulk_change_id, auth=auth)
            failures = [f for f in failures if _bulk_failure_allowed(settings, f)]
        return BulkChangeReport(change=change, failures=failures)


# A write to an issue whose queue forbids AI tools goes through, but its answer
# leaves the issue's content out - otherwise any write would read the issue.


async def _issue_answer(
    ctx: Context[AppContext], settings: Settings, issue: Issue
) -> Issue:
    """The issue a create, update or move answers with. The key it comes back
    under names the queue it is in now, so a move is judged by its target."""
    if await answer_hidden(ctx, settings, issue.key):
        return restricted_issue(issue)
    await hide_restricted_refs(ctx, settings, issue)
    return issue


async def _worklog_answer(
    ctx: Context[AppContext], settings: Settings, worklog: Worklog, hidden: bool
) -> Worklog:
    if hidden:
        worklog.comment = None
    await hide_restricted_refs(ctx, settings, worklog)
    return worklog


def _comment_answer(comment: IssueComment, hidden: bool) -> IssueComment:
    """A reaction answers with the comment, which is someone else's text."""
    if hidden:
        comment.text = None
        comment.text_html = None
    return comment


def _checklist_answer(
    checklist: list[ChecklistItem], hidden: bool
) -> list[ChecklistItem]:
    """A checklist write answers with every item; under a forbidding queue only
    what the next write needs stays - the ids, and whether each is checked."""
    if not hidden:
        return checklist
    return [
        ChecklistItem(id=item.id, text="", checked=item.checked) for item in checklist
    ]
