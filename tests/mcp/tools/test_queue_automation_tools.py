"""Queue automation (triggers, autoactions, macros) and administration tools."""

import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.types.queue_automation import (
    QueueAutoaction,
    QueueAutoactionRun,
    QueueAutoactionRunIssue,
    QueueIssueTypeConfigInput,
    QueueMacro,
    QueueTriggerLog,
)
from mcp_tracker.tracker.proto.types.queues import Queue, QueueTrigger
from mcp_tracker.tracker.proto.types.refs import IssueReference
from mcp_tracker.tracker.proto.types.workflows import Workflow
from tests.mcp.conftest import get_tool_result_content

ACTIONS = [{"type": "Transition", "status": {"key": "open"}}]


@pytest.fixture
def sample_trigger() -> QueueTrigger:
    return QueueTrigger.model_construct(id=16, name="T", version=4, active=True)


@pytest.fixture
def sample_macro() -> QueueMacro:
    return QueueMacro.model_construct(id=3, name="My macro", body="text")


@pytest.fixture
def sample_autoaction() -> QueueAutoaction:
    return QueueAutoaction.model_construct(id=9, name="A", version=1)


@pytest.fixture
def sample_queue() -> Queue:
    return Queue.model_construct(id=111, key="DESIGN", name="Design")


def queue_with_types(default: str, *types: tuple[str, str, list[str]]) -> Queue:
    """A queue as `GET v3/queues/{key}?expand=issueTypesConfig` returns it."""
    return Queue.model_validate(
        {
            "key": "DESIGN",
            "defaultType": {"key": default},
            "issueTypesConfig": [
                {
                    "issueType": {"key": key},
                    "workflow": {"id": workflow},
                    "resolutions": [
                        {"id": i, "key": r} for i, r in enumerate(resolutions)
                    ],
                }
                for key, workflow, resolutions in types
            ],
        }
    )


def ai_restricted_queue() -> Queue:
    return Queue.model_validate({"key": "DESIGN", "aiAccessLevel": "none"})


class TestQueueGetTrigger:
    async def test_returns_the_trigger(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_trigger: QueueTrigger,
    ) -> None:
        mock_queues_protocol.queue_get_trigger.return_value = sample_trigger

        result = await client_session.call_tool(
            "queue_get_trigger", {"queue_id": "DESIGN", "trigger_id": 16}
        )

        assert not result.is_error
        assert get_tool_result_content(result)["version"] == 4
        call = mock_queues_protocol.queue_get_trigger.call_args
        assert call.args == ("DESIGN", 16)

    async def test_restricted_queue(
        self, client_session_with_limits: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "queue_get_trigger", {"queue_id": "DESIGN", "trigger_id": 16}
        )

        assert result.is_error
        mock_queues_protocol.queue_get_trigger.assert_not_called()


