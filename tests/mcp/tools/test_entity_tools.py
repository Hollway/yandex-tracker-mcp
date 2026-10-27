"""Tools that projects, portfolios and goals share (`tools/_entity.py`)."""

from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.entities import (
    EntityAttachment,
    EntityLink,
    EntityMetricItem,
)
from tests.mcp.conftest import get_tool_result_content

ENTITY_TYPES = ["project", "portfolio", "goal"]


class TestGetLinks:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_returns_links(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_get_links.return_value = [
            EntityLink(type="depends on", linkFieldValues={"id": "b1", "summary": "B"})
        ]

        result = await client_session.call_tool(
            f"{entity_type}_get_links", {"entity_id": "e1"}
        )

        assert not result.is_error
        mock_entities_protocol.entity_get_links.assert_called_once_with(
            entity_type, "e1", fields=None, auth=YandexAuth()
        )
        content = get_tool_result_content(result)
        assert content == [
            {"type": "depends on", "linkFieldValues": {"id": "b1", "summary": "B"}}
        ]

    async def test_passes_fields(
        self, client_session: Client, mock_entities_protocol: AsyncMock
    ) -> None:
        mock_entities_protocol.entity_get_links.return_value = []

        await client_session.call_tool(
            "goal_get_links", {"entity_id": "g1", "fields": ["summary", "lead"]}
        )

        mock_entities_protocol.entity_get_links.assert_called_once_with(
            "goal", "g1", fields=["summary", "lead"], auth=YandexAuth()
        )


class TestDeleteLink:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_deletes_link(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_delete_link.return_value = None

        result = await client_session.call_tool(
            f"{entity_type}_delete_link",
            {"entity_id": "e1", "linked_entity_id": "e2"},
        )

        assert not result.is_error
        mock_entities_protocol.entity_delete_link.assert_called_once_with(
            entity_type, "e1", "e2", auth=YandexAuth()
        )

    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_not_registered_read_only(
        self, client_session_read_only: Client, entity_type: str
    ) -> None:
        result = await client_session_read_only.call_tool(
            f"{entity_type}_delete_link",
            {"entity_id": "e1", "linked_entity_id": "e2"},
        )

        assert result.is_error


class TestGetAttachments:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_returns_attachments(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_get_attachments.return_value = [
            EntityAttachment(id="8021", name="a.txt", comment_id="c1")
        ]

        result = await client_session.call_tool(
            f"{entity_type}_get_attachments", {"entity_id": "e1"}
        )

        assert not result.is_error
        mock_entities_protocol.entity_get_attachments.assert_called_once_with(
            entity_type, "e1", auth=YandexAuth()
        )
        content = get_tool_result_content(result)
        assert content == [{"id": "8021", "name": "a.txt", "commentId": "c1"}]


class TestDeleteAttachment:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_deletes_attachment(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_delete_attachment.return_value = None

        result = await client_session.call_tool(
            f"{entity_type}_delete_attachment",
            {"entity_id": "e1", "attachment_id": "8021"},
        )

        assert not result.is_error
        mock_entities_protocol.entity_delete_attachment.assert_called_once_with(
            entity_type, "e1", "8021", auth=YandexAuth()
        )

    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_not_registered_read_only(
        self, client_session_read_only: Client, entity_type: str
    ) -> None:
        result = await client_session_read_only.call_tool(
            f"{entity_type}_delete_attachment",
            {"entity_id": "e1", "attachment_id": "8021"},
        )

        assert result.is_error


class TestMetrics:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_add_metric(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_add_metric.return_value = [
            EntityMetricItem(id="m1", text="Burndown", url="https://example.com/w")
        ]

        result = await client_session.call_tool(
            f"{entity_type}_add_metric",
            {"entity_id": "e1", "text": "Burndown", "url": "https://example.com/w"},
        )

        assert not result.is_error
        mock_entities_protocol.entity_add_metric.assert_called_once_with(
            entity_type,
            "e1",
            text="Burndown",
            url="https://example.com/w",
            auth=YandexAuth(),
        )
        assert get_tool_result_content(result) == [
            {"id": "m1", "text": "Burndown", "url": "https://example.com/w"}
        ]

    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_update_metric(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_update_metric.return_value = []

        result = await client_session.call_tool(
            f"{entity_type}_update_metric",
            {"entity_id": "e1", "metric_id": "m1", "text": "New"},
        )

        assert not result.is_error
        mock_entities_protocol.entity_update_metric.assert_called_once_with(
            entity_type, "e1", "m1", text="New", url=None, auth=YandexAuth()
        )

    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_delete_metric(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_delete_metric.return_value = []

        result = await client_session.call_tool(
            f"{entity_type}_delete_metric", {"entity_id": "e1", "metric_id": "m1"}
        )

        assert not result.is_error
        mock_entities_protocol.entity_delete_metric.assert_called_once_with(
            entity_type, "e1", "m1", auth=YandexAuth()
        )

    @pytest.mark.parametrize(
        "tool,args",
        [
            ("project_add_metric", {"text": "x"}),
            ("portfolio_update_metric", {"metric_id": "m1", "text": "x"}),
            ("goal_delete_metric", {"metric_id": "m1"}),
        ],
    )
    async def test_not_registered_read_only(
        self, client_session_read_only: Client, tool: str, args: dict[str, str]
    ) -> None:
        result = await client_session_read_only.call_tool(
            tool, {"entity_id": "e1", **args}
        )

        assert result.is_error
