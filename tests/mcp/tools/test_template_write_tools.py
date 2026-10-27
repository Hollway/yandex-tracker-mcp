from typing import Any
from unittest.mock import ANY, AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.types.inputs import ChecklistItemInput
from mcp_tracker.tracker.proto.types.issues import Issue
from mcp_tracker.tracker.proto.types.templates import CommentTemplate, IssueTemplate
from tests.mcp.conftest import get_tool_result_content


def issue_template(queue: str | None = "TEST", **extra: Any) -> IssueTemplate:
    data: dict[str, Any] = {"id": 1, "version": 3, "name": "Bug report", **extra}
    if queue is not None:
        data["queue"] = {"id": "1", "key": queue, "display": queue}
    return IssueTemplate.model_validate(data)


def comment_template(queue: str | None = "TEST") -> CommentTemplate:
    data: dict[str, Any] = {"id": 1, "version": 5, "name": "Ack"}
    if queue is not None:
        data["queue"] = {"id": "1", "key": queue, "display": queue}
    return CommentTemplate.model_validate(data)


class TestIssueTemplateCreate:
    async def test_creates_the_template(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.issue_template_create.return_value = issue_template()

        result = await client_session.call_tool(
            "issue_template_create",
            {
                "name": "Bug report",
                "queue": "TEST",
                "field_templates": {"summary": "[Bug] "},
                "checklist_items": [{"text": "Reproduce"}],
            },
        )

        assert not result.is_error
        assert get_tool_result_content(result)["name"] == "Bug report"
        kwargs = mock_templates_protocol.issue_template_create.call_args.kwargs
        assert kwargs["queue"] == "TEST"
        assert kwargs["field_templates"] == {"summary": "[Bug] "}
        assert kwargs["checklist_items"] == [ChecklistItemInput(text="Reproduce")]

    async def test_a_queue_outside_the_allow_list_is_refused(
        self, client_session_with_limits: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_template_create", {"name": "x", "queue": "HIDDEN"}
        )

        assert result.is_error
        mock_templates_protocol.issue_template_create.assert_not_called()

    async def test_an_own_template_needs_no_queue(
        self, client_session_with_limits: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.issue_template_create.return_value = issue_template(
            queue=None
        )

        result = await client_session_with_limits.call_tool(
            "issue_template_create", {"name": "Mine"}
        )

        assert not result.is_error


class TestIssueTemplateUpdate:
    async def test_reads_the_current_version_when_none_is_given(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.get_issue_template.return_value = issue_template()
        mock_templates_protocol.issue_template_update.return_value = issue_template()

        result = await client_session.call_tool(
            "issue_template_update", {"template_id": "1", "name": "Renamed"}
        )

        assert not result.is_error
        mock_templates_protocol.issue_template_update.assert_awaited_once_with(
            "1",
            version=3,
            name="Renamed",
            field_templates=None,
            checklist_items=None,
            auth=ANY,
        )

    async def test_a_given_version_is_sent(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.get_issue_template.return_value = issue_template()
        mock_templates_protocol.issue_template_update.return_value = issue_template()

        await client_session.call_tool(
            "issue_template_update",
            {"template_id": "1", "field_templates": {"tags": ["x"]}, "version": 1},
        )

        kwargs = mock_templates_protocol.issue_template_update.call_args.kwargs
        assert kwargs["version"] == 1

    async def test_an_empty_update_is_refused_unread(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "issue_template_update", {"template_id": "1"}
        )

        assert result.is_error
        mock_templates_protocol.get_issue_template.assert_not_called()

    async def test_a_template_of_a_read_only_queue_is_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_templates_protocol: AsyncMock,
    ) -> None:
        mock_templates_protocol.get_issue_template.return_value = issue_template(
            queue="READONLY"
        )

        result = await client_session_with_read_only_queues.call_tool(
            "issue_template_update", {"template_id": "1", "name": "x"}
        )

        assert result.is_error
        assert "read-only" in result.content[0].text  # type: ignore[union-attr]
        mock_templates_protocol.issue_template_update.assert_not_called()


class TestIssueTemplateDelete:
    async def test_deletes_with_the_current_version(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.get_issue_template.return_value = issue_template()

        result = await client_session.call_tool(
            "issue_template_delete", {"template_id": "1"}
        )

        assert not result.is_error
        mock_templates_protocol.issue_template_delete.assert_awaited_once_with(
            "1", version=3, auth=ANY
        )

    async def test_a_template_outside_the_allow_list_is_refused(
        self, client_session_with_limits: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.get_issue_template.return_value = issue_template(
            queue="HIDDEN"
        )

        result = await client_session_with_limits.call_tool(
            "issue_template_delete", {"template_id": "1"}
        )

        assert result.is_error
        mock_templates_protocol.issue_template_delete.assert_not_called()


class TestCommentTemplateWrites:
    async def test_create(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.comment_template_create.return_value = (
            comment_template()
        )

        result = await client_session.call_tool(
            "comment_template_create",
            {"name": "Ack", "text": "On it", "summonees": ["login"]},
        )

        assert not result.is_error
        mock_templates_protocol.comment_template_create.assert_awaited_once_with(
            name="Ack",
            queue=None,
            text="On it",
            summonees=["login"],
            maillist_summonees=None,
            auth=ANY,
        )

    async def test_update_reads_the_current_version(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.get_comment_template.return_value = comment_template()
        mock_templates_protocol.comment_template_update.return_value = (
            comment_template()
        )

        result = await client_session.call_tool(
            "comment_template_update", {"template_id": "1", "text": "New"}
        )

        assert not result.is_error
        kwargs = mock_templates_protocol.comment_template_update.call_args.kwargs
        assert kwargs["version"] == 5
        assert kwargs["text"] == "New"

    async def test_an_empty_update_is_refused(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "comment_template_update", {"template_id": "1"}
        )

        assert result.is_error
        mock_templates_protocol.get_comment_template.assert_not_called()

    async def test_delete(
        self, client_session: Client, mock_templates_protocol: AsyncMock
    ) -> None:
        mock_templates_protocol.get_comment_template.return_value = comment_template(
            queue=None
        )

        result = await client_session.call_tool(
            "comment_template_delete", {"template_id": "1", "version": 4}
        )

        assert not result.is_error
        mock_templates_protocol.comment_template_delete.assert_awaited_once_with(
            "1", version=4, auth=ANY
        )


@pytest.mark.parametrize(
    "tool",
    [
        "issue_template_create",
        "issue_template_update",
        "issue_template_delete",
        "comment_template_create",
        "comment_template_update",
        "comment_template_delete",
    ],
)
async def test_not_registered_read_only(
    client_session_read_only: Client, tool: str
) -> None:
    tools = {t.name for t in (await client_session_read_only.list_tools()).tools}

    assert tool not in tools


class TestIssueCreateFromTemplate:
    """The template fills what the arguments leave out; an argument wins."""

    @pytest.fixture
    def template(self, mock_templates_protocol: AsyncMock) -> IssueTemplate:
        template = issue_template(
            fieldTemplates={
                "summary": "[Bug] ",
                "description": "Steps",
                "type": {"self": "u", "id": "1", "key": "bug", "display": "Bug"},
                "followers": [{"self": "u", "id": "42", "display": "User"}],
                "tags": ["triage"],
                "storyPoints": 3.0,
            },
            checklistItems=[
                {"id": "a", "text": "Reproduce", "checked": False},
                {
                    "id": "b",
                    "text": "Fix",
                    "checked": True,
                    "assignee": {"id": 42, "login": "dev", "display": "Dev"},
                },
            ],
        )
        mock_templates_protocol.get_issue_template.return_value = template
        return template

    async def test_the_template_fills_the_body(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        template: IssueTemplate,
    ) -> None:
        mock_issues_protocol.issue_create.return_value = Issue(key="TEST-5")

        result = await client_session.call_tool(
            "issue_create", {"queue": "TEST", "template_id": "1"}
        )

        assert not result.is_error
        kwargs = mock_issues_protocol.issue_create.call_args.kwargs
        assert kwargs["summary"] == "[Bug] "
        assert kwargs["type"] is None
        assert kwargs["fields"] == {
            "description": "Steps",
            "type": {"id": "1"},
            "followers": [{"id": "42"}],
            "tags": ["triage"],
            "storyPoints": 3.0,
        }
        mock_issues_protocol.issue_add_checklist_items.assert_awaited_once_with(
            "TEST-5",
            items=[
                ChecklistItemInput(text="Reproduce", checked=False),
                ChecklistItemInput(text="Fix", checked=True, assignee="dev"),
            ],
            auth=ANY,
        )

    async def test_an_argument_wins_over_the_template(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        template: IssueTemplate,
    ) -> None:
        mock_issues_protocol.issue_create.return_value = Issue(key="TEST-5")

        await client_session.call_tool(
            "issue_create",
            {
                "queue": "TEST",
                "template_id": "1",
                "summary": "Crash on start",
                "type": "task",
                "fields": {"storyPoints": 5},
            },
        )

        kwargs = mock_issues_protocol.issue_create.call_args.kwargs
        assert kwargs["summary"] == "Crash on start"
        assert kwargs["type"] == "task"
        assert "type" not in kwargs["fields"]
        assert kwargs["fields"]["storyPoints"] == 5

    async def test_a_template_of_another_queue_is_refused(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        template: IssueTemplate,
    ) -> None:
        result = await client_session.call_tool(
            "issue_create", {"queue": "OTHER", "template_id": "1", "summary": "x"}
        )

        assert result.is_error
        mock_issues_protocol.issue_create.assert_not_called()

    async def test_no_summary_without_a_template_is_refused(
        self, client_session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool("issue_create", {"queue": "TEST"})

        assert result.is_error
        assert "summary" in result.content[0].text  # type: ignore[union-attr]
        mock_issues_protocol.issue_create.assert_not_called()

    async def test_without_a_template_no_checklist_is_added(
        self, client_session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_create.return_value = Issue(key="TEST-5")

        await client_session.call_tool(
            "issue_create", {"queue": "TEST", "summary": "x"}
        )

        assert mock_issues_protocol.issue_create.call_args.kwargs["fields"] is None
        mock_issues_protocol.issue_add_checklist_items.assert_not_called()
