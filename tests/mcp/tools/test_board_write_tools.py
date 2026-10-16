from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.mcp.tools import board_write
from mcp_tracker.tracker.custom.errors import SprintVersionConflict
from mcp_tracker.tracker.proto.types.boards import Sprint
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
