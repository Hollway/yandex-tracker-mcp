from pathlib import Path
from typing import Any

import pytest
from aiohttp import ClientTimeout
from aioresponses import aioresponses
from pytest_mock import MockerFixture

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    AttachmentNotFound,
    AttachmentTooLarge,
    IssueNotFound,
    TrackerAPITimeout,
)
from mcp_tracker.tracker.proto.types.issues import IssueAttachment
from tests.aioresponses_utils import RequestCapture

UPLOAD_URL = "https://api.tracker.yandex.net/v3/issues/TEST-123/attachments/"
DOWNLOAD_URL = "https://api.tracker.yandex.net/v3/issues/TEST-123/attachments/7946"

# Not valid UTF-8, with the bytes a text-mode round trip would mangle.
FILE_CONTENT = b"\x89PNG\r\n\x1a\n\x00\xff binary\nbody"


@pytest.fixture
def uploaded_attachment_data() -> dict[str, Any]:
    return {
        "self": "https://api.tracker.yandex.net/v3/issues/TEST-123/attachments/4159",
        "id": "4159",
        "name": "скриншот.png",
        "content": "https://api.tracker.yandex.net/v3/issues/TEST-123/attachments/4159/скриншот.png",
        "thumbnail": "https://api.tracker.yandex.net/v3/issues/TEST-123/thumbnails/4159",
        "createdBy": {
            "self": "https://api.tracker.yandex.net/v3/users/1234567890",
            "id": "user123",
            "display": "Test User",
        },
        "createdAt": "2026-09-25T12:00:00.000+0000",
        "mimetype": "image/png",
        "size": len(FILE_CONTENT),
    }


class TestIssueGetAttachments:
    async def test_success(self, tracker_client: TrackerClient) -> None:
        attachment_data = {
            "self": "https://api.tracker.yandex.net/v3/issues/TEST-123/attachments/1",
            "id": "attachment-123",
            "name": "test_file.txt",
            "content": "https://api.tracker.yandex.net/v3/issues/TEST-123/attachments/1/content",
            "createdBy": {
                "self": "https://api.tracker.yandex.net/v3/users/1234567890",
                "id": "user123",
                "display": "Test User",
            },
            "createdAt": "2023-01-01T12:00:00.000+0000",
            "mimetype": "text/plain",
            "size": 1024,
        }
        attachments_response = [attachment_data]

        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/issues/TEST-123/attachments",
                payload=attachments_response,
            )

            result = await tracker_client.issue_get_attachments("TEST-123")

            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], IssueAttachment)
            assert result[0].name == "test_file.txt"

    async def test_not_found(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/issues/NOTFOUND-123/attachments",
                status=404,
            )

            with pytest.raises(IssueNotFound) as exc_info:
                await tracker_client.issue_get_attachments("NOTFOUND-123")

            assert exc_info.value.issue_id == "NOTFOUND-123"


