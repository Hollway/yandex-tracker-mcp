"""The queue setting «Доступ для AI инструментов» (AI tools access).

A queue can forbid AI tools its issues' content. Tracker's own MCP server then
returns only the key of such an issue, marked `restricted`, and still lets the
issue be changed. Tracker's API does not enforce it - it only reports the
setting on the queue (`aiAccessLevel`: "full" or not, and `noMcp`) - so this
server does what Tracker's own one does, unless the queue is listed in
`TRACKER_AI_ACCESS_IGNORED_QUEUES`.
"""

import time

from mcp.server.mcpserver import Context

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import YandexTrackerError
from mcp_tracker.tracker.proto.types.issues import Issue
from mcp_tracker.tracker.proto.types.queues import Queue

# A queue's setting rarely changes; reading it once per queue per ten minutes
# keeps a listing from costing a request per row.
AI_ACCESS_TTL_SECONDS = 600.0


class AiAccessRestricted(TrackerError):
    def __init__(self, issue_id: str, queue: str):
        super().__init__(
            f"Queue `{queue}` forbids AI tools access to its issues (the queue "
            f"setting 'Доступ для AI инструментов'), so the content of `{issue_id}` "
            f"is not returned. Changing the issue is still allowed. The owner of "
            f"this server can list the queue in TRACKER_AI_ACCESS_IGNORED_QUEUES."
        )
        self.issue_id = issue_id
        self.queue = queue


def queue_forbids_ai(queue: Queue) -> bool:
    """Whether the queue's settings, as the API reports them, forbid AI tools."""
    extra = queue.model_extra or {}
    level = extra.get("aiAccessLevel")
    return extra.get("noMcp") is True or (isinstance(level, str) and level != "full")


async def is_ai_restricted(
    ctx: Context[AppContext], settings: Settings, queue: str
) -> bool:
    key = queue.upper()
    if settings.tracker_ai_access_ignored_queues and (
        key in settings.tracker_ai_access_ignored_queues
    ):
        return False

    context = ctx.request_context.lifespan_context
    now = time.monotonic()
    cached = context.ai_access.get(key)
    if cached is not None and cached[1] > now:
        return cached[0]

    try:
        queue_data = await context.queues.queue_get(key, auth=get_yandex_auth(ctx))
    except YandexTrackerError:
        # A queue the token cannot read reports no setting; the issue read that
        # follows answers for the access itself.
        restricted = False
    else:
        restricted = queue_forbids_ai(queue_data)
    context.ai_access[key] = (restricted, now + AI_ACCESS_TTL_SECONDS)
    return restricted


def _queue_of(issue_id: str) -> str:
    return issue_id.split("-")[0]


async def check_ai_access(
    ctx: Context[AppContext], settings: Settings, issue_id: str
) -> None:
    """Refuse to return the content of an issue in a queue that forbids AI tools."""
    queue = _queue_of(issue_id)
    if await is_ai_restricted(ctx, settings, queue):
        raise AiAccessRestricted(issue_id, queue)


async def hide_ai_restricted(
    ctx: Context[AppContext], settings: Settings, issues: list[Issue]
) -> list[Issue]:
    """Replace each issue of a forbidding queue with its key and `restricted`."""
    result: list[Issue] = []
    for issue in issues:
        # The key names the queue; `issues_find` asks for it even under a
        # projection that leaves it out, so that this check can be made.
        queue = _queue_of(issue.key or "")
        if queue and await is_ai_restricted(ctx, settings, queue):
            # `restricted` is not a field of the model: it goes in as an extra key,
            # which the model keeps (extra="allow").
            result.append(Issue.model_validate({"key": issue.key, "restricted": True}))
        else:
            result.append(issue)
    return result


def is_restricted_row(issue: Issue) -> bool:
    """Whether the row is a placeholder `hide_ai_restricted` put in."""
    return (issue.model_extra or {}).get("restricted") is True
