import datetime
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import VersionEmptyUpdate, VersionNotFound
from tests.aioresponses_utils import RequestCapture

VERSION_URL = "https://api.tracker.yandex.net/v3/versions/123"


@pytest.fixture
def version_data() -> dict[str, Any]:
    """`PATCH v3/versions/{id}` as the documentation shows its answer."""
    return {
        "self": VERSION_URL,
        "id": 123,
        "version": 2,
        "queue": {"id": "1", "key": "TEST", "display": "Тестовая очередь"},
        "name": "Версия 1.1",
        "description": "Описание версии",
        "startDate": "2026-08-26",
        "dueDate": "2026-08-27",
        "released": False,
        "archived": False,
    }


class TestQueueGetVersion:
    async def test_reads_the_version_with_its_queue(
        self, tracker_client: TrackerClient, version_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(VERSION_URL, payload=version_data)

            result = await tracker_client.queue_get_version(123)

        assert result.queue is not None
        assert result.queue.key == "TEST"

    async def test_not_found(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(VERSION_URL, status=404)

            with pytest.raises(VersionNotFound):
                await tracker_client.queue_get_version(123)


class TestQueueUpdateVersion:
    async def test_sends_only_what_changes(
        self, tracker_client: TrackerClient, version_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=version_data)

        with aioresponses() as m:
            m.patch(VERSION_URL, callback=capture.callback)

            result = await tracker_client.queue_update_version(
                123, name="Версия 1.1", due_date=datetime.date(2026, 8, 27)
            )

        capture.last_request.assert_json_body(
            {"name": "Версия 1.1", "dueDate": "2026-08-27"}
        )
        assert result.name == "Версия 1.1"

    async def test_an_empty_update_is_refused_without_a_request(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses():
            with pytest.raises(VersionEmptyUpdate):
                await tracker_client.queue_update_version(123)


class TestQueueDeleteVersion:
    async def test_deletes(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(VERSION_URL, callback=capture.callback)

            await tracker_client.queue_delete_version(123)

        capture.assert_called_once()

    async def test_not_found(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.delete(VERSION_URL, status=404)

            with pytest.raises(VersionNotFound):
                await tracker_client.queue_delete_version(123)
