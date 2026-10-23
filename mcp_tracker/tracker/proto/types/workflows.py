"""Workflows, their transitions and transition screens.

Two shapes, because the API reads and writes them differently (verified on the
live API 2026-10-23, see AGENTS.md, *Workflows*): a read gives names as strings
in the language of `Accept-Language` and statuses, screens and resolutions as
reference objects, while a write wants every name as `{"ru": ..., "en": ...}`,
statuses by key and a screen as its list of fields. `Workflow*` is the read
shape, `*Draft` the write shape; `TrackerClient.workflow_get_draft` converts
the first into the second.
"""

import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from mcp_tracker.tracker.proto.types.base import (
    BaseTrackerEntity,
    NoneExcludedField,
    none_excluder,
)
from mcp_tracker.tracker.proto.types.refs import (
    BaseReference,
    QueueReference,
    StatusReference,
    UserReference,
)


class ScreenReference(BaseReference):
    display: str | None = None


class WorkflowAction(BaseTrackerEntity):
    """A transition from a status, as the API returns it."""

    id: str
    name: str | None = NoneExcludedField
    description: str | None = NoneExcludedField
    target: StatusReference | None = NoneExcludedField
    screen: ScreenReference | None = NoneExcludedField
    post_functions: list[dict[str, Any]] | None = Field(
        None,
        validation_alias=AliasChoices("postFunctions", "post_functions"),
        serialization_alias="postFunctions",
        exclude_if=none_excluder,
    )
    conditions: list[dict[str, Any]] | None = NoneExcludedField
    action_coords: dict[str, Any] | None = Field(
        None,
        validation_alias=AliasChoices("actionCoords", "action_coords"),
        serialization_alias="actionCoords",
        exclude_if=none_excluder,
    )


class WorkflowStep(BaseTrackerEntity):
    """A status of a workflow with the transitions out of it."""

    status: StatusReference
    actions: list[WorkflowAction] | None = NoneExcludedField
    status_type: str | None = Field(
        None,
        validation_alias=AliasChoices("statusType", "status_type"),
        serialization_alias="statusType",
        exclude_if=none_excluder,
    )
    meta_action: WorkflowAction | None = Field(
        None,
        validation_alias=AliasChoices("metaAction", "meta_action"),
        serialization_alias="metaAction",
        exclude_if=none_excluder,
    )
    step_coords: dict[str, Any] | None = Field(
        None,
        validation_alias=AliasChoices("stepCoords", "step_coords"),
        serialization_alias="stepCoords",
        exclude_if=none_excluder,
    )


class Workflow(BaseTrackerEntity):
    id: str
    name: str
    version: int
    steps: list[WorkflowStep] = Field(default_factory=list)
    initial_action: WorkflowAction | None = Field(
        None,
        validation_alias=AliasChoices("initialAction", "initial_action"),
        serialization_alias="initialAction",
        exclude_if=none_excluder,
    )
    queue: QueueReference | None = NoneExcludedField
    type: str | None = NoneExcludedField
    created: datetime.datetime | None = NoneExcludedField
    updated: datetime.datetime | None = NoneExcludedField
    created_by: UserReference | None = Field(
        None,
        validation_alias=AliasChoices("createdBy", "created_by"),
        serialization_alias="createdBy",
        exclude_if=none_excluder,
    )
    updated_by: UserReference | None = Field(
        None,
        validation_alias=AliasChoices("updatedBy", "updated_by"),
        serialization_alias="updatedBy",
        exclude_if=none_excluder,
    )
    deleted: bool | None = NoneExcludedField


class ScreenElementField(BaseReference):
    display: str | None = None


class ScreenElement(BaseTrackerEntity):
    field: ScreenElementField
    required: bool = False


class Screen(BaseTrackerEntity):
    """A transition screen: the fields asked for when a transition runs."""

    id: int
    version: int | None = NoneExcludedField
    type: str | None = NoneExcludedField
    title: str | None = NoneExcludedField
    elements: list[ScreenElement] = Field(default_factory=list)


class _Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LocalizedText(_Draft):
    """A name or description in both languages - Tracker refuses a write that
    gives one of them only (422)."""

    ru: str
    en: str


class ScreenElementDraft(_Draft):
    field: str = Field(description="Field id or key, e.g. 'assignee', 'resolution'.")
    required: bool = False


class ScreenDraft(_Draft):
    """A transition screen as a write sends it. Tracker takes no reference to
    an existing screen: each write that carries one creates a new screen."""

    title: LocalizedText | None = Field(None, exclude_if=none_excluder)
    elements: list[ScreenElementDraft] = Field(min_length=1)


class WorkflowActionDraft(_Draft):
    """A transition as a write sends it. A write replaces the whole transition:
    whatever is left out (screen, functions, description) is removed."""

    id: str | None = Field(None, exclude_if=none_excluder)
    name: LocalizedText
    target: str = Field(description="Key of the status the transition leads to.")
    description: LocalizedText | None = Field(None, exclude_if=none_excluder)
    screen: ScreenDraft | None = Field(None, exclude_if=none_excluder)
    post_functions: list[dict[str, Any]] | None = Field(
        None,
        validation_alias=AliasChoices("postFunctions", "post_functions"),
        serialization_alias="postFunctions",
        exclude_if=none_excluder,
    )
    conditions: list[dict[str, Any]] | None = Field(None, exclude_if=none_excluder)
    action_coords: dict[str, Any] | None = Field(
        None,
        validation_alias=AliasChoices("actionCoords", "action_coords"),
        serialization_alias="actionCoords",
        exclude_if=none_excluder,
    )


class WorkflowStepDraft(_Draft):
    status: str = Field(description="Status key.")
    status_type: str | None = Field(
        None,
        validation_alias=AliasChoices("statusType", "status_type"),
        serialization_alias="statusType",
        exclude_if=none_excluder,
    )
    meta_action: WorkflowActionDraft | None = Field(
        None,
        validation_alias=AliasChoices("metaAction", "meta_action"),
        serialization_alias="metaAction",
        exclude_if=none_excluder,
    )
    step_coords: dict[str, Any] | None = Field(
        None,
        validation_alias=AliasChoices("stepCoords", "step_coords"),
        serialization_alias="stepCoords",
        exclude_if=none_excluder,
    )
    actions: list[WorkflowActionDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_action_ids(self) -> "WorkflowStepDraft":
        ids = [a.id for a in self.actions if a.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError(f"step '{self.status}' has duplicate transition ids")
        return self


class IssueTypeResolutionsDraft(_Draft):
    """The resolutions an issue type may be closed with under a workflow."""

    issue_type: str = Field(
        validation_alias=AliasChoices("issueType", "issue_type"),
        serialization_alias="issueType",
        description="Issue type key, e.g. 'task'.",
    )
    resolutions: list[str] = Field(
        min_length=1, description="Resolution keys, e.g. ['fixed', 'wontFix']."
    )


class WorkflowDraft(_Draft):
    """A whole workflow in the write shape, with the `version` it was read at."""

    id: str
    version: int
    name: str
    queue: str | None = None
    initial_action: WorkflowActionDraft = Field(
        validation_alias=AliasChoices("initialAction", "initial_action"),
        serialization_alias="initialAction",
    )
    steps: list[WorkflowStepDraft]

    def step(self, status: str) -> WorkflowStepDraft | None:
        return next((s for s in self.steps if s.status == status), None)
