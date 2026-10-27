from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.client import ClientRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.types import ElicitRequestParams, ElicitResult, TextContent

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from mcp_tracker.tracker.proto.types.permissions import (
    GranteeChange,
    Group,
    PermissionChange,
    PermissionGrantees,
    PermissionRef,
    QueuePermissions,
    SubjectPermissions,
)
from mcp_tracker.tracker.proto.types.refs import QueueReference
from tests.mcp.conftest import get_tool_result_content, safe_client_session

PERMISSIONS = QueuePermissions.model_construct(
    version=2,
    read=PermissionGrantees.model_construct(
        groups=[PermissionRef.model_construct(id="3", display="Администратор")],
        roles=[PermissionRef.model_construct(id="access", display="Доступ")],
    ),
)
SUBJECT = SubjectPermissions.model_construct(
    group=PermissionRef.model_construct(id="1", display="Все сотрудники"),
    permissions={
        "WRITE": PermissionGrantees.model_construct(
            groups=[PermissionRef.model_construct(id="1")]
        )
    },
)
COMPONENT = Component.model_construct(
    id=1,
    version=1,
    name="MCP comp",
    queue=QueueReference.model_construct(key="ALLOWED"),
)
OTHER_COMPONENT = Component.model_construct(
    id=2, version=1, name="Hidden", queue=QueueReference.model_construct(key="OTHER")
)


def error_text(content: list[Any]) -> str:
    assert isinstance(content[0], TextContent)
    return content[0].text


@asynccontextmanager
async def answering_session(
    mcp_server: MCPServer[AppContext], answer: ElicitResult
) -> AsyncIterator[Client]:
    """A client that answers every confirmation with ``answer``."""

    async def callback(
        context: ClientRequestContext, params: ElicitRequestParams
    ) -> ElicitResult:
        return answer

    async with safe_client_session(mcp_server, elicitation_callback=callback) as c:
        yield c


