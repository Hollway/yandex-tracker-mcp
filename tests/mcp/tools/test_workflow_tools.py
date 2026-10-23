from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.tracker.custom.errors import ScreenNotFound, WorkflowNotFound
from mcp_tracker.tracker.proto.types.refs import QueueReference, StatusReference
from mcp_tracker.tracker.proto.types.workflows import (
    Screen,
    ScreenElement,
    ScreenElementField,
    ScreenReference,
    Workflow,
    WorkflowAction,
    WorkflowStep,
)
from tests.mcp.conftest import get_tool_result_content

FIXED_REF = {
    "self": "https://api.tracker.yandex.net/v3/resolutions/1",
    "id": "1",
    "key": "fixed",
    "display": "Решен",
}


def status(key: str, display: str) -> StatusReference:
    return StatusReference.model_construct(key=key, display=display)


def workflow(
    workflow_id: str, queue: str | None, *, deleted: bool | None = False
) -> Workflow:
    return Workflow.model_construct(
        id=workflow_id,
        name=f"Процесс {workflow_id}",
        version=7,
        queue=QueueReference.model_construct(id="1", key=queue, display=queue)
        if queue
        else None,
        initial_action=WorkflowAction.model_construct(
            id="create", name="Создать", target=status("open", "Открыт")
        ),
        steps=[
            WorkflowStep.model_construct(
                status=status("open", "Открыт"),
                status_type="new",
                step_coords={"x": 100, "y": 100},
                actions=[
                    WorkflowAction.model_construct(
                        id="start",
                        name="В работу",
                        target=status("inProgress", "В работе"),
                        action_coords={"start": 2, "finish": 0},
                    )
                ],
            ),
            WorkflowStep.model_construct(
                status=status("inProgress", "В работе"),
                status_type="inProgress",
                actions=[
                    WorkflowAction.model_construct(
                        id="close",
                        name="Закрыть",
                        target=status("closed", "Закрыт"),
                        screen=ScreenReference.model_construct(id="704", display="704"),
                        post_functions=[
                            {
                                "type": "SetResolutionFunction",
                                "resolution": FIXED_REF,
                            }
                        ],
                    )
                ],
            ),
            WorkflowStep.model_construct(
                status=status("closed", "Закрыт"), status_type="done", actions=[]
            ),
        ],
        deleted=deleted,
    )


@pytest.fixture
def sample_screen() -> Screen:
    return Screen.model_construct(
        id=704,
        version=1,
        type="workflow",
        title="Укажите резолюцию",
        elements=[
            ScreenElement.model_construct(
                field=ScreenElementField.model_construct(
                    id="resolution", display="Резолюция"
                ),
                required=True,
            ),
            ScreenElement.model_construct(
                field=ScreenElementField.model_construct(
                    id="6582fa303d406816db7e1dd4--systemId", display="ID системы"
                ),
                required=False,
            ),
        ],
    )


