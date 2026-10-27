from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.mcp.tools import board_write
from mcp_tracker.tracker.custom.errors import (
    BoardVersionConflict,
    SprintVersionConflict,
)
from mcp_tracker.tracker.proto.types.boards import Board, BoardColumnDetail, Sprint
from mcp_tracker.tracker.proto.types.inputs import BoardColumnInput
from tests.mcp.conftest import get_tool_result_content


@pytest.fixture
def no_conflict_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry at once rather than after the seconds Tracker needs."""
    monkeypatch.setattr(
        board_write,
        "SPURIOUS_CONFLICT_WAITS",
        (0.0,) * len(board_write.SPURIOUS_CONFLICT_WAITS),
    )


class TestBoardSprintWrites:
    async def test_create(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.sprint_create.return_value = Sprint(id=4401, name="S1")

        result = await client_session.call_tool(
            "board_create_sprint",
            {
                "board_id": 3,
                "name": "S1",
                "start_date": "2026-10-19",
                "end_date": "2026-11-01",
            },
        )

        assert not result.is_error
        assert mock_boards_protocol.sprint_create.call_args.args == (3,)
        assert get_tool_result_content(result)["id"] == 4401

    async def test_update_reads_the_current_version_when_omitted(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.sprint_get.return_value = Sprint(id=4401, version=7)
        mock_boards_protocol.sprint_update.return_value = Sprint(id=4401, version=8)

        result = await client_session.call_tool(
            "board_update_sprint", {"sprint_id": 4401, "name": "S2"}
        )

        assert not result.is_error
        assert mock_boards_protocol.sprint_update.call_args.kwargs["version"] == 7

    async def test_a_given_version_skips_the_read(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.sprint_start.return_value = Sprint(id=4401)

        result = await client_session.call_tool(
            "board_start_sprint", {"sprint_id": 4401, "version": 3}
        )

        assert not result.is_error
        mock_boards_protocol.sprint_get.assert_not_called()
        assert mock_boards_protocol.sprint_start.call_args.kwargs["version"] == 3

    async def test_archive_and_delete(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.sprint_get.return_value = Sprint(id=4401, version=1)
        mock_boards_protocol.sprint_archive.return_value = Sprint(id=4401)

        archived = await client_session.call_tool(
            "board_archive_sprint", {"sprint_id": 4401}
        )
        deleted = await client_session.call_tool(
            "board_delete_sprint", {"sprint_id": 4401}
        )

        assert not archived.is_error
        assert not deleted.is_error
        mock_boards_protocol.sprint_delete.assert_called_once()

    @pytest.mark.parametrize(
        ("tool", "method", "args"),
        [
            ("board_update_sprint", "sprint_update", {"name": "S2"}),
            ("board_start_sprint", "sprint_start", {}),
            ("board_archive_sprint", "sprint_archive", {}),
        ],
    )
    async def test_a_conflict_on_a_version_read_here_is_retried(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
        no_conflict_waits: None,
        tool: str,
        method: str,
        args: dict[str, Any],
    ) -> None:
        mock_boards_protocol.sprint_get.side_effect = [
            Sprint(id=4401, version=3),
            Sprint(id=4401, version=3),
        ]
        write = getattr(mock_boards_protocol, method)
        write.side_effect = [SprintVersionConflict(4401, 3), Sprint(id=4401, version=4)]

        result = await client_session.call_tool(tool, {"sprint_id": 4401, **args})

        assert not result.is_error
        assert write.await_count == 2
        assert mock_boards_protocol.sprint_get.await_count == 2
        assert get_tool_result_content(result)["version"] == 4

    async def test_the_retries_end_with_the_conflict(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
        no_conflict_waits: None,
    ) -> None:
        mock_boards_protocol.sprint_get.return_value = Sprint(id=4401, version=3)
        mock_boards_protocol.sprint_start.side_effect = SprintVersionConflict(4401, 3)

        result = await client_session.call_tool(
            "board_start_sprint", {"sprint_id": 4401}
        )

        assert result.is_error
        error = result.content[0]
        assert isinstance(error, TextContent)
        assert "Editing conflict for sprint '4401'" in error.text
        attempts = len(board_write.SPURIOUS_CONFLICT_WAITS) + 1
        assert mock_boards_protocol.sprint_start.await_count == attempts

    async def test_a_conflict_on_the_callers_version_is_not_retried(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
        no_conflict_waits: None,
    ) -> None:
        mock_boards_protocol.sprint_archive.side_effect = SprintVersionConflict(4401, 2)

        result = await client_session.call_tool(
            "board_archive_sprint", {"sprint_id": 4401, "version": 2}
        )

        assert result.is_error
        assert mock_boards_protocol.sprint_archive.await_count == 1
        mock_boards_protocol.sprint_get.assert_not_called()

    async def test_an_invalid_status_is_rejected(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "board_update_sprint", {"sprint_id": 4401, "status": "done"}
        )

        assert result.is_error
        mock_boards_protocol.sprint_update.assert_not_called()


class TestBoardWrites:
    async def test_create_passes_everything(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.board_create.return_value = Board(id=163, name="B")

        result = await client_session.call_tool(
            "board_create",
            {
                "name": "B",
                "columns": [{"name": "To Do", "statuses": ["open"], "limit": 2}],
                "auto_filter": {"queue": ["DEV"]},
                "owner": "i.ivanov",
                "private": True,
                "sprints": True,
            },
        )

        assert not result.is_error
        kwargs = mock_boards_protocol.board_create.call_args.kwargs
        assert kwargs["columns"] == [
            BoardColumnInput(name="To Do", statuses=["open"], limit=2)
        ]
        assert kwargs["auto_filter"] == {"queue": ["DEV"]}
        assert (kwargs["owner"], kwargs["private"], kwargs["sprints"]) == (
            "i.ivanov",
            True,
            True,
        )
        assert get_tool_result_content(result)["id"] == 163

    async def test_create_defaults_to_nothing_but_the_name(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.board_create.return_value = Board(id=163, name="B")

        result = await client_session.call_tool("board_create", {"name": "B"})

        assert not result.is_error
        kwargs = mock_boards_protocol.board_create.call_args.kwargs
        assert kwargs["name"] == "B"
        assert [kwargs[k] for k in ("columns", "auto_filter", "owner")] == [None] * 3

    async def test_a_column_limit_must_be_positive(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "board_create",
            {"name": "B", "columns": [{"name": "X", "statuses": [], "limit": 0}]},
        )

        assert result.is_error
        mock_boards_protocol.board_create.assert_not_called()

    @pytest.mark.parametrize("version", [None, 4])
    async def test_update_passes_the_version_through(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
        version: int | None,
    ) -> None:
        mock_boards_protocol.board_update.return_value = Board(id=163, version=5)
        args: dict[str, Any] = {"board_id": 163, "name": "N"}
        if version is not None:
            args["version"] = version

        result = await client_session.call_tool("board_update", args)

        assert not result.is_error
        call = mock_boards_protocol.board_update.call_args
        assert call.args == (163,)
        assert call.kwargs["version"] == version
        assert call.kwargs["name"] == "N"

    async def test_a_conflict_reaches_the_caller(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.board_update.side_effect = BoardVersionConflict(163, 4)

        result = await client_session.call_tool(
            "board_update", {"board_id": 163, "name": "N", "version": 4}
        )

        assert result.is_error
        error = result.content[0]
        assert isinstance(error, TextContent)
        assert "Editing conflict for board '163'" in error.text

    async def test_delete(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool("board_delete", {"board_id": 163})

        assert not result.is_error
        assert mock_boards_protocol.board_delete.call_args.args == (163,)


class TestBoardColumnWrites:
    async def test_create(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.board_create_column.return_value = BoardColumnDetail(
            id=8, name="Lim", limit=2
        )

        result = await client_session.call_tool(
            "board_create_column",
            {"board_id": 163, "name": "Lim", "statuses": ["inProgress"], "limit": 2},
        )

        assert not result.is_error
        call = mock_boards_protocol.board_create_column.call_args
        assert call.args == (163,)
        assert call.kwargs["statuses"] == ["inProgress"]
        assert (call.kwargs["limit"], call.kwargs["version"]) == (2, None)
        assert get_tool_result_content(result)["id"] == 8

    async def test_update_passes_only_what_was_given(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.board_update_column.return_value = BoardColumnDetail(
            id=7, name="Done"
        )

        result = await client_session.call_tool(
            "board_update_column",
            {"board_id": 163, "column_id": 7, "name": "Done", "version": 6},
        )

        assert not result.is_error
        call = mock_boards_protocol.board_update_column.call_args
        assert call.args == (163, 7)
        assert call.kwargs["name"] == "Done"
        assert call.kwargs["version"] == 6
        assert (call.kwargs["statuses"], call.kwargs["limit"]) == (None, None)

    async def test_delete(
        self,
        client_session: Client,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "board_delete_column", {"board_id": 163, "column_id": 7}
        )

        assert not result.is_error
        call = mock_boards_protocol.board_delete_column.call_args
        assert call.args == (163, 7)
        assert call.kwargs["version"] is None
