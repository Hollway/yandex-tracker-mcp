"""Finding an issue field by the name a user says, and the values it takes -
the logic behind `fields_find` and `field_get_values` in field.py.

Tracker names a field in the `Accept-Language` language, so a search reads the
fields in Russian and in English. Its query language names a field by that
name too, not by its id: `"Story Points": 3` works, `storyPoints: 3` answers
422 "Фильтр storypoints не существует"; a local field is `QUEUE."Name"`, and a
hidden one cannot be searched by at all (verified on the live API 2026-10-26).
"""

from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.tracker.proto.types.base import none_excluder
from mcp_tracker.tracker.proto.types.fields import GlobalField

# The value type of a field whose values come from a catalogue of their own,
# and the name `field_get_values` lists that catalogue under.
CATALOG_BY_VALUE_TYPE: dict[str, str] = {
    "priority": "priority",
    "issuetype": "type",
    "resolution": "resolution",
    "component": "components",
    "version": "fixVersions",
}

# The names `field_get_values` takes besides a field id.
CATALOG_FIELDS = frozenset(
    {"priority", "type", "resolution", "components", "fixVersions", "affectedVersions"}
)

# The tool that lists a field's values, by the value type.
_TOOL_BY_VALUE_TYPE: dict[str, str] = {
    **dict.fromkeys(CATALOG_BY_VALUE_TYPE, "field_get_values"),
    "user": "users_search",
    "queue": "queues_get_all",
    "status": "issue_get_transitions",
    "sprint": "board_get_sprints",
    "board": "boards_get_all",
    "group": "groups_get_all",
    "issue": "issues_find",
    "checklistItem": "issue_add_checklist_items",
    "project": "project_find",
    "metaEntity": "goal_find",
}

# Registered only under `TRACKER_ENTITIES_ENABLED`.
_ENTITY_TOOLS = frozenset({"project_find", "goal_find"})

_TOOL_BY_PROVIDER: dict[str, str] = {"TagOptionsProvider": "queue_get_tags"}

_FORMAT_BY_VALUE_TYPE: dict[str, str] = {
    "date": "date, YYYY-MM-DD",
    "datetime": "date and time, ISO 8601: 2026-10-26T12:00:00.000+0300",
    "timetracking": "duration, ISO 8601: P1DT4H30M",
    "integer": "integer",
    "float": "number",
    "string": "text",
    "text": "text, Markdown",
    "uri": "URL",
    "maillist": "mailing list address",
}

# A longer drop-down list is left to `field_get_values`, to keep a row short.
_MAX_INLINE_OPTIONS = 20


class FieldValuesHint(BaseModel):
    """How a field's value is given - exactly one of the three is set."""

    options: list[Any] | None = Field(
        None,
        description="The values the drop-down field takes, as they are written",
        exclude_if=none_excluder,
    )
    tool: str | None = Field(
        None, description="The tool that lists the values", exclude_if=none_excluder
    )
    format: str | None = Field(
        None, description="The form a free value takes", exclude_if=none_excluder
    )


class FieldRow(BaseModel):
    id: str = Field(
        description="The field id `fields` of issue_create / issue_update take"
    )
    name: str | None = Field(None, description="Russian name", exclude_if=none_excluder)
    name_en: str | None = Field(
        None,
        description="English name, when it differs from `name`",
        exclude_if=none_excluder,
    )
    queue: str | None = Field(
        None, description="The queue of a local field", exclude_if=none_excluder
    )
    type: str | None = Field(
        None, description="Value type; `array` for a list", exclude_if=none_excluder
    )
    items: str | None = Field(
        None, description="Item type of a list", exclude_if=none_excluder
    )
    readonly: bool | None = Field(None, exclude_if=none_excluder)
    hidden: bool | None = Field(None, exclude_if=none_excluder)
    ql_name: str | None = Field(
        None,
        description="The field's name in an issues_find `query`; absent when "
        "the field cannot be searched by",
        exclude_if=none_excluder,
    )
    values: FieldValuesHint


class FieldValue(BaseModel):
    id: str | None = Field(None, exclude_if=none_excluder)
    key: Any | None = Field(
        None,
        description="What a write takes; when absent, write the `id`",
        exclude_if=none_excluder,
    )
    display: str | None = Field(None, exclude_if=none_excluder)
    order: int | None = Field(
        None,
        description="Priority weight: higher is more urgent",
        exclude_if=none_excluder,
    )
    archived: bool | None = Field(None, exclude_if=none_excluder)


