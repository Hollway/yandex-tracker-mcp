"""Triggers, autoactions, macros and queue administration on the HTTP layer.

Payloads follow the API reference (Автоматизация / Очереди); nothing here was
checked against the live API except where AGENTS.md says so.
"""

import datetime
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom import client as client_module
from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    AutoactionNotFound,
    FieldClearConflict,
    MacroNotFound,
    QueueNotFound,
    TrackerAPIError,
    TriggerEmptyUpdate,
    TriggerNotFound,
    TriggerVersionConflict,
)
from mcp_tracker.tracker.proto.types.queue_automation import QueueIssueTypeConfigInput
from tests.aioresponses_utils import RequestCapture

API = "https://api.tracker.yandex.net/v3"
QUEUE_URL = f"{API}/queues/DESIGN"
TRIGGER_URL = f"{QUEUE_URL}/triggers/16"
AUTOACTION_URL = f"{QUEUE_URL}/autoactions/9"
MACRO_URL = f"{QUEUE_URL}/macros/3"
RETRY_LATER = {
    "errorMessages": ["Очередь: не удалось сохранить изменения, попробуйте ещё раз."],
    "statusCode": 412,
}


@pytest.fixture
def trigger_data() -> dict[str, Any]:
    """A trigger as the reference shows it (`GET .../triggers/{id}`)."""
    return {
        "id": 16,
        "self": TRIGGER_URL,
        "queue": {"id": "26", "key": "DESIGN", "display": "Design"},
        "name": "trigger_name",
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
        "version": 4,
        "active": True,
    }


@pytest.fixture
def autoaction_data() -> dict[str, Any]:
    """An autoaction as the reference shows it (`GET .../autoactions/{id}`)."""
    return {
        "id": 9,
        "self": AUTOACTION_URL,
        "queue": {"id": "26", "key": "DESIGN", "display": "Design"},
        "name": "autoaction_name",
        "version": 4,
        "active": True,
        "created": "2021-04-15T04:49:44.802+0000",
        "updated": "2022-01-26T16:29:05.356+0000",
        "filter": {"priority": ["critical"]},
        "actions": [
            {
                "type": "Transition",
                "id": 1,
                "status": {"id": "2", "key": "needInfo", "display": "Нужна информация"},
            }
        ],
        "enableNotifications": False,
        "lastLaunch": "2022-02-01T14:09:48.216+0000",
        "totalIssuesProcessed": 0,
        "intervalMillis": 3600000,
        "calendar": {"id": 2},
    }


@pytest.fixture
def macro_data() -> dict[str, Any]:
    """A macro as the reference shows it (`GET .../macros/{id}`)."""
    return {
        "self": MACRO_URL,
        "id": 3,
        "queue": {"id": "1", "key": "DESIGN", "display": "Design"},
        "name": "My macro",
        "body": "Test comment\n{{currentDateTime}}\n{{issue.author}}",
        "issueUpdate": [
            {
                "field": {"id": "tags", "display": "Теги"},
                "update": {"add": ["тег 1", "тег 2"]},
            }
        ],
    }


@pytest.fixture
def queue_data() -> dict[str, Any]:
    """`POST v3/queues` / `POST v3/queues/{key}/_restore` as the reference shows them."""
    return {
        "self": QUEUE_URL,
        "id": "111",
        "key": "DESIGN",
        "version": 1400150916068,
        "name": "Design",
        "lead": {"id": "11", "display": "Имя Фамилия"},
        "assignAuto": False,
        "defaultType": {"id": "2", "key": "task", "display": "Task"},
        "defaultPriority": {"id": "2", "key": "normal", "display": "Normal"},
    }