class TestWorkflowsGetAll:
    async def test_returns_compact_rows(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflows_get_all.return_value = [
            workflow("W9", "TEST"),
            workflow("quickStartV2PresetWorkflow", None),
        ]

        result = await client_session.call_tool("workflows_get_all", {})

        assert not result.is_error
        mock_workflows_protocol.workflows_get_all.assert_called_once()
        assert "auth" in mock_workflows_protocol.workflows_get_all.call_args.kwargs

        content = get_tool_result_content(result)
        assert content == [
            {
                "id": "W9",
                "name": "Процесс W9",
                "version": 7,
                "queue": "TEST",
                "statuses": ["open", "inProgress", "closed"],
            },
            {
                "id": "quickStartV2PresetWorkflow",
                "name": "Процесс quickStartV2PresetWorkflow",
                "version": 7,
                "queue": None,
                "statuses": ["open", "inProgress", "closed"],
            },
        ]

    async def test_marks_a_deleted_workflow(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflows_get_all.return_value = [
            workflow("W3", "TEST", deleted=True)
        ]

        result = await client_session.call_tool("workflows_get_all", {})

        assert not result.is_error
        assert get_tool_result_content(result)[0]["deleted"] is True

    async def test_queue_limits_drop_workflows_of_hidden_queues(
        self, client_session_with_limits: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflows_get_all.return_value = [
            workflow("W1", "RESTRICTED"),
            workflow("W2", "ALLOWED"),
            workflow("quickStartV2PresetWorkflow", None),
        ]

        result = await client_session_with_limits.call_tool("workflows_get_all", {})

        assert not result.is_error
        content = get_tool_result_content(result)
        # A shared workflow is kept: it carries no issue data.
        assert [row["id"] for row in content] == ["W2", "quickStartV2PresetWorkflow"]


class TestWorkflowGet:
    async def test_returns_workflow(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = workflow("W9", "TEST")

        result = await client_session.call_tool("workflow_get", {"workflow_id": "W9"})

        assert not result.is_error
        mock_workflows_protocol.workflow_get.assert_called_once()
        call_args = mock_workflows_protocol.workflow_get.call_args
        assert call_args.args[0] == "W9"
        assert "auth" in call_args.kwargs

        content = get_tool_result_content(result)
        assert content["id"] == "W9"
        assert content["version"] == 7
        assert content["queue"]["key"] == "TEST"
        assert content["initialAction"]["target"]["key"] == "open"
        assert [s["status"]["key"] for s in content["steps"]] == [
            "open",
            "inProgress",
            "closed",
        ]
        # The wire spellings, as the write tools and Tracker name them.
        assert content["steps"][0]["statusType"] == "new"
        close = content["steps"][1]["actions"][0]
        assert close["screen"]["id"] == "704"
        # Compact by default: references by key, no diagram coordinates.
        assert close["postFunctions"] == [
            {"type": "SetResolutionFunction", "resolution": "fixed"}
        ]
        assert "stepCoords" not in content["steps"][0]
        assert "actionCoords" not in content["steps"][0]["actions"][0]

    async def test_full_keeps_references_and_coordinates(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = workflow("W9", "TEST")

        result = await client_session.call_tool(
            "workflow_get", {"workflow_id": "W9", "full": True}
        )

        content = get_tool_result_content(result)
        assert content["steps"][0]["stepCoords"] == {"x": 100, "y": 100}
        assert content["steps"][0]["actions"][0]["actionCoords"] == {
            "start": 2,
            "finish": 0,
        }
        assert content["steps"][1]["actions"][0]["postFunctions"] == [
            {"type": "SetResolutionFunction", "resolution": FIXED_REF}
        ]

    async def test_one_status(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = workflow("W9", "TEST")

        result = await client_session.call_tool(
            "workflow_get", {"workflow_id": "W9", "status": "inProgress"}
        )

        content = get_tool_result_content(result)
        assert [s["status"]["key"] for s in content["steps"]] == ["inProgress"]
        assert content["initialAction"]["target"]["key"] == "open"

    async def test_unknown_status_names_the_statuses_there_are(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = workflow("W9", "TEST")

        result = await client_session.call_tool(
            "workflow_get", {"workflow_id": "W9", "status": "nowhere"}
        )

        assert result.is_error
        text = result.content[0]
        assert isinstance(text, TextContent)
        assert "open, inProgress, closed" in text.text

    async def test_unknown_workflow_error_is_passed_through(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.workflow_get.side_effect = WorkflowNotFound("W404")

        result = await client_session.call_tool("workflow_get", {"workflow_id": "W404"})

        assert result.is_error
        error = result.content[0]
        assert isinstance(error, TextContent)
        assert "W404" in error.text
        assert "workflows_get_all" in error.text

    async def test_restricted_queue_is_rejected_after_the_read(
        self, client_session_with_limits: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        """The id names no queue, so the check can only run on what came back."""
        mock_workflows_protocol.workflow_get.return_value = workflow("W1", "RESTRICTED")

        result = await client_session_with_limits.call_tool(
            "workflow_get", {"workflow_id": "W1"}
        )

        assert result.is_error
        mock_workflows_protocol.workflow_get.assert_called_once()
        # Reported as not found, without naming the queue the allow-list hides.
        error = result.content[0]
        assert isinstance(error, TextContent)
        assert "not found" in error.text
        assert "RESTRICTED" not in error.text

    @pytest.mark.parametrize(
        ("workflow_id", "queue"),
        [("W2", "ALLOWED"), ("quickStartV2PresetWorkflow", None)],
        ids=["allowed-queue", "shared"],
    )
    async def test_allowed_or_shared_workflow_passes(
        self,
        client_session_with_limits: Client,
        mock_workflows_protocol: AsyncMock,
        workflow_id: str,
        queue: str | None,
    ) -> None:
        mock_workflows_protocol.workflow_get.return_value = workflow(workflow_id, queue)

        result = await client_session_with_limits.call_tool(
            "workflow_get", {"workflow_id": workflow_id}
        )

        assert not result.is_error
        assert get_tool_result_content(result)["id"] == workflow_id


class TestScreenGet:
    async def test_returns_screen(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        sample_screen: Screen,
    ) -> None:
        mock_workflows_protocol.screen_get.return_value = sample_screen

        result = await client_session.call_tool("screen_get", {"screen_id": 704})

        assert not result.is_error
        mock_workflows_protocol.screen_get.assert_called_once()
        call_args = mock_workflows_protocol.screen_get.call_args
        assert call_args.args[0] == 704
        assert "auth" in call_args.kwargs

        content = get_tool_result_content(result)
        assert content["id"] == 704
        assert content["title"] == "Укажите резолюцию"
        assert [(e["field"]["id"], e["required"]) for e in content["elements"]] == [
            ("resolution", True),
            ("6582fa303d406816db7e1dd4--systemId", False),
        ]

    async def test_takes_the_id_as_a_workflow_read_gives_it(
        self,
        client_session: Client,
        mock_workflows_protocol: AsyncMock,
        sample_screen: Screen,
    ) -> None:
        """`workflow_get` returns `screen.id` as a string."""
        mock_workflows_protocol.screen_get.return_value = sample_screen

        result = await client_session.call_tool("screen_get", {"screen_id": "704"})

        assert not result.is_error
        assert mock_workflows_protocol.screen_get.call_args.args[0] == 704

    async def test_unknown_screen_error_is_passed_through(
        self, client_session: Client, mock_workflows_protocol: AsyncMock
    ) -> None:
        mock_workflows_protocol.screen_get.side_effect = ScreenNotFound(99999)

        result = await client_session.call_tool("screen_get", {"screen_id": 99999})

        assert result.is_error
        error = result.content[0]
        assert isinstance(error, TextContent)
        assert "99999" in error.text

    async def test_is_not_checked_against_queue_limits(
        self,
        client_session_with_limits: Client,
        mock_workflows_protocol: AsyncMock,
        sample_screen: Screen,
    ) -> None:
        """A screen carries no issue data, and names its queue nowhere usable."""
        mock_workflows_protocol.screen_get.return_value = sample_screen

        result = await client_session_with_limits.call_tool(
            "screen_get", {"screen_id": 704}
        )

        assert not result.is_error
