"""Saved filter tools, and searching issues by a saved filter."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.types.filters import FilterSort, IssueFilter
from mcp_tracker.tracker.proto.types.issues import Issue
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from tests.mcp.conftest import get_tool_result_content

FILTER_WRITE_TOOLS = {"filter_create", "filter_update", "filter_delete"}


@pytest.fixture
def sample_filter() -> IssueFilter:
    return IssueFilter.model_construct(id=10, name="Open", query="Queue: ORG")


class TestFilterGet:
    async def test_returns_the_filter(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_filter: IssueFilter,
    ) -> None:
        mock_issues_protocol.filter_get.return_value = sample_filter

        result = await client_session.call_tool("filter_get", {"filter_id": 10})

        assert not result.is_error
        assert get_tool_result_content(result)["query"] == "Queue: ORG"
        assert mock_issues_protocol.filter_get.call_args.args == (10,)

    async def test_not_covered_by_the_queue_allow_list(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
        sample_filter: IssueFilter,
    ) -> None:
        mock_issues_protocol.filter_get.return_value = sample_filter

        result = await client_session_with_limits.call_tool(
            "filter_get", {"filter_id": 10}
        )

        assert not result.is_error


class TestFilterWrites:
    async def test_creates_a_filter(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_filter: IssueFilter,
    ) -> None:
        mock_issues_protocol.filter_create.return_value = sample_filter

        result = await client_session.call_tool(
            "filter_create",
            {
                "name": "Open",
                "query": "Queue: ORG",
                "sorts": [{"field": "created", "isAscending": False}],
                "fields": ["key", "summary"],
            },
        )

        assert not result.is_error
        call = mock_issues_protocol.filter_create.call_args
        assert call.kwargs["name"] == "Open"
        assert call.kwargs["query"] == "Queue: ORG"
        assert call.kwargs["filter"] is None
        assert call.kwargs["sorts"] == [FilterSort(field="created", isAscending=False)]
        assert call.kwargs["fields"] == ["key", "summary"]

    async def test_updates_what_is_passed(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_filter: IssueFilter,
    ) -> None:
        mock_issues_protocol.filter_update.return_value = sample_filter

        result = await client_session.call_tool(
            "filter_update", {"filter_id": 10, "filter": {"queue": "ORG"}}
        )

        assert not result.is_error
        call = mock_issues_protocol.filter_update.call_args
        assert call.args == (10,)
        assert call.kwargs["filter"] == {"queue": "ORG"}
        assert call.kwargs["name"] is None
        assert call.kwargs["query"] is None

    async def test_deletes_a_filter(
        self, client_session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool("filter_delete", {"filter_id": 10})

        assert not result.is_error
        assert mock_issues_protocol.filter_delete.call_args.args == (10,)

    async def test_not_registered_read_only(
        self, client_session_read_only: Client
    ) -> None:
        tools = await client_session_read_only.list_tools()
        names = {tool.name for tool in tools.tools}

        assert not names & FILTER_WRITE_TOOLS
        assert "filter_get" in names


class TestSearchBySavedFilter:
    @pytest.mark.parametrize(
        ("arguments", "query", "filter_id"),
        [
            pytest.param({"filter_id": 10}, None, 10, id="filter"),
            pytest.param(
                {"filter_id": 10, "query": "Assignee: me()"},
                "Assignee: me()",
                10,
                id="both",
            ),
        ],
    )
    async def test_find_passes_the_filter(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        arguments: dict[str, Any],
        query: str | None,
        filter_id: int,
    ) -> None:
        mock_issues_protocol.issues_find.return_value = PaginatedResult[Issue](
            values=[]
        )

        result = await client_session.call_tool("issues_find", arguments)

        assert not result.is_error
        call = mock_issues_protocol.issues_find.call_args
        assert call.kwargs["query"] == query
        assert call.kwargs["filter_id"] == filter_id

    async def test_count_passes_the_filter(
        self, client_session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issues_count.return_value = 4

        result = await client_session.call_tool("issues_count", {"filter_id": 10})

        assert get_tool_result_content(result) == {"count": 4}
        call = mock_issues_protocol.issues_count.call_args
        assert call.args == (None,)
        assert call.kwargs["filter_id"] == 10

    @pytest.mark.parametrize("tool", ["issues_find", "issues_count"])
    async def test_needs_a_query_or_a_filter(
        self, client_session: Client, mock_issues_protocol: AsyncMock, tool: str
    ) -> None:
        result = await client_session.call_tool(tool, {})

        assert result.is_error
        assert "filter_id" in str(result.content)
        getattr(mock_issues_protocol, tool).assert_not_called()
