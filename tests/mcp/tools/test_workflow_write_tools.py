from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent

from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.tools import workflow_write
from mcp_tracker.mcp.tools.workflow_write import (
    ScreenFieldInput,
    add_status,
    build_action,
    diff_drafts,
    diff_steps,
    merge_action,
    new_action_id,
    remove_action,
    remove_status,
    update_step,
)
from mcp_tracker.tracker.custom.errors import TrackerAPIError, WorkflowVersionConflict
from mcp_tracker.tracker.proto.types.refs import QueueReference, StatusReference
from mcp_tracker.tracker.proto.types.workflows import (
    IssueTypeResolutionsDraft,
    LocalizedText,
    ScreenDraft,
    ScreenElementDraft,
    Workflow,
    WorkflowAction,
    WorkflowActionDraft,
    WorkflowDraft,
    WorkflowStep,
    WorkflowStepDraft,
)
from tests.mcp.conftest import get_tool_result_content

RESOLUTION_SCREEN = ScreenDraft(
    title=LocalizedText(ru="Резолюция", en="Resolution"),
    elements=[ScreenElementDraft(field="resolution", required=True)],
)
FIXED = [{"type": "SetResolutionFunction", "resolution": "fixed"}]
LEAD_ONLY = [{"type": "UserIsQueueLeadCondition"}]
IN_GROUP = [{"type": "UserInGroupCondition", "group": "3"}]


def start_action() -> WorkflowActionDraft:
    return WorkflowActionDraft(
        id="start",
        name=LocalizedText(ru="В работу", en="Start"),
        target="inProgress",
        action_coords={"start": 2, "finish": 0},
    )


def close_action() -> WorkflowActionDraft:
    return WorkflowActionDraft(
        id="close",
        name=LocalizedText(ru="Закрыть", en="Close"),
        target="closed",
        description=LocalizedText(ru="Опис", en="Descr"),
        screen=RESOLUTION_SCREEN,
        post_functions=FIXED,
        action_coords={"start": 1, "finish": 3},
    )


def draft(queue: str | None = "TEST", version: int = 5) -> WorkflowDraft:
    """open -> inProgress -> closed -> open, initial status `open`."""
    return WorkflowDraft(
        id="W9",
        version=version,
        name="MCP test",
        queue=queue,
        initial_action=WorkflowActionDraft(
            id="create", name=LocalizedText(ru="Создать", en="Create"), target="open"
        ),
        steps=[
            WorkflowStepDraft(
                status="open",
                status_type="new",
                step_coords={"x": 100, "y": 100},
                actions=[start_action(), close_action()],
            ),
            WorkflowStepDraft(
                status="inProgress",
                status_type="inProgress",
                step_coords={"x": 400, "y": 150},
                actions=[
                    WorkflowActionDraft(
                        id="close",
                        name=LocalizedText(ru="Закрыть", en="Close"),
                        target="closed",
                    )
                ],
            ),
            WorkflowStepDraft(
                status="closed",
                status_type="done",
                step_coords={"x": 700, "y": 100},
                actions=[
                    WorkflowActionDraft(
                        id="reopen",
                        name=LocalizedText(ru="Переоткрыть", en="Reopen"),
                        target="open",
                    )
                ],
            ),
        ],
    )


def written(steps: list[str], version: int = 6, queue: str | None = "TEST") -> Workflow:
    """A workflow in the read shape, as a write returns it."""
    return Workflow.model_construct(
        id="W9",
        name="MCP test",
        version=version,
        queue=QueueReference.model_construct(key=queue) if queue else None,
        steps=[
            WorkflowStep.model_construct(
                status=StatusReference.model_construct(key=key, display=key),
                actions=[WorkflowAction.model_construct(id=f"{key}-action")],
            )
            for key in steps
        ],
    )


def error_text(result: CallToolResult) -> str:
    assert result.is_error
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


@pytest.fixture
def no_conflict_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_write,
        "WORKFLOW_CONFLICT_WAITS",
        (0.0,) * len(workflow_write.WORKFLOW_CONFLICT_WAITS),
    )


