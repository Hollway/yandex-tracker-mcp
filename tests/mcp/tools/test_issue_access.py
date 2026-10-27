"""`check_issue`: a tool acting on one issue is checked against the queue the
issue is in now - Tracker serves a moved issue under its old key too - and the
issue is read for it only when that can change the answer."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.server import create_mcp_server
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import TrackerRateLimited
from mcp_tracker.tracker.proto.types.issues import Issue
from mcp_tracker.tracker.proto.types.queues import Queue
from tests.mcp.conftest import (
    create_test_settings,
    make_test_lifespan,
    page,
    safe_client_session,
)

INTERNAL_ID = "6ad1d166dc7d9f59dec67d79"

Connect = Callable[[Settings], AbstractAsyncContextManager[Client]]


@pytest.fixture
def connect(mock_app_context: AppContext) -> Connect:
    @asynccontextmanager
    async def connected(settings: Settings) -> AsyncIterator[Client]:
        server = create_mcp_server(
            settings=settings, lifespan=make_test_lifespan(mock_app_context)
        )
        async with safe_client_session(server) as session:
            yield session

    return connected


def text(result: Any) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


class TestQueueRestrictions:
    async def test_a_read_by_the_old_key_of_an_issue_moved_out_is_not_found(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="HIDDEN-7")

        async with connect(create_test_settings(limit_queues=["ALLOWED"])) as session:
            result = await session.call_tool(
                "issue_get_comments", {"issue_id": "ALLOWED-1"}
            )

        assert result.is_error
        assert "HIDDEN" not in text(result)
        mock_issues_protocol.issue_get_comments.assert_not_called()

    async def test_a_write_by_the_old_key_of_an_issue_moved_to_a_read_only_queue_is_refused(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="READONLY-3")

        async with connect(
            create_test_settings(read_only_queues=["READONLY"])
        ) as session:
            result = await session.call_tool(
                "issue_add_comment", {"issue_id": "TEST-1", "text": "x"}
            )

        assert result.is_error
        assert "read-only" in text(result)
        mock_issues_protocol.issue_add_comment.assert_not_called()

    async def test_an_internal_id_is_read_for_its_key(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="ALLOWED-2")
        mock_issues_protocol.issue_get_checklist.return_value = []

        async with connect(create_test_settings(limit_queues=["ALLOWED"])) as session:
            result = await session.call_tool(
                "issue_get_checklist", {"issue_id": INTERNAL_ID}
            )

        assert not result.is_error
        mock_issues_protocol.issue_get_checklist.assert_awaited_once()

    async def test_an_issue_that_has_not_moved_is_read_once(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get_checklist.return_value = []

        async with connect(create_test_settings(limit_queues=["ALLOWED"])) as session:
            result = await session.call_tool(
                "issue_get_checklist", {"issue_id": "ALLOWED-1"}
            )

        assert not result.is_error
        mock_issues_protocol.issue_get.assert_awaited_once()

    async def test_a_key_out_of_reach_is_refused_unread(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        async with connect(create_test_settings(limit_queues=["ALLOWED"])) as session:
            result = await session.call_tool(
                "issue_get_checklist", {"issue_id": "HIDDEN-1"}
            )

        assert result.is_error
        mock_issues_protocol.issue_get.assert_not_called()


class TestNothingToCheck:
    """Without queue restrictions and without a queue forbidding AI tools the
    queue an issue is in cannot change the answer, so it is not read."""

    async def test_a_read_does_not_read_the_issue(
        self,
        connect: Connect,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get_checklist.return_value = []

        async with connect(create_test_settings()) as session:
            for _ in range(2):
                result = await session.call_tool(
                    "issue_get_checklist", {"issue_id": "TEST-1"}
                )
                assert not result.is_error

        mock_issues_protocol.issue_get.assert_not_called()
        # Whether any queue forbids AI tools is remembered for ten minutes.
        mock_queues_protocol.queues_list.assert_awaited_once()

    async def test_a_read_in_a_server_with_read_only_queues_does_not_read_the_issue(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get_checklist.return_value = []

        async with connect(
            create_test_settings(read_only_queues=["READONLY"])
        ) as session:
            result = await session.call_tool(
                "issue_get_checklist", {"issue_id": "TEST-1"}
            )

        assert not result.is_error
        mock_issues_protocol.issue_get.assert_not_called()

    async def test_a_write_does_not_list_the_queues(
        self,
        connect: Connect,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_delete_checklist.return_value = []

        async with connect(create_test_settings()) as session:
            result = await session.call_tool(
                "issue_delete_checklist", {"issue_id": "TEST-1"}
            )

        assert not result.is_error
        mock_issues_protocol.issue_get.assert_not_called()
        mock_queues_protocol.queues_list.assert_not_called()


class TestAiAccess:
    @pytest.fixture(autouse=True)
    def queues(self, mock_queues_protocol: AsyncMock) -> None:
        """CLOSED forbids AI tools, OPEN allows them."""
        known = {
            "CLOSED": Queue.model_validate({"key": "CLOSED", "aiAccessLevel": "none"}),
            "OPEN": Queue.model_validate({"key": "OPEN", "aiAccessLevel": "full"}),
        }

        async def queue_get(key: str, **_: Any) -> Queue:
            return known[key]

        mock_queues_protocol.queue_get.side_effect = queue_get
        mock_queues_protocol.queues_list.return_value = page(list(known.values()))

    async def test_the_old_key_of_an_issue_moved_to_a_forbidding_queue_is_refused(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-7")

        async with connect(create_test_settings()) as session:
            result = await session.call_tool(
                "issue_get_checklist", {"issue_id": "OPEN-1"}
            )

        assert result.is_error
        assert "`CLOSED`" in text(result)
        mock_issues_protocol.issue_get_checklist.assert_not_called()

    async def test_the_listing_answers_for_the_queue_the_issue_is_in(
        self,
        connect: Connect,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-7")

        async with connect(create_test_settings()) as session:
            await session.call_tool("issue_get_checklist", {"issue_id": "OPEN-1"})

        # OPEN is read for the key passed; CLOSED came with the listing.
        assert [c.args[0] for c in mock_queues_protocol.queue_get.await_args_list] == [
            "OPEN"
        ]

    async def test_transitions_carry_no_content(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-7")
        mock_issues_protocol.issue_get_transitions.return_value = []

        async with connect(create_test_settings()) as session:
            result = await session.call_tool(
                "issue_get_transitions", {"issue_id": "OPEN-1"}
            )

        assert not result.is_error
        mock_issues_protocol.issue_get.assert_not_called()

    async def test_an_ignored_queue_does_not_count(
        self, connect: Connect, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get_checklist.return_value = []
        settings = create_test_settings().model_copy(
            update={"tracker_ai_access_ignored_queues": {"CLOSED"}}
        )

        async with connect(settings) as session:
            result = await session.call_tool(
                "issue_get_checklist", {"issue_id": "OPEN-1"}
            )

        assert not result.is_error
        mock_issues_protocol.issue_get.assert_not_called()

    async def test_a_failed_listing_is_raised_and_not_remembered(
        self,
        connect: Connect,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queues_list.side_effect = TrackerRateLimited(
            method="GET", url="v3/queues", body="", retries=3, retry_after=None
        )

        async with connect(create_test_settings()) as session:
            first = await session.call_tool(
                "issue_get_checklist", {"issue_id": "OPEN-1"}
            )
            second = await session.call_tool(
                "issue_get_checklist", {"issue_id": "OPEN-1"}
            )

        assert first.is_error
        assert second.is_error
        assert mock_queues_protocol.queues_list.await_count == 2
        mock_issues_protocol.issue_get_checklist.assert_not_called()