class TestIssueAddAttachment:
    async def test_sends_the_file_as_multipart_with_the_filename(
        self,
        tracker_client: TrackerClient,
        uploaded_attachment_data: dict[str, Any],
    ) -> None:
        capture = RequestCapture(status=201, payload=uploaded_attachment_data)

        with aioresponses() as m:
            m.post(f"{UPLOAD_URL}?filename=скриншот.png", callback=capture.callback)

            result = await tracker_client.issue_add_attachment(
                "TEST-123", content=FILE_CONTENT, filename="скриншот.png"
            )

        capture.assert_called_once()
        request = capture.last_request
        assert request.url.path == "/v3/issues/TEST-123/attachments/"
        request.assert_param("filename", "скриншот.png")
        request.assert_headers(
            {"Authorization": "OAuth test-token", "X-Org-ID": "test-org"}
        )

        parts = await request.get_multipart_parts()
        assert len(parts) == 1
        assert parts[0].name == "file"
        assert parts[0].filename == "скриншот.png"
        assert parts[0].content_type == "image/png"
        assert parts[0].content == FILE_CONTENT

        assert isinstance(result, IssueAttachment)
        assert result.id == "4159"
        assert result.name == "скриншот.png"

    async def test_unknown_extension_is_sent_as_octet_stream(
        self,
        tracker_client: TrackerClient,
        uploaded_attachment_data: dict[str, Any],
    ) -> None:
        capture = RequestCapture(status=201, payload=uploaded_attachment_data)

        with aioresponses() as m:
            m.post(f"{UPLOAD_URL}?filename=dump.qwx", callback=capture.callback)

            await tracker_client.issue_add_attachment(
                "TEST-123", content=FILE_CONTENT, filename="dump.qwx"
            )

        parts = await capture.last_request.get_multipart_parts()
        assert parts[0].content_type == "application/octet-stream"

    async def test_uses_the_attachment_timeout_not_the_api_one(
        self, uploaded_attachment_data: dict[str, Any]
    ) -> None:
        client = TrackerClient(
            token="test-token", org_id="test-org", timeout=10, attachment_timeout=600
        )
        capture = RequestCapture(status=201, payload=uploaded_attachment_data)

        try:
            with aioresponses() as m:
                m.post(f"{UPLOAD_URL}?filename=a.png", callback=capture.callback)

                await client.issue_add_attachment(
                    "TEST-123", content=FILE_CONTENT, filename="a.png"
                )
        finally:
            await client.close()

        assert capture.last_request.timeout == ClientTimeout(total=600)

    async def test_a_timeout_points_at_the_upload_setting(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(f"{UPLOAD_URL}?filename=a.png", exception=TimeoutError())

            with pytest.raises(TrackerAPITimeout) as exc_info:
                await tracker_client.issue_add_attachment(
                    "TEST-123", content=FILE_CONTENT, filename="a.png"
                )

        assert exc_info.value.timeout == tracker_client._attachment_timeout
        assert exc_info.value.setting == "TRACKER_ATTACHMENT_TIMEOUT"
        assert "TRACKER_ATTACHMENT_TIMEOUT" in str(exc_info.value)

    async def test_not_found(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/NOTFOUND-123/attachments/?filename=a.png",
                status=404,
            )

            with pytest.raises(IssueNotFound) as exc_info:
                await tracker_client.issue_add_attachment(
                    "NOTFOUND-123", content=FILE_CONTENT, filename="a.png"
                )

        assert exc_info.value.issue_id == "NOTFOUND-123"


class TestAttachmentCreate:
    async def test_uploads_to_the_temporary_attachments_endpoint(
        self,
        tracker_client: TrackerClient,
        uploaded_attachment_data: dict[str, Any],
    ) -> None:
        capture = RequestCapture(status=201, payload=uploaded_attachment_data)

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/attachments/?filename=скриншот.png",
                callback=capture.callback,
            )

            result = await tracker_client.attachment_create(
                content=FILE_CONTENT, filename="скриншот.png"
            )

        capture.assert_called_once()
        request = capture.last_request
        assert request.url.path == "/v3/attachments/"
        request.assert_param("filename", "скриншот.png")
        parts = await request.get_multipart_parts()
        assert [(p.name, p.filename, p.content) for p in parts] == [
            ("file", "скриншот.png", FILE_CONTENT)
        ]
        assert result.id == "4159"

    async def test_uses_the_attachment_timeout(
        self, uploaded_attachment_data: dict[str, Any]
    ) -> None:
        client = TrackerClient(
            token="test-token", org_id="test-org", timeout=10, attachment_timeout=600
        )
        capture = RequestCapture(status=201, payload=uploaded_attachment_data)

        try:
            with aioresponses() as m:
                m.post(
                    "https://api.tracker.yandex.net/v3/attachments/?filename=a.png",
                    callback=capture.callback,
                )

                await client.attachment_create(content=FILE_CONTENT, filename="a.png")
        finally:
            await client.close()

        assert capture.last_request.timeout == ClientTimeout(total=600)


