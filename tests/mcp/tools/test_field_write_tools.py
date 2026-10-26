from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.tracker.custom.errors import (
    CatalogObjectNotFound,
    CatalogVersionConflict,
)
from mcp_tracker.tracker.proto.types.fields import (
    FieldCategory,
    FieldSchema,
    GlobalField,
    OptionsProvider,
)
from mcp_tracker.tracker.proto.types.workflows import LocalizedText
from tests.mcp.conftest import get_tool_result_content

FIELD = GlobalField.model_construct(
    id="mcpTestField",
    key="mcpTestField",
    name="MCP test",
    version=4,
    schema_=FieldSchema(type="string", required=False),
    optionsProvider=OptionsProvider(
        type="FixedListOptionsProvider", values=["альфа", "бета"]
    ),
)
USER_FIELD = GlobalField.model_construct(
    id="reviewer",
    version=2,
    schema_=FieldSchema(type="user", required=False),
)
CATEGORY = FieldCategory.model_construct(
    id="6adf5611c2dc6e1bb4414db1", name="MCP test", version=3
)


def error_text(content: list[Any]) -> str:
    assert isinstance(content[0], TextContent)
    return content[0].text


class TestFieldRead:
    async def test_field_get(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_get.return_value = FIELD

        result = await client_session.call_tool(
            "field_get", {"field_id": "mcpTestField"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["id"] == "mcpTestField"
        assert content["version"] == 4
        mock_fields_protocol.field_get.assert_called_once()
        assert mock_fields_protocol.field_get.call_args.args == ("mcpTestField",)

    async def test_field_get_not_found(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_get.side_effect = CatalogObjectNotFound(
            "field", "nope", "get_global_fields"
        )

        result = await client_session.call_tool("field_get", {"field_id": "nope"})

        assert result.is_error
        assert "No field with key or ID 'nope'" in error_text(result.content)

    async def test_fields_get_categories(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.fields_get_categories.return_value = [CATEGORY]

        result = await client_session.call_tool("fields_get_categories", {})

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content[0]["id"] == "6adf5611c2dc6e1bb4414db1"
        assert content[0]["version"] == 3


class TestFieldCreate:
    async def test_minimal_create(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_create.return_value = FIELD

        result = await client_session.call_tool(
            "field_create",
            {
                "field_id": "mcpTestField",
                "name": "MCP test",
                "category": "6adf5611c2dc6e1bb4414db1",
                "type": "string",
            },
        )

        assert not result.is_error
        kwargs = mock_fields_protocol.field_create.call_args.kwargs
        assert kwargs["field_id"] == "mcpTestField"
        assert kwargs["name"] == LocalizedText(ru="MCP test", en="MCP test")
        assert kwargs["category"] == "6adf5611c2dc6e1bb4414db1"
        assert kwargs["type"] == "string"
        assert kwargs["options"] is None
        assert kwargs["hidden"] is None

    async def test_create_passes_every_argument(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_create.return_value = FIELD

        result = await client_session.call_tool(
            "field_create",
            {
                "field_id": "mcpTestField",
                "name": "Тест",
                "name_en": "Test",
                "category": "c1",
                "type": "integer",
                "description": "d",
                "order": 7,
                "readonly": True,
                "visible": False,
                "hidden": True,
                "container": True,
                "options": [1, 2, 3],
            },
        )

        assert not result.is_error
        kwargs = mock_fields_protocol.field_create.call_args.kwargs
        assert kwargs["name"] == LocalizedText(ru="Тест", en="Test")
        assert kwargs["type"] == "integer"
        assert kwargs["description"] == "d"
        assert kwargs["order"] == 7
        assert kwargs["readonly"] is True
        assert kwargs["visible"] is False
        assert kwargs["hidden"] is True
        assert kwargs["container"] is True
        assert kwargs["options"] == [1, 2, 3]

    async def test_unknown_type_is_rejected(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "field_create",
            {"field_id": "x", "name": "X", "category": "c1", "type": "boolean"},
        )

        assert result.is_error
        mock_fields_protocol.field_create.assert_not_called()

    async def test_create_category(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_category_create.return_value = CATEGORY

        result = await client_session.call_tool(
            "field_create_category", {"name": "MCP test", "order": 900}
        )

        assert not result.is_error
        kwargs = mock_fields_protocol.field_category_create.call_args.kwargs
        assert kwargs["name"] == LocalizedText(ru="MCP test", en="MCP test")
        assert kwargs["order"] == 900
        assert kwargs["description"] is None

    @pytest.mark.parametrize(
        ("tool", "args", "method"),
        [
            pytest.param(
                "field_create",
                {"field_id": "x", "name": "X", "category": "c1", "type": "date"},
                "field_create",
                id="field",
            ),
            pytest.param(
                "field_create_category",
                {"name": "X", "order": 1},
                "field_category_create",
                id="category",
            ),
        ],
    )
    async def test_create_allowed_on_a_server_limited_to_some_queues(
        self,
        client_session_with_limits: Client,
        mock_fields_protocol: AsyncMock,
        tool: str,
        args: dict[str, Any],
        method: str,
    ) -> None:
        getattr(mock_fields_protocol, method).return_value = (
            FIELD if method == "field_create" else CATEGORY
        )

        result = await client_session_with_limits.call_tool(tool, args)

        assert not result.is_error


class TestFieldUpdate:
    async def test_given_version_is_used_without_a_read(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_update.return_value = FIELD

        result = await client_session.call_tool(
            "field_update",
            {"field_id": "mcpTestField", "description": "d2", "version": 4},
        )

        assert not result.is_error
        mock_fields_protocol.field_get.assert_not_called()
        kwargs = mock_fields_protocol.field_update.call_args.kwargs
        assert kwargs["version"] == 4
        assert kwargs["description"] == "d2"
        assert kwargs["name"] is None
        assert kwargs["options"] is None

    async def test_omitted_version_is_read_first(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_get.return_value = FIELD
        mock_fields_protocol.field_update.return_value = FIELD

        result = await client_session.call_tool(
            "field_update", {"field_id": "mcpTestField", "hidden": False}
        )

        assert not result.is_error
        mock_fields_protocol.field_get.assert_called_once()
        assert mock_fields_protocol.field_update.call_args.kwargs["version"] == 4

    @pytest.mark.parametrize(
        ("sample", "user_options"),
        [
            pytest.param(FIELD, False, id="value-list"),
            pytest.param(USER_FIELD, True, id="user-field"),
        ],
    )
    async def test_options_are_written_as_the_kind_the_field_has(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        sample: GlobalField,
        user_options: bool,
    ) -> None:
        mock_fields_protocol.field_get.return_value = sample
        mock_fields_protocol.field_update.return_value = sample

        result = await client_session.call_tool(
            "field_update",
            {"field_id": sample.id, "options": ["a", "b"], "version": 9},
        )

        assert not result.is_error
        mock_fields_protocol.field_get.assert_called_once()
        kwargs = mock_fields_protocol.field_update.call_args.kwargs
        assert kwargs["options"] == ["a", "b"]
        assert kwargs["user_options"] is user_options
        assert kwargs["version"] == 9

    async def test_name_en_defaults_to_name(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_update.return_value = FIELD

        result = await client_session.call_tool(
            "field_update", {"field_id": "f", "name": "Новое", "version": 1}
        )

        assert not result.is_error
        assert mock_fields_protocol.field_update.call_args.kwargs[
            "name"
        ] == LocalizedText(ru="Новое", en="Новое")

    @pytest.mark.parametrize(
        ("tool", "args"),
        [
            pytest.param("field_update", {"field_id": "f"}, id="field"),
            pytest.param("field_update_category", {"category_id": "c1"}, id="category"),
        ],
    )
    async def test_empty_update_is_refused(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        tool: str,
        args: dict[str, Any],
    ) -> None:
        result = await client_session.call_tool(tool, args)

        assert result.is_error
        assert "must change something" in error_text(result.content)
        mock_fields_protocol.field_get.assert_not_called()
        mock_fields_protocol.field_update.assert_not_called()
        mock_fields_protocol.field_category_get.assert_not_called()
        mock_fields_protocol.field_category_update.assert_not_called()

    async def test_name_en_alone_is_refused(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "field_update", {"field_id": "f", "name_en": "X"}
        )

        assert result.is_error
        mock_fields_protocol.field_update.assert_not_called()

    async def test_version_conflict_reaches_the_caller(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_update.side_effect = CatalogVersionConflict(
            "field", "f", 1, "get_global_fields"
        )

        result = await client_session.call_tool(
            "field_update", {"field_id": "f", "description": "x", "version": 1}
        )

        assert result.is_error
        assert "Editing conflict for field 'f'" in error_text(result.content)

    async def test_category_omitted_version_is_read_first(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_category_get.return_value = CATEGORY
        mock_fields_protocol.field_category_update.return_value = CATEGORY

        result = await client_session.call_tool(
            "field_update_category",
            {"category_id": "c1", "name": "Новое", "order": 5},
        )

        assert not result.is_error
        mock_fields_protocol.field_category_get.assert_called_once()
        kwargs = mock_fields_protocol.field_category_update.call_args.kwargs
        assert kwargs["version"] == 3
        assert kwargs["name"] == LocalizedText(ru="Новое", en="Новое")
        assert kwargs["order"] == 5

    async def test_category_given_version_is_used_without_a_read(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.field_category_update.return_value = CATEGORY

        result = await client_session.call_tool(
            "field_update_category",
            {"category_id": "c1", "description": "d", "version": 2},
        )

        assert not result.is_error
        mock_fields_protocol.field_category_get.assert_not_called()
        assert (
            mock_fields_protocol.field_category_update.call_args.kwargs["version"] == 2
        )

    @pytest.mark.parametrize(
        ("tool", "args", "method"),
        [
            pytest.param(
                "field_update",
                {"field_id": "f", "description": "x", "version": 1},
                "field_update",
                id="field",
            ),
            pytest.param(
                "field_update_category",
                {"category_id": "c1", "description": "x", "version": 1},
                "field_category_update",
                id="category",
            ),
        ],
    )
    async def test_refused_on_a_server_limited_to_some_queues(
        self,
        client_session_with_limits: Client,
        mock_fields_protocol: AsyncMock,
        tool: str,
        args: dict[str, Any],
        method: str,
    ) -> None:
        result = await client_session_with_limits.call_tool(tool, args)

        assert result.is_error
        assert "shared by every queue" in error_text(result.content)
        getattr(mock_fields_protocol, method).assert_not_called()

    @pytest.mark.parametrize(
        ("tool", "args", "method"),
        [
            pytest.param(
                "field_update",
                {"field_id": "f", "description": "x", "version": 1},
                "field_update",
                id="field",
            ),
            pytest.param(
                "field_update_category",
                {"category_id": "c1", "description": "x", "version": 1},
                "field_category_update",
                id="category",
            ),
        ],
    )
    async def test_refused_with_read_only_queues(
        self,
        client_session_with_read_only_queues: Client,
        mock_fields_protocol: AsyncMock,
        tool: str,
        args: dict[str, Any],
        method: str,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(tool, args)

        assert result.is_error
        getattr(mock_fields_protocol, method).assert_not_called()


@pytest.mark.parametrize(
    "tool",
    [
        "field_create",
        "field_update",
        "field_create_category",
        "field_update_category",
    ],
)
async def test_read_only_mode_tool_not_registered(
    client_session_read_only: Client, tool: str
) -> None:
    tools = await client_session_read_only.list_tools()

    assert tool not in {t.name for t in tools.tools}
