from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.fields import (
    FieldSchema,
    GlobalField,
    LocalField,
    OptionsProvider,
    QueryProvider,
)
from mcp_tracker.tracker.proto.types.issue_types import IssueType
from mcp_tracker.tracker.proto.types.issues import Issue
from mcp_tracker.tracker.proto.types.priorities import Priority
from mcp_tracker.tracker.proto.types.queues import (
    Queue,
    QueueIssueTypeConfig,
    QueueVersion,
)
from mcp_tracker.tracker.proto.types.refs import IssueTypeReference
from mcp_tracker.tracker.proto.types.resolutions import Resolution
from tests.mcp.conftest import get_tool_result_content

QUERYABLE = QueryProvider(type="StringOptionalQueryProvider")


def field(
    id: str,
    name: str,
    value_type: str,
    *,
    items: str | None = None,
    options: list[Any] | None = None,
    provider: str | None = None,
    queryable: bool = True,
    **extra: Any,
) -> GlobalField:
    options_provider = None
    if options is not None or provider is not None:
        options_provider = OptionsProvider(
            type=provider or "FixedListOptionsProvider", values=options
        )
    return GlobalField.model_construct(
        id=id,
        key=id,
        name=name,
        schema_=FieldSchema(type=value_type, items=items),
        optionsProvider=options_provider,
        queryProvider=QUERYABLE if queryable else None,
        **extra,
    )


def local(key: str, name: str, options: list[Any] | None = None) -> LocalField:
    return LocalField.model_construct(
        id=f"6582fa303d406816db7e1dd4--{key}",
        key=key,
        name=name,
        schema_=FieldSchema(type="string"),
        optionsProvider=OptionsProvider(type="FixedListOptionsProvider", values=options)
        if options is not None
        else None,
        queryProvider=QUERYABLE,
    )


GLOBAL_RU = [
    field("projectSap", "Проект SAP", "string"),
    field("project", "Проект", "project", provider="ProjectOptionsProvider"),
    field("storyPoints", "Story Points", "float"),
    field("assignee", "Исполнитель", "user", provider="TeamOptionsProvider"),
    field("deadline", "Дедлайн", "date"),
    field("emailTo", "Кому", "array", items="string"),
    field("tags", "Теги", "array", items="string", provider="TagOptionsProvider"),
    field("priority", "Приоритет", "priority", provider="PriorityOptionsProvider"),
    field("mcpTestField", "MCP test", "string", options=["альфа", "бета"], hidden=True),
    field("possibleSpam", "Возможно спам", "integer", options=[0, 1]),
    field("big", "Большой", "string", options=[f"v{i}" for i in range(30)]),
    field("spent", "Затрачено времени", "timetracking", readonly=True),
    field("sla", "SLA", "sla", queryable=False),
]
GLOBAL_EN = [
    field("projectSap", "Project SAP", "string"),
    field("storyPoints", "Story Points", "float"),
    field("assignee", "Assignee", "user"),
    field("deadline", "Deadline", "date"),
    field("mcpTestField", "MCP test", "string"),
]
LOCAL_RU = [
    local("cats", "Добавить в CATS", ["Да", "Нет"]),
    local("systemId", "ID Системы"),
]
LOCAL_EN = [local("cats", "Add to CATS"), local("systemId", "System ID")]


def error_text(content: list[Any]) -> str:
    assert isinstance(content[0], TextContent)
    return content[0].text


@pytest.fixture
def fields_by_language(
    mock_fields_protocol: AsyncMock, mock_queues_protocol: AsyncMock
) -> None:
    mock_fields_protocol.get_global_fields.side_effect = (
        lambda *, language=None, auth=None: GLOBAL_EN if language == "en" else GLOBAL_RU
    )
    mock_queues_protocol.queues_get_local_fields.side_effect = (
        lambda queue, *, language=None, auth=None: (
            LOCAL_EN if language == "en" else LOCAL_RU
        )
    )


def rows_by_id(content: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in content}


