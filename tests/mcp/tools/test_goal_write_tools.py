import datetime
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.entities import GoalEntity
from mcp_tracker.tracker.proto.types.inputs import GoalKeyResultProgressInput
from mcp_tracker.tracker.proto.types.issues import IssueComment
from tests.mcp.conftest import get_tool_result_content


class TestGoalCreate:
    async def test_creates_goal(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_goal: GoalEntity,
    ) -> None:
        mock_entities_protocol.goal_create.return_value = sample_goal

        result = await client_session.call_tool("goal_create", {"summary": "New Goal"})

        assert not result.is_error
        mock_entities_protocol.goal_create.assert_called_once_with(
            summary="New Goal",
            description=None,
            lead=None,
            team_users=None,
            clients=None,
            followers=None,
            end=None,
            tags=None,
            entity_status=None,
            parent_entity=None,
            team_access=None,
            links=None,
            fields=None,
            auth=YandexAuth(),
        )
        content = get_tool_result_content(result)
        assert content["id"] == sample_goal.id

    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
    ) -> None:
        result = await client_session_read_only.call_tool(
            "goal_create", {"summary": "New Goal"}
        )

        assert result.is_error


class TestGoalUpdate:
    async def test_updates_goal(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_goal: GoalEntity,
    ) -> None:
        mock_entities_protocol.goal_update.return_value = sample_goal

        result = await client_session.call_tool(
            "goal_update",
            {"entity_id": "ghi789", "entity_status": "achieved", "comment": "done"},
        )

        assert not result.is_error
        mock_entities_protocol.goal_update.assert_called_once_with(
            "ghi789",
            summary=None,
            description=None,
            lead=None,
            team_users=None,
            clients=None,
            followers=None,
            end=None,
            tags=None,
            entity_status="achieved",
            parent_entity=None,
            team_access=None,
            comment="done",
            version=None,
            links=None,
            fields=None,
            auth=YandexAuth(),
        )

    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
    ) -> None:
        result = await client_session_read_only.call_tool(
            "goal_update", {"entity_id": "ghi789"}
        )

        assert result.is_error


class TestGoalDelete:
    async def test_deletes_goal(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
    ) -> None:
        mock_entities_protocol.goal_delete.return_value = None

        result = await client_session.call_tool("goal_delete", {"entity_id": "ghi789"})

        assert not result.is_error
        mock_entities_protocol.goal_delete.assert_called_once_with(
            "ghi789", auth=YandexAuth()
        )

    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
    ) -> None:
        result = await client_session_read_only.call_tool(
            "goal_delete", {"entity_id": "ghi789"}
        )

        assert result.is_error


class TestGoalAddComment:
    async def test_adds_comment(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_entities_protocol.goal_add_comment.return_value = sample_comment

        result = await client_session.call_tool(
            "goal_add_comment",
            {"entity_id": "ghi789", "text": "Hello", "summonees": ["user123"]},
        )

        assert not result.is_error
        mock_entities_protocol.goal_add_comment.assert_called_once_with(
            "ghi789",
            text="Hello",
            summonees=["user123"],
            maillist_summonees=None,
            auth=YandexAuth(),
        )
        content = get_tool_result_content(result)
        assert content["id"] == sample_comment.id

    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
    ) -> None:
        result = await client_session_read_only.call_tool(
            "goal_add_comment", {"entity_id": "ghi789", "text": "Hello"}
        )

        assert result.is_error


class TestGoalUpdateComment:
    async def test_updates_comment(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_entities_protocol.goal_update_comment.return_value = sample_comment

        result = await client_session.call_tool(
            "goal_update_comment",
            {"entity_id": "ghi789", "comment_id": 1, "text": "Updated"},
        )

        assert not result.is_error
        mock_entities_protocol.goal_update_comment.assert_called_once_with(
            "ghi789",
            1,
            text="Updated",
            summonees=None,
            maillist_summonees=None,
            auth=YandexAuth(),
        )
        content = get_tool_result_content(result)
        assert content["id"] == sample_comment.id

    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
    ) -> None:
        result = await client_session_read_only.call_tool(
            "goal_update_comment",
            {"entity_id": "ghi789", "comment_id": 1, "text": "Updated"},
        )

        assert result.is_error


