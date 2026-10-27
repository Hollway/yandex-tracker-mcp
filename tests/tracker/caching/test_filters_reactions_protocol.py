"""Caching wrappers of saved filters, comment reactions, suggest, queue forms
and trigger delete."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_tracker.tracker.caching.client import make_cached_protocols
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.filters import FilterSort

SORTS = [FilterSort(field="created", isAscending=False)]

# (protocol, method, positional args, keyword args) - every wrapper passes them
# through.
CALLS: list[tuple[str, str, tuple[Any, ...], dict[str, Any]]] = [
    ("issues", "filter_get", (10,), {}),
    (
        "issues",
        "filter_create",
        (),
        {
            "name": "F",
            "query": "Queue: Q",
            "filter": None,
            "sorts": SORTS,
            "fields": ["key"],
        },
    ),
    (
        "issues",
        "filter_update",
        (10,),
        {
            "name": None,
            "query": None,
            "filter": {"queue": "Q"},
            "sorts": None,
            "fields": None,
        },
    ),
    ("issues", "filter_delete", (10,), {}),
    ("issues", "issue_add_comment_reaction", ("Q-1", 5, "LIKE"), {}),
    ("issues", "issue_delete_comment_reaction", ("Q-1", "abc", "FIRE"), {}),
    ("issues", "issues_suggest", ("text",), {}),
    ("queues", "queue_delete_trigger", ("Q", 15), {}),
    ("queues", "queue_get_forms", ("Q",), {}),
]


@pytest.fixture
def mock_original() -> AsyncMock:
    return AsyncMock()


def wrap(protocol: str, original: AsyncMock) -> Any:
    return getattr(make_cached_protocols({"ttl": 300}), protocol)(original)


@pytest.mark.parametrize(
    ("protocol", "method", "args", "kwargs"), CALLS, ids=[call[1] for call in CALLS]
)
async def test_passes_the_call_through(
    mock_original: AsyncMock,
    yandex_auth: YandexAuth,
    protocol: str,
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    wrapped = wrap(protocol, mock_original)

    result = await getattr(wrapped, method)(*args, **kwargs, auth=yandex_auth)

    getattr(mock_original, method).assert_called_once_with(
        *args, **kwargs, auth=yandex_auth
    )
    assert result is getattr(mock_original, method).return_value


@pytest.mark.parametrize(
    ("protocol", "method", "args", "calls"),
    [
        # A filter changed through filter_update is read back right after.
        pytest.param("issues", "filter_get", (10,), 2, id="filter_get"),
        pytest.param("issues", "issues_suggest", ("text",), 1, id="issues_suggest"),
        pytest.param("queues", "queue_get_forms", ("Q",), 1, id="queue_get_forms"),
    ],
)
async def test_caching(
    mock_original: AsyncMock,
    protocol: str,
    method: str,
    args: tuple[Any, ...],
    calls: int,
) -> None:
    wrapped = wrap(protocol, mock_original)

    await getattr(wrapped, method)(*args)
    await getattr(wrapped, method)(*args)

    assert getattr(mock_original, method).call_count == calls
