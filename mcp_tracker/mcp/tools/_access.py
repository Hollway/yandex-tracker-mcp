"""Access control helpers for MCP tools."""

import re

from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import (
    ComponentNotFound,
    IssueNotFound,
    VersionNotFound,
    WorkflowNotFound,
)
from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.queues import QueueVersion


def _is_read_only_queue(settings: Settings, queue: str) -> bool:
    """Return True if the given queue is configured as read-only."""
    return bool(
        settings.tracker_read_only_queues
        and queue.upper() in settings.tracker_read_only_queues
    )


def is_queue_allowed(settings: Settings, queue: str) -> bool:
    """Return True if the queue is reachable under ``TRACKER_LIMIT_QUEUES``.

    The raising `check_*_access` helpers below and the tools that filter whole
    listings share this one definition of the allow-list. Both settings hold a
    set of upper-cased keys (see `Settings.decode_queue_keys`), so the casing of
    the configuration does not matter and the check stays a hash lookup - which
    is what a listing tool does per row.
    """
    return (
        not settings.tracker_limit_queues
        or queue.upper() in settings.tracker_limit_queues
    )


def _check_scoped_queue(
    settings: Settings, queue: str, *, not_found: Exception, write: bool
) -> None:
    """The one check behind every `check_*_access` helper.

    Raises ``not_found`` for a queue outside ``TRACKER_LIMIT_QUEUES`` and, for
    a ``write``, rejects a queue listed in ``TRACKER_READ_ONLY_QUEUES``.
    """
    if not is_queue_allowed(settings, queue):
        raise not_found
    if write and _is_read_only_queue(settings, queue):
        raise TrackerError(
            f"Queue `{queue}` is read-only; write operations are not allowed."
        )


_ISSUE_KEY = re.compile(r"([A-Za-z][A-Za-z0-9_]*)-\d+")


def queue_of_key(issue_id: str) -> str | None:
    """The queue an issue key names, upper-cased: `queue-12` -> `QUEUE`.

    `None` for anything that is not a key - Tracker also takes an issue's
    internal id (`6ad1d166dc7d9f59dec67d79`), which names no queue at all.
    """
    match = _ISSUE_KEY.fullmatch(issue_id.strip())
    return match.group(1).upper() if match else None


def check_issue_access(
    settings: Settings, issue_id: str, *, write: bool = False
) -> None:
    """Check access to an issue through the queue its key names.

    An internal id names no queue, so under a restriction it is refused rather
    than let through - taking the id itself for the queue used to let a write
    past ``TRACKER_READ_ONLY_QUEUES``. An old key of a moved issue still names
    its old queue; `check_issue` in `_issue_access.py` reads the issue for the
    queue it is in now, and is what a tool acting on one issue calls.
    """
    queue = queue_of_key(issue_id)
    if queue is None:
        if queue_checks_needed(settings, write=write):
            raise TrackerError(
                f"`{issue_id}` is not an issue key like QUEUE-123, so the queue "
                f"restrictions cannot be checked; pass the issue key."
            )
        return
    _check_scoped_queue(settings, queue, not_found=IssueNotFound(issue_id), write=write)


def check_issue_queue_access(
    settings: Settings, issue_id: str, queue: str, *, write: bool = False
) -> None:
    """`check_issue_access` against a queue known otherwise than from the id -
    the one the issue was read back under."""
    _check_scoped_queue(settings, queue, not_found=IssueNotFound(issue_id), write=write)


def check_fetched_issue_access(
    settings: Settings, issue_id: str, issue_key: str | None
) -> None:
    """Check ``TRACKER_LIMIT_QUEUES`` against the key Tracker answered with.

    Tracker serves an issue moved to another queue under its old key too, so
    the key the caller passed can name a queue the issue has left. An issue
    that came back without a key is refused under ``TRACKER_LIMIT_QUEUES``.
    """
    queue = queue_of_key(issue_key or "")
    if queue is None:
        if settings.tracker_limit_queues:
            raise TrackerError(
                f"Issue `{issue_id}` came back without a key, so its queue cannot "
                f"be checked against the queue restrictions; refusing."
            )
        return
    if not is_queue_allowed(settings, queue):
        raise IssueNotFound(issue_id)


def check_queue_access(
    settings: Settings, queue_id: str, *, write: bool = False
) -> None:
    """Check access to a queue named by the caller."""
    _check_scoped_queue(
        settings,
        queue_id,
        not_found=TrackerError(f"Queue `{queue_id}` not found or not allowed."),
        write=write,
    )


def queue_checks_needed(settings: Settings, *, write: bool) -> bool:
    """Whether a tool has to learn an entity's queue before acting on it.

    True when ``TRACKER_LIMIT_QUEUES`` is set, or - for a write - when
    ``TRACKER_READ_ONLY_QUEUES`` is. A tool whose argument names no queue (a
    component id, say) needs an extra read to find the queue to check, and
    on an unrestricted server that read buys nothing.
    """
    if settings.tracker_limit_queues:
        return True
    return write and bool(settings.tracker_read_only_queues)


def check_component_access(
    settings: Settings, component: Component, *, write: bool = False
) -> None:
    """Check access to a component through the queue it belongs to.

    A no-op unless `queue_checks_needed`. A component whose response carries
    no queue key cannot be checked, so under a restriction it is refused
    rather than let through. One in a queue outside ``TRACKER_LIMIT_QUEUES``
    raises `ComponentNotFound`, one in a read-only queue is rejected for a
    write with the queue named, as `check_queue_access` does.
    """
    if not queue_checks_needed(settings, write=write):
        return

    queue_key = component.queue.key if component.queue is not None else None
    if queue_key is None:
        raise TrackerError(
            f"Component `{component.id}` names no queue, so its access cannot be "
            f"checked against the queue restrictions; refusing."
        )

    # The caller knows the component by id alone, and the key came from the
    # API: a queue the allow-list hides must not be named back at them.
    _check_scoped_queue(
        settings, queue_key, not_found=ComponentNotFound(component.id), write=write
    )


def check_version_access(
    settings: Settings, version: QueueVersion, *, write: bool = False
) -> None:
    """Check access to a queue version through its queue, as
    `check_component_access` does for a component: a version outside
    ``TRACKER_LIMIT_QUEUES`` raises `VersionNotFound`, one with no queue key is
    refused under a restriction."""
    if not queue_checks_needed(settings, write=write):
        return

    queue_key = version.queue.key if version.queue is not None else None
    if queue_key is None:
        raise TrackerError(
            f"Version `{version.id}` names no queue, so its access cannot be "
            f"checked against the queue restrictions; refusing."
        )
    _check_scoped_queue(
        settings, queue_key, not_found=VersionNotFound(version.id), write=write
    )


def check_workflow_access(
    settings: Settings,
    workflow_id: str,
    queue_key: str | None,
    *,
    write: bool = False,
) -> None:
    """Check access to a workflow through the queue it is bound to.

    A no-op unless `queue_checks_needed`. One bound to a queue outside
    ``TRACKER_LIMIT_QUEUES`` raises `WorkflowNotFound`, one bound to a
    read-only queue is rejected for a write. A shared workflow (bound to no
    queue) can be read - it carries no issue data - but not written under a
    restriction: it may run queues the restriction keeps out of reach.
    """
    if not queue_checks_needed(settings, write=write):
        return
    if queue_key is None:
        if write:
            raise TrackerError(
                f"Workflow `{workflow_id}` is shared - bound to no queue - and may "
                f"run queues outside the ones this server may change; refusing."
            )
        return
    _check_scoped_queue(
        settings, queue_key, not_found=WorkflowNotFound(workflow_id), write=write
    )
