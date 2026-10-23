"""Workflow write tools: transitions, their screens and statuses.

Registered on a writable server with TRACKER_WORKFLOWS_WRITE_ENABLED. A
workflow is often shared by several queues and a change applies to all of
them; under TRACKER_LIMIT_QUEUES / TRACKER_READ_ONLY_QUEUES a shared workflow
(bound to no queue) is not written at all - see `check_workflow_access`.

How the API takes these writes (verified on the live API 2026-10-23, see
AGENTS.md, *Workflows*): a transition is written whole, so changing one means
reading it, merging the caller's changes and sending all of it. There is no
call that removes a transition or adds or removes a status, so those rewrite
every step of the workflow (`workflow_update(steps=...)`), which re-creates
every transition screen under a new id. The workflow is read again after such
a rewrite and compared with what was meant to be written; a difference is
reported in the result rather than raised, since the write has happened.

The draft manipulation below is plain functions over the `*Draft` models,
which never change the draft they are given.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Any, Literal, Protocol, TypeVar

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import WorkflowID
from mcp_tracker.mcp.tools._access import check_queue_access, check_workflow_access
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import WorkflowVersionConflict
from mcp_tracker.tracker.proto.types.base import none_excluder
from mcp_tracker.tracker.proto.types.workflows import (
    IssueTypeResolutionsDraft,
    LocalizedText,
    ScreenDraft,
    ScreenElementDraft,
    Workflow,
    WorkflowActionDraft,
    WorkflowDraft,
    WorkflowStep,
    WorkflowStepDraft,
)
from mcp_tracker.tracker.proto.workflows import WorkflowsProtocol

# Waits before re-reading the workflow and writing again, when Tracker refused
# a write made with a version read here (412) - a change that landed in
# between, or the passing refusal Tracker also gives sprints.
WORKFLOW_CONFLICT_WAITS = (2.0, 5.0)

# What a workflow made by `workflow_create` starts with - the id and name most
# of the organization's own workflows use for their initial action.
INITIAL_ACTION_ID = "create"
INITIAL_ACTION_NAME = LocalizedText(ru="Создать", en="Create")

StatusType = Literal["new", "inProgress", "paused", "done", "cancelled"]

# Parameters shared by the tools and the transition input models.
StatusParam = Annotated[
    str,
    Field(
        description="Key of the status the transition leaves, e.g. 'open' - a "
        "step's `status.key` in workflow_get."
    ),
]
ActionIDParam = Annotated[
    str,
    Field(
        description="Transition id, e.g. 'start' - an action's `id` in workflow_get."
    ),
]
NewActionIDParam = Annotated[
    str | None,
    Field(
        description="Id of the new transition, unique within the status it leaves. "
        "Defaults to the target status key, numbered if that is taken."
    ),
]
NameParam = Annotated[str, Field(description="Transition name in Russian.")]
NameOptionalParam = Annotated[
    str | None,
    Field(description="Transition name in Russian. Omit to keep it."),
]
NameEnParam = Annotated[
    str | None,
    Field(
        description="Transition name in English. Defaults to `name` when that is "
        "passed."
    ),
]
TargetParam = Annotated[
    str,
    Field(
        description="Key of the status the transition leads to; it has to be a "
        "status of this workflow."
    ),
]
TargetOptionalParam = Annotated[
    str | None,
    Field(
        description="Key of the status the transition leads to; it has to be a "
        "status of this workflow. Omit to keep it."
    ),
]
DescriptionParam = Annotated[
    str | None, Field(description="Transition description in Russian.")
]
DescriptionUpdateParam = Annotated[
    str | None,
    Field(description="Transition description in Russian. Omit to keep it."),
]
DescriptionEnParam = Annotated[
    str | None,
    Field(
        description="Transition description in English. Defaults to `description` "
        "when that is passed."
    ),
]
ScreenTitleParam = Annotated[
    str | None,
    Field(description="Title of the transition screen in Russian."),
]
ScreenTitleEnParam = Annotated[
    str | None,
    Field(
        description="Title of the transition screen in English. Defaults to "
        "`screen_title`."
    ),
]
PostFunctionsParam = Annotated[
    list[dict[str, Any]] | None,
    Field(
        description="Functions run after the transition, in Tracker's write shape "
        "with references by key, e.g. [{'type': 'SetResolutionFunction', "
        "'resolution': 'fixed'}]."
    ),
]
PostFunctionsUpdateParam = Annotated[
    list[dict[str, Any]] | None,
    Field(
        description="Functions run after the transition, in Tracker's write shape "
        "with references by key, e.g. [{'type': 'SetResolutionFunction', "
        "'resolution': 'fixed'}]. Replaces the current ones; [] removes them, "
        "omit to keep them."
    ),
]
_CONDITIONS_TEXT = (
    "Conditions under which the transition is offered, all of which must hold, "
    "with references by key or id: [{'type': 'UserInFieldCondition', 'field': "
    "'assignee'}], UserIsQueueLeadCondition, UserInListCondition {users: [uid]}, "
    "UserInGroupCondition {group: id}, HasLinksCondition {queues: [key]} (issue "
    "linked to one in those queues), ToPreviousStatusOnlyCondition, and "
    "OrCondition / AndCondition {conditions: [...]} to nest."
)
ConditionsParam = Annotated[
    list[dict[str, Any]] | None, Field(description=_CONDITIONS_TEXT)
]
ConditionsUpdateParam = Annotated[
    list[dict[str, Any]] | None,
    Field(
        description=_CONDITIONS_TEXT
        + " Replaces the current ones; [] removes them, omit to keep them."
    ),
]
StatusTypeParam = Annotated[
    StatusType | None,
    Field(description="Category of the status. Omit to let Tracker decide."),
]
WorkflowVersionParam = Annotated[
    int | None,
    Field(
        description="The workflow's `version` for optimistic locking. Omit it to "
        "act on the current version, which is read first."
    ),
]


class ScreenFieldInput(BaseModel):
    """A field a transition screen asks for."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(
        description="Field key, e.g. 'resolution' or 'assignee'; a queue's local "
        "field by its id as screen_get shows it."
    )
    required: bool = Field(
        False, description="Whether the transition needs the field filled."
    )


