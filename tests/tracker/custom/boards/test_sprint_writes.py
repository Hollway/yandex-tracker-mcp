import datetime
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    SprintEmptyUpdate,
    SprintNotFound,
    SprintVersionConflict,
)
from tests.aioresponses_utils import RequestCapture

SPRINTS_URL = "https://api.tracker.yandex.net/v3/sprints"


@pytest.fixture
def sprint_data() -> dict[str, Any]:
    """A sprint as the documentation shows `POST v3/sprints` answering."""
    return {
        "self": f"{SPRINTS_URL}/4401",
        "id": 4401,
        "version": 2,
        "name": "New Sprint",
        "board": {"self": "https://api.tracker.yandex.net/v3/boards/3", "id": "3"},
        "status": "draft",
        "archived": False,
        "startDate": "2026-10-19",
        "endDate": "2026-11-01",
    }


class TestSprintCreate:
    async def test_sends_the_board_and_dates(
        self, tracker_client: TrackerClient, sprint_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=sprint_data)

        with aioresponses() as m:
            m.post(SPRINTS_URL, callback=capture.callback)

            result = await tracker_client.sprint_create(
                3,
                name="New Sprint",
                start_date=datetime.date(2026, 10, 19),
                end_date=datetime.date(2026, 11, 1),
            )

        capture.last_request.assert_json_body(
            {
                "name": "New Sprint",
                "board": {"id": "3"},
                "startDate": "2026-10-19",
                "endDate": "2026-11-01",
            }
        )
        assert result.id == 4401


class TestSprintUpdate:
    async def test_sends_if_match_and_only_the_changes(
        self, tracker_client: TrackerClient, sprint_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=sprint_data)

        with aioresponses() as m:
            m.patch(f"{SPRINTS_URL}/4401", callback=capture.callback)

            await tracker_client.sprint_update(4401, version=2, status="in_progress")

        capture.last_request.assert_header("If-Match", '"2"')
        capture.last_request.assert_json_body({"status": "in_progress"})

    @pytest.mark.parametrize("status", [409, 412])
    async def test_a_stale_version_is_a_conflict(
        self, tracker_client: TrackerClient, status: int
    ) -> None:
        with aioresponses() as m:
            m.patch(f"{SPRINTS_URL}/4401", status=status)

            with pytest.raises(SprintVersionConflict):
                await tracker_client.sprint_update(4401, version=1, name="x")

    async def test_an_empty_update_is_refused(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses():
            with pytest.raises(SprintEmptyUpdate):
                await tracker_client.sprint_update(4401, version=2)


class TestSprintActions:
    @pytest.mark.parametrize(
        ("method", "action"),
        [("sprint_start", "_start"), ("sprint_archive", "_archive")],
    )
    async def test_posts_the_action_with_if_match(
        self,
        tracker_client: TrackerClient,
        sprint_data: dict[str, Any],
        method: str,
        action: str,
    ) -> None:
        capture = RequestCapture(payload=sprint_data)

        with aioresponses() as m:
            m.post(f"{SPRINTS_URL}/4401/{action}", callback=capture.callback)

            await getattr(tracker_client, method)(4401, version=2)

        capture.last_request.assert_header("If-Match", '"2"')

    async def test_delete(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(f"{SPRINTS_URL}/4401", callback=capture.callback)

            await tracker_client.sprint_delete(4401)

        capture.assert_called_once()

    async def test_unknown_sprint(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{SPRINTS_URL}/4401", status=404)

            with pytest.raises(SprintNotFound):
                await tracker_client.sprint_get(4401)