class TestGoalDeleteComment:
    async def test_deletes_comment(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
    ) -> None:
        mock_entities_protocol.goal_delete_comment.return_value = None

        result = await client_session.call_tool(
            "goal_delete_comment", {"entity_id": "ghi789", "comment_id": 1}
        )

        assert not result.is_error
        mock_entities_protocol.goal_delete_comment.assert_called_once_with(
            "ghi789", 1, auth=YandexAuth()
        )

    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
    ) -> None:
        result = await client_session_read_only.call_tool(
            "goal_delete_comment", {"entity_id": "ghi789", "comment_id": 1}
        )

        assert result.is_error


class TestGoalAddKeyResult:
    async def test_passes_every_field(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_goal: GoalEntity,
    ) -> None:
        mock_entities_protocol.goal_add_key_result.return_value = sample_goal

        result = await client_session.call_tool(
            "goal_add_key_result",
            {
                "entity_id": "ghi789",
                "text": "Revenue",
                "type": "value",
                "assignee": "i.ivanov",
                "deadline": "2026-12-31",
                "progress": {"start": 0, "end": 100, "current": 20},
                "status": "at_risk",
            },
        )

        assert not result.is_error
        mock_entities_protocol.goal_add_key_result.assert_called_once_with(
            "ghi789",
            text="Revenue",
            type="value",
            assignee="i.ivanov",
            deadline=datetime.date(2026, 12, 31),
            progress=GoalKeyResultProgressInput(start=0, end=100, current=20),
            achieved=None,
            status="at_risk",
            auth=YandexAuth(),
        )

    async def test_rejects_unknown_type(self, client_session: Client) -> None:
        result = await client_session.call_tool(
            "goal_add_key_result",
            {"entity_id": "ghi789", "text": "x", "type": "percent"},
        )

        assert result.is_error


class TestGoalUpdateKeyResult:
    async def test_passes_only_given_fields(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_goal: GoalEntity,
    ) -> None:
        mock_entities_protocol.goal_update_key_result.return_value = sample_goal

        result = await client_session.call_tool(
            "goal_update_key_result",
            {"entity_id": "ghi789", "key_result_id": "kr1", "achieved": True},
        )

        assert not result.is_error
        mock_entities_protocol.goal_update_key_result.assert_called_once_with(
            "ghi789",
            "kr1",
            text=None,
            type=None,
            assignee=None,
            deadline=None,
            progress=None,
            achieved=True,
            status=None,
            auth=YandexAuth(),
        )


class TestGoalMoveKeyResult:
    @pytest.mark.parametrize("before", [None, "kr2"])
    async def test_passes_before(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_goal: GoalEntity,
        before: str | None,
    ) -> None:
        mock_entities_protocol.goal_move_key_result.return_value = sample_goal
        args = {"entity_id": "ghi789", "key_result_id": "kr1"}
        if before is not None:
            args["before"] = before

        result = await client_session.call_tool("goal_move_key_result", args)

        assert not result.is_error
        mock_entities_protocol.goal_move_key_result.assert_called_once_with(
            "ghi789", "kr1", before=before, auth=YandexAuth()
        )


class TestGoalDeleteKeyResults:
    async def test_deletes_one(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_goal: GoalEntity,
    ) -> None:
        mock_entities_protocol.goal_delete_key_result.return_value = sample_goal

        result = await client_session.call_tool(
            "goal_delete_key_result", {"entity_id": "ghi789", "key_result_id": "kr1"}
        )

        assert not result.is_error
        mock_entities_protocol.goal_delete_key_result.assert_called_once_with(
            "ghi789", "kr1", auth=YandexAuth()
        )
        assert get_tool_result_content(result)["id"] == sample_goal.id

    async def test_deletes_all(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        sample_goal: GoalEntity,
    ) -> None:
        mock_entities_protocol.goal_delete_all_key_results.return_value = sample_goal

        result = await client_session.call_tool(
            "goal_delete_all_key_results", {"entity_id": "ghi789"}
        )

        assert not result.is_error
        mock_entities_protocol.goal_delete_all_key_results.assert_called_once_with(
            "ghi789", auth=YandexAuth()
        )

    @pytest.mark.parametrize(
        "tool,args",
        [
            ("goal_add_key_result", {"text": "x", "type": "binary"}),
            ("goal_update_key_result", {"key_result_id": "kr1", "text": "x"}),
            ("goal_move_key_result", {"key_result_id": "kr1"}),
            ("goal_delete_key_result", {"key_result_id": "kr1"}),
            ("goal_delete_all_key_results", {}),
        ],
    )
    async def test_not_registered_read_only(
        self, client_session_read_only: Client, tool: str, args: dict[str, str]
    ) -> None:
        result = await client_session_read_only.call_tool(
            tool, {"entity_id": "ghi789", **args}
        )

        assert result.is_error
