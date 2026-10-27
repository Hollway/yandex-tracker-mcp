from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mcp_tracker.tracker.proto.types.base import BaseTrackerEntity
from mcp_tracker.tracker.proto.types.refs import BaseReference


class FieldSchema(BaseModel):
    """Field schema/data type information"""

    type: str | None = None
    items: str | None = None
    required: bool | None = None


class SuggestProvider(BaseModel):
    model_config = ConfigDict(
        extra="allow",
    )
    type: str | None = None


class QueryProvider(BaseModel):
    model_config = ConfigDict(
        extra="allow",
    )
    type: str | None = None


class OptionsProvider(BaseModel):
    model_config = ConfigDict(
        extra="allow",
    )
    type: str | None = None
    values: Any | None = None


class CategoryRef(BaseReference):
    display: str | None = None


class GlobalField(BaseTrackerEntity):
    """Global field available in Yandex Tracker"""

    id: str
    name: str | None = None
    key: str | None = None
    version: int | None = None
    schema_: FieldSchema | None = Field(
        default=None, alias="schema", serialization_alias="schema"
    )
    readonly: bool | None = None
    options: bool | None = None
    suggest: bool | None = None
    type: str | None = None
    order: int | None = None
    suggestProvider: SuggestProvider | None = None
    optionsProvider: OptionsProvider | None = None
    queryProvider: QueryProvider | None = None
    category: CategoryRef | None = None
    description: str | None = None
    hidden: bool | None = None
    visible: bool | None = None


class LocalField(GlobalField):
    """Queue-specific local field"""


# The language Tracker names fields in, sent as `Accept-Language`; without one
# the API answers in the organization's own language.
FieldLanguage = Literal["ru", "en"]


class FieldCategory(BaseTrackerEntity):
    """A category that groups the organization's issue fields."""

    id: str
    name: str | None = None
    description: str | None = None
    order: int | None = None
    version: int | None = None


# The value type of a new field, as the API spells it after
# `ru.yandex.startrek.core.fields.` - the short name is what a tool takes.
FIELD_TYPES: dict[str, str] = {
    "date": "DateFieldType",
    "datetime": "DateTimeFieldType",
    "string": "StringFieldType",
    "text": "TextFieldType",
    "float": "FloatFieldType",
    "integer": "IntegerFieldType",
    "user": "UserFieldType",
    "uri": "UriFieldType",
    "money": "MoneyFieldType",
    "money_with_rate": "MoneyWithRateFieldType",
    "duration": "TimeTrackingDurationFieldType",
}

FieldType = Literal[
    "date",
    "datetime",
    "string",
    "text",
    "float",
    "integer",
    "user",
    "uri",
    "money",
    "money_with_rate",
    "duration",
]