ScreenFieldsParam = Annotated[
    list[ScreenFieldInput] | None,
    Field(
        description="Fields the transition asks for, in order - its transition "
        "screen ('экран перехода')."
    ),
]
ScreenFieldsUpdateParam = Annotated[
    list[ScreenFieldInput] | None,
    Field(
        description="Fields the transition asks for, in order - its transition "
        "screen ('экран перехода'). Replaces the current fields; omit to keep them."
    ),
]


class _TransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: NewActionIDParam = None
    name: NameParam
    name_en: NameEnParam = None
    description: DescriptionParam = None
    description_en: DescriptionEnParam = None
    screen_fields: ScreenFieldsParam = None
    screen_title: ScreenTitleParam = None
    screen_title_en: ScreenTitleEnParam = None
    post_functions: PostFunctionsParam = None
    conditions: ConditionsParam = None

    def to_draft(self, target: str, taken: Sequence[str]) -> WorkflowActionDraft:
        return build_action(
            action_id=self.action_id,
            name=self.name,
            name_en=self.name_en,
            target=target,
            description=self.description,
            description_en=self.description_en,
            screen_fields=self.screen_fields,
            screen_title=self.screen_title,
            screen_title_en=self.screen_title_en,
            post_functions=self.post_functions,
            conditions=self.conditions,
            taken=taken,
        )


class WorkflowTransitionInput(_TransitionInput):
    """A transition out of a status."""

    target: TargetParam


class WorkflowIncomingTransitionInput(_TransitionInput):
    """A transition into a new status from an existing one."""

    from_status: str = Field(
        description="Key of the existing status the transition leaves."
    )


