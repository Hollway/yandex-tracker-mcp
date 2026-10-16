"""Issue read-only MCP tools."""

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import (
    CommentsCursorParam,
    CursorPerPageParam,
    IssueID,
    IssueIDs,
    PageParam,
    PerPageParam,
    YTQuery,
)
from mcp_tracker.mcp.tools._access import (
    check_fetched_issue_access,
    check_issue_access,
    queue_of_key,
)
from mcp_tracker.mcp.tools._ai_access import (
    check_ai_access,
    check_fetched_issue_ai_access,
    hide_ai_restricted,
    is_restricted_row,
)
from mcp_tracker.mcp.utils import (
    get_yandex_auth,
    safe_file_name,
    set_non_needed_fields_null,
)
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import AttachmentTooLarge
from mcp_tracker.tracker.proto.types.issues import (
    AttachmentFieldsEnum,
    ChangelogPage,
    ChecklistItem,
    CommentFieldsEnum,
    CommentsPage,
    DownloadedIssueAttachment,
    Issue,
    IssueAttachment,
    IssueComment,
    IssueLink,
    IssuesCount,
    IssueTransition,
    RemoteLink,
    Worklog,
    WorklogFieldsEnum,
    resolve_issue_field,
)
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult


def register_issue_read_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register issue read-only tools."""

    @mcp.tool(
        title="Get Issue",
        description="Read one Yandex Tracker issue (task, ticket, bug; in russian - "
        "'задача') by its key and return its full record, the current `version` "
        "included. To search instead, use `issues_find`. Comments, "
        "links, attachments, worklogs, checklist, changelog and transitions each have "
        "their own `issue_get_*` tool.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get(
        ctx: Context[AppContext],
        issue_id: IssueID,
        include_description: Annotated[
            bool,
            Field(
                description="Whether to include issue description in the issues result. "
                "It can be large, so use only when needed.",
            ),
        ] = True,
    ) -> Issue:
        check_issue_access(settings, issue_id)
        # A key names its queue, so a forbidding one is refused unread.
        if queue_of_key(issue_id) is not None:
            await check_ai_access(ctx, settings, issue_id)

        issue = await ctx.request_context.lifespan_context.issues.issue_get(
            issue_id,
            auth=get_yandex_auth(ctx),
        )
        # Checked again against the key the issue came back under: an internal
        # id or the old key of a moved issue names no queue, or the wrong one.
        check_fetched_issue_access(settings, issue_id, issue.key)
        await check_fetched_issue_ai_access(ctx, settings, issue_id, issue)

        if not include_description:
            issue.description = None

        return issue

    @mcp.tool(
        title="Get Issue Comments",
        description="Get a page of comments of a Yandex Tracker issue by its id. "
        "Returns the comments plus `next_cursor` - pass it back as `cursor` until it "
        "is null.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_comments(
        ctx: Context[AppContext],
        issue_id: IssueID,
        per_page: CursorPerPageParam = 50,
        cursor: CommentsCursorParam = None,
        fields: Annotated[
            list[CommentFieldsEnum] | None,
            Field(
                description="Fields to include in each comment; omit to get all. "
                "text/text_html can be large, so select only what you need.",
            ),
        ] = None,
    ) -> CommentsPage:
        check_issue_access(settings, issue_id)
        await check_ai_access(ctx, settings, issue_id)

        page = await ctx.request_context.lifespan_context.issues.issue_get_comments(
            issue_id,
            per_page=per_page,
            cursor=cursor,
            auth=get_yandex_auth(ctx),
        )

        if fields is not None:
            set_non_needed_fields_null(page.comments, {f.name for f in fields})

        return page

    @mcp.tool(
        title="Get Issue Links",
        description="Get a Yandex Tracker issue related links to other issues by its id",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_links(
        ctx: Context[AppContext],
        issue_id: IssueID,
    ) -> list[IssueLink]:
        check_issue_access(settings, issue_id)
        # Each link carries the linked issue's summary and status.
        await check_ai_access(ctx, settings, issue_id)

        return await ctx.request_context.lifespan_context.issues.issues_get_links(
            issue_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Issue Remote Links",
        description="Get the links of a Yandex Tracker issue to objects in other "
        "applications (pull requests, documents, CRM records, ...); links between "
        "issues come from issue_get_links.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_remote_links(
        ctx: Context[AppContext],
        issue_id: IssueID,
    ) -> list[RemoteLink]:
        check_issue_access(settings, issue_id)
        await check_ai_access(ctx, settings, issue_id)

        return await ctx.request_context.lifespan_context.issues.issue_get_remote_links(
            issue_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Find Issues",
        description="Find Yandex Tracker issues matching a Yandex Tracker Query (YQL) - not limited to "
        "queue/date, any indexed field can be used (assignee, status, tags, etc., see the `query` "
        "parameter for the full syntax).",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issues_find(
        ctx: Context[AppContext],
        query: YTQuery,
        include_description: Annotated[
            bool,
            Field(
                description="Whether to include the issue description; it can be large. "
                "Ignored when `description` is listed in `fields`.",
            ),
        ] = False,
        fields: Annotated[
            list[str] | None,
            Field(
                description="Fields to return, in Tracker's own spelling "
                "(`storyPoints`, not `story_points`); the standard ones are in this "
                "tool's output schema. For a queue's local or the organization's "
                "custom fields, pass the field `id` from `queue_get_fields`. An "
                "unknown name is dropped silently, so check there if a field comes "
                "back missing. Omitting this returns ALL fields."
            ),
        ] = None,
        page: PageParam = 1,
        per_page: PerPageParam = 100,
    ) -> PaginatedResult[Issue]:
        api_fields: list[str] | None = None
        selected: set[str] | None = None
        if fields is not None:
            resolved = [resolve_issue_field(name) for name in fields]
            # Asking for both spellings of one field would send it to the API twice.
            api_fields = list(dict.fromkeys(api for api, _ in resolved))
            selected = {key for _, key in resolved}
            # The key names the issue's queue, which the AI access check needs;
            # it is trimmed away again below unless it was asked for.
            if "key" not in api_fields:
                api_fields.append("key")

        result = await ctx.request_context.lifespan_context.issues.issues_find(
            query=query,
            per_page=per_page,
            page=page,
            fields=api_fields,
            auth=get_yandex_auth(ctx),
        )

        result.values = await hide_ai_restricted(ctx, settings, result.values)

        # A description asked for through `fields` is an explicit request for it,
        # so it is not stripped by `include_description` defaulting to False.
        if not include_description and "description" not in (selected or ()):
            for issue in result.values:
                issue.description = None  # Clear description to save context

        if selected is not None:
            # Tracker sends `self`, `id`, `version` and `favorite` on top of any
            # projection, so the response still needs trimming to what was asked for.
            set_non_needed_fields_null(
                [issue for issue in result.values if not is_restricted_row(issue)],
                selected,
            )

        return result

    @mcp.tool(
        title="Count Issues",
        description="Get the count of Yandex Tracker issues matching a query.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issues_count(
        ctx: Context[AppContext],
        query: YTQuery,
    ) -> IssuesCount:
        count = await ctx.request_context.lifespan_context.issues.issues_count(
            query,
            auth=get_yandex_auth(ctx),
        )
        return IssuesCount(count=count)

    @mcp.tool(
        title="Get Issue Comment",
        description="Get one comment of a Yandex Tracker issue by its id, with the "
        "files attached to it - e.g. a comment a link, a mention or the changelog "
        "points at, without paging through issue_get_comments.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_comment(
        ctx: Context[AppContext],
        issue_id: IssueID,
        comment_id: Annotated[
            int | str,
            Field(description="The comment's numeric `id` or its `longId`."),
        ],
    ) -> IssueComment:
        check_issue_access(settings, issue_id)
        await check_ai_access(ctx, settings, issue_id)

        return await ctx.request_context.lifespan_context.issues.issue_get_comment(
            issue_id, comment_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Get Issue Worklogs",
        description="Get worklogs of a Yandex Tracker issue by its id",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_worklogs(
        ctx: Context[AppContext],
        issue_ids: IssueIDs,
        fields: Annotated[
            list[WorklogFieldsEnum] | None,
            Field(
                description="Fields to include in each worklog entry; omit to get all. "
                "Select only what you need.",
            ),
        ] = None,
    ) -> dict[str, list[Worklog]]:
        for issue_id in issue_ids:
            check_issue_access(settings, issue_id)
            await check_ai_access(ctx, settings, issue_id)

        result: dict[str, list[Worklog]] = {}
        for issue_id in issue_ids:
            worklogs = (
                await ctx.request_context.lifespan_context.issues.issue_get_worklogs(
                    issue_id,
                    auth=get_yandex_auth(ctx),
                )
            )
            if fields is not None and worklogs:
                set_non_needed_fields_null(worklogs, {f.name for f in fields})
            result[issue_id] = worklogs or []

        return result

    @mcp.tool(
        title="Get Issue Attachments",
        description="Get attachments of a Yandex Tracker issue by its id",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_attachments(
        ctx: Context[AppContext],
        issue_id: IssueID,
        fields: Annotated[
            list[AttachmentFieldsEnum] | None,
            Field(
                description="Fields to include in each attachment; omit to get all. "
                "`content` is the API download URL, which needs the server's "
                "credentials to open.",
            ),
        ] = None,
    ) -> list[IssueAttachment]:
        check_issue_access(settings, issue_id)
        await check_ai_access(ctx, settings, issue_id)

        attachments = (
            await ctx.request_context.lifespan_context.issues.issue_get_attachments(
                issue_id,
                auth=get_yandex_auth(ctx),
            )
        )

        if fields is not None:
            set_non_needed_fields_null(attachments, {f.name for f in fields})

        return attachments

    @mcp.tool(
        title="Get Issue Checklist",
        description="Get checklist items of a Yandex Tracker issue by its id",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_checklist(
        ctx: Context[AppContext],
        issue_id: IssueID,
    ) -> list[ChecklistItem]:
        check_issue_access(settings, issue_id)
        await check_ai_access(ctx, settings, issue_id)

        return await ctx.request_context.lifespan_context.issues.issue_get_checklist(
            issue_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Issue Transitions",
        description="Get possible status transitions for a Yandex Tracker issue. "
        "Returns list of available transitions that can be performed on the issue.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_transitions(
        ctx: Context[AppContext],
        issue_id: IssueID,
    ) -> list[IssueTransition]:
        check_issue_access(settings, issue_id)

        return await ctx.request_context.lifespan_context.issues.issue_get_transitions(
            issue_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get Issue Changelog",
        description="Get the change history (changelog) of a Yandex Tracker issue: "
        "status transitions, field edits (who changed what from -> to and when), "
        "comment changes and executed triggers. Returns a page of entries plus "
        "`next_cursor` - pass it back as `cursor` until it is null.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def issue_get_changelog(
        ctx: Context[AppContext],
        issue_id: IssueID,
        per_page: CursorPerPageParam = 50,
        cursor: Annotated[
            str | None,
            Field(
                description="Cursor for the next page: the 'next_cursor' value returned by "
                "the previous call. Leave empty for the first page.",
            ),
        ] = None,
        field: Annotated[
            str | None,
            Field(
                description="Optional field key to filter the changelog by "
                "(e.g. 'status' to only see status changes).",
            ),
        ] = None,
        type: Annotated[
            str | None,
            Field(
                description="Optional change type to filter by (e.g. 'IssueWorkflow' for status transitions).",
            ),
        ] = None,
    ) -> ChangelogPage:
        check_issue_access(settings, issue_id)
        await check_ai_access(ctx, settings, issue_id)

        return await ctx.request_context.lifespan_context.issues.issue_get_changelog(
            issue_id,
            per_page=per_page,
            cursor=cursor,
            field=field,
            type=type,
            auth=get_yandex_auth(ctx),
        )


def register_issue_attachment_download_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register the tool that saves attachments to the server's disk.

    Registered only with `TRACKER_ATTACHMENT_DOWNLOAD_ENABLED`, which `Settings`
    refuses on anything but a local stdio server. It changes nothing in
    Tracker, so it stays available on a read-only server.
    """

    @mcp.tool(
        title="Download Issue Attachment",
        description="Save an attachment ('вложение') of a Yandex Tracker issue to "
        "the machine the server runs on and return its local path, to open an "
        "image, log or document from there (requires "
        "TRACKER_ATTACHMENT_DOWNLOAD_ENABLED).",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True
        ),
    )
    async def issue_download_attachment(
        ctx: Context[AppContext],
        issue_id: IssueID,
        attachment_id: Annotated[
            str,
            Field(description="Attachment `id` from issue_get_attachments."),
        ],
    ) -> DownloadedIssueAttachment:
        check_issue_access(settings, issue_id)
        await check_ai_access(ctx, settings, issue_id)

        issues = ctx.request_context.lifespan_context.issues
        auth = get_yandex_auth(ctx)

        # The metadata gives the name the download URL needs, and the size to
        # refuse an oversized file before a single byte of it is fetched.
        attachment = await issues.issue_get_attachment(
            issue_id, attachment_id, auth=auth
        )

        limit = settings.tracker_max_attachment_bytes
        if attachment.size is not None and attachment.size > limit:
            raise AttachmentTooLarge(attachment_id, attachment.size, limit)

        # An attachment never changes, so the same id downloaded again is the
        # file already on disk.
        destination = (
            settings.attachments_dir
            / safe_file_name(issue_id)
            / safe_file_name(f"{attachment.id}-{attachment.name}")
        )
        if (
            attachment.size is not None
            and destination.is_file()
            and destination.stat().st_size == attachment.size
        ):
            size = attachment.size
        else:
            size = await issues.issue_download_attachment(
                issue_id, attachment.id, attachment.name, destination, auth=auth
            )

        return DownloadedIssueAttachment(
            issue_id=issue_id,
            attachment_id=attachment.id,
            name=attachment.name,
            path=str(destination),
            mime_type=attachment.mimetype,
            size=size,
        )
