"""Attaching a file the server fetches by URL (`TRACKER_ATTACHMENT_URL_PREFIXES`):
only under the prefixes the operator listed, without following redirects, without
Tracker's credentials and within `TRACKER_MAX_ATTACHMENT_BYTES`."""

import re
from unittest.mock import AsyncMock

import pytest
from aioresponses import aioresponses
from mcp import Client
from mcp.types import CallToolResult, TextContent

from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.tools._files import fetch_upload_url
from mcp_tracker.tracker.proto.types.issues import IssueAttachment
from tests.mcp.conftest import (
    TEST_URL_PREFIX,
    create_test_settings,
    get_tool_result_content,
)

FILE_URL = f"{TEST_URL_PREFIX}reports/%D0%BE%D1%82%D1%87%D1%91%D1%82.xlsx"
CONTENT = b"PK\x03\x04 report"


def error_text(result: CallToolResult) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


class TestIssueAddAttachmentFromUrl:
    async def test_uploads_the_fetched_bytes_under_the_url_name(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_attachment: IssueAttachment,
    ) -> None:
        mock_issues_protocol.issue_add_attachment.return_value = sample_attachment

        with aioresponses() as m:
            m.get(FILE_URL, body=CONTENT)
            result = await client_session.call_tool(
                "issue_add_attachment_from_url",
                {"issue_id": "TEST-1", "file_url": FILE_URL},
            )

        assert not result.is_error
        call = mock_issues_protocol.issue_add_attachment.call_args
        assert call.args == ("TEST-1",)
        assert call.kwargs["content"] == CONTENT
        assert call.kwargs["filename"] == "отчёт.xlsx"
        assert get_tool_result_content(result)["id"] == sample_attachment.id

    async def test_filename_overrides_the_url_name(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_attachment: IssueAttachment,
    ) -> None:
        mock_issues_protocol.issue_add_attachment.return_value = sample_attachment

        with aioresponses() as m:
            m.get(FILE_URL, body=CONTENT)
            await client_session.call_tool(
                "issue_add_attachment_from_url",
                {"issue_id": "TEST-1", "file_url": FILE_URL, "filename": "q3.xlsx"},
            )

        assert mock_issues_protocol.issue_add_attachment.call_args.kwargs[
            "filename"
        ] == ("q3.xlsx")

    async def test_a_read_only_queue_is_refused_before_the_fetch(
        self,
        client_session_with_read_only_queues: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        with aioresponses() as m:
            result = await client_session_with_read_only_queues.call_tool(
                "issue_add_attachment_from_url",
                {"issue_id": "READONLY-1", "file_url": FILE_URL},
            )
            assert not m.requests

        assert result.is_error
        mock_issues_protocol.issue_add_attachment.assert_not_called()


class TestAttachmentCreateFromUrl:
    async def test_uploads_a_temporary_attachment(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        sample_attachment: IssueAttachment,
    ) -> None:
        mock_issues_protocol.attachment_create.return_value = sample_attachment

        with aioresponses() as m:
            m.get(FILE_URL, body=CONTENT)
            result = await client_session.call_tool(
                "attachment_create_from_url", {"file_url": FILE_URL}
            )

        assert not result.is_error
        call = mock_issues_protocol.attachment_create.call_args
        assert (call.kwargs["content"], call.kwargs["filename"]) == (
            CONTENT,
            "отчёт.xlsx",
        )

    async def test_a_url_outside_the_prefixes_is_refused(
        self, client_session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "attachment_create_from_url",
            {"file_url": "https://files.example.com.attacker.net/x.txt"},
        )

        assert result.is_error
        assert "TRACKER_ATTACHMENT_URL_PREFIXES" in error_text(result)
        mock_issues_protocol.attachment_create.assert_not_called()


class TestFetchUploadUrl:
    async def test_sends_no_tracker_credentials(self) -> None:
        with aioresponses() as m:
            m.get(FILE_URL, body=CONTENT)
            await fetch_upload_url(create_test_settings(), FILE_URL)

            (request,) = [call for calls in m.requests.values() for call in calls]
        headers = {k.lower() for k in (request.kwargs.get("headers") or {})}
        assert not headers & {"authorization", "x-org-id", "x-cloud-org-id"}
        assert request.kwargs["allow_redirects"] is False

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("http://files.example.com/x.txt", id="plain-http"),
            pytest.param("https://files.example.com.evil.net/x", id="look-alike"),
            pytest.param("https://other.example.com/x.txt", id="other-host"),
        ],
    )
    async def test_refuses_a_url_outside_the_prefixes(self, url: str) -> None:
        with aioresponses() as m:
            with pytest.raises(TrackerError, match="not under a URL prefix"):
                await fetch_upload_url(create_test_settings(), url)
            assert not m.requests

    async def test_does_not_follow_a_redirect(self) -> None:
        with aioresponses() as m:
            m.get(FILE_URL, status=302, headers={"Location": "https://evil.net/x"})
            with pytest.raises(TrackerError, match="redirect"):
                await fetch_upload_url(create_test_settings(), FILE_URL)

    async def test_an_error_status_is_reported(self) -> None:
        with aioresponses() as m:
            m.get(FILE_URL, status=404)
            with pytest.raises(TrackerError, match="404"):
                await fetch_upload_url(create_test_settings(), FILE_URL)

    async def test_a_file_over_the_limit_is_refused(self) -> None:
        settings = create_test_settings().model_copy(
            update={"tracker_max_attachment_bytes": 4}
        )

        with aioresponses() as m:
            m.get(FILE_URL, body=CONTENT)
            with pytest.raises(TrackerError, match="TRACKER_MAX_ATTACHMENT_BYTES"):
                await fetch_upload_url(settings, FILE_URL)

    async def test_a_url_without_a_file_name_gets_a_default(self) -> None:
        with aioresponses() as m:
            m.get(re.compile(re.escape(TEST_URL_PREFIX) + "$"), body=CONTENT)
            _, name = await fetch_upload_url(create_test_settings(), TEST_URL_PREFIX)

        assert name == "attachment"