class TestQueuePermissionReads:
    async def test_queue_get_permissions(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_get_permissions.return_value = PERMISSIONS

        result = await client_session.call_tool(
            "queue_get_permissions", {"queue_id": "TEST"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["version"] == 2
        assert content["read"]["groups"][0]["id"] == "3"

    @pytest.mark.parametrize(
        ("tool", "args", "method", "expected"),
        [
            pytest.param(
                "queue_get_user_permissions",
                {"queue_id": "TEST", "user": "i.ivanov"},
                "queue_get_user_permissions",
                ("TEST", "i.ivanov"),
                id="user",
            ),
            pytest.param(
                "queue_get_group_permissions",
                {"queue_id": "TEST", "group_id": 1},
                "queue_get_group_permissions",
                ("TEST", 1),
                id="group",
            ),
        ],
    )
    async def test_subject_permissions(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        tool: str,
        args: dict[str, Any],
        method: str,
        expected: tuple[Any, ...],
    ) -> None:
        getattr(mock_queues_protocol, method).return_value = SUBJECT

        result = await client_session.call_tool(tool, args)

        assert not result.is_error
        assert "WRITE" in get_tool_result_content(result)["permissions"]
        assert getattr(mock_queues_protocol, method).call_args.args == expected

    @pytest.mark.parametrize(
        ("tool", "args"),
        [
            ("queue_get_permissions", {"queue_id": "OTHER"}),
            ("queue_get_user_permissions", {"queue_id": "OTHER", "user": "x"}),
            ("queue_get_group_permissions", {"queue_id": "OTHER", "group_id": 1}),
        ],
    )
    async def test_queue_outside_the_allow_list_is_refused(
        self,
        client_session_with_limits: Client,
        mock_queues_protocol: AsyncMock,
        tool: str,
        args: dict[str, Any],
    ) -> None:
        result = await client_session_with_limits.call_tool(tool, args)

        assert result.is_error
        mock_queues_protocol.queue_get_permissions.assert_not_called()
        mock_queues_protocol.queue_get_user_permissions.assert_not_called()
        mock_queues_protocol.queue_get_group_permissions.assert_not_called()


class TestComponentPermissionReads:
    @pytest.mark.parametrize(
        ("tool", "args", "method", "expected"),
        [
            pytest.param(
                "component_get_user_permissions",
                {"component_id": 1, "user": "i.ivanov"},
                "component_get_user_permissions",
                (1, "i.ivanov"),
                id="user",
            ),
            pytest.param(
                "component_get_group_permissions",
                {"component_id": 1, "group_id": 3},
                "component_get_group_permissions",
                (1, 3),
                id="group",
            ),
        ],
    )
    async def test_read_without_restrictions_skips_the_component_read(
        self,
        client_session: Client,
        mock_components_protocol: AsyncMock,
        tool: str,
        args: dict[str, Any],
        method: str,
        expected: tuple[Any, ...],
    ) -> None:
        getattr(mock_components_protocol, method).return_value = SUBJECT

        result = await client_session.call_tool(tool, args)

        assert not result.is_error
        mock_components_protocol.component_get.assert_not_called()
        assert getattr(mock_components_protocol, method).call_args.args == expected

    async def test_allowed_queue_under_restrictions(
        self,
        client_session_with_limits: Client,
        mock_components_protocol: AsyncMock,
    ) -> None:
        mock_components_protocol.component_get.return_value = COMPONENT
        mock_components_protocol.component_get_user_permissions.return_value = SUBJECT

        result = await client_session_with_limits.call_tool(
            "component_get_user_permissions", {"component_id": 1, "user": "x"}
        )

        assert not result.is_error
        mock_components_protocol.component_get.assert_called_once()

    async def test_hidden_queue_reads_as_not_found(
        self,
        client_session_with_limits: Client,
        mock_components_protocol: AsyncMock,
    ) -> None:
        mock_components_protocol.component_get.return_value = OTHER_COMPONENT

        result = await client_session_with_limits.call_tool(
            "component_get_group_permissions", {"component_id": 2, "group_id": 1}
        )

        assert result.is_error
        assert "OTHER" not in error_text(result.content)
        mock_components_protocol.component_get_group_permissions.assert_not_called()


class TestGroupsGetAll:
    async def test_lists_groups(
        self, client_session: Client, mock_users_protocol: AsyncMock
    ) -> None:
        mock_users_protocol.groups_list.return_value = PaginatedResult(
            values=[Group.model_construct(id=1, name="Все сотрудники")],
            hits=7,
            pages=1,
        )

        result = await client_session.call_tool("groups_get_all", {"per_page": 10})

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["values"][0]["id"] == 1
        assert mock_users_protocol.groups_list.call_args.kwargs["per_page"] == 10
        assert mock_users_protocol.groups_list.call_args.kwargs["page"] == 1


class TestQueueUpdatePermissions:
    ARGS: dict[str, Any] = {
        "queue_id": "TEST",
        "read": {"groups": {"add": [3]}},
        "deny": {"users": {"set": []}},
    }

    async def test_client_that_cannot_be_asked_goes_ahead(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_update_permissions.return_value = PERMISSIONS

        result = await client_session.call_tool("queue_update_permissions", self.ARGS)

        assert not result.is_error
        call = mock_queues_protocol.queue_update_permissions.call_args
        assert call.args == (
            "TEST",
            {
                "read": PermissionChange(groups=GranteeChange(add=[3])),
                "deny": PermissionChange(users=GranteeChange(set=[])),
            },
        )

    async def test_confirmed_change_is_applied(
        self, mcp_server: MCPServer[AppContext], mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_update_permissions.return_value = PERMISSIONS

        async with answering_session(
            mcp_server, ElicitResult(action="accept", content={"confirm": True})
        ) as client:
            result = await client.call_tool("queue_update_permissions", self.ARGS)

        assert not result.is_error
        mock_queues_protocol.queue_update_permissions.assert_called_once()

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
        mock_queues_protocol: AsyncMock,
        answer: ElicitResult,
    ) -> None:
        async with answering_session(mcp_server, answer) as client:
            result = await client.call_tool("queue_update_permissions", self.ARGS)

        assert result.is_error
        assert "cancelled by the user" in error_text(result.content)
        mock_queues_protocol.queue_update_permissions.assert_not_called()

    async def test_empty_change_is_refused(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "queue_update_permissions", {"queue_id": "TEST"}
        )

        assert result.is_error
        assert "must change something" in error_text(result.content)
        mock_queues_protocol.queue_update_permissions.assert_not_called()

    @pytest.mark.parametrize(
        "change",
        [
            pytest.param({"groups": {"set": [1], "add": [2]}}, id="set-and-add"),
            pytest.param({"groups": {}}, id="nothing-in-grantees"),
            pytest.param({}, id="no-grantees"),
        ],
    )
    async def test_malformed_change_is_rejected(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        change: dict[str, Any],
    ) -> None:
        result = await client_session.call_tool(
            "queue_update_permissions", {"queue_id": "TEST", "write": change}
        )

        assert result.is_error
        mock_queues_protocol.queue_update_permissions.assert_not_called()

    async def test_read_only_queue_is_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            "queue_update_permissions",
            {"queue_id": "READONLY", "read": {"groups": {"add": [3]}}},
        )

        assert result.is_error
        mock_queues_protocol.queue_update_permissions.assert_not_called()

    async def test_read_only_mode_tool_not_registered(
        self, client_session_read_only: Client
    ) -> None:
        tools = await client_session_read_only.list_tools()

        assert "queue_update_permissions" not in {t.name for t in tools.tools}


class TestComponentUpdatePermissions:
    ARGS: dict[str, Any] = {"component_id": 1, "read": {"users": {"add": ["a"]}}}

    async def test_reads_the_permissions_version_and_applies(
        self, client_session: Client, mock_components_protocol: AsyncMock
    ) -> None:
        mock_components_protocol.component_get_permissions.return_value = (
            QueuePermissions.model_construct(version=7)
        )
        mock_components_protocol.component_update_permissions.return_value = PERMISSIONS

        result = await client_session.call_tool(
            "component_update_permissions", self.ARGS
        )

        assert not result.is_error
        call = mock_components_protocol.component_update_permissions.call_args
        assert call.args == (
            1,
            {"read": PermissionChange(users=GranteeChange(add=["a"]))},
        )
        assert call.kwargs["version"] == 7
        # No queue restriction: the component itself is not read.
        mock_components_protocol.component_get.assert_not_called()

    async def test_a_given_version_skips_the_read(
        self, client_session: Client, mock_components_protocol: AsyncMock
    ) -> None:
        mock_components_protocol.component_update_permissions.return_value = PERMISSIONS

        await client_session.call_tool(
            "component_update_permissions", {**self.ARGS, "version": 3}
        )

        mock_components_protocol.component_get_permissions.assert_not_called()
        call = mock_components_protocol.component_update_permissions.call_args
        assert call.kwargs["version"] == 3

    @pytest.mark.parametrize(
        "answer",
        [
            pytest.param(ElicitResult(action="decline"), id="decline"),
            pytest.param(
                ElicitResult(action="accept", content={"confirm": False}), id="no"
            ),
        ],
    )
    async def test_unconfirmed_change_is_not_applied(
        self,
        mcp_server: MCPServer[AppContext],
        mock_components_protocol: AsyncMock,
        answer: ElicitResult,
    ) -> None:
        async with answering_session(mcp_server, answer) as client:
            result = await client.call_tool("component_update_permissions", self.ARGS)

        assert result.is_error
        assert "cancelled by the user" in error_text(result.content)
        mock_components_protocol.component_update_permissions.assert_not_called()

    async def test_empty_change_is_refused(
        self, client_session: Client, mock_components_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "component_update_permissions", {"component_id": 1}
        )

        assert result.is_error
        assert "`grant`." in error_text(result.content)
        mock_components_protocol.component_update_permissions.assert_not_called()

    async def test_component_of_a_hidden_queue_is_not_found(
        self,
        client_session_with_limits: Client,
        mock_components_protocol: AsyncMock,
    ) -> None:
        mock_components_protocol.component_get.return_value = OTHER_COMPONENT

        result = await client_session_with_limits.call_tool(
            "component_update_permissions", {**self.ARGS, "component_id": 2}
        )

        assert result.is_error
        assert "OTHER" not in error_text(result.content)
        mock_components_protocol.component_update_permissions.assert_not_called()

    async def test_read_only_mode_tool_not_registered(
        self, client_session_read_only: Client
    ) -> None:
        tools = await client_session_read_only.list_tools()

        assert "component_update_permissions" not in {t.name for t in tools.tools}