class TestMergeAction:
    def test_keeps_what_is_not_given(self) -> None:
        merged = merge_action(close_action(), name="Готово")

        assert merged == close_action().model_copy(
            update={"name": LocalizedText(ru="Готово", en="Готово")}
        )

    def test_english_name_alone_keeps_the_russian_one(self) -> None:
        merged = merge_action(close_action(), name_en="Done")

        assert merged.name == LocalizedText(ru="Закрыть", en="Done")

    def test_description_on_a_transition_without_one(self) -> None:
        merged = merge_action(start_action(), description_en="Begin")

        assert merged.description == LocalizedText(ru="Begin", en="Begin")

    def test_new_fields_keep_the_screen_title(self) -> None:
        merged = merge_action(
            close_action(), screen_fields=[ScreenFieldInput(field="assignee")]
        )

        assert merged.screen == ScreenDraft(
            title=RESOLUTION_SCREEN.title,
            elements=[ScreenElementDraft(field="assignee", required=False)],
        )
        assert merged.post_functions == FIXED
        assert merged.action_coords == {"start": 1, "finish": 3}

    def test_a_title_alone_keeps_the_fields(self) -> None:
        merged = merge_action(close_action(), screen_title="Итог")

        assert merged.screen == ScreenDraft(
            title=LocalizedText(ru="Итог", en="Итог"),
            elements=RESOLUTION_SCREEN.elements,
        )

    def test_a_title_alone_needs_a_screen(self) -> None:
        with pytest.raises(TrackerError, match="has no screen to title"):
            merge_action(start_action(), screen_title="Итог")

    def test_remove_screen(self) -> None:
        merged = merge_action(close_action(), remove_screen=True)

        assert merged.screen is None
        assert merged.post_functions == FIXED

    @pytest.mark.parametrize(
        "screen",
        [
            pytest.param({"screen_fields": [ScreenFieldInput(field="a")]}, id="fields"),
            pytest.param({"screen_title": "T"}, id="title"),
        ],
    )
    def test_remove_screen_conflicts_with_a_new_one(
        self, screen: dict[str, Any]
    ) -> None:
        with pytest.raises(TrackerError, match="`remove_screen` cannot be passed"):
            merge_action(close_action(), remove_screen=True, **screen)

    def test_conditions_replace_the_current_ones(self) -> None:
        current = close_action().model_copy(update={"conditions": LEAD_ONLY})

        assert merge_action(current, conditions=IN_GROUP).conditions == IN_GROUP
        assert merge_action(current, conditions=[]).conditions is None
        assert merge_action(current, name="x").conditions == LEAD_ONLY

    def test_empty_post_functions_remove_them(self) -> None:
        merged = merge_action(close_action(), post_functions=[])

        assert merged.post_functions == []

    def test_empty_screen_fields_are_refused(self) -> None:
        with pytest.raises(TrackerError, match="`screen_fields` is empty"):
            merge_action(close_action(), screen_fields=[])

    @pytest.mark.parametrize(
        "changes",
        [
            pytest.param({}, id="nothing-given"),
            pytest.param({"name": "Закрыть", "name_en": "Close"}, id="same-name"),
            pytest.param({"target": "closed", "post_functions": FIXED}, id="same"),
        ],
    )
    def test_nothing_to_change_is_refused(self, changes: dict[str, Any]) -> None:
        with pytest.raises(TrackerError, match="Nothing to change"):
            merge_action(close_action(), **changes)


class TestDraftHelpers:
    @pytest.mark.parametrize(
        ("taken", "expected"),
        [
            pytest.param([], "closed", id="free"),
            pytest.param(["closed"], "closed2", id="taken"),
            pytest.param(["closed", "closed2"], "closed3", id="taken-twice"),
        ],
    )
    def test_new_action_id(self, taken: list[str], expected: str) -> None:
        assert new_action_id("closed", taken) == expected

    def test_build_action_refuses_a_taken_id(self) -> None:
        with pytest.raises(TrackerError, match="'start' is taken"):
            build_action(
                action_id="start",
                name="x",
                name_en=None,
                target="open",
                taken=["start"],
            )

    def test_remove_action_leaves_the_draft_alone(self) -> None:
        source = draft()

        steps = remove_action(source.steps, "open", "start")

        assert [a.id for a in steps[0].actions] == ["close"]
        assert steps[1:] == source.steps[1:]
        assert source == draft()

    def test_remove_action_names_the_transitions_there_are(self) -> None:
        with pytest.raises(TrackerError, match="its transitions are: start, close"):
            remove_action(draft().steps, "open", "nope")

    def test_remove_action_names_the_statuses_there_are(self) -> None:
        with pytest.raises(
            TrackerError, match="its statuses are: open, inProgress, closed"
        ):
            remove_action(draft().steps, "nope", "start")

    def test_remove_status_drops_the_transitions_into_it(self) -> None:
        steps, removed = remove_status(draft(), "closed")

        assert [s.status for s in steps] == ["open", "inProgress"]
        assert [a.id for a in steps[0].actions] == ["start"]
        assert steps[1].actions == []
        assert removed == ["open/close", "inProgress/close"]

    def test_remove_status_refuses_the_initial_one(self) -> None:
        with pytest.raises(TrackerError, match="initial status"):
            remove_status(draft(), "open")

    def test_add_status_refuses_one_already_there(self) -> None:
        with pytest.raises(TrackerError, match="already in this workflow"):
            add_status(draft().steps, WorkflowStepDraft(status="closed"), [])