class FieldValues(BaseModel):
    field: str
    values: list[FieldValue]
    truncated: bool = Field(
        description="More values match than were returned: narrow `query`"
    )


def value_type(field: GlobalField) -> str | None:
    """What one value of the field is: the item type of a list."""
    schema = field.schema_
    if schema is None:
        return None
    return schema.items if schema.type == "array" and schema.items else schema.type


def fixed_options(field: GlobalField) -> list[Any] | None:
    provider = field.optionsProvider
    if provider is not None and isinstance(provider.values, list):
        return provider.values
    return None


def values_hint(field: GlobalField, *, entities_enabled: bool) -> FieldValuesHint:
    options = fixed_options(field)
    if options is not None:
        if len(options) <= _MAX_INLINE_OPTIONS:
            return FieldValuesHint(options=options)
        return FieldValuesHint(tool="field_get_values")

    provider = field.optionsProvider.type if field.optionsProvider else None
    kind = value_type(field)
    tool = _TOOL_BY_PROVIDER.get(provider or "") or _TOOL_BY_VALUE_TYPE.get(kind or "")
    if tool is not None and (entities_enabled or tool not in _ENTITY_TOOLS):
        return FieldValuesHint(tool=tool)

    value_format = _FORMAT_BY_VALUE_TYPE.get(kind or "", kind or "unknown")
    if field.schema_ is not None and field.schema_.type == "array":
        value_format = f"list of {value_format}"
    return FieldValuesHint(format=value_format)


def ql_name(field: GlobalField, name_en: str | None, queue: str | None) -> str | None:
    if field.hidden or field.queryProvider is None:
        return None
    name = name_en or field.name
    if not name:
        return None
    quoted = '"' + name.replace('"', '\\"') + '"'
    return f"{queue}.{quoted}" if queue else quoted


def field_rows(
    fields: Sequence[GlobalField],
    fields_en: Sequence[GlobalField],
    *,
    queue: str | None,
    entities_enabled: bool,
) -> list[FieldRow]:
    names_en = {f.id: f.name for f in fields_en}
    rows = []
    for field in fields:
        name_en = names_en.get(field.id)
        schema = field.schema_
        rows.append(
            FieldRow(
                id=field.id,
                name=field.name,
                name_en=name_en if name_en != field.name else None,
                queue=queue,
                type=schema.type if schema else None,
                items=schema.items if schema else None,
                readonly=field.readonly or None,
                hidden=field.hidden or None,
                ql_name=ql_name(field, name_en, queue),
                values=values_hint(field, entities_enabled=entities_enabled),
            )
        )
    return rows


def _row_texts(row: FieldRow, key: str | None) -> list[str]:
    return [
        text.casefold()
        for text in (row.id, key, row.name, row.name_en)
        if text is not None
    ]


def match_rows(
    rows: list[FieldRow], keys: dict[str, str | None], query: str | None
) -> list[FieldRow]:
    """The rows whose id, key or either name contains `query`, exact ones first."""
    if query is None:
        return rows
    needle = query.strip().casefold()
    exact, partial = [], []
    for row in rows:
        texts = _row_texts(row, keys.get(row.id))
        if needle in texts:
            exact.append(row)
        elif any(needle in text for text in texts):
            partial.append(row)
    return exact + partial


def find_field(fields: Iterable[GlobalField], field_id: str) -> GlobalField | None:
    return next((f for f in fields if field_id in (f.id, f.key)), None)


def free_value_error(field_id: str, hint: FieldValuesHint) -> TrackerError:
    if hint.tool is not None:
        return TrackerError(
            f"The values of `{field_id}` are not a fixed list: look them up with "
            f"{hint.tool}."
        )
    return TrackerError(
        f"`{field_id}` takes a free value, not one from a list: {hint.format}."
    )


def select_values(
    field_id: str, values: list[FieldValue], query: str | None, limit: int
) -> FieldValues:
    if query is not None:
        needle = query.strip().casefold()
        values = [
            value
            for value in values
            if any(
                needle in str(text).casefold()
                for text in (value.key, value.display, value.id)
                if text is not None
            )
        ]
    return FieldValues(
        field=field_id, values=values[:limit], truncated=len(values) > limit
    )
