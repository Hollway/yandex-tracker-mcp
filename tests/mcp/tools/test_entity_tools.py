"""Tools that projects, portfolios and goals share (`tools/_entity.py`)."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import ElicitResult

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.entities import (
    EntityAttachment,
    EntityLink,
    EntityMetricItem,
)
from mcp_tracker.tracker.proto.types.permissions import (
    EntityAcl,
    EntityGranteeChange,
    EntityGrantees,
    EntityPermissionChange,
    EntityPermissions,
    EntityRoleChange,
)
from tests.mcp.conftest import get_tool_result_content
from tests.mcp.tools.test_permission_tools import answering_session, error_text

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


PERMISSIONS = EntityPermissions(
    acl=EntityAcl(write=EntityGrantees(roles=["AUTHOR", "OWNER"])),
    accessType="custom",
)


class TestGetPermissions:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_returns_permissions(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_get_permissions.return_value = PERMISSIONS

        result = await client_session.call_tool(
            f"{entity_type}_get_permissions", {"entity_id": "e1"}
        )

        assert not result.is_error
        mock_entities_protocol.entity_get_permissions.assert_called_once_with(
            entity_type, "e1", auth=YandexAuth()
        )
        content = get_tool_result_content(result)
        assert content["acl"] == {"WRITE": {"roles": ["AUTHOR", "OWNER"]}}
        assert content["accessType"] == "custom"


class TestUpdatePermissions:
    ARGS: dict[str, Any] = {
        "entity_id": "e1",
        "read": {"groups": {"add": [1]}},
        "write": {"roles": {"remove": ["FOLLOWER"]}},
        "inherit": False,
    }

    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_client_that_cannot_be_asked_goes_ahead(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        entity_type: str,
    ) -> None:
        mock_entities_protocol.entity_update_permissions.return_value = PERMISSIONS

        result = await client_session.call_tool(
            f"{entity_type}_update_permissions", self.ARGS
        )

        assert not result.is_error
        mock_entities_protocol.entity_update_permissions.assert_called_once_with(
            entity_type,
            "e1",
            {
                "READ": EntityPermissionChange(groups=EntityGranteeChange(add=[1])),
                "WRITE": EntityPermissionChange(
                    roles=EntityRoleChange(remove=["FOLLOWER"])
                ),
            },
            inherit=False,
            auth=YandexAuth(),
        )

    async def test_confirmed_change_is_applied(
        self, mcp_server: MCPServer[AppContext], mock_entities_protocol: AsyncMock
    ) -> None:
        mock_entities_protocol.entity_update_permissions.return_value = PERMISSIONS

        async with answering_session(
            mcp_server, ElicitResult(action="accept", content={"confirm": True})
        ) as client:
            result = await client.call_tool("project_update_permissions", self.ARGS)

        assert not result.is_error
        mock_entities_protocol.entity_update_permissions.assert_called_once()

    @pytest.mark.parametrize(
        "answer",
        [
            pytest.param(
                ElicitResult(action="accept", content={"confirm": False}), id="no"
            ),
            pytest.param(ElicitResult(action="decline"), id="decline"),
            pytest.param(ElicitResult(action="cancel"), id="cancel"),
        ],
    )
    async def test_unconfirmed_change_is_not_applied(
        self,
        mcp_server: MCPServer[AppContext],
        mock_entities_protocol: AsyncMock,
        answer: ElicitResult,
    ) -> None:
        async with answering_session(mcp_server, answer) as client:
            result = await client.call_tool("goal_update_permissions", self.ARGS)

        assert result.is_error
        assert "cancelled by the user" in error_text(result.content)
        mock_entities_protocol.entity_update_permissions.assert_not_called()

    @pytest.mark.parametrize(
        "args,message",
        [
            pytest.param({}, "must change something", id="empty"),
            pytest.param(
                {"inherit": True, "grant": {"users": {"add": ["i.ivanov"]}}},
                "pass one or the other",
                id="inherit-and-change",
            ),
        ],
    )
    async def test_refused_before_asking(
        self,
        mcp_server: MCPServer[AppContext],
        mock_entities_protocol: AsyncMock,
        args: dict[str, Any],
        message: str,
    ) -> None:
        async with answering_session(
            mcp_server, ElicitResult(action="accept", content={"confirm": True})
        ) as client:
            result = await client.call_tool(
                "portfolio_update_permissions", {"entity_id": "e1", **args}
            )

        assert result.is_error
        assert message in error_text(result.content)
        mock_entities_protocol.entity_update_permissions.assert_not_called()

    @pytest.mark.parametrize(
        "change",
        [
            pytest.param({"roles": {"add": ["BOSS"]}}, id="unknown-role"),
            pytest.param({"groups": {}}, id="nothing-in-grantees"),
            pytest.param({}, id="no-grantees"),
        ],
    )
    async def test_malformed_change_is_rejected(
        self,
        client_session: Client,
        mock_entities_protocol: AsyncMock,
        change: dict[str, Any],
    ) -> None:
        result = await client_session.call_tool(
            "project_update_permissions", {"entity_id": "e1", "write": change}
        )

        assert result.is_error
        mock_entities_protocol.entity_update_permissions.assert_not_called()

    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_not_registered_read_only(
        self, client_session_read_only: Client, entity_type: str
    ) -> None:
        result = await client_session_read_only.call_tool(
            f"{entity_type}_update_permissions", self.ARGS
        )

        assert result.is_error