class TestDiff:
    def test_identical_drafts_differ_in_nothing(self) -> None:
        assert diff_drafts(draft(), draft().steps, draft(version=6)) == []

    def test_a_lost_post_function_is_reported(self) -> None:
        after = draft()
        after.steps[0].actions[1].post_functions = None

        differences = diff_steps(draft().steps, draft().steps, after.steps)

        assert len(differences) == 1
        assert differences[0].startswith("open/close: postFunctions is None")

    @pytest.mark.parametrize(
        ("expected", "actual"),
        [
            pytest.param(None, [], id="none-vs-empty"),
            pytest.param([], None, id="empty-vs-none"),
        ],
    )
    def test_no_functions_is_no_functions(
        self, expected: list[dict[str, Any]] | None, actual: list[dict[str, Any]] | None
    ) -> None:
        before = draft()
        after = draft()
        before.steps[1].actions[0].post_functions = expected
        after.steps[1].actions[0].post_functions = actual

        assert diff_steps(before.steps, before.steps, after.steps) == []

    def test_missing_and_unexpected_transitions(self) -> None:
        after = draft()
        after.steps[2].actions[0].id = "reopen2"

        assert diff_steps(draft().steps, draft().steps, after.steps) == [
            "transition 'closed/reopen' is missing",
            "transition 'closed/reopen2' was not expected",
        ]

    def test_missing_and_unexpected_statuses(self) -> None:
        after = draft()
        after.steps[2].status = "done"

        assert diff_steps(draft().steps, draft().steps, after.steps) == [
            "status 'closed' is missing",
            "status 'done' was not expected",
        ]

    def test_a_new_status_is_compared_by_what_tracker_keeps(self) -> None:
        """Tracker places a new status and names a screen field by its id."""
        incoming = WorkflowActionDraft(
            id="ask",
            name=LocalizedText(ru="Спросить", en="Ask"),
            target="needInfo",
            screen=ScreenDraft(elements=[ScreenElementDraft(field="systemId")]),
        )
        new_step = WorkflowStepDraft(status="needInfo")
        expected = add_status(draft().steps, new_step, [("open", incoming)])
        actual = add_status(
            draft().steps,
            new_step.model_copy(
                update={"step_coords": {"x": 1, "y": 2}, "status_type": "paused"}
            ),
            [
                (
                    "open",
                    incoming.model_copy(
                        update={
                            "screen": ScreenDraft(
                                elements=[ScreenElementDraft(field="65f--systemId")]
                            ),
                            "action_coords": {"start": 0, "finish": 0},
                        }
                    ),
                )
            ],
        )

        assert diff_steps(draft().steps, expected, actual) == []

    def test_a_changed_initial_action_is_reported(self) -> None:
        after = draft()
        after.initial_action.target = "closed"

        assert diff_drafts(draft(), draft().steps, after) == [
            "initial action: target is 'closed', expected 'open'"
        ]


