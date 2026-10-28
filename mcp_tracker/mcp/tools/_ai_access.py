"""The queue setting «Доступ для AI инструментов» (AI tools access).

A queue can forbid AI tools its issues' content. Tracker's own MCP server then
returns only the key of such an issue, marked `restricted`, and still lets the
issue be changed. Tracker's API does not enforce it - it only reports the
setting on the queue (`aiAccessLevel`: "full" or not, and `noMcp`) - so this
server does what Tracker's own one does, unless the queue is listed in
`TRACKER_AI_ACCESS_IGNORED_QUEUES`. That covers more than the reads of such an
issue: the summary other issues carry of it (`hide_restricted_refs`) and the
answers of the writes to it (`restricted_issue`), which would otherwise turn any
write into a read.
"""

import asyncio
import re
import time
from collections.abc import Iterable
from typing import Any

from mcp.server.mcpserver import Context
from pydantic import BaseModel

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.tools._access import queue_of_key
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import QueueNotFound, TrackerAPIError
from mcp_tracker.tracker.proto.types.issues import Issue
from mcp_tracker.tracker.proto.types.queues import Queue
from mcp_tracker.tracker.proto.types.refs import IssueReference

# A queue's setting rarely changes; reading it once per queue per ten minutes
# keeps a listing from costing a request per row.
AI_ACCESS_TTL_SECONDS = 600.0


class AiAccessRestricted(TrackerError):
    def __init__(self, issue_id: str, queue: str):
        super().__init__(
            f"Queue `{queue}` forbids AI tools access to its issues (the queue "
            f"setting 'Доступ для AI инструментов'), so the content of `{issue_id}` "
            f"is not returned. Changing the issue is still allowed, though the "
            f"answer leaves its content out. The owner of "
            f"this server can list the queue in TRACKER_AI_ACCESS_IGNORED_QUEUES."
        )
        self.issue_id = issue_id
        self.queue = queue


def queue_forbids_ai(queue: Queue) -> bool:
    """Whether the queue's settings, as the API reports them, forbid AI tools."""
    extra = queue.model_extra or {}
    level = extra.get("aiAccessLevel")
    return extra.get("noMcp") is True or (isinstance(level, str) and level != "full")


def _is_ignored(settings: Settings, key: str) -> bool:
    return bool(
        settings.tracker_ai_access_ignored_queues
        and key in settings.tracker_ai_access_ignored_queues
    )


async def is_ai_restricted(
    ctx: Context[AppContext], settings: Settings, queue: str
) -> bool:
    key = queue.upper()
    if _is_ignored(settings, key):
        return False

    context = ctx.request_context.lifespan_context
    now = time.monotonic()
    cached = context.ai_access.get(key)
    if cached is not None and cached[1] > now:
        return cached[0]

    try:
        queue_data = await context.queues.queue_get(key, auth=get_yandex_auth(ctx))
    except (QueueNotFound, TrackerAPIError) as exc:
        # A queue the token cannot read (404, 403) reports no setting; the issue
        # read that follows answers for the access itself. Any other failure - a
        # 429, a 5xx - says nothing about the setting, so it is raised and not
        # remembered: taken for "allowed", it opened the queue for the whole TTL.
        if isinstance(exc, TrackerAPIError) and exc.status != 403:
            raise
        restricted = False
    else:
        restricted = queue_forbids_ai(queue_data)
    context.ai_access[key] = (restricted, now + AI_ACCESS_TTL_SECONDS)
    return restricted


_QUEUES_PAGE = 100
# A guard against a listing that never ends; no organization comes close.
_MAX_QUEUE_PAGES = 100


async def ai_forbidden_anywhere(ctx: Context[AppContext], settings: Settings) -> bool:
    """Whether any queue the token can see forbids AI tools.

    The listing reports each queue's setting, so one pass over it - every ten
    minutes - answers this and fills the per-queue answers of `is_ai_restricted`
    on the way. A failure is raised and not remembered, as there.
    """
    context = ctx.request_context.lifespan_context
    now = time.monotonic()
    cached = context.ai_forbidden_anywhere
    if cached is not None and cached[1] > now:
        return cached[0]

    expires = now + AI_ACCESS_TTL_SECONDS
    found = False
    for page in range(1, _MAX_QUEUE_PAGES + 1):
        result = await context.queues.queues_list(
            per_page=_QUEUES_PAGE, page=page, auth=get_yandex_auth(ctx)
        )
        for queue in result.values:
            if not queue.key:
                continue
            key = queue.key.upper()
            restricted = not _is_ignored(settings, key) and queue_forbids_ai(queue)
            context.ai_access[key] = (restricted, expires)
            found = found or restricted
        if len(result.values) < _QUEUES_PAGE:
            break
    context.ai_forbidden_anywhere = (found, expires)
    return found


async def ai_restricted_queues(
    ctx: Context[AppContext], settings: Settings, queues: Iterable[str]
) -> set[str]:
    """The ones among `queues` that forbid AI tools, their settings read at once."""
    distinct = sorted(set(queues))
    answers = await asyncio.gather(
        *(is_ai_restricted(ctx, settings, queue) for queue in distinct)
    )
    return {
        queue for queue, restricted in zip(distinct, answers, strict=True) if restricted
    }


