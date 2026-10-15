from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import QueueNotFound
from tests.aioresponses_utils import RequestCapture

TRIGGERS_URL = "https://api.tracker.yandex.net/v3/queues/DESIGN/triggers"


def trigger(trigger_id: int, **extra: Any) -> dict[str, Any]:
    """A trigger as the documentation shows it (`GET v3/queues/{queue}/triggers`)."""
    return {
        "id": trigger_id,
        "self": f"{TRIGGERS_URL}/{trigger_id}",
        "queue": {"id": "26", "key": "DESIGN", "display": "Design"},
        "name": f"trigger {trigger_id}",
        "order": "0.0002",
        "actions": [
            {
                "type": "Transition",
                "id": 1,
                "status": {"id": "2", "key": "needInfo", "display": "Нужна информация"},
            }
        ],
        "conditions": [
            {"type": "Or", "conditions": [{"type": "Event.comment-create"}]}
        ],
        "version": 1,
        "active": True,
        **extra,
    }


class TestQueuesGetTriggers:
    async def test_reads_conditions_and_actions(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(f"{TRIGGERS_URL}?perPage=100", payload=[trigger(16)])

            result = await tracker_client.queues_get_triggers("DESIGN")

        assert [t.id for t in result] == [16]
        assert result[0].actions is not None
        assert result[0].actions[0]["status"]["key"] == "needInfo"
        assert result[0].conditions is not None
        assert result[0].conditions[0]["type"] == "Or"

    async def test_pages_after_the_last_id(self, tracker_client: TrackerClient) -> None:
        second = RequestCapture(payload=[trigger(500)])

        with aioresponses() as m:
            m.get(
                f"{TRIGGERS_URL}?perPage=100",
                payload=[trigger(i) for i in range(1, 101)],
            )
            m.get(f"{TRIGGERS_URL}?perPage=100&id=100", callback=second.callback)

            result = await tracker_client.queues_get_triggers("DESIGN")

        assert len(result) == 101
        second.last_request.assert_params({"perPage": 100, "id": 100})

    async def test_webhook_secrets_are_left_out(
        self, tracker_client: TrackerClient
    ) -> None:
        webhook = trigger(
            7,
            actions=[
                {
                    "type": "Webhook",
                    "endpoint": "https://example.com/hook",
                    "method": "POST",
                    "authContext": {"type": "basic", "login": "u", "password": "***"},
                    "headers": {"X-Token": "***"},
                    "body": "{}",
                }
            ],
        )

        with aioresponses() as m:
            m.get(f"{TRIGGERS_URL}?perPage=100", payload=[webhook])

            result = await tracker_client.queues_get_triggers("DESIGN")

        assert result[0].actions == [
            {
                "type": "Webhook",
                "endpoint": "https://example.com/hook",
                "method": "POST",
                "body": "{}",
            }
        ]

    async def test_unknown_queue(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{TRIGGERS_URL}?perPage=100", status=404)

            with pytest.raises(QueueNotFound):
                await tracker_client.queues_get_triggers("DESIGN")
