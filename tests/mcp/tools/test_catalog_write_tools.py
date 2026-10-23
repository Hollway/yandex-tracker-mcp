from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent
from pydantic import BaseModel

from mcp_tracker.tracker.custom.errors import CatalogObjectNotFound
from mcp_tracker.tracker.proto.types.issue_types import IssueType
from mcp_tracker.tracker.proto.types.priorities import Priority
from mcp_tracker.tracker.proto.types.resolutions import Resolution
from mcp_tracker.tracker.proto.types.statuses import Status
from mcp_tracker.tracker.proto.types.workflows import LocalizedText
from tests.mcp.conftest import get_tool_result_content

STATUS = Status.model_construct(
    id=29,
    version=3,
    key="pause",
    name="Приостановлен",
    order=350,
    type="paused",
)
RESOLUTION = Resolution.model_construct(
    id=9, version=3, key="wontFix", name="Не будет исправлено", order=90
)
ISSUE_TYPE = IssueType.model_construct(id=23, version=3, key="client", name="Клиент")
PRIORITY = Priority.model_construct(id=6, version=3, key="one", name="Низкий", order=60)

# (entity prefix, id argument, sample object)
ENTITIES = [
    pytest.param("status", "status_id", STATUS, id="status"),
    pytest.param("resolution", "resolution_id", RESOLUTION, id="resolution"),
    pytest.param("issue_type", "issue_type_id", ISSUE_TYPE, id="issue_type"),
    pytest.param("priority", "priority_id", PRIORITY, id="priority"),
]


def create_args(prefix: str) -> dict[str, Any]:
    """The arguments every create tool needs - a status also needs a type."""
    args: dict[str, Any] = {"key": "myKey", "name": "Моё"}
    if prefix == "status":
        args["type"] = "paused"
    return args


def error_text(content: list[Any]) -> str:
    assert isinstance(content[0], TextContent)
    return content[0].text