class WorkflowStepInput(BaseModel):
    """A status of a new workflow with the transitions out of it."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="Status key, e.g. 'open'; get_statuses lists them.")
    status_type: StatusTypeParam = None
    actions: list[WorkflowTransitionInput] = Field(
        default_factory=list, description="Transitions out of the status."
    )


class WorkflowChange(BaseModel):
    """What a workflow write tool returns: the step it changed, as
    workflow_get shows it, rather than the whole workflow."""

    id: str = Field(description="Workflow id.")
    version: int = Field(description="Workflow version after the change.")
    step: WorkflowStep | None = Field(
        None,
        exclude_if=none_excluder,
        description="The changed status with its transitions.",
    )
    removed_transitions: list[str] | None = Field(
        None,
        exclude_if=none_excluder,
        description="Transitions removed with the status, as 'status/transition'.",
    )
    differences: list[str] | None = Field(
        None,
        exclude_if=none_excluder,
        description="Where the workflow, read again after the rewrite, differs from "
        "what was written; empty when it matches.",
    )


# --- Pure draft manipulation -------------------------------------------------


def localized(text: str, text_en: str | None) -> LocalizedText:
    return LocalizedText(ru=text, en=text if text_en is None else text_en)


def _localized_optional(text: str | None, text_en: str | None) -> LocalizedText | None:
    if text is None and text_en is None:
        return None
    return LocalizedText(
        ru=text if text is not None else text_en or "",
        en=text_en if text_en is not None else text or "",
    )


def build_screen(
    fields: Sequence[ScreenFieldInput] | None,
    title: str | None,
    title_en: str | None,
) -> ScreenDraft | None:
    if fields is None:
        if title is not None or title_en is not None:
            raise TrackerError(
                "A screen title needs `screen_fields`: a transition screen is the "
                "list of fields it asks for."
            )
        return None
    return ScreenDraft(
        title=_localized_optional(title, title_en), elements=_screen_elements(fields)
    )


def _screen_elements(fields: Sequence[ScreenFieldInput]) -> list[ScreenElementDraft]:
    if not fields:
        raise TrackerError(
            "`screen_fields` is empty: give at least one field, or leave it out for "
            "a transition without a screen."
        )
    return [ScreenElementDraft(field=f.field, required=f.required) for f in fields]


def new_action_id(target: str, taken: Sequence[str]) -> str:
    """The target status key, numbered when a transition of the step has it."""
    candidate, n = target, 1
    while candidate in taken:
        n += 1
        candidate = f"{target}{n}"
    return candidate


def build_action(
    *,
    action_id: str | None,
    name: str,
    name_en: str | None,
    target: str,
    description: str | None = None,
    description_en: str | None = None,
    screen_fields: Sequence[ScreenFieldInput] | None = None,
    screen_title: str | None = None,
    screen_title_en: str | None = None,
    post_functions: list[dict[str, Any]] | None = None,
    conditions: list[dict[str, Any]] | None = None,
    taken: Sequence[str] = (),
) -> WorkflowActionDraft:
    """A new transition; `taken` are the ids already used in its step."""
    if action_id is not None and action_id in taken:
        raise TrackerError(
            f"Transition id '{action_id}' is taken in that status; its transitions "
            f"are: {', '.join(taken)}."
        )
    return WorkflowActionDraft(
        id=action_id if action_id is not None else new_action_id(target, taken),
        name=localized(name, name_en),
        target=target,
        description=_localized_optional(description, description_en),
        screen=build_screen(screen_fields, screen_title, screen_title_en),
        post_functions=post_functions,
        conditions=conditions or None,
    )


def merge_action(
    current: WorkflowActionDraft,
    *,
    name: str | None = None,
    name_en: str | None = None,
    target: str | None = None,
    description: str | None = None,
    description_en: str | None = None,
    screen_fields: Sequence[ScreenFieldInput] | None = None,
    screen_title: str | None = None,
    screen_title_en: str | None = None,
    remove_screen: bool = False,
    post_functions: list[dict[str, Any]] | None = None,
    conditions: list[dict[str, Any]] | None = None,
) -> WorkflowActionDraft:
    """`current` with the given changes; what is not given is kept as it is.

    The API replaces a transition whole, so whatever this leaves out of the
    result - its screen, post-functions, conditions, coordinates - is lost.
    """
    screen_changed = (
        screen_fields is not None
        or screen_title is not None
        or screen_title_en is not None
    )
    if remove_screen and screen_changed:
        raise TrackerError(
            "`remove_screen` cannot be passed with `screen_fields` / `screen_title`: "
            "pass the fields to set a new screen, or `remove_screen` to drop it."
        )

    update: dict[str, Any] = {}
    if name is not None or name_en is not None:
        update["name"] = LocalizedText(
            ru=name if name is not None else current.name.ru,
            en=name_en if name_en is not None else name or current.name.en,
        )
    if target is not None:
        update["target"] = target
    if description is not None or description_en is not None:
        old = current.description
        update["description"] = LocalizedText(
            ru=description
            if description is not None
            else (old.ru if old else description_en or ""),
            en=description_en
            if description_en is not None
            else (description if description is not None else old.en if old else ""),
        )
    if remove_screen:
        update["screen"] = None
    elif screen_changed:
        old_screen = current.screen
        if screen_fields is None and old_screen is None:
            raise TrackerError(
                f"Transition '{current.id}' has no screen to title: pass "
                f"`screen_fields` to give it one."
            )
        title = old_screen.title if old_screen else None
        if screen_title is not None or screen_title_en is not None:
            title = LocalizedText(
                ru=screen_title
                if screen_title is not None
                else (title.ru if title else screen_title_en or ""),
                en=screen_title_en
                if screen_title_en is not None
                else (
                    screen_title
                    if screen_title is not None
                    else title.en
                    if title
                    else ""
                ),
            )
        if screen_fields is not None:
            update["screen"] = ScreenDraft(
                title=title, elements=_screen_elements(screen_fields)
            )
        elif old_screen is not None:
            update["screen"] = old_screen.model_copy(update={"title": title})
    if post_functions is not None:
        update["post_functions"] = post_functions
    if conditions is not None:
        update["conditions"] = conditions or None

    merged = current.model_copy(update=update)
    if merged == current:
        raise TrackerError(
            f"Nothing to change in transition '{current.id}': the arguments are "
            f"missing or match its current values."
        )
    return merged


def require_status(
    statuses: Sequence[str], status: str, *, what: str = "Status"
) -> None:
    if status not in statuses:
        raise TrackerError(
            f"{what} '{status}' is not a status of this workflow; its statuses are: "
            f"{', '.join(statuses)}."
        )


def require_step(steps: Sequence[WorkflowStepDraft], status: str) -> WorkflowStepDraft:
    require_status([s.status for s in steps], status)
    return next(s for s in steps if s.status == status)


def require_action(step: WorkflowStepDraft, action_id: str) -> WorkflowActionDraft:
    action = next((a for a in step.actions if a.id == action_id), None)
    if action is None:
        ids = ", ".join(a.id or "?" for a in step.actions) or "none"
        raise TrackerError(
            f"Status '{step.status}' has no transition '{action_id}'; its transitions "
            f"are: {ids}."
        )
    return action


def replace_action(
    steps: Sequence[WorkflowStepDraft], status: str, action: WorkflowActionDraft
) -> list[WorkflowStepDraft]:
    """`steps` with the transition of `action.id` in `status` replaced."""
    return [
        s.model_copy(
            update={"actions": [action if a.id == action.id else a for a in s.actions]}
        )
        if s.status == status
        else s
        for s in steps
    ]


def remove_action(
    steps: Sequence[WorkflowStepDraft], status: str, action_id: str
) -> list[WorkflowStepDraft]:
    """`steps` without the transition `action_id` of `status`."""
    require_action(require_step(steps, status), action_id)
    return [
        s.model_copy(update={"actions": [a for a in s.actions if a.id != action_id]})
        if s.status == status
        else s
        for s in steps
    ]


def remove_status(
    draft: WorkflowDraft, status: str
) -> tuple[list[WorkflowStepDraft], list[str]]:
    """The steps without `status` and without every transition into it, and
    those transitions as 'status/transition'."""
    require_step(draft.steps, status)
    if draft.initial_action.target == status:
        raise TrackerError(
            f"Status '{status}' is the initial status of the workflow - every new "
            f"issue starts in it - and cannot be removed."
        )
    removed: list[str] = []
    steps: list[WorkflowStepDraft] = []
    for step in draft.steps:
        if step.status == status:
            continue
        kept = []
        for action in step.actions:
            if action.target == status:
                removed.append(f"{step.status}/{action.id}")
            else:
                kept.append(action)
        update: dict[str, Any] = {"actions": kept}
        if step.meta_action is not None and step.meta_action.target == status:
            removed.append(f"{step.status}/{step.meta_action.id}")
            update["meta_action"] = None
        steps.append(step.model_copy(update=update))
    return steps, removed


def add_status(
    steps: Sequence[WorkflowStepDraft],
    new_step: WorkflowStepDraft,
    incoming: Sequence[tuple[str, WorkflowActionDraft]],
) -> list[WorkflowStepDraft]:
    """`steps` with `new_step` appended and each (from_status, transition) of
    `incoming` added to its step."""
    if any(s.status == new_step.status for s in steps):
        raise TrackerError(
            f"Status '{new_step.status}' is already in this workflow; "
            f"workflow_add_action adds a transition into it."
        )
    added: dict[str, list[WorkflowActionDraft]] = {}
    for from_status, action in incoming:
        added.setdefault(from_status, []).append(action)
    return [
        s.model_copy(update={"actions": [*s.actions, *added[s.status]]})
        if s.status in added
        else s
        for s in steps
    ] + [new_step]


def _empty(value: Any) -> Any:
    return value if value else None


def _diff_action(
    where: str,
    expected: WorkflowActionDraft,
    actual: WorkflowActionDraft,
    *,
    known: bool,
) -> list[str]:
    """Differences of one transition. One the workflow had before (`known`)
    is compared field by field; a new one only by what Tracker keeps as given:
    its name and target, and whether it has a screen - Tracker names a screen
    field by its id, which a caller may have given by key."""
    pairs: list[tuple[str, Any, Any]] = [
        ("name", expected.name, actual.name),
        ("target", expected.target, actual.target),
    ]
    if known:
        pairs += [
            ("description", expected.description, actual.description),
            ("screen", expected.screen, actual.screen),
            (
                "postFunctions",
                _empty(expected.post_functions),
                _empty(actual.post_functions),
            ),
            ("conditions", _empty(expected.conditions), _empty(actual.conditions)),
        ]
        if expected.action_coords is not None:
            pairs.append(("actionCoords", expected.action_coords, actual.action_coords))
    else:
        pairs.append(("screen", expected.screen is not None, actual.screen is not None))
    return [
        f"{where}: {field} is {_show(got)}, expected {_show(want)}"
        for field, want, got in pairs
        if want != got
    ]


def _show(value: Any) -> str:
    if isinstance(value, BaseModel):
        return repr(value.model_dump(by_alias=True, exclude_none=True))
    return repr(value)


def diff_steps(
    before: Sequence[WorkflowStepDraft],
    expected: Sequence[WorkflowStepDraft],
    actual: Sequence[WorkflowStepDraft],
) -> list[str]:
    """Where `actual` (read after a write) differs from `expected` (written).

    Screens are compared by title and fields, not by id: every rewrite makes
    new ones. `before` tells which statuses and transitions the workflow
    already had; Tracker fills in coordinates and categories for new ones,
    so those are compared only where `expected` gives them.
    """
    known_steps = {s.status for s in before}
    known_actions = {(s.status, a.id) for s in before for a in s.actions}
    remaining = {s.status: s for s in actual}
    differences: list[str] = []
    for step in expected:
        got = remaining.pop(step.status, None)
        if got is None:
            differences.append(f"status '{step.status}' is missing")
            continue
        if step.status_type is not None and step.status_type != got.status_type:
            differences.append(
                f"status '{step.status}': statusType is {got.status_type!r}, "
                f"expected {step.status_type!r}"
            )
        if step.step_coords is not None and step.step_coords != got.step_coords:
            differences.append(
                f"status '{step.status}': stepCoords is {got.step_coords!r}, "
                f"expected {step.step_coords!r}"
            )
        if step.meta_action is not None:
            if got.meta_action is None:
                differences.append(f"status '{step.status}': metaAction is missing")
            else:
                differences += _diff_action(
                    f"{step.status} metaAction",
                    step.meta_action,
                    got.meta_action,
                    known=step.status in known_steps,
                )
        elif got.meta_action is not None and step.status in known_steps:
            differences.append(f"status '{step.status}': unexpected metaAction")

        got_actions = {a.id: a for a in got.actions}
        for action in step.actions:
            where = f"{step.status}/{action.id}"
            found = got_actions.pop(action.id, None)
            if found is None:
                differences.append(f"transition '{where}' is missing")
                continue
            differences += _diff_action(
                where,
                action,
                found,
                known=(step.status, action.id) in known_actions,
            )
        differences += [
            f"transition '{step.status}/{action_id}' was not expected"
            for action_id in got_actions
        ]
    differences += [f"status '{status}' was not expected" for status in remaining]
    return differences


def diff_drafts(
    before: WorkflowDraft, expected: Sequence[WorkflowStepDraft], actual: WorkflowDraft
) -> list[str]:
    """`diff_steps`, plus the initial action, which a rewrite of the steps
    does not send and so must not change."""
    differences = diff_steps(before.steps, expected, actual.steps)
    differences += _diff_action(
        "initial action", before.initial_action, actual.initial_action, known=True
    )
    return differences


# --- Tools -------------------------------------------------------------------


def update_step(
    steps: Sequence[WorkflowStepDraft],
    status: str,
    *,
    status_type: str | None = None,
    on_enter_functions: list[dict[str, Any]] | None = None,
    remove_on_enter: bool = False,
) -> list[WorkflowStepDraft]:
    """`steps` with the type and the on-enter functions of `status` changed.

    The on-enter functions are the step's `metaAction`: an action Tracker runs
    by itself whenever an issue enters the status, whose target is the status
    itself. A new one is named after the status key, as the preset workflows
    name theirs after the status.
    """
    if remove_on_enter and on_enter_functions is not None:
        raise TrackerError(
            "Pass either `on_enter_functions` or `remove_on_enter`, not both."
        )
    if status_type is None and on_enter_functions is None and not remove_on_enter:
        raise TrackerError(
            "Nothing to change: pass `status_type`, `on_enter_functions` or "
            "`remove_on_enter`."
        )
    step = require_step(steps, status)
    update: dict[str, Any] = {}
    if status_type is not None:
        update["status_type"] = status_type
    if remove_on_enter:
        if step.meta_action is None:
            raise TrackerError(f"Status '{status}' has no on-enter functions.")
        update["meta_action"] = None
    elif on_enter_functions is not None:
        meta = step.meta_action or WorkflowActionDraft(
            id=status, name=LocalizedText(ru=status, en=status), target=status
        )
        update["meta_action"] = meta.model_copy(
            update={"post_functions": on_enter_functions or None}
        )
    return [s.model_copy(update=update) if s.status == status else s for s in steps]


class _Versioned(Protocol):
    @property
    def version(self) -> int: ...


Current = TypeVar("Current", bound=_Versioned)
Written = TypeVar("Written")


async def _write_current(
    read: Callable[[], Awaitable[Current]],
    version: int | None,
    write: Callable[[Current, int], Awaitable[Written]],
) -> Written:
    """Read the workflow, then `write` with the caller's version or the one read.

    A conflict on a version read here means the workflow changed in between
    (or Tracker's passing refusal), so the read and the write are repeated; a
    version the caller gave is theirs to judge, and its conflict is raised.
    """

    async def attempt() -> Written:
        current = await read()
        return await write(current, current.version if version is None else version)

    if version is not None:
        return await attempt()
    for wait in WORKFLOW_CONFLICT_WAITS:
        try:
            return await attempt()
        except WorkflowVersionConflict:
            await asyncio.sleep(wait)
    return await attempt()


def _step_of(workflow: Workflow, status: str) -> WorkflowStep | None:
    return next((s for s in workflow.steps if s.status.key == status), None)


def register_workflow_write_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register workflow write tools (writable server and
    tracker_workflows_write_enabled)."""

    def draft_reader(
        workflows: WorkflowsProtocol, workflow_id: str, ctx: Context[AppContext]
    ) -> Callable[[], Awaitable[WorkflowDraft]]:
        async def read() -> WorkflowDraft:
            draft = await workflows.workflow_get_draft(
                workflow_id, auth=get_yandex_auth(ctx)
            )
            check_workflow_access(settings, workflow_id, draft.queue, write=True)
            return draft

        return read

    def workflow_reader(
        workflows: WorkflowsProtocol, workflow_id: str, ctx: Context[AppContext]
    ) -> Callable[[], Awaitable[Workflow]]:
        async def read() -> Workflow:
            workflow = await workflows.workflow_get(
                workflow_id, auth=get_yandex_auth(ctx)
            )
            check_workflow_access(
                settings,
                workflow_id,
                workflow.queue.key if workflow.queue else None,
                write=True,
            )
            return workflow

        return read

    async def rewrite_steps(
        ctx: Context[AppContext],
        workflow_id: str,
        version: int | None,
        change: Callable[[WorkflowDraft], tuple[list[WorkflowStepDraft], list[str]]],
        status: str,
    ) -> WorkflowChange:
        """Write the steps `change` makes of the draft, read the workflow
        again and report how it differs from them."""
        workflows = ctx.request_context.lifespan_context.workflows
        auth = get_yandex_auth(ctx)
        written: dict[str, Any] = {}

        async def write(draft: WorkflowDraft, v: int) -> Workflow:
            steps, removed = change(draft)
            written.update(before=draft, steps=steps, removed=removed)
            return await workflows.workflow_update(
                workflow_id, version=v, steps=steps, auth=auth
            )

        workflow = await _write_current(
            draft_reader(workflows, workflow_id, ctx), version, write
        )
        try:
            after = await workflows.workflow_get_draft(workflow_id, auth=auth)
            differences = diff_drafts(written["before"], written["steps"], after)
        except ToolError as e:
            differences = [f"the workflow could not be read again to check it: {e}"]
        return WorkflowChange(
            id=workflow.id,
            version=workflow.version,
            step=_step_of(workflow, status),
            removed_transitions=written["removed"] or None,
            differences=differences,
        )

    @mcp.tool(
        title="Create Workflow",
        description="Create a Yandex Tracker workflow ('рабочий процесс') from its "
        "statuses and the transitions between them, and return it. Every status "
        "has to be reachable from `initial_status`.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def workflow_create(
        ctx: Context[AppContext],
        name: Annotated[str, Field(description="Workflow name.")],
        steps: Annotated[
            list[WorkflowStepInput],
            Field(min_length=1, description="The statuses with their transitions."),
        ],
        initial_status: Annotated[
            str,
            Field(
                description="Key of the status a new issue starts in; one of `steps`."
            ),
        ],
        queue: Annotated[
            str | None,
            Field(
                description="Key of the queue the workflow belongs to. Omit for a shared one."
            ),
        ] = None,
    ) -> Workflow:
        if queue is not None:
            check_queue_access(settings, queue, write=True)
        statuses = [s.status for s in steps]
        if len(set(statuses)) != len(statuses):
            raise TrackerError("`steps` name a status more than once.")
        require_status(statuses, initial_status, what="Initial status")
        drafts = []
        for step in steps:
            actions: list[WorkflowActionDraft] = []
            for transition in step.actions:
                require_status(statuses, transition.target, what="Target status")
                actions.append(
                    transition.to_draft(
                        transition.target, [a.id or "" for a in actions]
                    )
                )
            drafts.append(
                WorkflowStepDraft(
                    status=step.status, status_type=step.status_type, actions=actions
                )
            )
        return await ctx.request_context.lifespan_context.workflows.workflow_create(
            name=name,
            initial_action=WorkflowActionDraft(
                id=INITIAL_ACTION_ID, name=INITIAL_ACTION_NAME, target=initial_status
            ),
            steps=drafts,
            queue=queue,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Delete Workflow",
        description="Delete a Yandex Tracker workflow ('рабочий процесс') by id. "
        "Cannot be undone.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def workflow_delete(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
    ) -> None:
        workflows = ctx.request_context.lifespan_context.workflows
        await workflow_reader(workflows, workflow_id, ctx)()
        await workflows.workflow_delete(workflow_id, auth=get_yandex_auth(ctx))

    @mcp.tool(
        title="Add Workflow Transition",
        description="Add a transition ('переход') out of a status of a Yandex "
        "Tracker workflow, optionally with a screen of fields to fill and "
        "post-functions; returns that status with its transitions. Applies to every "
        "queue on the workflow.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def workflow_add_action(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
        status: StatusParam,
        name: NameParam,
        target: TargetParam,
        action_id: NewActionIDParam = None,
        name_en: NameEnParam = None,
        description: DescriptionParam = None,
        description_en: DescriptionEnParam = None,
        screen_fields: ScreenFieldsParam = None,
        screen_title: ScreenTitleParam = None,
        screen_title_en: ScreenTitleEnParam = None,
        post_functions: PostFunctionsParam = None,
        conditions: ConditionsParam = None,
        version: WorkflowVersionParam = None,
    ) -> WorkflowChange:
        workflows = ctx.request_context.lifespan_context.workflows
        auth = get_yandex_auth(ctx)
        # Checked before any request: a screen title without fields, say.
        build_screen(screen_fields, screen_title, screen_title_en)

        async def write(workflow: Workflow, v: int) -> Workflow:
            statuses = [s.status.key or "" for s in workflow.steps]
            require_status(statuses, status)
            require_status(statuses, target, what="Target status")
            step = _step_of(workflow, status)
            taken = [a.id for a in (step.actions if step else None) or []]
            action = build_action(
                action_id=action_id,
                name=name,
                name_en=name_en,
                target=target,
                description=description,
                description_en=description_en,
                screen_fields=screen_fields,
                screen_title=screen_title,
                screen_title_en=screen_title_en,
                post_functions=post_functions,
                conditions=conditions,
                taken=taken,
            )
            return await workflows.workflow_add_action(
                workflow_id, status, version=v, action=action, auth=auth
            )

        workflow = await _write_current(
            workflow_reader(workflows, workflow_id, ctx), version, write
        )
        return WorkflowChange(
            id=workflow.id, version=workflow.version, step=_step_of(workflow, status)
        )

    @mcp.tool(
        title="Update Workflow Transition",
        description="Change a transition ('переход') of a Yandex Tracker workflow: "
        "its name, target, description, screen, post-functions or conditions. Only "
        "the "
        "arguments passed change; returns that status with its transitions. A "
        "transition with a screen gets a new copy of it under a new id.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def workflow_update_action(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
        status: StatusParam,
        action_id: ActionIDParam,
        name: NameOptionalParam = None,
        name_en: NameEnParam = None,
        target: TargetOptionalParam = None,
        description: DescriptionUpdateParam = None,
        description_en: DescriptionEnParam = None,
        screen_fields: ScreenFieldsUpdateParam = None,
        screen_title: ScreenTitleParam = None,
        screen_title_en: ScreenTitleEnParam = None,
        remove_screen: Annotated[
            bool, Field(description="Remove the transition's screen.")
        ] = False,
        post_functions: PostFunctionsUpdateParam = None,
        conditions: ConditionsUpdateParam = None,
        version: WorkflowVersionParam = None,
    ) -> WorkflowChange:
        workflows = ctx.request_context.lifespan_context.workflows
        auth = get_yandex_auth(ctx)

        async def write(draft: WorkflowDraft, v: int) -> Workflow:
            current = require_action(require_step(draft.steps, status), action_id)
            if target is not None:
                require_status(
                    [s.status for s in draft.steps], target, what="Target status"
                )
            action = merge_action(
                current,
                name=name,
                name_en=name_en,
                target=target,
                description=description,
                description_en=description_en,
                screen_fields=screen_fields,
                screen_title=screen_title,
                screen_title_en=screen_title_en,
                remove_screen=remove_screen,
                post_functions=post_functions,
                conditions=conditions,
            )
            return await workflows.workflow_update_action(
                workflow_id, status, action_id, version=v, action=action, auth=auth
            )

        workflow = await _write_current(
            draft_reader(workflows, workflow_id, ctx), version, write
        )
        return WorkflowChange(
            id=workflow.id, version=workflow.version, step=_step_of(workflow, status)
        )

    @mcp.tool(
        title="Delete Workflow Transition",
        description="Delete a transition ('переход') of a Yandex Tracker workflow. "
        "The whole workflow is rewritten, so every transition screen gets a new id; "
        "returns the status with its remaining transitions and any difference "
        "found on reading the workflow again.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def workflow_delete_action(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
        status: StatusParam,
        action_id: ActionIDParam,
        version: WorkflowVersionParam = None,
    ) -> WorkflowChange:
        return await rewrite_steps(
            ctx,
            workflow_id,
            version,
            lambda draft: (remove_action(draft.steps, status, action_id), []),
            status,
        )

    @mcp.tool(
        title="Add Workflow Status",
        description="Add a status ('статус') to a Yandex Tracker workflow with at "
        "least one transition into it from an existing status, and optionally "
        "transitions out. The whole workflow is rewritten, so every transition "
        "screen gets a new id; returns the new status and any difference found on "
        "reading the workflow again.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def workflow_add_status(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
        status: Annotated[
            str,
            Field(
                description="Key of the status to add, e.g. 'needInfo'; get_statuses lists them."
            ),
        ],
        incoming: Annotated[
            list[WorkflowIncomingTransitionInput],
            Field(
                min_length=1,
                description="Transitions into the new status from existing ones; "
                "Tracker refuses a status no transition reaches.",
            ),
        ],
        actions: Annotated[
            list[WorkflowTransitionInput] | None,
            Field(description="Transitions out of the new status."),
        ] = None,
        status_type: StatusTypeParam = None,
        version: WorkflowVersionParam = None,
    ) -> WorkflowChange:
        def change(draft: WorkflowDraft) -> tuple[list[WorkflowStepDraft], list[str]]:
            statuses = [s.status for s in draft.steps]
            outgoing: list[WorkflowActionDraft] = []
            for transition in actions or []:
                require_status(
                    [*statuses, status], transition.target, what="Target status"
                )
                outgoing.append(
                    transition.to_draft(
                        transition.target, [a.id or "" for a in outgoing]
                    )
                )
            taken = {s.status: [a.id or "" for a in s.actions] for s in draft.steps}
            into: list[tuple[str, WorkflowActionDraft]] = []
            for entry in incoming:
                require_status(statuses, entry.from_status)
                action = entry.to_draft(status, taken[entry.from_status])
                taken[entry.from_status].append(action.id or "")
                into.append((entry.from_status, action))
            new_step = WorkflowStepDraft(
                status=status, status_type=status_type, actions=outgoing
            )
            return add_status(draft.steps, new_step, into), []

        return await rewrite_steps(ctx, workflow_id, version, change, status)

    @mcp.tool(
        title="Delete Workflow Status",
        description="Remove a status ('статус') from a Yandex Tracker workflow with "
        "every transition into it, which the result lists. Refused for the initial "
        "status. The whole workflow is rewritten, so every transition screen gets a "
        "new id; returns any difference found on reading the workflow again.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def workflow_delete_status(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
        status: Annotated[
            str, Field(description="Key of the status to remove, e.g. 'needInfo'.")
        ],
        version: WorkflowVersionParam = None,
    ) -> WorkflowChange:
        return await rewrite_steps(
            ctx,
            workflow_id,
            version,
            lambda draft: remove_status(draft, status),
            status,
        )

    @mcp.tool(
        title="Update Workflow",
        description="Rename a Yandex Tracker workflow ('рабочий процесс'), change "
        "the status new issues start in, or set which resolutions each issue type "
        "may be closed with under it. Only the arguments passed change.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def workflow_update(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
        name: Annotated[str | None, Field(description="New workflow name.")] = None,
        initial_status: Annotated[
            str | None,
            Field(
                description="Key of the status a new issue starts in; a status of "
                "this workflow."
            ),
        ] = None,
        issue_type_resolutions: Annotated[
            list[IssueTypeResolutionsDraft] | None,
            Field(
                description="Resolutions per issue type, e.g. [{'issue_type': "
                "'task', 'resolutions': ['fixed', 'wontFix']}]. Every resolution a "
                "transition sets has to be among them."
            ),
        ] = None,
        version: WorkflowVersionParam = None,
    ) -> WorkflowChange:
        if name is None and initial_status is None and issue_type_resolutions is None:
            raise TrackerError(
                "Nothing to change: pass `name`, `initial_status` or "
                "`issue_type_resolutions`."
            )
        workflows = ctx.request_context.lifespan_context.workflows
        auth = get_yandex_auth(ctx)

        async def write(draft: WorkflowDraft, v: int) -> Workflow:
            initial = None
            if initial_status is not None:
                require_status(
                    [s.status for s in draft.steps],
                    initial_status,
                    what="Initial status",
                )
                initial = draft.initial_action.model_copy(
                    update={"target": initial_status}
                )
            return await workflows.workflow_update(
                workflow_id,
                version=v,
                name=name,
                initial_action=initial,
                issue_type_resolutions=issue_type_resolutions,
                auth=auth,
            )

        workflow = await _write_current(
            draft_reader(workflows, workflow_id, ctx), version, write
        )
        return WorkflowChange(id=workflow.id, version=workflow.version)

    @mcp.tool(
        title="Update Workflow Status",
        description="Change a status ('статус') of a Yandex Tracker workflow: its "
        "type, or the functions Tracker runs whenever an issue enters it. The "
        "whole workflow is rewritten, so every transition screen gets a new id; "
        "returns the status and any difference found on reading it again.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def workflow_update_status(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
        status: Annotated[
            str, Field(description="Key of the status to change, e.g. 'closed'.")
        ],
        status_type: Annotated[
            StatusType | None, Field(description="New category of the status.")
        ] = None,
        on_enter_functions: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description="Functions run whenever an issue enters the status, in "
                "the shape of a transition's post-functions, e.g. [{'type': "
                "'UnsetResolutionFunction'}]. Replaces the current ones."
            ),
        ] = None,
        remove_on_enter: Annotated[
            bool, Field(description="Remove the status's on-enter functions.")
        ] = False,
        version: WorkflowVersionParam = None,
    ) -> WorkflowChange:
        # Checked before any request.
        if status_type is None and on_enter_functions is None and not remove_on_enter:
            raise TrackerError(
                "Nothing to change: pass `status_type`, `on_enter_functions` or "
                "`remove_on_enter`."
            )
        return await rewrite_steps(
            ctx,
            workflow_id,
            version,
            lambda draft: (
                update_step(
                    draft.steps,
                    status,
                    status_type=status_type,
                    on_enter_functions=on_enter_functions,
                    remove_on_enter=remove_on_enter,
                ),
                [],
            ),
            status,
        )
