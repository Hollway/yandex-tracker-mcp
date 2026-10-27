import datetime
import re
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    EntityItemEmptyUpdate,
    EntityItemNotFound,
)
from mcp_tracker.tracker.proto.types.inputs import GoalKeyResultProgressInput
from tests.aioresponses_utils import RequestCapture

GOAL_URL = re.compile(r"^https://api\.tracker\.yandex\.net/v3/entities/goal/g1(\?.*)?$")

REVENUE = {
    "id": "kr1",
    "type": "value",
    "text": "Revenue",
    "assignee": {"id": "42", "display": "Lead"},
    "deadline": {
        "date": "2026-12-31T00:00:00.000+0000",
        "deadlineType": "date",
        "isExceeded": False,
    },
    "progress": {"start": 0.0, "end": 100.0, "current": 20.0},
    "status": {"id": "at_risk", "display": "Есть риски"},
}
LAUNCH = {
    "id": "kr2",
    "type": "binary",
    "text": "Launch",
    "achieved": False,
    "status": {"id": "draft", "display": "Новый"},
}
# The same two as a write takes them: no id, references by id, the status by key.
REVENUE_DRAFT = {
    "type": "value",
    "text": "Revenue",
    "assignee": "42",
    "deadline": {"date": "2026-12-31", "deadlineType": "date"},
    "progress": {"start": 0.0, "end": 100.0, "current": 20.0},
    "status": "at_risk",
}
LAUNCH_DRAFT = {
    "type": "binary",
    "text": "Launch",
    "achieved": False,
    "status": "draft",
}


def goal(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "g1",
        "entityType": "goal",
        "fields": {"keyResultItems": items, "progressPercentage": 0.1},
    }


class TestGoalAddKeyResult:
    async def test_sends_add(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=goal([REVENUE]))

        with aioresponses() as m:
            m.patch(GOAL_URL, callback=capture.callback)
            result = await tracker_client.goal_add_key_result(
                "g1",
                text="Revenue",
                type="value",
                assignee="42",
                deadline=datetime.date(2026, 12, 31),
                progress=GoalKeyResultProgressInput(start=0, end=100, current=20),
                status="at_risk",
            )

        capture.last_request.assert_param("fields", "keyResultItems,progressPercentage")
        capture.last_request.assert_json_body(
            {
                "fields": {
                    "keyResultItems": {
                        "add": {
                            "type": "value",
                            "text": "Revenue",
                            "assignee": "42",
                            "deadline": {"date": "2026-12-31", "deadlineType": "date"},
                            "progress": {"start": 0, "end": 100, "current": 20},
                            "status": "at_risk",
                        }
                    }
                }
            }
        )
        assert result.fields is not None
        assert result.fields.keyResultItems is not None
        status = result.fields.keyResultItems[0].status
        assert status is not None
        assert status.id == "at_risk"

    async def test_sends_only_given_fields(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=goal([LAUNCH]))

        with aioresponses() as m:
            m.patch(GOAL_URL, callback=capture.callback)
            await tracker_client.goal_add_key_result("g1", text="Launch", type="binary")

        capture.last_request.assert_json_body(
            {
                "fields": {
                    "keyResultItems": {"add": {"type": "binary", "text": "Launch"}}
                }
            }
        )


