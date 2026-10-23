"""Caching wrappers of the queue automation and administration methods."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_tracker.tracker.caching.client import make_cached_protocols
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.queue_automation import QueueIssueTypeConfigInput

CONFIG = [QueueIssueTypeConfigInput(issue_type="task", workflow="W1", resolutions=[])]

# (method, positional args, keyword args) - every wrapper passes them through.
CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("queue_get_trigger", ("Q", 1), {}),
    (
        "queue_create_trigger",
        ("Q",),
        {"name": "T", "actions": [], "conditions": None, "active": True},
    ),
    (
        "queue_update_trigger",
        ("Q", 1),
        {
            "version": 2,
            "name": None,
            "actions": None,
            "conditions": {"type": "Or", "conditions": []},
            "active": False,
            "before": 5,
        },
    ),
    (
        "queue_get_trigger_logs",
        ("Q", 1),
        {"issue_id": "Q-1", "limit": 5, "created_from": None, "created_to": None},
    ),
    ("queues_get_autoactions", ("Q",), {}),
    ("queue_get_autoaction", ("Q", 9), {}),
    (
        "queue_create_autoaction",
        ("Q",),
        {
            "name": "A",
            "actions": [],
            "filter": None,
            "query": "x",
            "active": None,
            "enable_notifications": None,
            "interval_millis": 60000,
            "calendar_id": None,
        },
    ),
    ("queue_get_autoaction_runs", ("Q", 9), {}),
    ("queue_get_autoaction_run", ("Q", 9, "r1"), {}),
    ("queues_get_macros", ("Q",), {}),
    ("queue_get_macro", ("Q", 3), {}),
    ("queue_create_macro", ("Q",), {"name": "M", "body": None, "issue_update": {}}),
    (
        "queue_update_macro",
        ("Q", 3),
        {"name": "M", "body": None, "issue_update": None, "clear_body": True},
    ),
    ("queue_delete_macro", ("Q", 3), {}),
    (
        "queue_create",
        (),
        {
            "key": "Q",
            "name": "N",
            "lead": "u",
            "default_type": "task",
            "default_priority": "normal",
            "issue_types_config": CONFIG,
        },
    ),
    ("queue_delete", ("Q",), {}),
    ("queue_restore", ("Q",), {}),
    ("queue_get_fresh", ("Q",), {"expand": ["issueTypesConfig"]}),
    (
        "queue_update_issue_types_config",
        ("Q",),
        {"issue_types_config": CONFIG, "default_type": None},
    ),
]

# Reads that feed a write, or whose answer is "what just happened".
UNCACHED_READS = [
    ("queue_get_trigger", ("Q", 1)),
    ("queue_get_macro", ("Q", 3)),
    ("queue_get_fresh", ("Q",)),
    ("queue_get_trigger_logs", ("Q", 1)),
    ("queue_get_autoaction_runs", ("Q", 9)),
]


@pytest.fixture
def mock_original() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def caching_queues(mock_original: AsyncMock) -> Any:
    return make_cached_protocols({"ttl": 300}).queues(mock_original)


@pytest.mark.parametrize(
    ("method", "args", "kwargs"), CALLS, ids=[call[0] for call in CALLS]
)
async def test_passes_the_call_through(
    caching_queues: Any,
    mock_original: AsyncMock,
    yandex_auth: YandexAuth,
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    result = await getattr(caching_queues, method)(*args, **kwargs, auth=yandex_auth)

    getattr(mock_original, method).assert_called_once_with(
        *args, **kwargs, auth=yandex_auth
    )
    assert result is getattr(mock_original, method).return_value


@pytest.mark.parametrize(
    ("method", "args"), UNCACHED_READS, ids=[read[0] for read in UNCACHED_READS]
)
async def test_reads_the_api_every_time(
    caching_queues: Any,
    mock_original: AsyncMock,
    method: str,
    args: tuple[Any, ...],
) -> None:
    await getattr(caching_queues, method)(*args)
    await getattr(caching_queues, method)(*args)

    assert getattr(mock_original, method).call_count == 2