@pytest.mark.usefixtures("fields_by_language")
class TestFieldsFind:
    async def test_finds_by_russian_name(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool("fields_find", {"query": "проект sap"})

        assert not result.is_error
        assert get_tool_result_content(result) == [
            {
                "id": "projectSap",
                "name": "Проект SAP",
                "name_en": "Project SAP",
                "type": "string",
                "ql_name": '"Project SAP"',
                "values": {"format": "text"},
            }
        ]
        languages = [
            call.kwargs["language"]
            for call in mock_fields_protocol.get_global_fields.call_args_list
        ]
        assert sorted(languages) == ["en", "ru"]
        mock_queues_protocol.queues_get_local_fields.assert_not_called()

    @pytest.mark.parametrize("query", ["Deadline", "deadl", "DEADLINE"])
    async def test_finds_by_english_name_or_id(
        self, client_session: Client, query: str
    ) -> None:
        result = await client_session.call_tool("fields_find", {"query": query})

        assert [row["id"] for row in get_tool_result_content(result)] == ["deadline"]

    async def test_exact_match_comes_first(self, client_session: Client) -> None:
        result = await client_session.call_tool("fields_find", {"query": "проект"})

        assert [row["id"] for row in get_tool_result_content(result)] == [
            "project",
            "projectSap",
        ]

    async def test_no_match_is_an_empty_list(self, client_session: Client) -> None:
        result = await client_session.call_tool("fields_find", {"query": "zzz"})

        assert not result.is_error
        assert get_tool_result_content(result) == []

    async def test_queue_alone_lists_its_local_fields(
        self,
        client_session: Client,
        mock_fields_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool("fields_find", {"queue": "sap"})

        assert not result.is_error
        rows = get_tool_result_content(result)
        assert rows[0] == {
            "id": "6582fa303d406816db7e1dd4--cats",
            "name": "Добавить в CATS",
            "name_en": "Add to CATS",
            "queue": "SAP",
            "type": "string",
            "ql_name": 'SAP."Add to CATS"',
            "values": {"options": ["Да", "Нет"]},
        }
        assert len(rows) == 2
        mock_fields_protocol.get_global_fields.assert_not_called()
        assert {
            call.args[0]
            for call in mock_queues_protocol.queues_get_local_fields.call_args_list
        } == {"SAP"}

    async def test_query_with_queue_searches_both(self, client_session: Client) -> None:
        result = await client_session.call_tool(
            "fields_find", {"query": "system", "queue": "SAP"}
        )

        assert [row["id"] for row in get_tool_result_content(result)] == [
            "6582fa303d406816db7e1dd4--systemId"
        ]

    async def test_hidden_field_has_no_query_name(self, client_session: Client) -> None:
        result = await client_session.call_tool("fields_find", {"query": "mcpTest"})

        row = get_tool_result_content(result)[0]
        assert row["hidden"] is True
        assert "ql_name" not in row
        assert "name_en" not in row
        assert row["values"] == {"options": ["альфа", "бета"]}

    @pytest.mark.parametrize(
        ("query", "values"),
        [
            ("assignee", {"tool": "users_search"}),
            ("deadline", {"format": "date, YYYY-MM-DD"}),
            ("emailTo", {"format": "list of text"}),
            ("tags", {"tool": "queue_get_tags"}),
            ("priority", {"tool": "field_get_values"}),
            ("big", {"tool": "field_get_values"}),
            ("possibleSpam", {"options": [0, 1]}),
            ("project", {"tool": "project_find"}),
            ("spent", {"format": "duration, ISO 8601: P1DT4H30M"}),
        ],
    )
    async def test_says_how_values_are_given(
        self, client_session: Client, query: str, values: dict[str, Any]
    ) -> None:
        result = await client_session.call_tool("fields_find", {"query": query})

        assert rows_by_id(get_tool_result_content(result))[query]["values"] == values

    async def test_entity_tool_is_not_named_when_entities_are_off(
        self, client_session_entities_disabled: Client
    ) -> None:
        result = await client_session_entities_disabled.call_tool(
            "fields_find", {"query": "Проект"}
        )

        row = rows_by_id(get_tool_result_content(result))["project"]
        assert row["values"] == {"format": "project"}

    async def test_unsearchable_field_has_no_query_name(
        self, client_session: Client
    ) -> None:
        result = await client_session.call_tool("fields_find", {"query": "sla"})

        assert "ql_name" not in get_tool_result_content(result)[0]

    async def test_query_or_queue_required(self, client_session: Client) -> None:
        result = await client_session.call_tool("fields_find", {})

        assert result.is_error
        assert "Pass `query`, `queue` or both" in error_text(result.content)

    async def test_queue_outside_the_allow_list(
        self,
        client_session_with_limits: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "fields_find", {"queue": "SAP"}
        )

        assert result.is_error
        mock_queues_protocol.queues_get_local_fields.assert_not_called()


TASK = IssueTypeReference(id="2", key="task", display="Задача")
MILESTONE = IssueTypeReference(id="21", key="milestone", display="Веха")
FIXED = Resolution.model_construct(id=1, key="fixed", display="Решен")
WONT_FIX = Resolution.model_construct(id=2, key="wontFix", display="Не будет")
DUPLICATE = Resolution.model_construct(id=4, key="duplicate", display="Дубликат")
QUEUE_WITH_TYPES = Queue.model_construct(
    key="SAP",
    issueTypesConfig=[
        QueueIssueTypeConfig.model_construct(
            issueType=MILESTONE, resolutions=[FIXED, WONT_FIX]
        ),
        QueueIssueTypeConfig.model_construct(
            issueType=TASK, resolutions=[DUPLICATE, FIXED]
        ),
    ],
)
PRIORITIES = [
    Priority.model_construct(
        id=4, version=1, key="critical", name="Критичный", order=40
    ),
    Priority.model_construct(
        id=6, version=1, key="minimal", name="Минимальный", order=5
    ),
    Priority.model_construct(id=3, version=1, key="normal", name="Средний", order=30),
]


async def values_of(client: Client, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool("field_get_values", arguments)
    assert not result.is_error, error_text(result.content)
    content: dict[str, Any] = get_tool_result_content(result)
    return content


@pytest.mark.usefixtures("fields_by_language")
class TestFieldGetValues:
    async def test_priorities_by_weight(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.get_priorities.return_value = PRIORITIES

        content = await values_of(client_session, {"field": "priority"})

        assert content == {
            "field": "priority",
            "values": [
                {"id": "6", "key": "minimal", "display": "Минимальный", "order": 5},
                {"id": "3", "key": "normal", "display": "Средний", "order": 30},
                {"id": "4", "key": "critical", "display": "Критичный", "order": 40},
            ],
            "truncated": False,
        }

    async def test_query_filters_by_name(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.get_priorities.return_value = PRIORITIES

        content = await values_of(
            client_session, {"field": "priority", "query": "КРИТ"}
        )

        assert [value["key"] for value in content["values"]] == ["critical"]

    async def test_types_of_a_queue(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_get.return_value = QUEUE_WITH_TYPES

        content = await values_of(client_session, {"field": "type", "queue": "sap"})

        assert content["values"] == [
            {"id": "21", "key": "milestone", "display": "Веха"},
            {"id": "2", "key": "task", "display": "Задача"},
        ]
        assert mock_queues_protocol.queue_get.call_args.args == ("SAP",)
        assert mock_queues_protocol.queue_get.call_args.kwargs["expand"] == [
            "issueTypesConfig"
        ]

    async def test_types_of_the_organization(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.get_issue_types.return_value = [
            IssueType.model_construct(id=1, version=1, key="bug", name="Ошибка")
        ]

        content = await values_of(client_session, {"field": "type"})

        assert content["values"] == [{"id": "1", "key": "bug", "display": "Ошибка"}]

    async def test_resolutions_of_a_queue_are_every_types(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queue_get.return_value = QUEUE_WITH_TYPES

        content = await values_of(
            client_session, {"field": "resolution", "queue": "SAP"}
        )

        assert [value["key"] for value in content["values"]] == [
            "fixed",
            "wontFix",
            "duplicate",
        ]

    async def test_resolutions_of_an_issue_are_its_types(
        self,
        client_session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue.model_construct(
            key="SAP-1", type=TASK
        )
        mock_queues_protocol.queue_get.return_value = QUEUE_WITH_TYPES

        content = await values_of(
            client_session, {"field": "resolution", "issue_id": "SAP-1"}
        )

        assert content["values"] == [
            {"id": "4", "key": "duplicate", "display": "Дубликат"},
            {"id": "1", "key": "fixed", "display": "Решен"},
        ]
        assert mock_queues_protocol.queue_get.call_args.args == ("SAP",)

    async def test_resolutions_of_the_organization(
        self, client_session: Client, mock_fields_protocol: AsyncMock
    ) -> None:
        mock_fields_protocol.get_resolutions.return_value = [
            Resolution.model_construct(id=1, key="fixed", name="Решен")
        ]

        content = await values_of(client_session, {"field": "resolution"})

        assert content["values"] == [{"id": "1", "key": "fixed", "display": "Решен"}]

    async def test_components(
        self, client_session: Client, mock_queues_protocol: AsyncMock
    ) -> None:
        mock_queues_protocol.queues_get_components.return_value = [
            Component.model_construct(id=7, version=1, name="Backend")
        ]

        content = await values_of(
            client_session, {"field": "components", "queue": "SAP"}
        )

        assert content["values"] == [{"id": "7", "display": "Backend"}]

    @pytest.mark.parametrize("field_id", ["fixVersions", "affectedVersions"])
    async def test_versions_mark_archived(
        self, client_session: Client, mock_queues_protocol: AsyncMock, field_id: str
    ) -> None:
        mock_queues_protocol.queues_get_versions.return_value = [
            QueueVersion.model_construct(
                id=1, version=1, released=False, name="1.0", archived=True
            ),
            QueueVersion.model_construct(
                id=2, version=1, released=False, name="2.0", archived=False
            ),
        ]

        content = await values_of(client_session, {"field": field_id, "queue": "SAP"})

        assert content["values"] == [
            {"id": "1", "display": "1.0", "archived": True},
            {"id": "2", "display": "2.0"},
        ]

    @pytest.mark.parametrize("field_id", ["components", "fixVersions"])
    async def test_queue_catalogue_needs_a_queue(
        self, client_session: Client, field_id: str
    ) -> None:
        result = await client_session.call_tool("field_get_values", {"field": field_id})

        assert result.is_error
        assert "belong to a queue" in error_text(result.content)

    async def test_fixed_list_is_capped(self, client_session: Client) -> None:
        content = await values_of(client_session, {"field": "big", "limit": 2})

        assert content == {
            "field": "big",
            "values": [
                {"key": "v0", "display": "v0"},
                {"key": "v1", "display": "v1"},
            ],
            "truncated": True,
        }

    async def test_numeric_options_keep_their_type(
        self, client_session: Client
    ) -> None:
        content = await values_of(client_session, {"field": "possibleSpam"})

        assert content["values"] == [
            {"key": 0, "display": "0"},
            {"key": 1, "display": "1"},
        ]

    @pytest.mark.parametrize("field_id", ["cats", "6582fa303d406816db7e1dd4--cats"])
    async def test_local_field_by_key_or_id(
        self, client_session: Client, field_id: str
    ) -> None:
        content = await values_of(client_session, {"field": field_id, "queue": "SAP"})

        assert [value["key"] for value in content["values"]] == ["Да", "Нет"]

    async def test_local_field_needs_its_queue(self, client_session: Client) -> None:
        result = await client_session.call_tool(
            "field_get_values", {"field": "6582fa303d406816db7e1dd4--cats"}
        )

        assert result.is_error
        assert "is a local field" in error_text(result.content)

    @pytest.mark.parametrize(
        ("arguments", "message"),
        [
            ({"field": "nope"}, "No issue field `nope`; find it with fields_find"),
            ({"field": "nope", "queue": "SAP"}, "No issue field `nope` in queue SAP"),
            ({"field": "assignee"}, "look them up with users_search"),
            ({"field": "deadline"}, "takes a free value, not one from a list: date"),
            (
                {"field": "type", "queue": "SAP", "issue_id": "SAP-1"},
                "not both",
            ),
        ],
    )
    async def test_errors(
        self, client_session: Client, arguments: dict[str, Any], message: str
    ) -> None:
        result = await client_session.call_tool("field_get_values", arguments)

        assert result.is_error
        assert message in error_text(result.content)

    @pytest.mark.parametrize(
        "arguments",
        [
            {"field": "type", "queue": "SAP"},
            {"field": "resolution", "issue_id": "SAP-1"},
        ],
    )
    async def test_outside_the_allow_list(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
        arguments: dict[str, Any],
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "field_get_values", arguments
        )

        assert result.is_error
        mock_issues_protocol.issue_get.assert_not_called()
        mock_queues_protocol.queue_get.assert_not_called()

    async def test_moved_issue_checks_the_key_it_answers_with(
        self,
        client_session_with_limits: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue.model_construct(
            key="SAP-1", type=TASK
        )

        result = await client_session_with_limits.call_tool(
            "field_get_values", {"field": "resolution", "issue_id": "ALLOWED-1"}
        )

        assert result.is_error
        mock_queues_protocol.queue_get.assert_not_called()