class TestGoalUpdateKeyResult:
    async def test_rewrites_the_list_with_the_change(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=goal([REVENUE, LAUNCH]))

        with aioresponses() as m:
            m.get(GOAL_URL, payload=goal([REVENUE, LAUNCH]))
            m.patch(GOAL_URL, callback=capture.callback)
            await tracker_client.goal_update_key_result(
                "g1",
                "kr1",
                text="Revenue, %",
                progress=GoalKeyResultProgressInput(current=60),
            )

        capture.last_request.assert_json_body(
            {
                "fields": {
                    "keyResultItems": [
                        {
                            **REVENUE_DRAFT,
                            "text": "Revenue, %",
                            "progress": {"start": 0.0, "end": 100.0, "current": 60},
                        },
                        LAUNCH_DRAFT,
                    ]
                }
            }
        )

    async def test_achieved_lets_tracker_derive_the_status(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=goal([LAUNCH]))

        with aioresponses() as m:
            m.get(GOAL_URL, payload=goal([LAUNCH]))
            m.patch(GOAL_URL, callback=capture.callback)
            await tracker_client.goal_update_key_result("g1", "kr2", achieved=True)

        sent = capture.last_request.get_json_body()["fields"]["keyResultItems"]
        assert sent == [{"type": "binary", "text": "Launch", "achieved": True}]

    async def test_explicit_status_wins(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=goal([LAUNCH]))

        with aioresponses() as m:
            m.get(GOAL_URL, payload=goal([LAUNCH]))
            m.patch(GOAL_URL, callback=capture.callback)
            await tracker_client.goal_update_key_result(
                "g1", "kr2", achieved=True, status="exceeded"
            )

        sent = capture.last_request.get_json_body()["fields"]["keyResultItems"]
        assert sent[0]["status"] == "exceeded"

    async def test_unknown_id_is_refused(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(GOAL_URL, payload=goal([REVENUE]))
            with pytest.raises(EntityItemNotFound, match="No key result 'nope'"):
                await tracker_client.goal_update_key_result("g1", "nope", text="x")

    async def test_empty_update_is_refused(self, tracker_client: TrackerClient) -> None:
        with pytest.raises(EntityItemEmptyUpdate):
            await tracker_client.goal_update_key_result("g1", "kr1")


class TestGoalMoveKeyResult:
    @pytest.mark.parametrize(
        "key_result_id,before,expected",
        [
            ("kr1", None, [LAUNCH_DRAFT, REVENUE_DRAFT]),
            ("kr2", "kr1", [LAUNCH_DRAFT, REVENUE_DRAFT]),
            ("kr2", None, [REVENUE_DRAFT, LAUNCH_DRAFT]),
        ],
    )
    async def test_rewrites_in_the_new_order(
        self,
        tracker_client: TrackerClient,
        key_result_id: str,
        before: str | None,
        expected: list[dict[str, Any]],
    ) -> None:
        capture = RequestCapture(payload=goal([LAUNCH, REVENUE]))

        with aioresponses() as m:
            m.get(GOAL_URL, payload=goal([REVENUE, LAUNCH]))
            m.patch(GOAL_URL, callback=capture.callback)
            await tracker_client.goal_move_key_result(
                "g1", key_result_id, before=before
            )

        capture.last_request.assert_json_body({"fields": {"keyResultItems": expected}})

    async def test_unknown_before_is_refused(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(GOAL_URL, payload=goal([REVENUE, LAUNCH]))
            with pytest.raises(EntityItemNotFound, match="'nope'"):
                await tracker_client.goal_move_key_result("g1", "kr1", before="nope")


class TestGoalDeleteKeyResult:
    async def test_removes_by_id(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=goal([LAUNCH]))

        with aioresponses() as m:
            m.get(GOAL_URL, payload=goal([REVENUE, LAUNCH]))
            m.patch(GOAL_URL, callback=capture.callback)
            await tracker_client.goal_delete_key_result("g1", "kr1")

        capture.last_request.assert_json_body(
            {"fields": {"keyResultItems": {"remove": {"id": "kr1"}}}}
        )

    @pytest.mark.parametrize(
        "payload",
        [goal([]), {"id": "g1", "entityType": "goal"}],
        ids=["empty", "no-fields"],
    )
    async def test_unknown_id_is_refused(
        self, tracker_client: TrackerClient, payload: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(GOAL_URL, payload=payload)
            with pytest.raises(EntityItemNotFound):
                await tracker_client.goal_delete_key_result("g1", "kr1")


class TestGoalDeleteAllKeyResults:
    async def test_sends_null(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=goal([]))

        with aioresponses() as m:
            m.patch(GOAL_URL, callback=capture.callback)
            result = await tracker_client.goal_delete_all_key_results("g1")

        capture.last_request.assert_json_body({"fields": {"keyResultItems": None}})
        assert result.fields is not None
        assert result.fields.keyResultItems == []
