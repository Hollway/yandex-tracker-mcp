from unittest.mock import AsyncMock

from mcp import Client
from mcp.types import TextContent

from mcp_tracker.tracker.proto.types.queues import QueueVersion
from mcp_tracker.tracker.proto.types.refs import QueueReference
from tests.mcp.conftest import get_tool_result_content


class TestQueueCreateVersion:
    async def test_creates_version(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample_queue_versions: list[QueueVersion],
    ) -> None:
        created_version = sample_queue_versions[0]
        mock_queues_protocol.queue_create_version.return_value = created_version

        result = await client_session.call_tool(
            "queue_create_version",
            {
                "queue_id": "TEST",
                "name": "1.0.0",
                "description": "Initial release",
                "start_date": "2023-01-01",
                "due_date": "2023-12-31",
            },
        )

        assert not result.is_error
        mock_queues_protocol.queue_create_version.assert_called_once()
        call_args = mock_queues_protocol.queue_create_version.call_args
        assert call_args.args[0] == "TEST"
        assert call_args.kwargs["name"] == "1.0.0"
        assert call_args.kwargs["description"] == "Initial release"
        assert call_args.kwargs["start_date"].isoformat() == "2023-01-01"
        assert call_args.kwargs["due_date"].isoformat() == "2023-12-31"

        content = get_tool_result_content(result)
        assert content["name"] == created_version.name

    async def test_restricted_queue_raises_error(
        self,
        client_session_with_limits: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "queue_create_version",
            {"queue_id": "RESTRICTED", "name": "1.0.0"},
        )

        assert result.is_error
        mock_queues_protocol.queue_create_version.assert_not_called()


class TestPerQueueReadOnlyAccess:
    """Per-queue read-only enforcement (TRACKER_READ_ONLY_QUEUES)."""

    async def test_create_version_in_read_only_queue_rejected(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            "queue_create_version",
            {"queue_id": "READONLY", "name": "1.0.0"},
        )

        assert result.is_error
        mock_queues_protocol.queue_create_version.assert_not_called()

    async def test_create_version_in_writable_queue_allowed(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
        sample_queue_versions: list[QueueVersion],
    ) -> None:
        mock_queues_protocol.queue_create_version.return_value = sample_queue_versions[
            0
        ]

        result = await client_session_with_read_only_queues.call_tool(
            "queue_create_version",
            {"queue_id": "TEST", "name": "1.0.0"},
        )

        assert not result.is_error
        mock_queues_protocol.queue_create_version.assert_called_once()


def version_in(queue_key: str) -> QueueVersion:
    return QueueVersion.model_construct(
        id=123,
        version=1,
        name="1.0",
        released=False,
        archived=False,
        queue=QueueReference.model_construct(key=queue_key),
    )


class TestQueueUpdateVersion:
    async def test_updates_without_an_extra_read_when_unrestricted(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queue_update_version.return_value = version_in("TEST")

        result = await client_session.call_tool(
            "queue_update_version", {"version_id": 123, "name": "1.1"}
        )

        assert not result.is_error
        mock_queues_protocol.queue_get_version.assert_not_called()
        call = mock_queues_protocol.queue_update_version.call_args
        assert call.args == (123,)
        assert call.kwargs["name"] == "1.1"

    async def test_a_version_in_a_hidden_queue_is_reported_missing(
        self,
        client_session_with_limits: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queue_get_version.return_value = version_in("SECRET")

        result = await client_session_with_limits.call_tool(
            "queue_update_version", {"version_id": 123, "name": "1.1"}
        )

        assert result.is_error
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "not found" in content.text
        assert "SECRET" not in content.text
        mock_queues_protocol.queue_update_version.assert_not_called()

    async def test_a_read_only_queue_is_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queue_get_version.return_value = version_in("READONLY")

        result = await client_session_with_read_only_queues.call_tool(
            "queue_update_version", {"version_id": 123, "name": "1.1"}
        )

        assert result.is_error
        mock_queues_protocol.queue_update_version.assert_not_called()


class TestQueueDeleteVersion:
    async def test_deletes(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "queue_delete_version", {"version_id": 123}
        )

        assert not result.is_error
        assert mock_queues_protocol.queue_delete_version.call_args.args == (123,)

    async def test_an_allowed_queue_is_checked_then_deleted(
        self,
        client_session_with_limits: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queue_get_version.return_value = version_in("ALLOWED")

        result = await client_session_with_limits.call_tool(
            "queue_delete_version", {"version_id": 123}
        )

        assert not result.is_error
        mock_queues_protocol.queue_delete_version.assert_called_once()
