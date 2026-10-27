from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    BoardColumnEmptyUpdate,
    BoardEmptyUpdate,
    BoardNotFound,
    BoardVersionConflict,
    TrackerAPIError,
)
from mcp_tracker.tracker.proto.types.inputs import BoardColumnInput
from tests.aioresponses_utils import RequestCapture

API = "https://api.tracker.yandex.net/v3"
BOARD_URL = f"{API}/boards/163"
COLUMNS_URL = f"{BOARD_URL}/columns"


@pytest.fixture
def board_data() -> dict[str, Any]:
    """A board as `POST v3/liveBoards` answered on the live API (trimmed)."""
    return {
        "self": BOARD_URL,
        "id": 163,
        "version": 1,
        "name": "MCP temp board",
        "columns": [
            {"self": f"{COLUMNS_URL}/1", "id": "1", "display": "To Do"},
            {"self": f"{COLUMNS_URL}/2", "id": "2", "display": "Doing"},
        ],
    }


@pytest.fixture
def column_data() -> dict[str, Any]:
    """A column as the column writes answered on the live API."""
    return {
        "self": f"{COLUMNS_URL}/7",
        "id": 7,
        "name": "Closed",
        "limit": 3,
        "statuses": [
            {
                "self": f"{API}/statuses/8",
                "id": "8",
                "key": "closed",
                "display": "Закрыт",
            }
        ],
    }


class TestBoardCreate:
    async def test_posts_to_live_boards_with_the_whole_body(
        self, tracker_client: TrackerClient, board_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=board_data)

        with aioresponses() as m:
            m.post(f"{API}/liveBoards", callback=capture.callback)

            result = await tracker_client.board_create(
                name="MCP temp board",
                columns=[
                    BoardColumnInput(name="To Do", statuses=["open", "new"]),
                    BoardColumnInput(name="Doing", statuses=["inProgress"], limit=2),
                ],
                owner="i.ivanov",
                private=True,
                sprints=True,
                auto_filter={"queue": ["DEV"], "assignee": ["a", "b"]},
            )

        capture.last_request.assert_json_body(
            {
                "name": "MCP temp board",
                "columns": [
                    {"name": "To Do", "statuses": ["open", "new"]},
                    {"name": "Doing", "statuses": ["inProgress"], "limit": 2},
                ],
                "owner": "i.ivanov",
                "boardPermissionsTemplate": "private",
                "sprintsAvailable": True,
                "backlogAvailable": True,
                "autoFilters": {
                    "addFilter": {
                        "liveFilter": {
                            "fieldValues": {
                                "queue": [{"fixed": "DEV"}],
                                "assignee": [{"fixed": "a"}, {"fixed": "b"}],
                            }
                        },
                        "enabled": True,
                    }
                },
            }
        )
        assert result.id == 163

    async def test_sends_only_the_name_by_default(
        self, tracker_client: TrackerClient, board_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=board_data)

        with aioresponses() as m:
            m.post(f"{API}/liveBoards", callback=capture.callback)

            await tracker_client.board_create(name="MCP temp board")

        capture.last_request.assert_json_body({"name": "MCP temp board"})

    async def test_public_board(
        self, tracker_client: TrackerClient, board_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=board_data)

        with aioresponses() as m:
            m.post(f"{API}/liveBoards", callback=capture.callback)

            await tracker_client.board_create(name="B", private=False, sprints=False)

        capture.last_request.assert_json_body(
            {
                "name": "B",
                "boardPermissionsTemplate": "public",
                "sprintsAvailable": False,
                "backlogAvailable": False,
            }
        )


