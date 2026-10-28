"""Worklog search across issues (read-only)."""

import datetime
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.tools._access import is_queue_allowed, queue_of_key
from mcp_tracker.mcp.tools._ai_access import (
    ai_restricted_queues,
    hide_restricted_refs,
)
from mcp_tracker.mcp.utils import (
    get_yandex_auth,
    local_day_end,
    local_day_start,
    set_non_needed_fields_null,
)
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.issues import Worklog, WorklogFieldsEnum


def register_worklog_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register the worklog search tool."""

    @mcp.tool(
        title="Find Worklogs",
        description="Find the time logged ('списания времени') by one user across "
        "all issues over a period, e.g. 'what did I log last week'. Filter by the "
        "day the work was done (`start_*`) or by the day the record was entered "
        "(`created_*`); days are in the server's local time zone.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def worklogs_find(
        ctx: Context[AppContext],
        author: Annotated[
            str | None,
            Field(
                description="Login or uid of the user who logged the time; omit for "
                "the current user."
            ),
        ] = None,
        start_from: Annotated[
            datetime.date | None,
            Field(
                description="First day of the work, YYYY-MM-DD. Records entered "
                "before this day are not searched, so time logged in advance is "
                "missed."
            ),
        ] = None,
        start_to: Annotated[
            datetime.date | None,
            Field(description="Last day of the work, YYYY-MM-DD, inclusive."),
        ] = None,
        created_from: Annotated[
            datetime.date | None,
            Field(description="First day the records were entered, YYYY-MM-DD."),
        ] = None,
        created_to: Annotated[
            datetime.date | None,
            Field(
                description="Last day the records were entered, YYYY-MM-DD, inclusive."
            ),
        ] = None,
        fields: Annotated[
            list[WorklogFieldsEnum] | None,
            Field(
                description="Fields to include in each worklog entry; omit to get all."
            ),
        ] = None,
    ) -> list[Worklog]:
        first_day = created_from if created_from is not None else start_from
        if first_day is None:
            raise TrackerError(
                "Pass `start_from` or `created_from`: without a first day the "
                "search would return everything the user has ever logged."
            )

        context = ctx.request_context.lifespan_context
        auth = get_yandex_auth(ctx)
        if author is None:
            author = (await context.users.user_get_current(auth=auth)).login

        # Tracker filters only by when a record was entered. Work done on or
        # after `start_from` is entered on or after it too - unless it was
        # logged in advance - so that is the entry window to ask for, and the
        # days of the work itself are checked here.
        worklogs = await context.issues.worklogs_find(
            created_by=author,
            created_from=local_day_start(first_day),
            created_to=local_day_end(created_to) if created_to else None,
            auth=auth,
        )

        low = local_day_start(start_from) if start_from else None
        high = local_day_end(start_to) if start_to else None
        found = [
            worklog
            for worklog in worklogs
            if _issue_allowed(settings, worklog)
            and (low is None or (worklog.start is not None and worklog.start >= low))
            and (high is None or (worklog.start is not None and worklog.start < high))
        ]
        # The time logged is the user's own record; the comment and the
        # issue's summary are issue content, which a queue that forbids AI
        # tools does not hand out.
        restricted = await ai_restricted_queues(
            ctx, settings, (q for w in found if (q := _queue(w)) is not None)
        )
        for worklog in found:
            if _queue(worklog) in restricted:
                worklog.comment = None
        await hide_restricted_refs(ctx, settings, found)
        found.sort(
            key=lambda w: w.start or datetime.datetime.min.replace(tzinfo=datetime.UTC)
        )

        if fields is not None:
            set_non_needed_fields_null(found, {f.name for f in fields})
        return found


def _queue(worklog: Worklog) -> str | None:
    """The queue of the worklog's issue, from its key."""
    key = worklog.issue.key if worklog.issue is not None else None
    return queue_of_key(str(key)) if key else None


def _issue_allowed(settings: Settings, worklog: Worklog) -> bool:
    """Whether the worklog's issue is in a queue `TRACKER_LIMIT_QUEUES` allows."""
    if not settings.tracker_limit_queues:
        return True
    queue = _queue(worklog)
    return queue is not None and is_queue_allowed(settings, queue)
