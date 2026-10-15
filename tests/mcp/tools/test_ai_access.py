"""The queue setting «Доступ для AI инструментов» is honoured as Tracker's own MCP
server honours it: an issue of a queue that forbids AI tools is returned as its
key and `restricted`, single-issue reads are refused, writes still work."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from mcp.client.session import ClientSession
from mcp.types import TextContent

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.server import create_mcp_server
from mcp_tracker.mcp.tools._ai_access import queue_forbids_ai
from mcp_tracker.tracker.custom.errors import QueueNotFound
from mcp_tracker.tracker.proto.types.issues import Issue, IssueComment
from mcp_tracker.tracker.proto.types.queues import Queue
from tests.mcp.conftest import (
    create_test_settings,
    get_tool_result_content,
    make_test_lifespan,
    page,
    safe_client_session,
)


def queue(key: str, **settings: Any) -> Queue:
    """A queue as `GET v3/queues/{key}` answers it, with the AI settings given."""
    return Queue.model_validate({"key": key, **settings})


@pytest.fixture
def queues_by_key(mock_queues_protocol: AsyncMock) -> dict[str, Any]:
    """CLOSED forbids AI tools, OPEN allows them."""
    known = {
        "CLOSED": queue("CLOSED", aiAccessLevel="none", noMcp=False),
        "OPEN": queue("OPEN", aiAccessLevel="full", noMcp=False),
    }

    async def queue_get(key: str, **_: Any) -> Any:
        return known[key]

    mock_queues_protocol.queue_get.side_effect = queue_get
    return known


@pytest_asyncio.fixture(loop_scope="function")
async def session(
    mock_app_context: AppContext, queues_by_key: dict[str, Any]
) -> AsyncIterator[ClientSession]:
    server = create_mcp_server(
        settings=create_test_settings(),
        lifespan=make_test_lifespan(mock_app_context),
    )
    async with safe_client_session(server) as connected:
        yield connected


def text(result: Any) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


@pytest.mark.parametrize(
    ("settings", "forbids"),
    [
        pytest.param({"aiAccessLevel": "full", "noMcp": False}, False, id="full"),
        pytest.param({"aiAccessLevel": "none", "noMcp": False}, True, id="none"),
        pytest.param({"aiAccessLevel": "full", "noMcp": True}, True, id="no-mcp"),
        pytest.param({}, False, id="not-reported"),
    ],
)
def test_queue_forbids_ai(settings: dict[str, Any], forbids: bool) -> None:
    assert queue_forbids_ai(queue("Q", **settings)) is forbids


class TestSingleIssueReads:
    async def test_a_forbidding_queue_is_refused(
        self, session: ClientSession, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await session.call_tool("issue_get", {"issue_id": "CLOSED-1"})

        assert result.isError
        assert "Доступ для AI инструментов" in text(result)
        mock_issues_protocol.issue_get.assert_not_called()

    async def test_an_allowing_queue_is_read(
        self,
        session: ClientSession,
        mock_issues_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_issues_protocol.issue_get_comment.return_value = sample_comment

        result = await session.call_tool(
            "issue_get_comment", {"issue_id": "OPEN-1", "comment_id": 1}
        )

        assert not result.isError

    async def test_the_setting_is_read_once_per_queue(
        self,
        session: ClientSession,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        for _ in range(3):
            await session.call_tool("issue_get_checklist", {"issue_id": "CLOSED-1"})

        assert mock_queues_protocol.queue_get.call_count == 1

    async def test_writes_still_work(
        self,
        session: ClientSession,
        mock_issues_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_issues_protocol.issue_add_comment.return_value = sample_comment

        result = await session.call_tool(
            "issue_add_comment", {"issue_id": "CLOSED-1", "text": "x"}
        )

        assert not result.isError

    async def test_an_unreadable_queue_does_not_block(
        self,
        session: ClientSession,
        mock_queues_protocol: AsyncMock,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queue_get.side_effect = QueueNotFound("OTHER")
        mock_issues_protocol.issue_get_checklist.return_value = []

        result = await session.call_tool("issue_get_checklist", {"issue_id": "OTHER-1"})

        assert not result.isError


class TestListings:
    async def test_issues_find_keeps_only_the_key(
        self,
        session: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(
            [
                Issue(key="OPEN-1", summary="visible"),
                Issue(key="CLOSED-1", summary="secret"),
            ]
        )

        result = await session.call_tool(
            "issues_find", {"query": "Queue: OPEN, CLOSED", "fields": ["summary"]}
        )

        assert not result.isError
        values = get_tool_result_content(result)["values"]
        assert values[0]["summary"] == "visible"
        assert values[1] == {"key": "CLOSED-1", "restricted": True}

    async def test_ignored_queues_are_read(
        self,
        mock_app_context: AppContext,
        queues_by_key: dict[str, Any],
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get_checklist.return_value = []
        server = create_mcp_server(
            settings=create_test_settings().model_copy(
                update={"tracker_ai_access_ignored_queues": {"CLOSED"}}
            ),
            lifespan=make_test_lifespan(mock_app_context),
        )

        async with safe_client_session(server) as connected:
            result = await connected.call_tool(
                "issue_get_checklist", {"issue_id": "CLOSED-1"}
            )

        assert not result.isError