class TestWorkflowAddAction:
    async def test_adds_a_transition_at_the_current_version(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = written(
            ["open", "closed"], version=5
        )
        mock_workflows_protocol.workflow_add_action.return_value = written(
            ["open", "closed"]
        )

        result = await client_session.call_tool(
            "workflow_add_action",
            {
                "workflow_id": "W9",
                "status": "open",
                "name": "Быстро закрыть",
                "name_en": "Quick close",
                "target": "closed",
                "description": "Сразу",
                "screen_fields": [{"field": "resolution", "required": True}],
                "screen_title": "Резолюция",
                "screen_title_en": "Resolution",
                "post_functions": FIXED,
            },
        )

        assert not result.is_error
        call = mock_workflows_protocol.workflow_add_action.call_args
        assert call.args == ("W9", "open")
        assert call.kwargs["version"] == 5
        assert call.kwargs["action"] == WorkflowActionDraft(
            id="closed",
            name=LocalizedText(ru="Быстро закрыть", en="Quick close"),
            target="closed",
            description=LocalizedText(ru="Сразу", en="Сразу"),
            screen=RESOLUTION_SCREEN,
            post_functions=FIXED,
        )
        content = get_tool_result_content(result)
        assert content["id"] == "W9"
        assert content["version"] == 6
        assert content["step"]["status"]["key"] == "open"
        assert "differences" not in content

    async def test_conditions_are_sent(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = written(
            ["open", "inProgress", "closed"], version=5
        )
        mock_workflows_protocol.workflow_add_action.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_add_action",
            {
                "workflow_id": "W9",
                "status": "open",
                "name": "Закрыть",
                "target": "closed",
                "conditions": IN_GROUP,
            },
        )

        assert not result.is_error
        action = mock_workflows_protocol.workflow_add_action.call_args.kwargs["action"]
        assert action.conditions == IN_GROUP

    async def test_given_version_is_sent(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = written(
            ["open", "closed"], version=5
        )
        mock_workflows_protocol.workflow_add_action.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_add_action",
            {
                "workflow_id": "W9",
                "status": "open",
                "name": "Закрыть",
                "target": "closed",
                "action_id": "quick",
                "version": 3,
            },
        )

        assert not result.is_error
        call = mock_workflows_protocol.workflow_add_action.call_args
        assert call.kwargs["version"] == 3
        assert call.kwargs["action"].id == "quick"
        assert call.kwargs["action"].name == LocalizedText(ru="Закрыть", en="Закрыть")

    @pytest.mark.parametrize(
        ("status", "target", "message"),
        [
            pytest.param("nope", "closed", "Status 'nope' is not", id="status"),
            pytest.param("open", "nope", "Target status 'nope' is not", id="target"),
        ],
    )
    async def test_unknown_status_is_refused(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        status: str,
        target: str,
        message: str,
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = written(["open", "closed"])

        result = await client_session.call_tool(
            "workflow_add_action",
            {"workflow_id": "W9", "status": status, "name": "x", "target": target},
        )

        assert message in error_text(result)
        mock_workflows_protocol.workflow_add_action.assert_not_called()

    async def test_screen_title_without_fields_is_refused_before_reading(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "workflow_add_action",
            {
                "workflow_id": "W9",
                "status": "open",
                "name": "x",
                "target": "closed",
                "screen_title": "T",
            },
        )

        assert "needs `screen_fields`" in error_text(result)
        mock_workflows_protocol.workflow_get.assert_not_called()


class TestWorkflowUpdateAction:
    async def test_merges_into_the_current_transition(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()
        mock_workflows_protocol.workflow_update_action.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_update_action",
            {
                "workflow_id": "W9",
                "status": "open",
                "action_id": "close",
                "name": "Завершить",
                "name_en": "Finish",
            },
        )

        assert not result.is_error
        call = mock_workflows_protocol.workflow_update_action.call_args
        assert call.args == ("W9", "open", "close")
        assert call.kwargs["version"] == 5
        assert call.kwargs["action"] == close_action().model_copy(
            update={"name": LocalizedText(ru="Завершить", en="Finish")}
        )
        assert get_tool_result_content(result)["step"]["status"]["key"] == "open"

    async def test_remove_screen(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()
        mock_workflows_protocol.workflow_update_action.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_update_action",
            {
                "workflow_id": "W9",
                "status": "open",
                "action_id": "close",
                "remove_screen": True,
                "version": 4,
            },
        )

        assert not result.is_error
        call = mock_workflows_protocol.workflow_update_action.call_args
        assert call.kwargs["version"] == 4
        assert call.kwargs["action"] == close_action().model_copy(
            update={"screen": None}
        )

    @pytest.mark.parametrize(
        ("arguments", "message"),
        [
            pytest.param(
                {"status": "open", "action_id": "close"},
                "Nothing to change in transition 'close'",
                id="nothing",
            ),
            pytest.param(
                {"status": "open", "action_id": "nope", "name": "x"},
                "Status 'open' has no transition 'nope'; its transitions are: "
                "start, close.",
                id="unknown-action",
            ),
            pytest.param(
                {"status": "nope", "action_id": "close", "name": "x"},
                "Status 'nope' is not a status of this workflow; its statuses are: "
                "open, inProgress, closed.",
                id="unknown-status",
            ),
            pytest.param(
                {"status": "open", "action_id": "close", "target": "nope"},
                "Target status 'nope' is not",
                id="unknown-target",
            ),
            pytest.param(
                {
                    "status": "open",
                    "action_id": "close",
                    "remove_screen": True,
                    "screen_fields": [{"field": "assignee"}],
                },
                "`remove_screen` cannot be passed",
                id="remove-and-set-screen",
            ),
        ],
    )
    async def test_refused_without_writing(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        arguments: dict[str, Any],
        message: str,
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()

        result = await client_session.call_tool(
            "workflow_update_action", {"workflow_id": "W9", **arguments}
        )

        assert message in error_text(result)
        mock_workflows_protocol.workflow_update_action.assert_not_called()


class TestConflictRetry:
    async def test_a_conflict_on_a_version_read_here_is_retried_on_a_new_read(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        no_conflict_waits: None,
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.side_effect = [
            draft(version=5),
            draft(version=7),
        ]
        mock_workflows_protocol.workflow_update_action.side_effect = [
            WorkflowVersionConflict("W9", 5),
            written(["open"], version=8),
        ]

        result = await client_session.call_tool(
            "workflow_update_action",
            {"workflow_id": "W9", "status": "open", "action_id": "start", "name": "Go"},
        )

        assert not result.is_error
        calls = mock_workflows_protocol.workflow_update_action.call_args_list
        assert [c.kwargs["version"] for c in calls] == [5, 7]
        assert get_tool_result_content(result)["version"] == 8

    async def test_the_retries_end_with_the_conflict(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        no_conflict_waits: None,
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = written(["open", "closed"])
        mock_workflows_protocol.workflow_add_action.side_effect = (
            WorkflowVersionConflict("W9", 5)
        )

        result = await client_session.call_tool(
            "workflow_add_action",
            {"workflow_id": "W9", "status": "open", "name": "x", "target": "closed"},
        )

        assert "Editing conflict for workflow 'W9'" in error_text(result)
        attempts = len(workflow_write.WORKFLOW_CONFLICT_WAITS) + 1
        assert mock_workflows_protocol.workflow_add_action.await_count == attempts
        assert mock_workflows_protocol.workflow_get.await_count == attempts

    async def test_a_conflict_on_the_callers_version_is_not_retried(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        no_conflict_waits: None,
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()
        mock_workflows_protocol.workflow_update.side_effect = WorkflowVersionConflict(
            "W9", 2
        )

        result = await client_session.call_tool(
            "workflow_delete_action",
            {"workflow_id": "W9", "status": "open", "action_id": "start", "version": 2},
        )

        assert result.is_error
        assert mock_workflows_protocol.workflow_update.await_count == 1
        assert mock_workflows_protocol.workflow_get_draft.await_count == 1


class TestWorkflowDeleteAction:
    async def test_rewrites_the_steps_and_checks_them(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        expected = remove_action(draft().steps, "open", "start")
        mock_workflows_protocol.workflow_get_draft.side_effect = [
            draft(),
            draft(version=6).model_copy(update={"steps": expected}),
        ]
        mock_workflows_protocol.workflow_update.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_delete_action",
            {"workflow_id": "W9", "status": "open", "action_id": "start"},
        )

        assert not result.is_error
        call = mock_workflows_protocol.workflow_update.call_args
        assert call.args == ("W9",)
        assert call.kwargs["version"] == 5
        assert call.kwargs["steps"] == expected
        content = get_tool_result_content(result)
        assert content["differences"] == []
        assert content["step"]["status"]["key"] == "open"
        assert "removed_transitions" not in content

    async def test_reports_a_difference_without_failing(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        expected = remove_action(draft().steps, "open", "start")
        after = draft(version=6).model_copy(update={"steps": expected})
        after.steps[0].actions[0].screen = None
        mock_workflows_protocol.workflow_get_draft.side_effect = [draft(), after]
        mock_workflows_protocol.workflow_update.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_delete_action",
            {"workflow_id": "W9", "status": "open", "action_id": "start"},
        )

        assert not result.is_error
        differences = get_tool_result_content(result)["differences"]
        assert len(differences) == 1
        assert differences[0].startswith("open/close: screen is None, expected")

    async def test_a_failed_check_is_reported_without_failing(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.side_effect = [
            draft(),
            TrackerAPIError(status=503, method="GET", url="v3/workflows/W9", body="x"),
        ]
        mock_workflows_protocol.workflow_update.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_delete_action",
            {"workflow_id": "W9", "status": "open", "action_id": "start"},
        )

        assert not result.is_error
        (difference,) = get_tool_result_content(result)["differences"]
        assert difference.startswith("the workflow could not be read again")

    async def test_unknown_transition_is_refused(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()

        result = await client_session.call_tool(
            "workflow_delete_action",
            {"workflow_id": "W9", "status": "closed", "action_id": "nope"},
        )

        assert "its transitions are: reopen" in error_text(result)
        mock_workflows_protocol.workflow_update.assert_not_called()


class TestWorkflowAddStatus:
    async def test_adds_the_status_with_its_transitions(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        ask = WorkflowActionDraft(
            id="needInfo",
            name=LocalizedText(ru="Спросить", en="Ask"),
            target="needInfo",
            screen=ScreenDraft(elements=[ScreenElementDraft(field="comment")]),
        )
        back = WorkflowActionDraft(
            id="back", name=LocalizedText(ru="Назад", en="Back"), target="open"
        )
        new_step = WorkflowStepDraft(
            status="needInfo", status_type="paused", actions=[back]
        )
        expected = add_status(draft().steps, new_step, [("open", ask)])
        mock_workflows_protocol.workflow_get_draft.side_effect = [
            draft(),
            draft(version=6).model_copy(update={"steps": expected}),
        ]
        mock_workflows_protocol.workflow_update.return_value = written(
            ["open", "needInfo"]
        )

        result = await client_session.call_tool(
            "workflow_add_status",
            {
                "workflow_id": "W9",
                "status": "needInfo",
                "status_type": "paused",
                "incoming": [
                    {
                        "from_status": "open",
                        "name": "Спросить",
                        "name_en": "Ask",
                        "screen_fields": [{"field": "comment"}],
                    }
                ],
                "actions": [
                    {
                        "action_id": "back",
                        "name": "Назад",
                        "name_en": "Back",
                        "target": "open",
                    }
                ],
            },
        )

        assert not result.is_error
        call = mock_workflows_protocol.workflow_update.call_args
        assert call.kwargs["version"] == 5
        assert call.kwargs["steps"] == expected
        content = get_tool_result_content(result)
        assert content["differences"] == []
        assert content["step"]["status"]["key"] == "needInfo"

    async def test_reports_a_status_missing_after_the_write(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.side_effect = [
            draft(),
            draft(version=6),
        ]
        mock_workflows_protocol.workflow_update.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_add_status",
            {
                "workflow_id": "W9",
                "status": "needInfo",
                "incoming": [{"from_status": "open", "name": "Спросить"}],
            },
        )

        assert not result.is_error
        assert get_tool_result_content(result)["differences"] == [
            "transition 'open/needInfo' is missing",
            "status 'needInfo' is missing",
        ]

    @pytest.mark.parametrize(
        ("arguments", "message"),
        [
            pytest.param(
                {"incoming": [{"from_status": "nope", "name": "x"}]},
                "Status 'nope' is not",
                id="unknown-from-status",
            ),
            pytest.param(
                {
                    "incoming": [{"from_status": "open", "name": "x"}],
                    "actions": [{"name": "y", "target": "nope"}],
                },
                "Target status 'nope' is not",
                id="unknown-target",
            ),
            pytest.param(
                {
                    "status": "closed",
                    "incoming": [{"from_status": "open", "name": "x"}],
                },
                "Status 'closed' is already in this workflow",
                id="existing-status",
            ),
            pytest.param(
                {
                    "incoming": [
                        {"from_status": "open", "name": "x", "action_id": "start"}
                    ]
                },
                "Transition id 'start' is taken",
                id="taken-id",
            ),
        ],
    )
    async def test_refused_without_writing(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        arguments: dict[str, Any],
        message: str,
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()

        result = await client_session.call_tool(
            "workflow_add_status",
            {"workflow_id": "W9", "status": "needInfo", **arguments},
        )

        assert message in error_text(result)
        mock_workflows_protocol.workflow_update.assert_not_called()

    async def test_needs_an_incoming_transition(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "workflow_add_status",
            {"workflow_id": "W9", "status": "needInfo", "incoming": []},
        )

        assert result.is_error
        mock_workflows_protocol.workflow_get_draft.assert_not_called()


class TestWorkflowDeleteStatus:
    async def test_removes_the_status_and_the_transitions_into_it(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        expected, _ = remove_status(draft(), "closed")
        mock_workflows_protocol.workflow_get_draft.side_effect = [
            draft(),
            draft(version=6).model_copy(update={"steps": expected}),
        ]
        mock_workflows_protocol.workflow_update.return_value = written(
            ["open", "inProgress"]
        )

        result = await client_session.call_tool(
            "workflow_delete_status", {"workflow_id": "W9", "status": "closed"}
        )

        assert not result.is_error
        assert mock_workflows_protocol.workflow_update.call_args.kwargs["steps"] == (
            expected
        )
        content = get_tool_result_content(result)
        assert content["removed_transitions"] == ["open/close", "inProgress/close"]
        assert content["differences"] == []
        assert "step" not in content

    async def test_refuses_the_initial_status(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()

        result = await client_session.call_tool(
            "workflow_delete_status", {"workflow_id": "W9", "status": "open"}
        )

        assert "initial status" in error_text(result)
        mock_workflows_protocol.workflow_update.assert_not_called()


class TestWorkflowCreate:
    async def test_creates_the_workflow(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_create.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_create",
            {
                "name": "MCP test",
                "queue": "TEST",
                "initial_status": "open",
                "steps": [
                    {
                        "status": "open",
                        "status_type": "new",
                        "actions": [
                            {"name": "Закрыть", "name_en": "Close", "target": "closed"}
                        ],
                    },
                    {"status": "closed", "status_type": "done"},
                ],
            },
        )

        assert not result.is_error
        call = mock_workflows_protocol.workflow_create.call_args
        assert call.kwargs["name"] == "MCP test"
        assert call.kwargs["queue"] == "TEST"
        assert call.kwargs["initial_action"] == WorkflowActionDraft(
            id="create", name=LocalizedText(ru="Создать", en="Create"), target="open"
        )
        assert call.kwargs["steps"] == [
            WorkflowStepDraft(
                status="open",
                status_type="new",
                actions=[
                    WorkflowActionDraft(
                        id="closed",
                        name=LocalizedText(ru="Закрыть", en="Close"),
                        target="closed",
                    )
                ],
            ),
            WorkflowStepDraft(status="closed", status_type="done"),
        ]
        assert get_tool_result_content(result)["id"] == "W9"

    @pytest.mark.parametrize(
        ("arguments", "message"),
        [
            pytest.param(
                {"initial_status": "nope", "steps": [{"status": "open"}]},
                "Initial status 'nope' is not",
                id="initial",
            ),
            pytest.param(
                {
                    "initial_status": "open",
                    "steps": [
                        {"status": "open", "actions": [{"name": "x", "target": "nope"}]}
                    ],
                },
                "Target status 'nope' is not",
                id="target",
            ),
            pytest.param(
                {
                    "initial_status": "open",
                    "steps": [{"status": "open"}, {"status": "open"}],
                },
                "name a status more than once",
                id="duplicate",
            ),
        ],
    )
    async def test_refused_without_writing(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        arguments: dict[str, Any],
        message: str,
    ) -> None:
        result = await client_session.call_tool(
            "workflow_create", {"name": "MCP test", **arguments}
        )

        assert message in error_text(result)
        mock_workflows_protocol.workflow_create.assert_not_called()


class TestWorkflowDelete:
    async def test_deletes(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_delete", {"workflow_id": "W9"}
        )

        assert not result.is_error
        assert mock_workflows_protocol.workflow_delete.call_args.args == ("W9",)


class TestWorkflowWriteAccess:
    @pytest.mark.parametrize(
        ("queue", "message"),
        [
            pytest.param("TEST", "Workflow with ID 'W9' not found", id="outside"),
            pytest.param(None, "is shared", id="shared"),
        ],
    )
    @pytest.mark.parametrize(
        "arguments",
        [
            pytest.param(
                {"tool": "workflow_update_action", "action_id": "start", "name": "x"},
                id="update_action",
            ),
            pytest.param(
                {"tool": "workflow_delete_action", "action_id": "start"},
                id="delete_action",
            ),
            pytest.param({"tool": "workflow_delete_status"}, id="delete_status"),
        ],
    )
    async def test_draft_writes_under_queue_limits(
        self,
        client_session_with_limits: Client,
        mock_workflows_protocol: AsyncMock,
        queue: str | None,
        message: str,
        arguments: dict[str, Any],
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft(queue=queue)
        tool = arguments["tool"]
        status = "closed" if tool == "workflow_delete_status" else "open"
        rest = {k: v for k, v in arguments.items() if k != "tool"}

        result = await client_session_with_limits.call_tool(
            tool, {"workflow_id": "W9", "status": status, **rest}
        )

        assert message in error_text(result)
        mock_workflows_protocol.workflow_update.assert_not_called()
        mock_workflows_protocol.workflow_update_action.assert_not_called()

    @pytest.mark.parametrize(
        ("queue", "message"),
        [
            pytest.param("TEST", "Workflow with ID 'W9' not found", id="outside"),
            pytest.param(None, "is shared", id="shared"),
        ],
    )
    async def test_add_action_and_delete_under_queue_limits(
        self,
        client_session_with_limits: Client,
        mock_workflows_protocol: AsyncMock,
        queue: str | None,
        message: str,
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = written(
            ["open", "closed"], queue=queue
        )

        added = await client_session_with_limits.call_tool(
            "workflow_add_action",
            {"workflow_id": "W9", "status": "open", "name": "x", "target": "closed"},
        )
        deleted = await client_session_with_limits.call_tool(
            "workflow_delete", {"workflow_id": "W9"}
        )

        assert message in error_text(added)
        assert message in error_text(deleted)
        mock_workflows_protocol.workflow_add_action.assert_not_called()
        mock_workflows_protocol.workflow_delete.assert_not_called()

    async def test_allowed_queue_is_written(
        self,
        client_session_with_limits: Client,
        mock_workflows_protocol: AsyncMock,
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft(queue="ALLOWED")
        mock_workflows_protocol.workflow_update_action.return_value = written(["open"])

        result = await client_session_with_limits.call_tool(
            "workflow_update_action",
            {"workflow_id": "W9", "status": "open", "action_id": "start", "name": "x"},
        )

        assert not result.is_error
        mock_workflows_protocol.workflow_update_action.assert_awaited_once()

    async def test_read_only_queue_is_not_written(
        self,
        client_session_with_read_only_queues: Client,
        mock_workflows_protocol: AsyncMock,
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft(
            queue="READONLY"
        )

        result = await client_session_with_read_only_queues.call_tool(
            "workflow_delete_action",
            {"workflow_id": "W9", "status": "open", "action_id": "start"},
        )

        assert "read-only" in error_text(result)
        mock_workflows_protocol.workflow_update.assert_not_called()

    async def test_create_in_a_queue_outside_the_limits_is_refused(
        self,
        client_session_with_limits: Client,
        mock_workflows_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "workflow_create",
            {
                "name": "MCP test",
                "queue": "TEST",
                "initial_status": "open",
                "steps": [{"status": "open"}],
            },
        )

        assert "Queue `TEST` not found or not allowed" in error_text(result)
        mock_workflows_protocol.workflow_create.assert_not_called()


UNSET_RESOLUTION = [{"type": "UnsetResolutionFunction"}]


class TestUpdateStep:
    def test_sets_the_type(self) -> None:
        steps = update_step(draft().steps, "closed", status_type="cancelled")

        assert steps[2].status_type == "cancelled"
        assert steps[:2] == draft().steps[:2]

    def test_adds_on_enter_functions_named_after_the_status(self) -> None:
        steps = update_step(draft().steps, "open", on_enter_functions=UNSET_RESOLUTION)

        assert steps[0].meta_action == WorkflowActionDraft(
            id="open",
            name=LocalizedText(ru="open", en="open"),
            target="open",
            post_functions=UNSET_RESOLUTION,
        )

    def test_replaces_the_functions_of_an_existing_one(self) -> None:
        meta = WorkflowActionDraft(
            id="open",
            name=LocalizedText(ru="Открыть", en="Open"),
            target="open",
            post_functions=FIXED,
            action_coords={"start": 0, "finish": 100},
        )
        steps = [draft().steps[0].model_copy(update={"meta_action": meta})]

        result = update_step(steps, "open", on_enter_functions=UNSET_RESOLUTION)

        assert result[0].meta_action == meta.model_copy(
            update={"post_functions": UNSET_RESOLUTION}
        )

    def test_removes_on_enter_functions(self) -> None:
        meta = WorkflowActionDraft(
            id="open", name=LocalizedText(ru="o", en="o"), target="open"
        )
        steps = [draft().steps[0].model_copy(update={"meta_action": meta})]

        assert update_step(steps, "open", remove_on_enter=True)[0].meta_action is None

    @pytest.mark.parametrize(
        "changes",
        [
            pytest.param({}, id="nothing"),
            pytest.param(
                {"on_enter_functions": FIXED, "remove_on_enter": True}, id="both"
            ),
            pytest.param({"remove_on_enter": True}, id="nothing-to-remove"),
        ],
    )
    def test_refused(self, changes: dict[str, Any]) -> None:
        with pytest.raises(TrackerError):
            update_step(draft().steps, "open", **changes)


class TestWorkflowUpdate:
    async def test_renames_and_moves_the_initial_status(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()
        mock_workflows_protocol.workflow_update.return_value = written(["open"])

        result = await client_session.call_tool(
            "workflow_update",
            {
                "workflow_id": "W9",
                "name": "New name",
                "initial_status": "inProgress",
                "issue_type_resolutions": [
                    {"issue_type": "task", "resolutions": ["fixed", "wontFix"]}
                ],
            },
        )

        assert not result.is_error
        kwargs = mock_workflows_protocol.workflow_update.call_args.kwargs
        assert kwargs["version"] == 5
        assert kwargs["name"] == "New name"
        assert kwargs["initial_action"] == draft().initial_action.model_copy(
            update={"target": "inProgress"}
        )
        assert kwargs["issue_type_resolutions"] == [
            IssueTypeResolutionsDraft(
                issue_type="task", resolutions=["fixed", "wontFix"]
            )
        ]
        assert "steps" not in kwargs or kwargs["steps"] is None
        assert get_tool_result_content(result) == {"id": "W9", "version": 6}

    async def test_name_only_sends_no_initial_action(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()
        mock_workflows_protocol.workflow_update.return_value = written(["open"])

        await client_session.call_tool(
            "workflow_update", {"workflow_id": "W9", "name": "New name", "version": 7}
        )

        kwargs = mock_workflows_protocol.workflow_update.call_args.kwargs
        assert kwargs["version"] == 7
        assert kwargs["initial_action"] is None
        assert kwargs["issue_type_resolutions"] is None

    @pytest.mark.parametrize(
        "arguments",
        [
            pytest.param({}, id="nothing"),
            pytest.param({"initial_status": "nowhere"}, id="unknown-status"),
        ],
    )
    async def test_refused_without_writing(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        arguments: dict[str, Any],
    ) -> None:
        mock_workflows_protocol.workflow_get_draft.return_value = draft()

        result = await client_session.call_tool(
            "workflow_update", {"workflow_id": "W9", **arguments}
        )

        assert result.is_error
        mock_workflows_protocol.workflow_update.assert_not_called()


class TestWorkflowUpdateStatus:
    async def test_rewrites_the_steps_and_checks_them(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        expected = update_step(
            draft().steps,
            "closed",
            status_type="cancelled",
            on_enter_functions=UNSET_RESOLUTION,
        )
        mock_workflows_protocol.workflow_get_draft.side_effect = [
            draft(),
            draft(version=6).model_copy(update={"steps": expected}),
        ]
        mock_workflows_protocol.workflow_update.return_value = written(["closed"])

        result = await client_session.call_tool(
            "workflow_update_status",
            {
                "workflow_id": "W9",
                "status": "closed",
                "status_type": "cancelled",
                "on_enter_functions": UNSET_RESOLUTION,
            },
        )

        assert not result.is_error
        assert mock_workflows_protocol.workflow_update.call_args.kwargs["steps"] == (
            expected
        )
        content = get_tool_result_content(result)
        assert content["differences"] == []
        assert content["step"]["status"]["key"] == "closed"

    async def test_nothing_to_change_is_refused_before_reading(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "workflow_update_status", {"workflow_id": "W9", "status": "closed"}
        )

        assert result.is_error
        mock_workflows_protocol.workflow_get_draft.assert_not_called()
