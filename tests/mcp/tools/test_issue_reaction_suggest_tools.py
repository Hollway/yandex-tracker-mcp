"""Comment reactions and the quick issue lookup by summary (suggest)."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.types.issues import Issue, IssueComment
from mcp_tracker.tracker.proto.types.queues import Queue
from tests.mcp.conftest import get_tool_result_content, page

REACTION_TOOLS = [
    ("issue_add_comment_reaction", "issue_add_comment_reaction"),
    ("issue_delete_comment_reaction", "issue_delete_comment_reaction"),
]


def comment() -> IssueComment:
    return IssueComment.model_validate(
        {
            "id": 64399,
            "text": "Проверка",
            "reactionsCount": {"like": 1},
            "ownReactions": ["like"],
        }
    )


def forbid_ai_for(mock_queues_protocol: AsyncMock, *keys: str) -> None:
    """Make the listed queues forbid AI tools; every other queue allows them."""

    async def queue_get(key: str, **_: Any) -> Queue:
        level = "none" if key in keys else "full"
        return Queue.model_validate({"key": key, "aiAccessLevel": level})

    mock_queues_protocol.queue_get.side_effect = queue_get
    # The listing is what tells the server some queue forbids AI tools at all.
    mock_queues_protocol.queues_list.return_value = page(
        [Queue.model_validate({"key": key, "aiAccessLevel": "none"}) for key in keys]
    )


class TestCommentReactions:
    @pytest.mark.parametrize(("tool", "method"), REACTION_TOOLS)
    async def test_passes_the_reaction(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
        tool: str,
        method: str,
    ) -> None:
        forbid_ai_for(mock_queues_protocol)
        getattr(mock_issues_protocol, method).return_value = comment()

        result = await client_session.call_tool(
            tool, {"issue_id": "TEST-1", "comment_id": 64399, "reaction": "LIKE"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["reactionsCount"] == {"like": 1}
        assert content["text"] == "Проверка"
        assert getattr(mock_issues_protocol, method).call_args.args == (
            "TEST-1",
            64399,
            "LIKE",
        )

    async def test_long_id_is_passed_as_a_string(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        forbid_ai_for(mock_queues_protocol)
        mock_issues_protocol.issue_add_comment_reaction.return_value = comment()

        await client_session.call_tool(
            "issue_add_comment_reaction",
            {
                "issue_id": "TEST-1",
                "comment_id": "6ad1d17fdc7d9f59dec682e2",
                "reaction": "OK",
            },
        )

        call = mock_issues_protocol.issue_add_comment_reaction.call_args
        assert call.args[1] == "6ad1d17fdc7d9f59dec682e2"

    async def test_unknown_reaction_is_refused(
        self, client_session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "issue_add_comment_reaction",
            {"issue_id": "TEST-1", "comment_id": 1, "reaction": "BOGUS"},
        )

        assert result.is_error
        mock_issues_protocol.issue_add_comment_reaction.assert_not_called()

    @pytest.mark.parametrize(("tool", "method"), REACTION_TOOLS)
    async def test_text_is_held_back_in_an_ai_restricted_queue(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
        tool: str,
        method: str,
    ) -> None:
        forbid_ai_for(mock_queues_protocol, "TEST")
        mock_issues_protocol.issue_get.return_value = Issue(key="TEST-1")
        getattr(mock_issues_protocol, method).return_value = comment()

        result = await client_session.call_tool(
            tool, {"issue_id": "TEST-1", "comment_id": 64399, "reaction": "LIKE"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert "text" not in content
        assert content["reactionsCount"] == {"like": 1}

    @pytest.mark.parametrize(("tool", "method"), REACTION_TOOLS)
    async def test_read_only_queue_is_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_issues_protocol: AsyncMock,
        tool: str,
        method: str,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            tool, {"issue_id": "READONLY-1", "comment_id": 1, "reaction": "LIKE"}
        )

        assert result.is_error
        assert "read-only" in str(result.content)
        getattr(mock_issues_protocol, method).assert_not_called()

    async def test_queue_outside_the_allow_list_is_refused(
        self, client_session_with_limits: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_add_comment_reaction",
            {"issue_id": "OTHER-1", "comment_id": 1, "reaction": "LIKE"},
        )

        assert result.is_error
        mock_issues_protocol.issue_add_comment_reaction.assert_not_called()

    async def test_not_registered_read_only(
        self, client_session_read_only: Client
    ) -> None:
        tools = await client_session_read_only.list_tools()
        names = {tool.name for tool in tools.tools}

        assert not names & {tool for tool, _ in REACTION_TOOLS}


def suggested(*keys: str) -> list[Issue]:
    return [Issue.model_construct(key=key, summary=f"About {key}") for key in keys]


class TestIssuesSuggest:
    async def test_returns_the_issues(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        forbid_ai_for(mock_queues_protocol)
        mock_issues_protocol.issues_suggest.return_value = suggested("ORG-14")

        result = await client_session.call_tool("issues_suggest", {"text": "Тест"})

        assert not result.is_error
        assert get_tool_result_content(result) == [
            {"key": "ORG-14", "summary": "About ORG-14"}
        ]
        assert mock_issues_protocol.issues_suggest.call_args.args == ("Тест",)

    async def test_queue_is_applied_to_the_keys(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        forbid_ai_for(mock_queues_protocol)
        mock_issues_protocol.issues_suggest.return_value = suggested(
            "SAP-1", "ORG-14", "WEB-2"
        )

        result = await client_session.call_tool(
            "issues_suggest", {"text": "test", "queue": "org"}
        )

        assert [row["key"] for row in get_tool_result_content(result)] == ["ORG-14"]

    async def test_queues_outside_the_allow_list_are_dropped(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        forbid_ai_for(mock_queues_protocol)
        mock_issues_protocol.issues_suggest.return_value = suggested(
            "OTHER-1", "ALLOWED-2"
        )

        result = await client_session_with_limits.call_tool(
            "issues_suggest", {"text": "test"}
        )

        assert [row["key"] for row in get_tool_result_content(result)] == ["ALLOWED-2"]

    async def test_ai_restricted_issues_keep_only_their_key(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        forbid_ai_for(mock_queues_protocol, "CLOSED")
        mock_issues_protocol.issues_suggest.return_value = suggested(
            "CLOSED-1", "OPEN-1"
        )

        result = await client_session.call_tool("issues_suggest", {"text": "test"})

        assert get_tool_result_content(result) == [
            {"key": "CLOSED-1", "restricted": True},
            {"key": "OPEN-1", "summary": "About OPEN-1"},
        ]

    async def test_empty_text_is_refused(
        self, client_session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool("issues_suggest", {"text": ""})

        assert result.is_error
        mock_issues_protocol.issues_suggest.assert_not_called()
