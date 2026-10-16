from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from mcp import Client
from mcp.types import CallToolResult, TextContent

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.server import create_mcp_server
from mcp_tracker.tracker.custom.errors import AttachmentNotFound, TrackerAPIError
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.issues import (
    ChangelogComments,
    ChangelogEntry,
    ChangelogExecutedTrigger,
    ChangelogPage,
    ChangelogReference,
    ChecklistItem,
    CommentsPage,
    Issue,
    IssueAttachment,
    IssueComment,
    IssueLink,
    IssueTransition,
    RemoteLink,
    Worklog,
)
from tests.mcp.conftest import (
    create_test_settings,
    get_tool_result_content,
    make_test_lifespan,
    page,
    safe_client_session,
)


class TestIssueGetUrl:
    async def test_returns_tracker_url(
        self,
        client_session: Client,
    ) -> None:
        result = await client_session.call_tool(
            "issue_get_url", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content == "https://tracker.yandex.ru/TEST-123"


class TestIssueGet:
    async def test_a_moved_issue_is_checked_by_its_new_queue(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        """Tracker serves an issue moved out of an allowed queue under its old key
        too: the key it answers with decides."""
        mock_issues_protocol.issue_get.return_value = Issue(
            key="HIDDEN-7", summary="secret"
        )

        result = await client_session_with_limits.call_tool(
            "issue_get", {"issue_id": "ALLOWED-1"}
        )

        assert result.is_error
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "secret" not in content.text

    async def test_returns_issue(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issue: Issue,
    ) -> None:
        mock_issues_protocol.issue_get.return_value = sample_issue

        result = await client_session.call_tool("issue_get", {"issue_id": "TEST-123"})

        assert not result.is_error
        mock_issues_protocol.issue_get.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, dict)
        assert content["key"] == sample_issue.key
        assert content["summary"] == sample_issue.summary

    async def test_with_description_excluded(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issue: Issue,
    ) -> None:
        mock_issues_protocol.issue_get.return_value = sample_issue

        result = await client_session.call_tool(
            "issue_get", {"issue_id": "TEST-123", "include_description": False}
        )

        assert not result.is_error
        mock_issues_protocol.issue_get.assert_called_once()
        content = get_tool_result_content(result)
        assert content["key"] == sample_issue.key
        # Description should be None when excluded
        assert content.get("description") is None

    async def test_restricted_queue_raises_error(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_get", {"issue_id": "RESTRICTED-123"}
        )

        assert result.is_error
        mock_issues_protocol.issue_get.assert_not_called()

    async def test_tracker_api_error_text_reaches_the_caller(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        """`TrackerAPIError` subclasses `ToolError`, so the SDK keeps its text in
        the result instead of hiding it behind a bare `Error executing tool`."""
        mock_issues_protocol.issue_get.side_effect = TrackerAPIError(
            status=403,
            method="GET",
            url="https://api.tracker.yandex.net/v3/issues/TEST-123",
            body='{"errorMessages": ["You do not have access to this issue."], "errors": {}}',
        )

        result = await client_session.call_tool("issue_get", {"issue_id": "TEST-123"})

        assert result.is_error
        error = result.content[0]
        assert isinstance(error, TextContent)
        assert error.text.startswith("Error executing tool issue_get:")
        assert (
            "Yandex Tracker API error 403 on GET "
            "https://api.tracker.yandex.net/v3/issues/TEST-123" in error.text
        )
        assert "You do not have access to this issue." in error.text


class TestIssueGetComments:
    async def test_returns_comments(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_comments: list[IssueComment],
    ) -> None:
        mock_issues_protocol.issue_get_comments.return_value = CommentsPage(
            comments=sample_comments, next_cursor="99"
        )

        result = await client_session.call_tool(
            "issue_get_comments", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        mock_issues_protocol.issue_get_comments.assert_called_once_with(
            "TEST-123", per_page=50, cursor=None, auth=YandexAuth()
        )
        content = get_tool_result_content(result)
        assert content["next_cursor"] == "99"
        assert len(content["comments"]) == len(sample_comments)
        assert content["comments"][0]["text"] == sample_comments[0].text

    async def test_passes_pagination_params(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_comments: list[IssueComment],
    ) -> None:
        mock_issues_protocol.issue_get_comments.return_value = CommentsPage(
            comments=sample_comments
        )

        result = await client_session.call_tool(
            "issue_get_comments",
            {"issue_id": "TEST-123", "per_page": 10, "cursor": "42"},
        )

        assert not result.is_error
        mock_issues_protocol.issue_get_comments.assert_called_once_with(
            "TEST-123", per_page=10, cursor="42", auth=YandexAuth()
        )

    async def test_restricted_queue_raises_error(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_get_comments", {"issue_id": "RESTRICTED-123"}
        )

        assert result.is_error
        mock_issues_protocol.issue_get_comments.assert_not_called()

    async def test_fields_filters_response(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_comments: list[IssueComment],
    ) -> None:
        mock_issues_protocol.issue_get_comments.return_value = CommentsPage(
            comments=sample_comments
        )

        result = await client_session.call_tool(
            "issue_get_comments", {"issue_id": "TEST-123", "fields": ["text"]}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["comments"][0]["text"] == sample_comments[0].text
        assert content["comments"][0].get("createdBy") is None


class TestIssueGetLinks:
    async def test_returns_links(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_links: list[IssueLink],
    ) -> None:
        mock_issues_protocol.issues_get_links.return_value = sample_links

        result = await client_session.call_tool(
            "issue_get_links", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        mock_issues_protocol.issues_get_links.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        assert len(content) == len(sample_links)
        assert content[0]["direction"] == sample_links[0].direction


class TestIssuesFind:
    async def test_finds_issues(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issues: list[Issue],
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(
            sample_issues, hits=403, pages=5
        )

        result = await client_session.call_tool("issues_find", {"query": "Queue: TEST"})

        assert not result.is_error
        mock_issues_protocol.issues_find.assert_called_once()
        content = get_tool_result_content(result)
        assert len(content["values"]) == len(sample_issues)
        assert content["values"][0]["key"] == sample_issues[0].key

    async def test_returns_pagination_totals(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issues: list[Issue],
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(
            sample_issues, hits=403, pages=5
        )

        result = await client_session.call_tool("issues_find", {"query": "Queue: TEST"})

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["hits"] == 403
        assert content["pages"] == 5

    async def test_with_pagination(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issues: list[Issue],
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(sample_issues)

        result = await client_session.call_tool(
            "issues_find", {"query": "Queue: TEST", "page": 2, "per_page": 50}
        )

        assert not result.is_error
        call_kwargs = mock_issues_protocol.issues_find.call_args.kwargs
        assert call_kwargs["page"] == 2
        assert call_kwargs["per_page"] == 50
        content = get_tool_result_content(result)
        assert len(content["values"]) == len(sample_issues)

    async def test_excludes_description_by_default(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issues: list[Issue],
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(sample_issues)

        result = await client_session.call_tool("issues_find", {"query": "Queue: TEST"})

        assert not result.is_error
        mock_issues_protocol.issues_find.assert_called_once()
        content = get_tool_result_content(result)
        # By default, description is excluded (set to None)
        for issue in content["values"]:
            assert issue.get("description") is None

    async def test_fields_are_pushed_down_to_the_api(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issues: list[Issue],
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(sample_issues)

        result = await client_session.call_tool(
            "issues_find", {"query": "Queue: TEST", "fields": ["key", "story_points"]}
        )

        assert not result.is_error
        # The API only understands Tracker's own spelling of a field name.
        assert sorted(mock_issues_protocol.issues_find.call_args.kwargs["fields"]) == [
            "key",
            "storyPoints",
        ]

    async def test_fields_accept_trackers_own_spelling(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        issue = Issue.model_construct(key="TEST-123", story_points=3.0)
        mock_issues_protocol.issues_find.return_value = page([issue])

        result = await client_session.call_tool(
            "issues_find", {"query": "Queue: TEST", "fields": ["key", "storyPoints"]}
        )

        assert not result.is_error
        assert mock_issues_protocol.issues_find.call_args.kwargs["fields"] == [
            "key",
            "storyPoints",
        ]
        # Requested Tracker's way, kept under the model's own name.
        content = get_tool_result_content(result)
        assert content["values"][0]["storyPoints"] == 3.0

    async def test_both_spellings_of_one_field_are_sent_once(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issues: list[Issue],
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(sample_issues)

        result = await client_session.call_tool(
            "issues_find",
            {"query": "Queue: TEST", "fields": ["story_points", "storyPoints"]},
        )

        assert not result.is_error
        assert not result.is_error
        # `key` rides along: the AI access check needs the queue it names.
        assert mock_issues_protocol.issues_find.call_args.kwargs["fields"] == [
            "storyPoints",
            "key",
        ]

    async def test_fields_accept_a_field_the_model_does_not_declare(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        """A queue's local fields and the standard fields `Issue` omits are only
        reachable because the selector is free-form."""
        issue = Issue.model_validate(
            {
                "key": "TEST-123",
                "resolution": {"id": "1", "key": "fixed"},
                "694c13a2974fc069fc7db927--chapter": "Support",
                "queue": {"id": "1", "key": "TEST"},
            }
        )
        mock_issues_protocol.issues_find.return_value = page([issue])

        result = await client_session.call_tool(
            "issues_find",
            {
                "query": "Queue: TEST",
                "fields": ["key", "resolution", "694c13a2974fc069fc7db927--chapter"],
            },
        )

        assert not result.is_error
        assert mock_issues_protocol.issues_find.call_args.kwargs["fields"] == [
            "key",
            "resolution",
            "694c13a2974fc069fc7db927--chapter",
        ]
        content = get_tool_result_content(result)
        # Requested extras survive; `queue`, which was not asked for, does not.
        assert content["values"][0] == {
            "key": "TEST-123",
            "resolution": {"id": "1", "key": "fixed"},
            "694c13a2974fc069fc7db927--chapter": "Support",
        }

    async def test_no_fields_param_when_not_selected(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_issues: list[Issue],
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(sample_issues)

        result = await client_session.call_tool("issues_find", {"query": "Queue: TEST"})

        assert not result.is_error
        assert mock_issues_protocol.issues_find.call_args.kwargs["fields"] is None

    async def test_fields_drop_undeclared_api_fields(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        # Tracker adds `self`, `id`, `version` and `favorite` to every projection,
        # and a queue's local fields come back as `<queue-id>--<key>`. None of them
        # are declared on `Issue`, so they land in the model's extras.
        issue = Issue.model_validate(
            {
                "self": "https://api.tracker.yandex.net/v3/issues/TEST-123",
                "id": "593cd211ef7e8a33abcd1234",
                "key": "TEST-123",
                "version": 1,
                "favorite": False,
                "statusStartTime": "2024-01-01T00:00:00.000+0000",
                "queue": {"id": "1", "key": "TEST"},
                "694c13a2974fc069fc7db927--chapter": None,
            }
        )
        mock_issues_protocol.issues_find.return_value = page([issue])

        result = await client_session.call_tool(
            "issues_find", {"query": "Queue: TEST", "fields": ["key"]}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["values"] == [{"key": "TEST-123"}]

    async def test_description_selected_through_fields_is_kept(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        issue = Issue.model_construct(key="TEST-123", description="Body text")
        mock_issues_protocol.issues_find.return_value = page([issue])

        result = await client_session.call_tool(
            "issues_find",
            {"query": "Queue: TEST", "fields": ["key", "description"]},
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        # `include_description` defaults to False, but asking for `description`
        # through `fields` is an explicit request for it.
        assert content["values"][0]["description"] == "Body text"


class TestIssuesCount:
    async def test_returns_count(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issues_count.return_value = 42

        result = await client_session.call_tool(
            "issues_count", {"query": "Queue: TEST"}
        )

        assert not result.is_error
        mock_issues_protocol.issues_count.assert_called_once()
        content = get_tool_result_content(result)
        # A named field, so the number cannot be mistaken for an HTTP status.
        assert content == {"count": 42}


class TestIssueGetWorklogs:
    async def test_returns_worklogs_for_multiple_issues(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_worklogs: list[Worklog],
    ) -> None:
        mock_issues_protocol.issue_get_worklogs.return_value = sample_worklogs

        result = await client_session.call_tool(
            "issue_get_worklogs", {"issue_ids": ["TEST-123", "TEST-124"]}
        )

        assert not result.is_error
        # Should be called once per issue
        assert mock_issues_protocol.issue_get_worklogs.call_count == 2
        content = get_tool_result_content(result)
        assert isinstance(content, dict)
        assert "TEST-123" in content
        assert "TEST-124" in content
        assert len(content["TEST-123"]) == len(sample_worklogs)

    async def test_restricted_queue_raises_error(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_get_worklogs", {"issue_ids": ["RESTRICTED-123"]}
        )

        assert result.is_error
        mock_issues_protocol.issue_get_worklogs.assert_not_called()

    async def test_fields_filters_response(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_worklogs: list[Worklog],
    ) -> None:
        mock_issues_protocol.issue_get_worklogs.return_value = sample_worklogs

        result = await client_session.call_tool(
            "issue_get_worklogs",
            {"issue_ids": ["TEST-123"], "fields": ["comment"]},
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["TEST-123"][0]["comment"] == sample_worklogs[0].comment
        assert content["TEST-123"][0].get("createdBy") is None


class TestIssueGetAttachments:
    async def test_returns_attachments(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_attachments: list[IssueAttachment],
    ) -> None:
        mock_issues_protocol.issue_get_attachments.return_value = sample_attachments

        result = await client_session.call_tool(
            "issue_get_attachments", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        mock_issues_protocol.issue_get_attachments.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        assert len(content) == len(sample_attachments)
        assert content[0]["name"] == sample_attachments[0].name

    async def test_fields_filters_response(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_attachments: list[IssueAttachment],
    ) -> None:
        mock_issues_protocol.issue_get_attachments.return_value = sample_attachments

        result = await client_session.call_tool(
            "issue_get_attachments", {"issue_id": "TEST-123", "fields": ["name"]}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content[0]["name"] == sample_attachments[0].name
        assert content[0].get("content") is None


@pytest_asyncio.fixture(loop_scope="function")
async def download_session(
    mock_app_context: AppContext, tmp_path: Path
) -> AsyncIterator[Client]:
    """A session whose downloads land in `tmp_path`, with ALLOWED the only queue."""
    server = create_mcp_server(
        settings=create_test_settings(
            limit_queues=["ALLOWED"], attachments_dir=str(tmp_path)
        ),
        lifespan=make_test_lifespan(mock_app_context),
    )
    async with safe_client_session(server) as session:
        yield session


async def write_attachment(
    issue_id: str,
    attachment_id: str,
    file_name: str,
    destination: Path,
    *,
    auth: Any = None,
) -> int:
    """Stands in for the HTTP download: writes the file where it was asked to."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"x" * 1024)
    return 1024


def error_text(result: CallToolResult) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


class TestIssueDownloadAttachment:
    @pytest.fixture
    def attachment(self) -> IssueAttachment:
        return IssueAttachment.model_construct(
            id="7946", name="image.png", size=1024, mimetype="image/png"
        )

    async def test_saves_under_the_issue_and_returns_the_absolute_path(
        self,
        download_session: Client,
        mock_issues_protocol: AsyncMock,
        attachment: IssueAttachment,
        tmp_path: Path,
    ) -> None:
        mock_issues_protocol.issue_get_attachment.return_value = attachment
        mock_issues_protocol.issue_download_attachment.side_effect = write_attachment

        result = await download_session.call_tool(
            "issue_download_attachment",
            {"issue_id": "ALLOWED-1", "attachment_id": "7946"},
        )

        assert not result.is_error
        mock_issues_protocol.issue_get_attachment.assert_called_once()
        assert mock_issues_protocol.issue_get_attachment.call_args.args == (
            "ALLOWED-1",
            "7946",
        )
        mock_issues_protocol.issue_get_attachments.assert_not_called()
        expected = tmp_path / "ALLOWED-1" / "7946-image.png"
        call_args = mock_issues_protocol.issue_download_attachment.call_args
        assert call_args.args == ("ALLOWED-1", "7946", "image.png", expected)
        content = get_tool_result_content(result)
        assert content == {
            "issue_id": "ALLOWED-1",
            "attachment_id": "7946",
            "name": "image.png",
            "path": str(expected),
            "mime_type": "image/png",
            "size": 1024,
        }
        assert Path(content["path"]).is_absolute()
        assert expected.is_file()

    async def test_a_file_already_downloaded_is_reused(
        self,
        download_session: Client,
        mock_issues_protocol: AsyncMock,
        attachment: IssueAttachment,
        tmp_path: Path,
    ) -> None:
        existing = tmp_path / "ALLOWED-1" / "7946-image.png"
        existing.parent.mkdir()
        existing.write_bytes(b"x" * 1024)
        mock_issues_protocol.issue_get_attachment.return_value = attachment

        result = await download_session.call_tool(
            "issue_download_attachment",
            {"issue_id": "ALLOWED-1", "attachment_id": "7946"},
        )

        assert not result.is_error
        mock_issues_protocol.issue_download_attachment.assert_not_called()
        assert get_tool_result_content(result)["path"] == str(existing)

    async def test_a_file_of_another_size_is_downloaded_again(
        self,
        download_session: Client,
        mock_issues_protocol: AsyncMock,
        attachment: IssueAttachment,
        tmp_path: Path,
    ) -> None:
        existing = tmp_path / "ALLOWED-1" / "7946-image.png"
        existing.parent.mkdir()
        existing.write_bytes(b"x" * 10)
        mock_issues_protocol.issue_get_attachment.return_value = attachment
        mock_issues_protocol.issue_download_attachment.side_effect = write_attachment

        result = await download_session.call_tool(
            "issue_download_attachment",
            {"issue_id": "ALLOWED-1", "attachment_id": "7946"},
        )

        assert not result.is_error
        mock_issues_protocol.issue_download_attachment.assert_called_once()

    async def test_an_unsafe_name_stays_inside_the_directory(
        self,
        download_session: Client,
        mock_issues_protocol: AsyncMock,
        tmp_path: Path,
    ) -> None:
        mock_issues_protocol.issue_get_attachment.return_value = (
            IssueAttachment.model_construct(
                id="7946", name="../../evil:name?.png", size=1024, mimetype=None
            )
        )
        mock_issues_protocol.issue_download_attachment.side_effect = write_attachment

        result = await download_session.call_tool(
            "issue_download_attachment",
            {"issue_id": "ALLOWED-1", "attachment_id": "7946"},
        )

        assert not result.is_error
        call_args = mock_issues_protocol.issue_download_attachment.call_args
        destination = call_args.args[3]
        assert destination.parent == tmp_path / "ALLOWED-1"
        assert destination.name == "7946-.._.._evil_name_.png"
        # Tracker is still asked for the attachment under its real name.
        assert call_args.args[2] == "../../evil:name?.png"

    async def test_an_unknown_attachment_is_reported_without_a_download(
        self,
        download_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get_attachment.side_effect = AttachmentNotFound(
            "ALLOWED-1", "1"
        )

        result = await download_session.call_tool(
            "issue_download_attachment",
            {"issue_id": "ALLOWED-1", "attachment_id": "1"},
        )

        assert result.is_error
        assert "issue_get_attachments" in error_text(result)
        mock_issues_protocol.issue_download_attachment.assert_not_called()

    async def test_an_oversized_attachment_is_refused_before_the_download(
        self,
        download_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get_attachment.return_value = (
            IssueAttachment.model_construct(
                id="7946", name="video.mp4", size=51 * 1024 * 1024, mimetype=None
            )
        )

        result = await download_session.call_tool(
            "issue_download_attachment",
            {"issue_id": "ALLOWED-1", "attachment_id": "7946"},
        )

        assert result.is_error
        assert "TRACKER_MAX_ATTACHMENT_BYTES" in error_text(result)
        mock_issues_protocol.issue_download_attachment.assert_not_called()

    async def test_a_queue_outside_the_allow_list_is_refused(
        self,
        download_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await download_session.call_tool(
            "issue_download_attachment",
            {"issue_id": "OTHER-1", "attachment_id": "7946"},
        )

        assert result.is_error
        mock_issues_protocol.issue_get_attachment.assert_not_called()
        mock_issues_protocol.issue_download_attachment.assert_not_called()


class TestIssueGetChecklist:
    async def test_returns_checklist(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_checklist: list[ChecklistItem],
    ) -> None:
        mock_issues_protocol.issue_get_checklist.return_value = sample_checklist

        result = await client_session.call_tool(
            "issue_get_checklist", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        mock_issues_protocol.issue_get_checklist.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        assert len(content) == len(sample_checklist)
        assert content[0]["text"] == sample_checklist[0].text
        assert "textHtml" not in content[0]
        assert "assignee" not in content[0]
        assert "deadline" not in content[0]
        assert "checklistItemType" not in content[0]


class TestIssueGetTransitions:
    async def test_returns_transitions(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_transitions: list[IssueTransition],
    ) -> None:
        mock_issues_protocol.issue_get_transitions.return_value = sample_transitions

        result = await client_session.call_tool(
            "issue_get_transitions", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        mock_issues_protocol.issue_get_transitions.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        assert len(content) == len(sample_transitions)
        assert content[0]["id"] == sample_transitions[0].id
        assert content[0]["display"] == sample_transitions[0].display


class TestIssueGetChangelog:
    async def test_returns_changelog(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_changelog: ChangelogPage,
    ) -> None:
        mock_issues_protocol.issue_get_changelog.return_value = sample_changelog

        result = await client_session.call_tool(
            "issue_get_changelog", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        mock_issues_protocol.issue_get_changelog.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, dict)
        assert content["next_cursor"] == sample_changelog.next_cursor
        entries = content["entries"]
        assert len(entries) == len(sample_changelog.entries)
        assert entries[0]["id"] == sample_changelog.entries[0].id
        assert entries[0]["type"] == sample_changelog.entries[0].type
        # `from` is serialized by its alias, not the python-safe `from_`,
        # and its full reference-object value must survive serialization
        assert entries[0]["fields"][0]["from"] == {
            "id": "1",
            "key": "open",
            "display": "Open",
        }
        # field display must survive serialization
        assert entries[0]["fields"][0]["field"]["display"] == "Status"

    async def test_surfaces_comment_and_trigger_payload(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        # A comment-type entry carries its payload in top-level `comments`/
        # `executedTriggers` rather than `fields`; both must reach the client.
        mock_issues_protocol.issue_get_changelog.return_value = ChangelogPage(
            entries=[
                ChangelogEntry(
                    id="c1",
                    type="IssueCommentAdded",
                    comments=ChangelogComments(
                        added=[ChangelogReference(id=98765, display="Looks good")]
                    ),
                    executed_triggers=[
                        ChangelogExecutedTrigger(
                            trigger=ChangelogReference(id=7, display="Auto-assign"),
                            success=True,
                            message="ok",
                        )
                    ],
                )
            ],
            next_cursor=None,
        )

        result = await client_session.call_tool(
            "issue_get_changelog", {"issue_id": "TEST-123"}
        )

        assert not result.is_error
        entry = get_tool_result_content(result)["entries"][0]
        assert entry["comments"]["added"][0]["display"] == "Looks good"
        assert entry["executedTriggers"][0]["trigger"]["display"] == "Auto-assign"
        assert entry["executedTriggers"][0]["success"] is True

    async def test_passes_pagination_and_filters(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_changelog: ChangelogPage,
    ) -> None:
        mock_issues_protocol.issue_get_changelog.return_value = sample_changelog

        result = await client_session.call_tool(
            "issue_get_changelog",
            {
                "issue_id": "TEST-123",
                "per_page": 10,
                "cursor": "prev-entry-id",
                "field": "status",
                "type": "IssueWorkflow",
            },
        )

        assert not result.is_error
        _, kwargs = mock_issues_protocol.issue_get_changelog.call_args
        assert kwargs["per_page"] == 10
        assert kwargs["cursor"] == "prev-entry-id"
        assert kwargs["field"] == "status"
        assert kwargs["type"] == "IssueWorkflow"

    async def test_restricted_queue_raises_error(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_get_changelog", {"issue_id": "RESTRICTED-123"}
        )

        assert result.is_error
        mock_issues_protocol.issue_get_changelog.assert_not_called()

    async def test_rejects_non_positive_per_page(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "issue_get_changelog", {"issue_id": "TEST-123", "per_page": 0}
        )

        assert result.is_error
        mock_issues_protocol.issue_get_changelog.assert_not_called()


class TestIssueGetComment:
    async def test_returns_the_comment(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_issues_protocol.issue_get_comment.return_value = sample_comment

        result = await client_session.call_tool(
            "issue_get_comment", {"issue_id": "TEST-1", "comment_id": 7}
        )

        assert not result.is_error
        assert mock_issues_protocol.issue_get_comment.call_args.args == ("TEST-1", 7)
        assert get_tool_result_content(result)["id"] == sample_comment.id

    async def test_takes_a_long_id(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_issues_protocol.issue_get_comment.return_value = sample_comment

        await client_session.call_tool(
            "issue_get_comment",
            {"issue_id": "TEST-1", "comment_id": "5fa15a24ac894475dd14ff07"},
        )

        assert mock_issues_protocol.issue_get_comment.call_args.args == (
            "TEST-1",
            "5fa15a24ac894475dd14ff07",
        )

    async def test_restricted_queue_is_refused(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_get_comment", {"issue_id": "RESTRICTED-1", "comment_id": 7}
        )

        assert result.is_error
        mock_issues_protocol.issue_get_comment.assert_not_called()


class TestIssueGetRemoteLinks:
    async def test_returns_the_links(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get_remote_links.return_value = [
            RemoteLink(id=51, direction="outward", object={"key": "repo/pr/7"})
        ]

        result = await client_session.call_tool(
            "issue_get_remote_links", {"issue_id": "TEST-1"}
        )

        assert not result.is_error
        assert get_tool_result_content(result)[0]["object"]["key"] == "repo/pr/7"

    async def test_restricted_queue_is_refused(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "issue_get_remote_links", {"issue_id": "RESTRICTED-1"}
        )

        assert result.is_error
        mock_issues_protocol.issue_get_remote_links.assert_not_called()
