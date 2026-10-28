"""The access checks of a tool acting on one issue.

The queue restrictions and the AI tools access setting are per queue, and an
issue id names its queue only by its key - which, for an issue moved to another
queue, is still the old one: Tracker serves a moved issue under its old key too.
`check_issue` reads the issue for the queue it is in now whenever that can
change the answer, and only then.
"""

from mcp.server.mcpserver import Context

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.tools._access import (
    check_issue_access,
    check_issue_queue_access,
    queue_checks_needed,
    queue_of_key,
)
from mcp_tracker.mcp.tools._ai_access import (
    AiAccessRestricted,
    ai_forbidden_anywhere,
    check_ai_access,
    is_ai_restricted,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings


async def check_issue(
    ctx: Context[AppContext],
    settings: Settings,
    issue_id: str,
    *,
    write: bool = False,
    ai: bool = True,
) -> bool:
    """Check a read (or a ``write``) of one issue against the queue restrictions
    and - when the answer carries the issue's content (``ai``) - against the AI
    tools access setting: a read of an issue whose queue forbids AI tools is
    refused, a write goes through and gets True back, telling the tool to leave
    the content out of its answer.

    A key is checked as it is first, so a queue it names that is out of reach is
    refused without a request. The issue is then read for its current key only
    when the queue restrictions apply to the call or some queue forbids AI tools
    (`ai_forbidden_anywhere`, one listing every ten minutes): on a server with
    neither, an issue's queue cannot change the answer and costs nothing. An
    internal id, which names no queue, is checked the same way.
    """
    queue = queue_of_key(issue_id)
    if queue is not None:
        check_issue_access(settings, issue_id, write=write)
        if ai and not write:
            await check_ai_access(ctx, settings, issue_id)

    restricted = queue_checks_needed(settings, write=write)
    check_ai = ai and await ai_forbidden_anywhere(ctx, settings)
    if not restricted and not check_ai:
        return False

    issue = await ctx.request_context.lifespan_context.issues.issue_get(
        issue_id, auth=get_yandex_auth(ctx)
    )
    current = queue_of_key(issue.key or "")
    if current is None:
        if restricted:
            raise TrackerError(
                f"Issue `{issue_id}` came back without a key, so its queue cannot "
                f"be checked against the queue restrictions; refusing."
            )
        return False
    if current != queue:
        check_issue_queue_access(settings, issue_id, current, write=write)
    hidden = check_ai and await is_ai_restricted(ctx, settings, current)
    if hidden and not write:
        raise AiAccessRestricted(issue_id, current)
    return hidden