class TestIssueDownloadAttachment:
    async def test_streams_the_body_into_the_destination(
        self, tracker_client: TrackerClient, tmp_path: Path
    ) -> None:
        destination = tmp_path / "TEST-123" / "7946-image.png"

        with aioresponses() as m:
            m.get(f"{DOWNLOAD_URL}/image.png", body=FILE_CONTENT)

            written = await tracker_client.issue_download_attachment(
                "TEST-123", "7946", "image.png", destination
            )

        assert written == len(FILE_CONTENT)
        assert destination.read_bytes() == FILE_CONTENT
        assert list(destination.parent.iterdir()) == [destination]

    @pytest.mark.parametrize(
        ("file_name", "url_segment"),
        [
            pytest.param(
                "отчёт 1.txt",
                "%D0%BE%D1%82%D1%87%D1%91%D1%82%201.txt",
                id="cyrillic-and-space",
            ),
            pytest.param("a/b.png", "a%2Fb.png", id="slash"),
            pytest.param("../../v3/myself", "..%2F..%2Fv3%2Fmyself", id="traversal"),
        ],
    )
    async def test_the_name_is_one_quoted_path_segment(
        self,
        tracker_client: TrackerClient,
        tmp_path: Path,
        file_name: str,
        url_segment: str,
    ) -> None:
        capture = RequestCapture(status=200, body=FILE_CONTENT)

        with aioresponses() as m:
            m.get(f"{DOWNLOAD_URL}/{url_segment}", callback=capture.callback)

            await tracker_client.issue_download_attachment(
                "TEST-123", "7946", file_name, tmp_path / "file"
            )

        capture.assert_called_once()
        assert capture.last_request.url.raw_path == (
            f"/v3/issues/TEST-123/attachments/7946/{url_segment}"
        )

    async def test_a_declared_length_over_the_limit_is_refused_unread(
        self, tmp_path: Path
    ) -> None:
        client = TrackerClient(
            token="test-token", org_id="test-org", max_attachment_bytes=10
        )
        destination = tmp_path / "big.bin"

        try:
            with aioresponses() as m:
                m.get(
                    f"{DOWNLOAD_URL}/big.bin",
                    body=b"x" * 11,
                    headers={"Content-Length": "11"},
                )

                with pytest.raises(AttachmentTooLarge) as exc_info:
                    await client.issue_download_attachment(
                        "TEST-123", "7946", "big.bin", destination
                    )
        finally:
            await client.close()

        assert (exc_info.value.size, exc_info.value.limit) == (11, 10)
        assert not destination.exists()
        assert list(tmp_path.iterdir()) == []

    async def test_a_body_over_the_limit_leaves_no_file(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        client = TrackerClient(
            token="test-token", org_id="test-org", max_attachment_bytes=10
        )
        destination = tmp_path / "big.bin"

        try:
            with aioresponses() as m:
                m.get(f"{DOWNLOAD_URL}/big.bin", body=b"x" * 11)
                # A server that does not declare the length: the bytes are counted.
                mocker.patch(
                    "aiohttp.ClientResponse.content_length",
                    new_callable=mocker.PropertyMock,
                    return_value=None,
                )

                with pytest.raises(AttachmentTooLarge) as exc_info:
                    await client.issue_download_attachment(
                        "TEST-123", "7946", "big.bin", destination
                    )
        finally:
            await client.close()

        assert exc_info.value.limit == 10
        assert list(tmp_path.iterdir()) == []

    async def test_an_existing_file_is_replaced_only_when_complete(
        self, tracker_client: TrackerClient, tmp_path: Path
    ) -> None:
        destination = tmp_path / "image.png"
        destination.write_bytes(b"stale")

        with aioresponses() as m:
            m.get(f"{DOWNLOAD_URL}/image.png", body=FILE_CONTENT)

            await tracker_client.issue_download_attachment(
                "TEST-123", "7946", "image.png", destination
            )

        assert destination.read_bytes() == FILE_CONTENT

    async def test_not_found_names_the_attachment(
        self, tracker_client: TrackerClient, tmp_path: Path
    ) -> None:
        with aioresponses() as m:
            m.get(f"{DOWNLOAD_URL}/image.png", status=404)

            with pytest.raises(AttachmentNotFound) as exc_info:
                await tracker_client.issue_download_attachment(
                    "TEST-123", "7946", "image.png", tmp_path / "image.png"
                )

        assert (exc_info.value.issue_id, exc_info.value.attachment_id) == (
            "TEST-123",
            "7946",
        )
        assert "issue_get_attachments" in str(exc_info.value)
        assert list(tmp_path.iterdir()) == []

    async def test_uses_the_attachment_timeout(self, tmp_path: Path) -> None:
        client = TrackerClient(
            token="test-token", org_id="test-org", timeout=10, attachment_timeout=600
        )
        capture = RequestCapture(status=200, body=FILE_CONTENT)

        try:
            with aioresponses() as m:
                m.get(f"{DOWNLOAD_URL}/a.png", callback=capture.callback)

                await client.issue_download_attachment(
                    "TEST-123", "7946", "a.png", tmp_path / "a.png"
                )
        finally:
            await client.close()

        assert capture.last_request.timeout == ClientTimeout(total=600)

    async def test_a_timeout_points_at_the_attachment_setting(
        self, tracker_client: TrackerClient, tmp_path: Path
    ) -> None:
        with aioresponses() as m:
            m.get(f"{DOWNLOAD_URL}/a.png", exception=TimeoutError())

            with pytest.raises(TrackerAPITimeout) as exc_info:
                await tracker_client.issue_download_attachment(
                    "TEST-123", "7946", "a.png", tmp_path / "a.png"
                )

        assert exc_info.value.setting == "TRACKER_ATTACHMENT_TIMEOUT"
        assert list(tmp_path.iterdir()) == []
