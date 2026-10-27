"""Queue automation (triggers, autoactions, macros) and queue administration.

The automation objects are free-form in the API - an action or a condition is a
typed object whose other keys depend on its `type` - so they are kept as dicts
rather than modelled one type at a time. Webhook credentials and headers are
dropped from what comes back, as `QueueTrigger` does.
"""

import datetime
from typing import Any

from pydantic import ConfigDict, Field, field_validator

from mcp_tracker.tracker.proto.types.base import BaseTrackerEntity, NoneExcludedField
from mcp_tracker.tracker.proto.types.queues import _drop_secrets
from mcp_tracker.tracker.proto.types.refs import IssueReference, QueueReference


class QueueTriggerLog(BaseTrackerEntity):
    """One run of a trigger's HTTP request (Webhook) action."""

    id: str | None = NoneExcludedField
    triggerId: int | None = NoneExcludedField
    actionId: int | None = NoneExcludedField
    issueId: str | None = NoneExcludedField
    startTime: datetime.datetime | None = NoneExcludedField
    endTime: datetime.datetime | None = NoneExcludedField
    duration: int | None = NoneExcludedField
    request: dict[str, Any] | None = NoneExcludedField
    response: dict[str, Any] | None = NoneExcludedField

    @field_validator("request", "response", mode="before")
    @classmethod
    def drop_secrets(cls, value: Any) -> Any:
        return _drop_secrets(value)


class QueueAutoaction(BaseTrackerEntity):
    """A queue autoaction: on a schedule, `actions` run on the issues that
    `filter` or `query` selects."""

    id: int
    name: str | None = NoneExcludedField
    version: int | None = NoneExcludedField
    active: bool | None = NoneExcludedField
    created: datetime.datetime | None = NoneExcludedField
    updated: datetime.datetime | None = NoneExcludedField
    filter: Any = NoneExcludedField
    query: str | None = NoneExcludedField
    actions: list[dict[str, Any]] | None = NoneExcludedField
    enableNotifications: bool | None = NoneExcludedField
    lastLaunch: datetime.datetime | None = NoneExcludedField
    totalIssuesProcessed: int | None = NoneExcludedField
    intervalMillis: int | None = NoneExcludedField
    calendar: dict[str, Any] | None = NoneExcludedField

    @field_validator("actions", mode="before")
    @classmethod
    def drop_secrets(cls, value: Any) -> Any:
        return _drop_secrets(value)


class QueueAutoactionRun(BaseTrackerEntity):
    """One launch of an autoaction."""

    id: str
    launchTime: datetime.datetime | None = NoneExcludedField
    searchHits: int | None = NoneExcludedField
    successes: int | None = NoneExcludedField
    failures: int | None = NoneExcludedField
    searchFailed: bool | None = NoneExcludedField


class QueueAutoactionRunIssue(BaseTrackerEntity):
    """An issue one launch of an autoaction processed, and how it went."""

    id: int | None = NoneExcludedField
    issueReference: IssueReference | None = NoneExcludedField
    status: Any = NoneExcludedField


class QueueMacro(BaseTrackerEntity):
    """A queue macro: a comment and field changes applied to an issue on demand."""

    id: int
    name: str | None = NoneExcludedField
    queue: QueueReference | None = NoneExcludedField
    body: str | None = NoneExcludedField
    issueUpdate: list[dict[str, Any]] | None = NoneExcludedField


class QueueForm(BaseTrackerEntity):
    """An issue-intake form of a queue (a Yandex Forms form creating issues)."""

    # No form was available to read on the live API, so whatever else Tracker
    # sends is passed through as it comes.
    model_config = ConfigDict(extra="allow")

    id: int | str | None = NoneExcludedField
    name: str | None = NoneExcludedField
    description: str | None = NoneExcludedField
    path: str | None = NoneExcludedField


class QueueForms(BaseTrackerEntity):
    """The forms of a queue, in their configured order."""

    queue: QueueReference | None = NoneExcludedField
    forms: list[QueueForm] = Field(default_factory=list)
    showDefaultCreationForm: bool | None = NoneExcludedField


class QueueIssueTypeConfigInput(BaseTrackerEntity):
    """One issue type of a new queue, with the workflow and resolutions it uses."""

    issue_type: str = Field(description="Issue type key, e.g. 'task' or 'bug'.")
    workflow: str = Field(
        description="Workflow id, e.g. 'developmentPresetWorkflow' - "
        "`workflows_get_all` lists them."
    )
    resolutions: list[str] = Field(
        description="Resolution keys or ids an issue of this type can close with, "
        "e.g. ['fixed', 'wontFix'].",
    )
