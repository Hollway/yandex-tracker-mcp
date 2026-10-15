import re
from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator

from mcp_tracker.tracker.proto.types.base import BaseTrackerEntity, NoneExcludedField
from mcp_tracker.tracker.proto.types.refs import (
    IssueTypeReference,
    PriorityReference,
    QueueReference,
)
from mcp_tracker.tracker.proto.types.resolutions import Resolution


class QueueIssueTypeConfig(BaseTrackerEntity):
    """Issue type configuration within a queue, including available resolutions."""

    issueType: IssueTypeReference | None = Field(
        None, description="Issue type reference"
    )
    resolutions: list[Resolution] | None = Field(
        None, description="Available resolutions for this issue type"
    )


class Queue(BaseTrackerEntity):
    # `expand` sections (components, versions, projects, workflows, ...) are
    # returned as extra keys, and Tracker leaves a section out entirely when it
    # is empty. Dropping unknown keys here would silently discard everything
    # `expand` was asked for.
    model_config = ConfigDict(extra="allow")

    id: int | None = NoneExcludedField
    key: str | None = NoneExcludedField
    name: str | None = NoneExcludedField
    description: str | None = NoneExcludedField
    defaultType: IssueTypeReference | None = NoneExcludedField
    defaultPriority: PriorityReference | None = NoneExcludedField
    issueTypesConfig: list[QueueIssueTypeConfig] | None = NoneExcludedField


# Expand options for queue_get API
QueueExpandOption = Literal[
    "all",
    "projects",
    "components",
    "versions",
    "types",
    "team",
    "workflows",
    "fields",
    "issueTypesConfig",
]


QueueFieldsEnum = Enum(  # type: ignore[misc]
    "QueueFieldsEnum",
    {key: key for key in Queue.model_fields.keys()},
)


class QueueVersion(BaseTrackerEntity):
    model_config = ConfigDict(extra="ignore")

    id: int
    version: int
    queue: QueueReference | None = NoneExcludedField
    name: str
    description: str | None = None
    startDate: date | None = None
    dueDate: date | None = None
    released: bool
    archived: bool


# Keys whose values a trigger's actions must not hand out: webhook credentials
# and headers. Tracker masks them, but a masked value is no use to the caller
# either, and an unmasked one in a response would be a leak.
_SECRET_KEY = re.compile(r"auth|token|password|secret|header", re.IGNORECASE)


def _drop_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_secrets(item)
            for key, item in value.items()
            if not _SECRET_KEY.search(str(key))
        }
    if isinstance(value, list):
        return [_drop_secrets(item) for item in value]
    return value


class QueueTrigger(BaseTrackerEntity):
    """A queue automation trigger: when `conditions` hold, `actions` run."""

    id: int
    name: str | None = NoneExcludedField
    active: bool | None = NoneExcludedField
    order: str | None = NoneExcludedField
    version: int | None = NoneExcludedField
    conditions: list[dict[str, Any]] | None = NoneExcludedField
    actions: list[dict[str, Any]] | None = NoneExcludedField

    @field_validator("actions", mode="before")
    @classmethod
    def drop_secrets(cls, value: Any) -> Any:
        return _drop_secrets(value)
