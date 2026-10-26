"""Tools that projects, portfolios and goals share (`tools/_entity.py`)."""

from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.entities import EntityLink
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