class TestCatalogCreate:
    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_name_en_defaults_to_name(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        create = getattr(mock_fields_protocol, f"{prefix}_create")
        create.return_value = sample

        result = await client_session.call_tool(f"{prefix}_create", create_args(prefix))

        assert not result.is_error
        assert get_tool_result_content(result)["key"] == sample.model_dump()["key"]
        kwargs = create.call_args.kwargs
        assert kwargs["key"] == "myKey"
        assert kwargs["name"] == LocalizedText(ru="Моё", en="Моё")
        assert kwargs["description"] is None

    async def test_status_create_passes_every_argument(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.status_create.return_value = STATUS

        result = await client_session.call_tool(
            "status_create",
            {
                "key": "pause",
                "name": "Приостановлен",
                "name_en": "On pause",
                "type": "paused",
                "description": "Paused",
                "order": 350,
            },
        )

        assert not result.is_error
        mock_fields_protocol.status_create.assert_called_once()
        kwargs = mock_fields_protocol.status_create.call_args.kwargs
        assert kwargs["name"] == LocalizedText(ru="Приостановлен", en="On pause")
        assert kwargs["type"] == "paused"
        assert kwargs["description"] == "Paused"
        assert kwargs["order"] == 350

    async def test_status_create_rejects_an_unknown_type(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "status_create", {"key": "x", "name": "X", "type": "closed"}
        )

        assert result.is_error
        mock_fields_protocol.status_create.assert_not_called()

    @pytest.mark.parametrize("prefix", ["resolution", "priority"])
    async def test_order_is_passed(
        self, client_session: Client, mock_fields_protocol: AsyncMock, prefix: str
    ) -> None:
        create = getattr(mock_fields_protocol, f"{prefix}_create")
        create.return_value = RESOLUTION if prefix == "resolution" else PRIORITY

        result = await client_session.call_tool(
            f"{prefix}_create", {**create_args(prefix), "order": 70}
        )

        assert not result.is_error
        assert create.call_args.kwargs["order"] == 70

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_allowed_on_a_server_limited_to_some_queues(
        self,
        client_session_with_limits: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        getattr(mock_fields_protocol, f"{prefix}_create").return_value = sample

        result = await client_session_with_limits.call_tool(
            f"{prefix}_create", create_args(prefix)
        )

        assert not result.is_error

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        result = await client_session_read_only.call_tool(
            f"{prefix}_create", create_args(prefix)
        )

        assert result.is_error
        getattr(mock_fields_protocol, f"{prefix}_create").assert_not_called()


class TestCatalogUpdate:
    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_given_version_is_used_without_a_read(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        update = getattr(mock_fields_protocol, f"{prefix}_update")
        update.return_value = sample

        result = await client_session.call_tool(
            f"{prefix}_update",
            {id_arg: "myKey", "name": "Новое", "name_en": "New", "version": 7},
        )

        assert not result.is_error
        getattr(mock_fields_protocol, f"{prefix}_get").assert_not_called()
        update.assert_called_once()
        assert update.call_args.args == ("myKey",)
        kwargs = update.call_args.kwargs
        assert kwargs["version"] == 7
        assert kwargs["name"] == LocalizedText(ru="Новое", en="New")
        assert kwargs["description"] is None

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_omitted_version_is_read_first(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        get = getattr(mock_fields_protocol, f"{prefix}_get")
        get.return_value = sample
        update = getattr(mock_fields_protocol, f"{prefix}_update")
        update.return_value = sample

        result = await client_session.call_tool(
            f"{prefix}_update", {id_arg: "myKey", "description": "Новое описание"}
        )

        assert not result.is_error
        get.assert_called_once()
        assert get.call_args.args == ("myKey",)
        kwargs = update.call_args.kwargs
        assert kwargs["version"] == 3
        assert kwargs["name"] is None
        assert kwargs["description"] == "Новое описание"

    async def test_status_update_passes_order_and_type(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.status_update.return_value = STATUS

        result = await client_session.call_tool(
            "status_update",
            {"status_id": "pause", "order": 400, "type": "inProgress", "version": 3},
        )

        assert not result.is_error
        kwargs = mock_fields_protocol.status_update.call_args.kwargs
        assert kwargs["order"] == 400
        assert kwargs["type"] == "inProgress"

    async def test_name_en_defaults_to_name(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.priority_update.return_value = PRIORITY

        result = await client_session.call_tool(
            "priority_update", {"priority_id": "one", "name": "Низкий", "version": 3}
        )

        assert not result.is_error
        kwargs = mock_fields_protocol.priority_update.call_args.kwargs
        assert kwargs["name"] == LocalizedText(ru="Низкий", en="Низкий")

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_empty_update_is_refused(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        result = await client_session.call_tool(f"{prefix}_update", {id_arg: "myKey"})

        assert result.is_error
        assert "must change something" in error_text(result.content)
        getattr(mock_fields_protocol, f"{prefix}_get").assert_not_called()
        getattr(mock_fields_protocol, f"{prefix}_update").assert_not_called()

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_name_en_alone_is_refused(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        result = await client_session.call_tool(
            f"{prefix}_update", {id_arg: "myKey", "name_en": "New"}
        )

        assert result.is_error
        assert "`name_en`" in error_text(result.content)
        getattr(mock_fields_protocol, f"{prefix}_update").assert_not_called()

    async def test_not_found_reaches_the_caller(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.status_get.side_effect = CatalogObjectNotFound(
            "status", "nope", "get_statuses"
        )

        result = await client_session.call_tool(
            "status_update", {"status_id": "nope", "description": "x"}
        )

        assert result.is_error
        assert "get_statuses" in error_text(result.content)
        mock_fields_protocol.status_update.assert_not_called()

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_refused_on_a_server_limited_to_some_queues(
        self,
        client_session_with_limits: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            f"{prefix}_update", {id_arg: "myKey", "description": "x", "version": 3}
        )

        assert result.is_error
        assert "shared by every queue" in error_text(result.content)
        getattr(mock_fields_protocol, f"{prefix}_update").assert_not_called()

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_refused_with_read_only_queues(
        self,
        client_session_with_read_only_queues: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            f"{prefix}_update", {id_arg: "myKey", "description": "x", "version": 3}
        )

        assert result.is_error
        getattr(mock_fields_protocol, f"{prefix}_update").assert_not_called()

    @pytest.mark.parametrize(("prefix", "id_arg", "sample"), ENTITIES)
    async def test_read_only_mode_tool_not_registered(
        self,
        client_session_read_only: Client,
        mock_fields_protocol: AsyncMock,
        prefix: str,
        id_arg: str,
        sample: BaseModel,
    ) -> None:
        result = await client_session_read_only.call_tool(
            f"{prefix}_update", {id_arg: "myKey", "description": "x", "version": 3}
        )

        assert result.is_error
        getattr(mock_fields_protocol, f"{prefix}_update").assert_not_called()