async def check_ai_access(
    ctx: Context[AppContext], settings: Settings, issue_id: str
) -> None:
    """Refuse to return the content of an issue in a queue that forbids AI tools.

    An internal id names no queue, so the issue is read for its key first - one
    request, rather than skipping the check for whoever passes the id.
    """
    queue = queue_of_key(issue_id)
    if queue is None:
        issue = await ctx.request_context.lifespan_context.issues.issue_get(
            issue_id, auth=get_yandex_auth(ctx)
        )
        queue = queue_of_key(issue.key or "")
    if queue is not None and await is_ai_restricted(ctx, settings, queue):
        raise AiAccessRestricted(issue_id, queue)


async def check_fetched_issue_ai_access(
    ctx: Context[AppContext], settings: Settings, issue_id: str, issue: Issue
) -> None:
    """`check_ai_access` against the key Tracker answered with.

    For a tool that reads the issue itself: the key it comes back under names
    the queue the issue is in now, whatever id or old key the caller passed.
    """
    queue = queue_of_key(issue.key or "")
    if queue is not None and await is_ai_restricted(ctx, settings, queue):
        raise AiAccessRestricted(issue_id, queue)


async def hide_ai_restricted(
    ctx: Context[AppContext], settings: Settings, issues: list[Issue]
) -> list[Issue]:
    """Replace each issue of a forbidding queue with its key and `restricted`,
    and hide the summaries the others carry of such issues (`hide_restricted_refs`)."""
    # The key names the queue; `issues_find` asks for it even under a
    # projection that leaves it out, so that this check can be made.
    queues = {issue.key: queue_of_key(issue.key or "") for issue in issues}
    restricted = await ai_restricted_queues(
        ctx, settings, (queue for queue in queues.values() if queue is not None)
    )
    kept = [
        # `restricted` is not a field of the model: it goes in as an extra key,
        # which the model keeps (extra="allow").
        Issue.model_validate({"key": issue.key, "restricted": True})
        if queues[issue.key] in restricted
        else issue
        for issue in issues
    ]
    await hide_restricted_refs(ctx, settings, kept)
    return kept


_ISSUE_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*-\d+")

IssueRef = IssueReference | dict[str, Any]


def _issue_refs(value: Any, found: list[IssueRef]) -> None:
    """Collect the references to issues anywhere in a tool's answer: the
    `IssueReference` fields (parent, epic, a link's object, a worklog's issue)
    and, in what the models pass through untouched (a changelog's field
    changes, an issue's custom fields), dicts shaped like one."""
    if isinstance(value, IssueReference):
        found.append(value)
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            _issue_refs(getattr(value, name), found)
        for item in (value.model_extra or {}).values():
            _issue_refs(item, found)
    elif isinstance(value, dict):
        key = value.get("key")
        if "display" in value and isinstance(key, str) and _ISSUE_KEY.fullmatch(key):
            found.append(value)
        for item in value.values():
            _issue_refs(item, found)
    elif isinstance(value, list | tuple):
        for item in value:
            _issue_refs(item, found)


def _ref_key(ref: IssueRef) -> str | None:
    key = ref.key if isinstance(ref, IssueReference) else ref.get("key")
    return key if isinstance(key, str) else None


async def hide_restricted_refs(
    ctx: Context[AppContext], settings: Settings, answer: Any
) -> None:
    """Drop, in place, the summary (`display`) of every issue the answer refers
    to that is in a queue forbidding AI tools, and mark the reference
    `restricted`; the key and id stay. An issue that may be read can still name
    one that may not - as its parent, through a link, in a worklog or a
    changelog entry. On a server where no queue forbids AI tools this costs
    nothing beyond the listing `ai_forbidden_anywhere` makes every ten minutes.
    """
    refs: list[IssueRef] = []
    _issue_refs(answer, refs)
    refs = [
        ref
        for ref in refs
        if (ref.display if isinstance(ref, IssueReference) else ref.get("display"))
        is not None
    ]
    if not refs or not await ai_forbidden_anywhere(ctx, settings):
        return

    queues = {
        ref_key: queue_of_key(ref_key) for ref in refs if (ref_key := _ref_key(ref))
    }
    restricted = await ai_restricted_queues(
        ctx, settings, (queue for queue in queues.values() if queue is not None)
    )
    for ref in refs:
        ref_key = _ref_key(ref)
        # A reference without a key names no queue; with a forbidding queue
        # about, its summary is not risked.
        if ref_key is not None and queues[ref_key] not in restricted:
            continue
        if isinstance(ref, IssueReference):
            ref.display = None
            ref.restricted = True
        else:
            ref["display"] = None
            ref["restricted"] = True


async def answer_hidden(
    ctx: Context[AppContext], settings: Settings, key: str | None
) -> bool:
    """Whether a write's answer about the issue `key` leaves its content out:
    its queue forbids AI tools. A key that names no queue is not hidden."""
    queue = queue_of_key(key or "")
    return (
        queue is not None
        and await ai_forbidden_anywhere(ctx, settings)
        and await is_ai_restricted(ctx, settings, queue)
    )


def restricted_issue(issue: Issue) -> Issue:
    """What a write answers with for an issue whose queue forbids AI tools: the
    change went through, and the key, id and the `version` the next write needs
    come back without the content."""
    kept = {
        "key": issue.key,
        "id": (issue.model_extra or {}).get("id"),
        "version": issue.version,
    }
    return Issue.model_validate(
        {name: value for name, value in kept.items() if value is not None}
        | {"restricted": True}
    )


def is_restricted_row(issue: Issue) -> bool:
    """Whether the row is a placeholder `hide_ai_restricted` put in."""
    return (issue.model_extra or {}).get("restricted") is True
