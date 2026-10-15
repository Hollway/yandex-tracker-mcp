from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import BulkChangeNotFound
from tests.aioresponses_utils import RequestCapture

BULK_URL = "https://api.tracker.yandex.net/v3/bulkchange"


@pytest.fixture
def created() -> dict[str, Any]:
    """`POST v3/bulkchange/_update` as the documentation shows its answer."""
    return {
        "id": "1ab23cd4e5678901abcdef00",
        "self": f"{BULK_URL}/1ab23cd4e5678901abcdef00",
        "createdAt": "2020-12-15T11:52:53.665+0000",
        "status": "CREATED",
        "statusText": "Операция массового редактирования задач создана.",
        "executionChunkPercent": 0,
        "executionIssuePercent": 0,
    }


class TestBulkChanges:
    async def test_update(
        self, tracker_client: TrackerClient, created: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=created)

        with aioresponses() as m:
            m.post(f"{BULK_URL}/_update", callback=capture.callback)

            result = await tracker_client.issues_bulk_update(
                ["TEST-1", "TEST-2"], values={"priority": "minor"}
            )

        capture.last_request.assert_json_body(
            {"issues": ["TEST-1", "TEST-2"], "values": {"priority": "minor"}}
        )
        assert not capture.last_request.params
        assert (result.id, result.status) == ("1ab23cd4e5678901abcdef00", "CREATED")

    async def test_transition_with_notify(
        self, tracker_client: TrackerClient, created: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=created)

        with aioresponses() as m:
            m.post(f"{BULK_URL}/_transition?notify=true", callback=capture.callback)

            await tracker_client.issues_bulk_transition(
                ["TEST-1"],
                transition="close",
                values={"resolution": "fixed"},
                notify=True,
            )

        capture.last_request.assert_param("notify", "true")
        capture.last_request.assert_json_body(
            {
                "transition": "close",
                "issues": ["TEST-1"],
                "values": {"resolution": "fixed"},
            }
        )

    async def test_move_sends_the_flags_in_the_body(
        self, tracker_client: TrackerClient, created: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=created)

        with aioresponses() as m:
            m.post(f"{BULK_URL}/_move", callback=capture.callback)

            await tracker_client.issues_bulk_move(
                ["TEST-1"], queue="CHECK", move_all_fields=True, initial_status=True
            )

        capture.last_request.assert_json_body(
            {
                "queue": "CHECK",
                "issues": ["TEST-1"],
                "moveAllFields": True,
                "initialStatus": True,
            }
        )

    async def test_status_and_failures(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{BULK_URL}/abc",
                payload={
                    "id": "abc",
                    "status": "FAILED",
                    "statusText": "Изменения не выполнены",
                    "totalIssues": 24,
                    "totalCompletedIssues": 0,
                },
            )
            m.get(
                f"{BULK_URL}/abc/issues",
                payload=[
                    {
                        "issue": {"key": "TEST-1", "display": "My issue"},
                        "status": "FAILED",
                        "statusText": "Изменения не выполнены",
                        "error": {
                            "errors": {"resolution": "нельзя"},
                            "errorMessages": [],
                        },
                    }
                ],
            )

            change = await tracker_client.bulk_change_get("abc")
            failures = await tracker_client.bulk_change_get_failures("abc")

        assert (change.total_issues, change.total_completed_issues) == (24, 0)
        assert failures[0].issue is not None
        assert failures[0].issue.key == "TEST-1"
        assert failures[0].error == {
            "errors": {"resolution": "нельзя"},
            "errorMessages": [],
        }

    async def test_unknown_change(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BULK_URL}/abc", status=404)

            with pytest.raises(BulkChangeNotFound):
                await tracker_client.bulk_change_get("abc")