class TestBoardUpdate:
    async def test_without_version_sends_no_if_match(
        self, tracker_client: TrackerClient, board_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=board_data)

        with aioresponses() as m:
            m.patch(BOARD_URL, callback=capture.callback)

            await tracker_client.board_update(163, name="Renamed")

        assert "If-Match" not in capture.last_request.headers
        capture.last_request.assert_json_body({"name": "Renamed"})

    async def test_version_goes_as_quoted_if_match(
        self, tracker_client: TrackerClient, board_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=board_data)

        with aioresponses() as m:
            m.patch(BOARD_URL, callback=capture.callback)

            await tracker_client.board_update(
                163,
                version=4,
                columns=[BoardColumnInput(name="Closed", statuses=["closed"])],
                sprints=True,
            )

        capture.last_request.assert_header("If-Match", '"4"')
        capture.last_request.assert_json_body(
            {
                "columns": [{"name": "Closed", "statuses": ["closed"]}],
                "sprintsAvailable": True,
                "backlogAvailable": True,
            }
        )

    async def test_an_empty_update_is_refused_locally(
        self, tracker_client: TrackerClient
    ) -> None:
        with pytest.raises(BoardEmptyUpdate):
            await tracker_client.board_update(163, version=4)

    @pytest.mark.parametrize("status", [409, 412])
    async def test_a_stale_version_is_a_conflict(
        self, tracker_client: TrackerClient, status: int
    ) -> None:
        with aioresponses() as m:
            m.patch(BOARD_URL, status=status)

            with pytest.raises(BoardVersionConflict) as exc_info:
                await tracker_client.board_update(163, version=4, name="X")

        assert exc_info.value.version == 4

    async def test_unknown_board(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.patch(BOARD_URL, status=404)

            with pytest.raises(BoardNotFound):
                await tracker_client.board_update(163, name="X")


class TestBoardDelete:
    async def test_deletes(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(BOARD_URL, callback=capture.callback)

            await tracker_client.board_delete(163)

        capture.assert_called_once()

    async def test_unknown_board(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.delete(BOARD_URL, status=404)

            with pytest.raises(BoardNotFound):
                await tracker_client.board_delete(163)


class TestBoardColumns:
    async def test_get_reads_the_limit(
        self, tracker_client: TrackerClient, column_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(f"{COLUMNS_URL}/7", payload=column_data)

            column = await tracker_client.board_get_column(163, 7)

        assert column.limit == 3
        assert column.statuses is not None
        assert [s.key for s in column.statuses] == ["closed"]

    async def test_a_missing_column_passes_trackers_words_through(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(
                f"{COLUMNS_URL}/99",
                status=404,
                payload={"errorMessages": ["Колонка не существует."]},
            )

            with pytest.raises(TrackerAPIError, match="Колонка не существует"):
                await tracker_client.board_get_column(163, 99)

    async def test_create_without_version(
        self, tracker_client: TrackerClient, column_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=column_data)

        with aioresponses() as m:
            m.post(COLUMNS_URL, callback=capture.callback)

            column = await tracker_client.board_create_column(
                163, name="Closed", statuses=["closed"]
            )

        assert "If-Match" not in capture.last_request.headers
        capture.last_request.assert_json_body(
            {"name": "Closed", "statuses": ["closed"]}
        )
        assert column.id == 7

    async def test_create_with_limit_and_version(
        self, tracker_client: TrackerClient, column_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=column_data)

        with aioresponses() as m:
            m.post(COLUMNS_URL, callback=capture.callback)

            await tracker_client.board_create_column(
                163, name="Closed", statuses=["closed"], limit=3, version=9
            )

        capture.last_request.assert_header("If-Match", '"9"')
        capture.last_request.assert_json_body(
            {"name": "Closed", "statuses": ["closed"], "limit": 3}
        )

    async def test_update_sends_only_the_changes(
        self, tracker_client: TrackerClient, column_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=column_data)

        with aioresponses() as m:
            m.patch(f"{COLUMNS_URL}/7", callback=capture.callback)

            await tracker_client.board_update_column(163, 7, limit=3)

        capture.last_request.assert_json_body({"limit": 3})

    async def test_update_all_fields_with_version(
        self, tracker_client: TrackerClient, column_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=column_data)

        with aioresponses() as m:
            m.patch(f"{COLUMNS_URL}/7", callback=capture.callback)

            await tracker_client.board_update_column(
                163, 7, version=5, name="Done", statuses=["closed", "resolved"]
            )

        capture.last_request.assert_header("If-Match", '"5"')
        capture.last_request.assert_json_body(
            {"name": "Done", "statuses": ["closed", "resolved"]}
        )

    async def test_an_empty_update_is_refused_locally(
        self, tracker_client: TrackerClient
    ) -> None:
        with pytest.raises(BoardColumnEmptyUpdate):
            await tracker_client.board_update_column(163, 7)

    async def test_a_stale_version_is_a_board_conflict(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.patch(f"{COLUMNS_URL}/7", status=412)

            with pytest.raises(BoardVersionConflict) as exc_info:
                await tracker_client.board_update_column(163, 7, version=4, name="X")

        assert exc_info.value.board_id == 163

    @pytest.mark.parametrize(("version", "if_match"), [(None, None), (6, '"6"')])
    async def test_delete(
        self, tracker_client: TrackerClient, version: int | None, if_match: str | None
    ) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(f"{COLUMNS_URL}/7", callback=capture.callback)

            await tracker_client.board_delete_column(163, 7, version=version)

        assert capture.last_request.headers.get("If-Match") == if_match
