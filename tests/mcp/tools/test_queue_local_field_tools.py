from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.tracker.custom.errors import LocalFieldNotFound
from mcp_tracker.tracker.proto.types.fields import (
    FieldSchema,
    LocalField,
    OptionsProvider,
)
from mcp_tracker.tracker.proto.types.workflows import LocalizedText
from tests.mcp.conftest import get_tool_result_content

LOCAL_FIELD = LocalField.model_construct(
    id="6adf5b36c2dc6e1bb442dffa--locTest",
    key="locTest",
    name="Лок тест",
    version=1,
    schema_=FieldSchema(type="string", required=False),
    optionsProvider=OptionsProvider(type="FixedListOptionsProvider", values=["a"]),
)
USER_LOCAL_FIELD = LocalField.model_construct(
    id="6adf5b36c2dc6e1bb442dffa--locUser",
    key="locUser",
    version=1,
    schema_=FieldSchema(type="user", required=False),
)


def error_text(content: list[Any]) -> str:
    assert isinstance(content[0], TextContent)
    return content[0].text


class TestQueueGetLocalField:
    async def test_reads_by_key(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_get_local_field.return_value = LOCAL_FIELD

        result = await client_session.call_tool(
            "queue_get_local_field", {"queue_id": "TEST", "field_key": "locTest"}
        )

        assert not result.is_error
        assert get_tool_result_content(result)["id"] == LOCAL_FIELD.id
        assert mock_queues_protocol.queue_get_local_field.call_args.args == (
            "TEST",
            "locTest",
        )

    async def test_not_found_names_queue_and_field(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_get_local_field.side_effect = LocalFieldNotFound(
            "TEST", "nope"
        )

        result = await client_session.call_tool(
            "queue_get_local_field", {"queue_id": "TEST", "field_key": "nope"}
        )

        assert result.is_error
        text = error_text(result.content)
        assert "'nope'" in text
        assert "'TEST'" in text

    async def test_queue_outside_the_allow_list_is_refused(
        self, client_session_with_limits: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "queue_get_local_field", {"queue_id": "OTHER", "field_key": "locTest"}
        )

        assert result.is_error
        mock_queues_protocol.queue_get_local_field.assert_not_called()


class TestQueueCreateLocalField:
    async def test_create(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_create_local_field.return_value = LOCAL_FIELD

        result = await client_session.call_tool(
            "queue_create_local_field",
            {
                "queue_id": "TEST",
                "field_key": "locTest",
                "name": "Лок тест",
                "name_en": "Loc test",
                "category": "000000000000000000000001",
                "type": "string",
                "options": ["a", "b"],
                "container": True,
            },
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_create_local_field.call_args
        assert call.args == ("TEST",)
        assert call.kwargs["field_key"] == "locTest"
        assert call.kwargs["name"] == LocalizedText(ru="Лок тест", en="Loc test")
        assert call.kwargs["type"] == "string"
        assert call.kwargs["options"] == ["a", "b"]
        assert call.kwargs["container"] is True
        assert call.kwargs["hidden"] is None

    async def test_read_only_queue_is_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            "queue_create_local_field",
            {
                "queue_id": "READONLY",
                "field_key": "x",
                "name": "X",
                "category": "c",
                "type": "date",
            },
        )

        assert result.is_error
        mock_queues_protocol.queue_create_local_field.assert_not_called()


class TestQueueUpdateLocalField:
    async def test_update_without_options_does_not_read(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_update_local_field.return_value = LOCAL_FIELD

        result = await client_session.call_tool(
            "queue_update_local_field",
            {"queue_id": "TEST", "field_key": "locTest", "description": "d"},
        )

        assert not result.is_error
        mock_queues_protocol.queue_get_local_field.assert_not_called()
        call = mock_queues_protocol.queue_update_local_field.call_args
        assert call.args == ("TEST", "locTest")
        assert call.kwargs["description"] == "d"
        assert call.kwargs["options"] is None
        assert call.kwargs["user_options"] is False

    @pytest.mark.parametrize(
        ("sample", "user_options"),
        [
            pytest.param(LOCAL_FIELD, False, id="value-list"),
            pytest.param(USER_LOCAL_FIELD, True, id="user-field"),
        ],
    )
    async def test_options_are_written_as_the_kind_the_field_has(
        self,
        client_session: Client,
        mock_queues_protocol: AsyncMock,
        sample: LocalField,
        user_options: bool,
    ) -> None:
        mock_queues_protocol.queue_get_local_field.return_value = sample
        mock_queues_protocol.queue_update_local_field.return_value = sample

        result = await client_session.call_tool(
            "queue_update_local_field",
            {"queue_id": "TEST", "field_key": sample.key, "options": ["x"]},
        )

        assert not result.is_error
        call = mock_queues_protocol.queue_update_local_field.call_args
        assert call.kwargs["options"] == ["x"]
        assert call.kwargs["user_options"] is user_options

    async def test_empty_update_is_refused(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "queue_update_local_field", {"queue_id": "TEST", "field_key": "locTest"}
        )

        assert result.is_error
        assert "must change something" in error_text(result.content)
        mock_queues_protocol.queue_update_local_field.assert_not_called()

    async def test_read_only_queue_is_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            "queue_update_local_field",
            {"queue_id": "READONLY", "field_key": "x", "description": "d"},
        )

        assert result.is_error
        mock_queues_protocol.queue_update_local_field.assert_not_called()


class TestQueueDeleteTag:
    async def test_delete(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_delete_tag.return_value = None

        result = await client_session.call_tool(
            "queue_delete_tag", {"queue_id": "TEST", "tag": "старый"}
        )

        assert not result.is_error
        assert mock_queues_protocol.queue_delete_tag.call_args.args == (
            "TEST",
            "старый",
        )

    async def test_read_only_queue_is_refused(
        self,
        client_session_with_read_only_queues: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_read_only_queues.call_tool(
            "queue_delete_tag", {"queue_id": "READONLY", "tag": "x"}
        )

        assert result.is_error
        mock_queues_protocol.queue_delete_tag.assert_not_called()


@pytest.mark.parametrize(
    "tool",
    ["queue_create_local_field", "queue_update_local_field", "queue_delete_tag"],
)
async def test_read_only_mode_tool_not_registered(
    client_session_read_only: Client, tool: str
) -> None:
    tools = await client_session_read_only.list_tools()

    assert tool not in {t.name for t in tools.tools}