class TestQueueGetTrigger:
    async def test_reads_the_trigger(
        self, tracker_client: TrackerClient, trigger_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(TRIGGER_URL, payload=trigger_data)

            result = await tracker_client.queue_get_trigger("DESIGN", 16)

        assert result.id == 16
        assert result.version == 4

    async def test_404_names_trigger_and_queue(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(TRIGGER_URL, status=404)

            with pytest.raises(TriggerNotFound, match="queue_get_triggers"):
                await tracker_client.queue_get_trigger("DESIGN", 16)


class TestQueueCreateTrigger:
    async def test_sends_name_actions_conditions_and_active(
        self, tracker_client: TrackerClient, trigger_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=trigger_data)
        actions = [{"type": "Transition", "status": {"key": "open"}}]
        conditions = [{"type": "CommentFullyMatchCondition", "word": "Open"}]

        with aioresponses() as m:
            m.post(f"{QUEUE_URL}/triggers", callback=capture.callback)

            result = await tracker_client.queue_create_trigger(
                "DESIGN",
                name="TriggerName",
                actions=actions,
                conditions=conditions,
                active=False,
            )

        assert result.id == 16
        capture.last_request.assert_json_body(
            {
                "name": "TriggerName",
                "actions": actions,
                "conditions": conditions,
                "active": False,
            }
        )

    async def test_leaves_out_what_is_not_passed(
        self, tracker_client: TrackerClient, trigger_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=trigger_data)

        with aioresponses() as m:
            m.post(f"{QUEUE_URL}/triggers", callback=capture.callback)

            await tracker_client.queue_create_trigger(
                "DESIGN", name="T", actions=[{"type": "Move", "queue": "X"}]
            )

        capture.last_request.assert_json_body(
            {"name": "T", "actions": [{"type": "Move", "queue": "X"}]}
        )

    async def test_unknown_queue(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(f"{QUEUE_URL}/triggers", status=404)

            with pytest.raises(QueueNotFound):
                await tracker_client.queue_create_trigger(
                    "DESIGN", name="T", actions=[]
                )


class TestQueueUpdateTrigger:
    async def test_sends_version_as_query_and_only_what_is_passed(
        self, tracker_client: TrackerClient, trigger_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=trigger_data)

        with aioresponses() as m:
            m.patch(f"{TRIGGER_URL}?version=4", callback=capture.callback)

            await tracker_client.queue_update_trigger(
                "DESIGN", 16, version=4, active=False, before=6
            )

        capture.last_request.assert_params({"version": 4})
        capture.last_request.assert_json_body({"active": False, "before": 6})

    async def test_sends_the_grouped_conditions_object(
        self, tracker_client: TrackerClient, trigger_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=trigger_data)
        conditions = {"type": "Or", "conditions": [{"type": "Event.update"}]}

        with aioresponses() as m:
            m.patch(f"{TRIGGER_URL}?version=4", callback=capture.callback)

            await tracker_client.queue_update_trigger(
                "DESIGN", 16, version=4, name="N", conditions=conditions
            )

        capture.last_request.assert_json_body({"name": "N", "conditions": conditions})

    @pytest.mark.parametrize("status", [409, 412])
    async def test_stale_version_is_a_conflict(
        self, tracker_client: TrackerClient, status: int
    ) -> None:
        with aioresponses() as m:
            m.patch(f"{TRIGGER_URL}?version=1", status=status)

            with pytest.raises(TriggerVersionConflict, match="queue_get_trigger"):
                await tracker_client.queue_update_trigger(
                    "DESIGN", 16, version=1, active=True
                )

    async def test_404_is_trigger_not_found(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.patch(f"{TRIGGER_URL}?version=1", status=404)

            with pytest.raises(TriggerNotFound):
                await tracker_client.queue_update_trigger(
                    "DESIGN", 16, version=1, active=True
                )

    async def test_empty_update_is_refused_before_sending(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses():
            with pytest.raises(TriggerEmptyUpdate):
                await tracker_client.queue_update_trigger("DESIGN", 16, version=1)


class TestQueueGetTriggerLogs:
    async def test_sends_filters_and_drops_secrets(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(
            payload=[
                {
                    "startTime": "2025-02-25T14:22:03.596+0000",
                    "endTime": "2025-02-25T14:22:03.831+0000",
                    "duration": 235,
                    "triggerId": 16,
                    "actionId": 1,
                    "issueId": "66f682f13f442b0000000000",
                    "request": {
                        "method": "POST",
                        "endpoint": "https://example.com/hook",
                        "headers": {"X-Startrek-Transport": "secret"},
                        "body": '{"text": "hi"}',
                        "webhookAuthContext": {"type": "noauth"},
                    },
                    "response": {"headers": {"Server": "x"}, "statusCode": 200},
                    "id": "67bdd20b604a9c0000000000",
                }
            ]
        )

        with aioresponses() as m:
            m.get(
                f"{TRIGGER_URL}/webhooks/log?issueId=DESIGN-1&limit=100"
                "&from=2025-09-23T00:00:00.000000%2B0000"
                "&to=2025-09-23T23:59:59.000000%2B0000",
                callback=capture.callback,
            )

            result = await tracker_client.queue_get_trigger_logs(
                "DESIGN",
                16,
                issue_id="DESIGN-1",
                limit=100,
                created_from=datetime.datetime(2025, 9, 23, 0, 0, 0),
                created_to=datetime.datetime(2025, 9, 23, 23, 59, 59),
            )

        capture.last_request.assert_params(
            {
                "issueId": "DESIGN-1",
                "limit": 100,
                "from": "2025-09-23T00:00:00.000000+0000",
                "to": "2025-09-23T23:59:59.000000+0000",
            }
        )
        assert result[0].request == {
            "method": "POST",
            "endpoint": "https://example.com/hook",
            "body": '{"text": "hi"}',
        }
        assert result[0].response == {"statusCode": 200}

    async def test_404_is_trigger_not_found(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(f"{TRIGGER_URL}/webhooks/log", status=404)

            with pytest.raises(TriggerNotFound):
                await tracker_client.queue_get_trigger_logs("DESIGN", 16)


class TestQueueAutoactions:
    async def test_lists_autoactions(
        self, tracker_client: TrackerClient, autoaction_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(f"{QUEUE_URL}/autoactions", payload=[autoaction_data])

            result = await tracker_client.queues_get_autoactions("DESIGN")

        assert [a.id for a in result] == [9]
        assert result[0].intervalMillis == 3600000

    async def test_an_empty_listing(self, tracker_client: TrackerClient) -> None:
        """What the live API answered for a queue without autoactions."""
        with aioresponses() as m:
            m.get(f"{QUEUE_URL}/autoactions", payload=[])

            assert await tracker_client.queues_get_autoactions("DESIGN") == []

    async def test_reads_one_autoaction(
        self, tracker_client: TrackerClient, autoaction_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(AUTOACTION_URL, payload=autoaction_data)

            result = await tracker_client.queue_get_autoaction("DESIGN", 9)

        assert result.lastLaunch == datetime.datetime(
            2022, 2, 1, 14, 9, 48, 216000, tzinfo=datetime.UTC
        )
        assert result.filter == {"priority": ["critical"]}

    async def test_unknown_autoaction(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(AUTOACTION_URL, status=404)

            with pytest.raises(AutoactionNotFound, match="queue_get_autoactions"):
                await tracker_client.queue_get_autoaction("DESIGN", 9)

    async def test_creates_with_every_option(
        self, tracker_client: TrackerClient, autoaction_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=autoaction_data)
        actions = [{"type": "Transition", "status": {"key": "needInfo"}}]

        with aioresponses() as m:
            m.post(f"{QUEUE_URL}/autoactions", callback=capture.callback)

            await tracker_client.queue_create_autoaction(
                "DESIGN",
                name="AutoactionName",
                actions=actions,
                filter={"priority": ["critical"]},
                query='"Status": "In progress"',
                active=True,
                enable_notifications=False,
                interval_millis=7200000,
                calendar_id=2,
            )

        capture.last_request.assert_json_body(
            {
                "name": "AutoactionName",
                "actions": actions,
                "filter": {"priority": ["critical"]},
                "query": '"Status": "In progress"',
                "active": True,
                "enableNotifications": False,
                "intervalMillis": 7200000,
                "calendar": {"id": 2},
            }
        )

    async def test_lists_launches(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{AUTOACTION_URL}/logs",
                payload=[
                    {
                        "id": "6819cc43d8f6f00000000000",
                        "launchTime": "2025-05-06T08:45:55.778+0000",
                        "searchHits": 3,
                        "successes": 3,
                        "failures": 0,
                        "searchFailed": False,
                    }
                ],
            )

            result = await tracker_client.queue_get_autoaction_runs("DESIGN", 9)

        assert result[0].id == "6819cc43d8f6f00000000000"
        assert result[0].successes == 3

    async def test_reads_the_issues_of_one_launch(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(
                f"{AUTOACTION_URL}/logs/6819cc",
                payload=[
                    {
                        "id": 0,
                        "issueReference": {
                            "id": "66f682f13f442b0000000000",
                            "key": "DESIGN-1",
                            "display": "My issue",
                        },
                        "status": {"value": "success", "display": "Success"},
                    }
                ],
            )

            result = await tracker_client.queue_get_autoaction_run(
                "DESIGN", 9, "6819cc"
            )

        assert result[0].issueReference is not None
        assert result[0].issueReference.key == "DESIGN-1"
        assert result[0].status == {"value": "success", "display": "Success"}

    async def test_launches_of_an_unknown_autoaction(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(f"{AUTOACTION_URL}/logs", status=404)

            with pytest.raises(AutoactionNotFound):
                await tracker_client.queue_get_autoaction_runs("DESIGN", 9)


class TestQueueMacros:
    async def test_lists_macros(
        self, tracker_client: TrackerClient, macro_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(f"{QUEUE_URL}/macros", payload=[macro_data])

            result = await tracker_client.queues_get_macros("DESIGN")

        assert result[0].name == "My macro"
        assert result[0].issueUpdate is not None

    async def test_unknown_macro(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(MACRO_URL, status=404)

            with pytest.raises(MacroNotFound, match="queue_get_macros"):
                await tracker_client.queue_get_macro("DESIGN", 3)

    async def test_creates_a_macro(
        self, tracker_client: TrackerClient, macro_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=macro_data)
        issue_update = {"tags": {"add": "Новый тег"}, "resolution": None}

        with aioresponses() as m:
            m.post(f"{QUEUE_URL}/macros", callback=capture.callback)

            result = await tracker_client.queue_create_macro(
                "DESIGN", name="My macro", body="text", issue_update=issue_update
            )

        assert result.id == 3
        capture.last_request.assert_json_body(
            {"name": "My macro", "body": "text", "issueUpdate": issue_update}
        )

    async def test_update_always_sends_the_name(
        self, tracker_client: TrackerClient, macro_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=macro_data)

        with aioresponses() as m:
            m.patch(MACRO_URL, callback=capture.callback)

            await tracker_client.queue_update_macro(
                "DESIGN", 3, name="My macro", body="new"
            )

        capture.last_request.assert_json_body({"name": "My macro", "body": "new"})

    async def test_clear_body_sends_unset(
        self, tracker_client: TrackerClient, macro_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=macro_data)

        with aioresponses() as m:
            m.patch(MACRO_URL, callback=capture.callback)

            await tracker_client.queue_update_macro(
                "DESIGN", 3, name="My macro", clear_body=True
            )

        capture.last_request.assert_json_body(
            {"name": "My macro", "body": {"unset": 1}}
        )

    async def test_body_and_clear_body_conflict(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses():
            with pytest.raises(FieldClearConflict):
                await tracker_client.queue_update_macro(
                    "DESIGN", 3, name="M", body="x", clear_body=True
                )

    async def test_deletes_a_macro(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(MACRO_URL, callback=capture.callback)

            await tracker_client.queue_delete_macro("DESIGN", 3)

        capture.assert_called_once()

    async def test_delete_unknown_macro(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.delete(MACRO_URL, status=404)

            with pytest.raises(MacroNotFound):
                await tracker_client.queue_delete_macro("DESIGN", 3)


class TestQueueAdministration:
    async def test_creates_a_queue(
        self, tracker_client: TrackerClient, queue_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=queue_data)

        with aioresponses() as m:
            m.post(f"{API}/queues", callback=capture.callback)

            result = await tracker_client.queue_create(
                key="DESIGN",
                name="Design",
                lead="username",
                default_type="task",
                default_priority="normal",
                issue_types_config=[
                    QueueIssueTypeConfigInput(
                        issue_type="task",
                        workflow="hrPresetWorkflow",
                        resolutions=["fixed", "wontFix"],
                    )
                ],
            )

        assert result.key == "DESIGN"
        assert result.id == 111
        capture.last_request.assert_json_body(
            {
                "key": "DESIGN",
                "name": "Design",
                "lead": "username",
                "defaultType": "task",
                "defaultPriority": "normal",
                "issueTypesConfig": [
                    {
                        "issueType": "task",
                        "workflow": "hrPresetWorkflow",
                        "resolutions": ["fixed", "wontFix"],
                    }
                ],
            }
        )

    async def test_deletes_a_queue(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(QUEUE_URL, callback=capture.callback)

            await tracker_client.queue_delete("DESIGN")

        capture.assert_called_once()

    async def test_delete_is_retried_after_a_passing_412(
        self, tracker_client: TrackerClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client_module, "_QUEUE_DELETE_RETRY_WAITS", (0.0, 0.0))

        with aioresponses() as m:
            m.delete(QUEUE_URL, status=412, payload=RETRY_LATER)
            m.delete(QUEUE_URL, status=204)

            await tracker_client.queue_delete("DESIGN")

    async def test_delete_gives_up_after_the_retries(
        self, tracker_client: TrackerClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client_module, "_QUEUE_DELETE_RETRY_WAITS", (0.0, 0.0))

        with aioresponses() as m:
            for _ in range(3):
                m.delete(QUEUE_URL, status=412, payload=RETRY_LATER)

            with pytest.raises(TrackerAPIError) as exc_info:
                await tracker_client.queue_delete("DESIGN")

        assert exc_info.value.status == 412

    async def test_delete_unknown_queue(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.delete(QUEUE_URL, status=404)

            with pytest.raises(QueueNotFound):
                await tracker_client.queue_delete("DESIGN")

    async def test_restore_unknown_queue(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(f"{QUEUE_URL}/_restore", status=404)

            with pytest.raises(QueueNotFound):
                await tracker_client.queue_restore("DESIGN")

    async def test_restores_a_queue(
        self, tracker_client: TrackerClient, queue_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.post(f"{QUEUE_URL}/_restore", payload=queue_data)

            result = await tracker_client.queue_restore("DESIGN")

        assert result.key == "DESIGN"

    async def test_reads_the_issue_types_config_with_workflows(
        self, tracker_client: TrackerClient, queue_data: dict[str, Any]
    ) -> None:
        payload = {
            **queue_data,
            "issueTypesConfig": [
                {
                    "issueType": {"id": "2", "key": "task", "display": "Task"},
                    "workflow": {"id": "W1", "display": "Разработка"},
                    "resolutions": [{"id": "1", "key": "fixed", "display": "Решён"}],
                }
            ],
        }
        capture = RequestCapture(payload=payload)

        with aioresponses() as m:
            m.get(f"{QUEUE_URL}?expand=issueTypesConfig", callback=capture.callback)

            result = await tracker_client.queue_get_fresh(
                "DESIGN", expand=["issueTypesConfig"]
            )

        capture.last_request.assert_params({"expand": "issueTypesConfig"})
        assert result.issueTypesConfig is not None
        config = result.issueTypesConfig[0]
        assert config.workflow is not None
        assert config.workflow.id == "W1"

    async def test_replaces_the_issue_types_config(
        self, tracker_client: TrackerClient, queue_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=queue_data)

        with aioresponses() as m:
            m.patch(QUEUE_URL, callback=capture.callback)

            await tracker_client.queue_update_issue_types_config(
                "DESIGN",
                issue_types_config=[
                    QueueIssueTypeConfigInput(
                        issue_type="bug", workflow="W2", resolutions=["fixed"]
                    )
                ],
                default_type="bug",
            )

        capture.last_request.assert_json_body(
            {
                "issueTypesConfig": [
                    {"issueType": "bug", "workflow": "W2", "resolutions": ["fixed"]}
                ],
                "defaultType": "bug",
            }
        )
        assert capture.last_request.params in ({}, None)
