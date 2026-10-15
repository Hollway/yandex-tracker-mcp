from unittest.mock import AsyncMock

from mcp.client.session import ClientSession

from mcp_tracker.tracker.proto.types.boards import Sprint
from tests.mcp.conftest import get_tool_result_content


class TestBoardSprintWrites:
    async def test_create(
        self,
        client_session: ClientSession,
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

        assert not result.isError
        assert mock_boards_protocol.sprint_create.call_args.args == (3,)
        assert get_tool_result_content(result)["id"] == 4401

    async def test_update_reads_the_current_version_when_omitted(
        self,
        client_session: ClientSession,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.sprint_get.return_value = Sprint(id=4401, version=7)
        mock_boards_protocol.sprint_update.return_value = Sprint(id=4401, version=8)

        result = await client_session.call_tool(
            "board_update_sprint", {"sprint_id": 4401, "name": "S2"}
        )

        assert not result.isError
        assert mock_boards_protocol.sprint_update.call_args.kwargs["version"] == 7

    async def test_a_given_version_skips_the_read(
        self,
        client_session: ClientSession,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        mock_boards_protocol.sprint_start.return_value = Sprint(id=4401)

        result = await client_session.call_tool(
            "board_start_sprint", {"sprint_id": 4401, "version": 3}
        )

        assert not result.isError
        mock_boards_protocol.sprint_get.assert_not_called()
        assert mock_boards_protocol.sprint_start.call_args.kwargs["version"] == 3

    async def test_archive_and_delete(
        self,
        client_session: ClientSession,
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

        assert not archived.isError
        assert not deleted.isError
        mock_boards_protocol.sprint_delete.assert_called_once()

    async def test_an_invalid_status_is_rejected(
        self,
        client_session: ClientSession,
        mock_boards_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "board_update_sprint", {"sprint_id": 4401, "status": "done"}
        )

        assert result.isError
        mock_boards_protocol.sprint_update.assert_not_called()