class TestQueueGetTriggerLogs:
    @pytest.fixture
    def log(self) -> QueueTriggerLog:
        return QueueTriggerLog.model_construct(
            id="1", triggerId=16, request={"method": "POST", "body": "summary"}
        )

    async def test_passes_the_filters(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        log: QueueTriggerLog,
    ) -> None:
        mock_queues_protocol.queue_get_trigger_logs.return_value = [log]
        mock_queues_protocol.queue_get.return_value = Queue.model_construct(
            key="DESIGN"
        )

        result = await client_session.call_tool(
            "queue_get_trigger_logs",
            {
                "queue_id": "DESIGN",
                "trigger_id": 16,
                "issue_id": "DESIGN-1",
                "limit": 50,
                "created_from": "2025-09-23T00:00:00Z",
            },
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_get_trigger_logs.call_args
        assert call.args == ("DESIGN", 16)
        assert call.kwargs["issue_id"] == "DESIGN-1"
        assert call.kwargs["limit"] == 50
        assert call.kwargs["created_from"] == datetime.datetime(
            2025, 9, 23, tzinfo=datetime.UTC
        )
        assert call.kwargs["created_to"] is None
        assert get_tool_result_content(result)[0]["request"]["body"] == "summary"

    async def test_drops_the_body_for_an_ai_restricted_queue(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        log: QueueTriggerLog,
    ) -> None:
        mock_queues_protocol.queue_get_trigger_logs.return_value = [log]
        mock_queues_protocol.queue_get.return_value = ai_restricted_queue()

        result = await client_session.call_tool(
            "queue_get_trigger_logs", {"queue_id": "DESIGN", "trigger_id": 16}
        )

        assert not result.is_error
        assert get_tool_result_content(result)[0]["request"] == {"method": "POST"}

    async def test_limit_over_100_is_refused(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "queue_get_trigger_logs",
            {"queue_id": "DESIGN", "trigger_id": 16, "limit": 101},
        )

        assert result.is_error
        mock_queues_protocol.queue_get_trigger_logs.assert_not_called()


class TestQueueAutoactionReads:
    async def test_lists_autoactions(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_autoaction: QueueAutoaction,
    ) -> None:
        mock_queues_protocol.queues_get_autoactions.return_value = [sample_autoaction]

        result = await client_session.call_tool(
            "queue_get_autoactions", {"queue_id": "DESIGN"}
        )

        assert not result.is_error
        assert get_tool_result_content(result)[0]["id"] == 9

    async def test_reads_one_autoaction(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_autoaction: QueueAutoaction,
    ) -> None:
        mock_queues_protocol.queue_get_autoaction.return_value = sample_autoaction

        result = await client_session.call_tool(
            "queue_get_autoaction", {"queue_id": "DESIGN", "autoaction_id": 9}
        )

        assert not result.is_error
        assert mock_queues_protocol.queue_get_autoaction.call_args.args == (
            "DESIGN",
            9,
        )

    async def test_logs_without_run_id_list_launches(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_get_autoaction_runs.return_value = [
            QueueAutoactionRun.model_construct(id="r1", successes=3)
        ]

        result = await client_session.call_tool(
            "queue_get_autoaction_logs", {"queue_id": "DESIGN", "autoaction_id": 9}
        )

        assert not result.is_error
        assert get_tool_result_content(result)[0]["id"] == "r1"
        mock_queues_protocol.queue_get_autoaction_run.assert_not_called()

    @pytest.mark.parametrize(
        ("queue", "display"),
        [
            pytest.param(Queue.model_construct(key="DESIGN"), "My issue", id="allowed"),
            pytest.param(ai_restricted_queue(), None, id="ai-restricted"),
        ],
    )
    async def test_logs_with_run_id_list_the_issues(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        queue: Queue,
        display: str | None,
    ) -> None:
        mock_queues_protocol.queue_get.return_value = queue
        mock_queues_protocol.queue_get_autoaction_run.return_value = [
            QueueAutoactionRunIssue.model_construct(
                id=0,
                issueReference=IssueReference(key="DESIGN-1", display="My issue"),
                status={"value": "success"},
            )
        ]

        result = await client_session.call_tool(
            "queue_get_autoaction_logs",
            {"queue_id": "DESIGN", "autoaction_id": 9, "run_id": "r1"},
        )

        assert not result.is_error
        row = get_tool_result_content(result)[0]
        assert row["issueReference"]["key"] == "DESIGN-1"
        assert row["issueReference"].get("display") == display
        assert mock_queues_protocol.queue_get_autoaction_run.call_args.args == (
            "DESIGN",
            9,
            "r1",
        )


class TestQueueMacroReads:
    async def test_lists_macros(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_macro: QueueMacro,
    ) -> None:
        mock_queues_protocol.queues_get_macros.return_value = [sample_macro]

        result = await client_session.call_tool(
            "queue_get_macros", {"queue_id": "DESIGN"}
        )

        assert not result.is_error
        assert get_tool_result_content(result)[0]["name"] == "My macro"

    async def test_reads_one_macro(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_macro: QueueMacro,
    ) -> None:
        mock_queues_protocol.queue_get_macro.return_value = sample_macro

        result = await client_session.call_tool(
            "queue_get_macro", {"queue_id": "DESIGN", "macro_id": 3}
        )

        assert not result.is_error
        assert get_tool_result_content(result)["id"] == 3

    @pytest.mark.parametrize(
        ("tool", "arguments", "method"),
        [
            ("queue_get_macros", {}, "queues_get_macros"),
            ("queue_get_macro", {"macro_id": 3}, "queue_get_macro"),
            ("queue_get_autoactions", {}, "queues_get_autoactions"),
            ("queue_get_autoaction", {"autoaction_id": 9}, "queue_get_autoaction"),
            (
                "queue_get_autoaction_logs",
                {"autoaction_id": 9},
                "queue_get_autoaction_runs",
            ),
            ("queue_get_trigger_logs", {"trigger_id": 16}, "queue_get_trigger_logs"),
        ],
    )
    async def test_reads_outside_the_allow_list_are_refused(
        self,
        client_session_with_limits: Client,
        mock_queues_protocol: AsyncMock,
        tool: str,
        arguments: dict[str, Any],
        method: str,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            tool, {"queue_id": "DESIGN", **arguments}
        )

        assert result.is_error
        getattr(mock_queues_protocol, method).assert_not_called()


class TestQueueCreateTrigger:
    async def test_passes_everything(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_trigger: QueueTrigger,
    ) -> None:
        mock_queues_protocol.queue_create_trigger.return_value = sample_trigger
        conditions = {"type": "Or", "conditions": [{"type": "Event.update"}]}

        result = await client_session.call_tool(
            "queue_create_trigger",
            {
                "queue_id": "DESIGN",
                "name": "T",
                "actions": ACTIONS,
                "conditions": conditions,
                "active": False,
            },
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_create_trigger.call_args
        assert call.args == ("DESIGN",)
        assert call.kwargs["name"] == "T"
        assert call.kwargs["actions"] == ACTIONS
        assert call.kwargs["conditions"] == conditions
        assert call.kwargs["active"] is False

    async def test_optional_arguments_default_to_none(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_trigger: QueueTrigger,
    ) -> None:
        mock_queues_protocol.queue_create_trigger.return_value = sample_trigger

        result = await client_session.call_tool(
            "queue_create_trigger",
            {"queue_id": "DESIGN", "name": "T", "actions": ACTIONS},
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_create_trigger.call_args
        assert call.kwargs["conditions"] is None
        assert call.kwargs["active"] is None

    async def test_not_registered_read_only(
        self, client_session_read_only: Client
    ) -> None:
        tools = await client_session_read_only.list_tools()
        names = {tool.name for tool in tools.tools}

        assert not names & {
            "queue_create_trigger",
            "queue_update_trigger",
            "queue_create_autoaction",
            "queue_create_macro",
            "queue_update_macro",
            "queue_delete_macro",
            "queue_create",
            "queue_delete",
            "queue_restore",
            "queue_set_issue_type_workflow",
            "queue_remove_issue_type",
        }


class TestQueueUpdateTrigger:
    async def test_reads_the_version_when_omitted(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_trigger: QueueTrigger,
    ) -> None:
        mock_queues_protocol.queue_get_trigger.return_value = sample_trigger
        mock_queues_protocol.queue_update_trigger.return_value = sample_trigger

        result = await client_session.call_tool(
            "queue_update_trigger",
            {"queue_id": "DESIGN", "trigger_id": 16, "active": False},
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_update_trigger.call_args
        assert call.args == ("DESIGN", 16)
        assert call.kwargs["version"] == 4
        assert call.kwargs["active"] is False
        assert call.kwargs["actions"] is None

    async def test_a_given_version_is_used_as_is(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_trigger: QueueTrigger,
    ) -> None:
        mock_queues_protocol.queue_update_trigger.return_value = sample_trigger

        result = await client_session.call_tool(
            "queue_update_trigger",
            {
                "queue_id": "DESIGN",
                "trigger_id": 16,
                "version": 2,
                "before": 6,
                "actions": ACTIONS,
            },
        )

        assert not result.is_error
        mock_queues_protocol.queue_get_trigger.assert_not_called()
        call = mock_queues_protocol.queue_update_trigger.call_args
        assert call.kwargs["version"] == 2
        assert call.kwargs["before"] == 6
        assert call.kwargs["actions"] == ACTIONS

    async def test_empty_update_is_refused(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "queue_update_trigger", {"queue_id": "DESIGN", "trigger_id": 16}
        )

        assert result.is_error
        mock_queues_protocol.queue_get_trigger.assert_not_called()
        mock_queues_protocol.queue_update_trigger.assert_not_called()


class TestQueueCreateAutoaction:
    async def test_passes_everything(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_autoaction: QueueAutoaction,
    ) -> None:
        mock_queues_protocol.queue_create_autoaction.return_value = sample_autoaction

        result = await client_session.call_tool(
            "queue_create_autoaction",
            {
                "queue_id": "DESIGN",
                "name": "A",
                "actions": ACTIONS,
                "filter": {"priority": ["critical"]},
                "enable_notifications": True,
                "interval_millis": 7200000,
                "calendar_id": 2,
            },
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_create_autoaction.call_args
        assert call.kwargs["filter"] == {"priority": ["critical"]}
        assert call.kwargs["query"] is None
        assert call.kwargs["enable_notifications"] is True
        assert call.kwargs["interval_millis"] == 7200000
        assert call.kwargs["calendar_id"] == 2

    async def test_needs_filter_or_query(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "queue_create_autoaction",
            {"queue_id": "DESIGN", "name": "A", "actions": ACTIONS},
        )

        assert result.is_error
        mock_queues_protocol.queue_create_autoaction.assert_not_called()


class TestQueueMacroWrites:
    async def test_creates_a_macro(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_macro: QueueMacro,
    ) -> None:
        mock_queues_protocol.queue_create_macro.return_value = sample_macro

        result = await client_session.call_tool(
            "queue_create_macro",
            {
                "queue_id": "DESIGN",
                "name": "My macro",
                "body": "text",
                "issue_update": {"tags": {"add": "x"}, "resolution": None},
            },
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_create_macro.call_args
        assert call.kwargs["issue_update"] == {"tags": {"add": "x"}, "resolution": None}

    async def test_update_without_name_sends_the_current_one(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_macro: QueueMacro,
    ) -> None:
        mock_queues_protocol.queue_get_macro.return_value = sample_macro
        mock_queues_protocol.queue_update_macro.return_value = sample_macro

        result = await client_session.call_tool(
            "queue_update_macro",
            {"queue_id": "DESIGN", "macro_id": 3, "clear_body": True},
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_update_macro.call_args
        assert call.args == ("DESIGN", 3)
        assert call.kwargs["name"] == "My macro"
        assert call.kwargs["clear_body"] is True

    async def test_update_with_name_does_not_read(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_macro: QueueMacro,
    ) -> None:
        mock_queues_protocol.queue_update_macro.return_value = sample_macro

        result = await client_session.call_tool(
            "queue_update_macro",
            {"queue_id": "DESIGN", "macro_id": 3, "name": "New"},
        )

        assert not result.is_error
        mock_queues_protocol.queue_get_macro.assert_not_called()
        assert mock_queues_protocol.queue_update_macro.call_args.kwargs["name"] == "New"

    @pytest.mark.parametrize(
        "arguments",
        [
            pytest.param({}, id="empty"),
            pytest.param({"body": "x", "clear_body": True}, id="set-and-clear"),
        ],
    )
    async def test_update_refusals(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        arguments: dict[str, Any],
    ) -> None:
        result = await client_session.call_tool(
            "queue_update_macro", {"queue_id": "DESIGN", "macro_id": 3, **arguments}
        )

        assert result.is_error
        mock_queues_protocol.queue_update_macro.assert_not_called()

    async def test_deletes_a_macro(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "queue_delete_macro", {"queue_id": "DESIGN", "macro_id": 3}
        )

        assert not result.is_error
        assert mock_queues_protocol.queue_delete_macro.call_args.args == (
            "DESIGN",
            3,
        )


class TestQueueAdministration:
    async def test_creates_a_queue(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_queue: Queue,
    ) -> None:
        mock_queues_protocol.queue_create.return_value = sample_queue

        result = await client_session.call_tool(
            "queue_create",
            {
                "key": "DESIGN",
                "name": "Design",
                "lead": "username",
                "default_type": "task",
                "default_priority": "normal",
                "issue_types_config": [
                    {
                        "issue_type": "task",
                        "workflow": "developmentPresetWorkflow",
                        "resolutions": ["fixed"],
                    }
                ],
            },
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_create.call_args
        assert call.kwargs["key"] == "DESIGN"
        assert call.kwargs["issue_types_config"] == [
            QueueIssueTypeConfigInput(
                issue_type="task",
                workflow="developmentPresetWorkflow",
                resolutions=["fixed"],
            )
        ]

    async def test_create_outside_the_allow_list_is_refused(
        self, client_session_with_limits: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "queue_create",
            {
                "key": "DESIGN",
                "name": "Design",
                "lead": "username",
                "default_type": "task",
                "default_priority": "normal",
                "issue_types_config": [
                    {"issue_type": "task", "workflow": "W1", "resolutions": []}
                ],
            },
        )

        assert result.is_error
        mock_queues_protocol.queue_create.assert_not_called()

    async def test_deletes_a_queue(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool("queue_delete", {"queue_id": "DESIGN"})

        assert not result.is_error
        assert mock_queues_protocol.queue_delete.call_args.args == ("DESIGN",)

    async def test_restores_a_queue(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_queue: Queue,
    ) -> None:
        mock_queues_protocol.queue_restore.return_value = sample_queue

        result = await client_session.call_tool("queue_restore", {"queue_id": "DESIGN"})

        assert not result.is_error
        assert get_tool_result_content(result)["key"] == "DESIGN"

    @pytest.mark.parametrize(
        ("tool", "arguments", "method"),
        [
            ("queue_delete", {}, "queue_delete"),
            ("queue_restore", {}, "queue_restore"),
            ("queue_delete_macro", {"macro_id": 3}, "queue_delete_macro"),
            (
                "queue_create_trigger",
                {"name": "T", "actions": ACTIONS},
                "queue_create_trigger",
            ),
            (
                "queue_update_trigger",
                {"trigger_id": 16, "version": 1, "active": False},
                "queue_update_trigger",
            ),
            (
                "queue_remove_issue_type",
                {"issue_type": "bug"},
                "queue_update_issue_types_config",
            ),
        ],
    )
    async def test_writes_to_a_read_only_queue_are_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
        tool: str,
        arguments: dict[str, Any],
        method: str,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            tool, {"queue_id": "READONLY", **arguments}
        )

        assert result.is_error
        assert "read-only" in str(result.content)
        getattr(mock_queues_protocol, method).assert_not_called()


class TestQueueSetIssueTypeWorkflow:
    async def test_changes_the_workflow_and_keeps_the_resolutions(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        mock_workflows_protocol: AsyncMock,
        sample_queue: Queue,
    ) -> None:
        mock_queues_protocol.queue_get_fresh.return_value = queue_with_types(
            "task", ("task", "W1", ["fixed"]), ("bug", "W1", ["fixed", "wontFix"])
        )
        mock_queues_protocol.queue_update_issue_types_config.return_value = sample_queue

        result = await client_session.call_tool(
            "queue_set_issue_type_workflow",
            {"queue_id": "DESIGN", "issue_type": "bug", "workflow_id": "W2"},
        )

        assert not result.is_error
        mock_workflows_protocol.workflow_get.assert_not_called()
        fresh = mock_queues_protocol.queue_get_fresh.call_args
        assert fresh.kwargs["expand"] == ["issueTypesConfig"]
        call = mock_queues_protocol.queue_update_issue_types_config.call_args
        assert call.kwargs["issue_types_config"] == [
            QueueIssueTypeConfigInput(
                issue_type="task", workflow="W1", resolutions=["fixed"]
            ),
            QueueIssueTypeConfigInput(
                issue_type="bug", workflow="W2", resolutions=["fixed", "wontFix"]
            ),
        ]
        assert call.kwargs["default_type"] is None

    @pytest.mark.parametrize(
        ("post_functions", "expected"),
        [
            pytest.param(
                [
                    {
                        "type": "SetResolutionFunction",
                        "resolution": {"id": "1", "key": "fixed"},
                    },
                    {"type": "SetFieldFunction"},
                ],
                ["fixed", "duplicate"],
                id="from-the-workflow",
            ),
            pytest.param([], ["duplicate"], id="meta-action-only"),
        ],
    )
    async def test_a_new_type_gets_the_workflow_resolutions(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        mock_workflows_protocol: AsyncMock,
        sample_queue: Queue,
        post_functions: list[dict[str, Any]],
        expected: list[str],
    ) -> None:
        mock_queues_protocol.queue_get_fresh.return_value = queue_with_types(
            "task", ("task", "W1", ["fixed"])
        )
        mock_queues_protocol.queue_update_issue_types_config.return_value = sample_queue
        mock_workflows_protocol.workflow_get.return_value = Workflow.model_validate(
            {
                "id": "W2",
                "name": "W2",
                "version": 1,
                "steps": [
                    {
                        "status": {"key": "closed"},
                        "actions": [{"id": "close", "postFunctions": post_functions}],
                        "metaAction": {
                            "id": "meta",
                            "postFunctions": [
                                {
                                    "type": "SetResolutionFunction",
                                    "resolution": {"key": "duplicate"},
                                }
                            ],
                        },
                    }
                ],
            }
        )

        result = await client_session.call_tool(
            "queue_set_issue_type_workflow",
            {
                "queue_id": "DESIGN",
                "issue_type": "bug",
                "workflow_id": "W2",
                "make_default": True,
            },
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_update_issue_types_config.call_args
        assert call.kwargs["issue_types_config"][-1] == QueueIssueTypeConfigInput(
            issue_type="bug", workflow="W2", resolutions=expected
        )
        assert call.kwargs["default_type"] == "bug"

    async def test_a_workflow_that_sets_no_resolution_gets_fixed(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        mock_workflows_protocol: AsyncMock,
        sample_queue: Queue,
    ) -> None:
        mock_queues_protocol.queue_get_fresh.return_value = queue_with_types(
            "task", ("task", "W1", ["fixed"])
        )
        mock_queues_protocol.queue_update_issue_types_config.return_value = sample_queue
        mock_workflows_protocol.workflow_get.return_value = Workflow.model_construct(
            id="W2", name="W2", version=1, steps=[], initial_action=None
        )

        result = await client_session.call_tool(
            "queue_set_issue_type_workflow",
            {"queue_id": "DESIGN", "issue_type": "bug", "workflow_id": "W2"},
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_update_issue_types_config.call_args
        assert call.kwargs["issue_types_config"][-1].resolutions == ["fixed"]

    async def test_given_resolutions_win(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        mock_workflows_protocol: AsyncMock,
        sample_queue: Queue,
    ) -> None:
        mock_queues_protocol.queue_get_fresh.return_value = queue_with_types(
            "task", ("task", "W1", ["fixed"])
        )
        mock_queues_protocol.queue_update_issue_types_config.return_value = sample_queue

        result = await client_session.call_tool(
            "queue_set_issue_type_workflow",
            {
                "queue_id": "DESIGN",
                "issue_type": "task",
                "workflow_id": "W2",
                "resolutions": ["fixed", "later"],
            },
        )

        assert not result.is_error
        mock_workflows_protocol.workflow_get.assert_not_called()
        call = mock_queues_protocol.queue_update_issue_types_config.call_args
        assert call.kwargs["issue_types_config"] == [
            QueueIssueTypeConfigInput(
                issue_type="task", workflow="W2", resolutions=["fixed", "later"]
            )
        ]

    async def test_restricted_queue(
        self, client_session_with_limits: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "queue_set_issue_type_workflow",
            {"queue_id": "DESIGN", "issue_type": "bug", "workflow_id": "W2"},
        )

        assert result.is_error
        mock_queues_protocol.queue_get_fresh.assert_not_called()


class TestQueueRemoveIssueType:
    async def test_removes_a_type(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_queue: Queue,
    ) -> None:
        mock_queues_protocol.queue_get_fresh.return_value = queue_with_types(
            "task", ("task", "W1", ["fixed"]), ("bug", "W1", ["fixed"])
        )
        mock_queues_protocol.queue_update_issue_types_config.return_value = sample_queue

        result = await client_session.call_tool(
            "queue_remove_issue_type", {"queue_id": "DESIGN", "issue_type": "bug"}
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_update_issue_types_config.call_args
        assert call.kwargs["issue_types_config"] == [
            QueueIssueTypeConfigInput(
                issue_type="task", workflow="W1", resolutions=["fixed"]
            )
        ]
        assert call.kwargs["default_type"] is None

    async def test_removes_the_default_with_a_new_one(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_queue: Queue,
    ) -> None:
        mock_queues_protocol.queue_get_fresh.return_value = queue_with_types(
            "task", ("task", "W1", ["fixed"]), ("bug", "W1", ["fixed"])
        )
        mock_queues_protocol.queue_update_issue_types_config.return_value = sample_queue

        result = await client_session.call_tool(
            "queue_remove_issue_type",
            {"queue_id": "DESIGN", "issue_type": "task", "new_default_type": "bug"},
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_update_issue_types_config.call_args
        assert call.kwargs["default_type"] == "bug"
        assert [c.issue_type for c in call.kwargs["issue_types_config"]] == ["bug"]

    @pytest.mark.parametrize(
        ("arguments", "message"),
        [
            pytest.param({"issue_type": "task"}, "new_default_type", id="default"),
            pytest.param(
                {"issue_type": "task", "new_default_type": "task"},
                "types that stay",
                id="new-default-removed",
            ),
            pytest.param({"issue_type": "epic"}, "no issue type", id="unknown"),
        ],
    )
    async def test_refusals(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        arguments: dict[str, Any],
        message: str,
    ) -> None:
        mock_queues_protocol.queue_get_fresh.return_value = queue_with_types(
            "task", ("task", "W1", ["fixed"]), ("bug", "W1", ["fixed"])
        )

        result = await client_session.call_tool(
            "queue_remove_issue_type", {"queue_id": "DESIGN", **arguments}
        )

        assert result.is_error
        assert message in str(result.content)
        mock_queues_protocol.queue_update_issue_types_config.assert_not_called()

    async def test_a_type_without_workflow_is_not_written_back(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        queue = queue_with_types(
            "task", ("task", "W1", ["fixed"]), ("bug", "W1", ["fixed"])
        )
        assert queue.issueTypesConfig is not None
        queue.issueTypesConfig[0].workflow = None
        mock_queues_protocol.queue_get_fresh.return_value = queue

        result = await client_session.call_tool(
            "queue_remove_issue_type", {"queue_id": "DESIGN", "issue_type": "bug"}
        )

        assert result.is_error
        mock_queues_protocol.queue_update_issue_types_config.assert_not_called()
