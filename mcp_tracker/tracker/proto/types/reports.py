import datetime
from typing import Any, Literal

from pydantic import AliasChoices, Field, model_validator

from mcp_tracker.tracker.proto.types.base import (
    BaseTrackerEntity,
    NoneExcludedField,
    none_excluder,
)
from mcp_tracker.tracker.proto.types.mixins import CreatedMixin

ReportFormat = Literal["xlsx", "csv", "xml"]


class Report(CreatedMixin, BaseTrackerEntity):
    """An issue report ('отчёт'): an export of issues to a file, built by Tracker.

    Tracker nests `summary` and the rest under `fields`; they are lifted to the
    top level here.
    """

    id: str
    short_id: int | None = Field(
        None,
        validation_alias=AliasChoices("shortId", "short_id"),
        serialization_alias="shortId",
        exclude_if=none_excluder,
    )
    summary: str | None = NoneExcludedField
    entity_status: str | None = Field(
        None,
        validation_alias=AliasChoices("entityStatus", "entity_status"),
        serialization_alias="entityStatus",
        exclude_if=none_excluder,
        description="'done' once the file is built.",
    )
    updated_at: datetime.datetime | None = Field(
        None,
        validation_alias=AliasChoices("updatedAt", "updated_at"),
        serialization_alias="updatedAt",
        exclude_if=none_excluder,
    )
    parameters: dict[str, Any] | None = Field(
        None,
        exclude_if=none_excluder,
        description="What the report exports: its type, format, filter and fields.",
    )

    @model_validator(mode="before")
    @classmethod
    def _lift_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("fields"), dict):
            data = {**data, **data["fields"]}
        return data


class ReportSort(BaseTrackerEntity):
    """One sort key of a report."""

    order_by: str = Field(
        validation_alias=AliasChoices("order_by", "orderBy"),
        serialization_alias="orderBy",
        description="Issue field key, e.g. 'updated'.",
    )
    order_asc: bool = Field(
        True,
        validation_alias=AliasChoices("order_asc", "orderAsc"),
        serialization_alias="orderAsc",
        description="Ascending; false for descending.",
    )
