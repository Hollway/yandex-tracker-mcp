from typing import Protocol, runtime_checkable

from .common import YandexAuth
from .types.refs import IssueTypeReference
from .types.workflows import (
    IssueTypeResolutionsDraft,
    Screen,
    Workflow,
    WorkflowActionDraft,
    WorkflowDraft,
    WorkflowStepDraft,
)


@runtime_checkable
class WorkflowsProtocol(Protocol):
    async def workflows_get_all(
        self, *, auth: YandexAuth | None = None
    ) -> list[Workflow]: ...

    async def workflow_get(
        self, workflow_id: str, *, auth: YandexAuth | None = None
    ) -> Workflow: ...

    async def queues_get_workflows(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> dict[str, list[IssueTypeReference]]: ...

    async def screen_get(
        self, screen_id: int, *, auth: YandexAuth | None = None
    ) -> Screen: ...

    async def workflow_get_draft(
        self, workflow_id: str, *, auth: YandexAuth | None = None
    ) -> WorkflowDraft: ...

    async def workflow_create(
        self,
        *,
        name: str,
        initial_action: WorkflowActionDraft,
        steps: list[WorkflowStepDraft],
        queue: str | None = None,
        auth: YandexAuth | None = None,
    ) -> Workflow: ...

    async def workflow_update(
        self,
        workflow_id: str,
        *,
        version: int,
        name: str | None = None,
        initial_action: WorkflowActionDraft | None = None,
        steps: list[WorkflowStepDraft] | None = None,
        issue_type_resolutions: list[IssueTypeResolutionsDraft] | None = None,
        auth: YandexAuth | None = None,
    ) -> Workflow: ...

    async def workflow_add_action(
        self,
        workflow_id: str,
        status: str,
        *,
        version: int,
        action: WorkflowActionDraft,
        auth: YandexAuth | None = None,
    ) -> Workflow: ...

    async def workflow_update_action(
        self,
        workflow_id: str,
        status: str,
        action_id: str,
        *,
        version: int,
        action: WorkflowActionDraft,
        auth: YandexAuth | None = None,
    ) -> Workflow: ...

    async def workflow_delete(
        self, workflow_id: str, *, auth: YandexAuth | None = None
    ) -> None: ...


class WorkflowsProtocolWrap(WorkflowsProtocol):
    def __init__(self, original: WorkflowsProtocol):
        self._original = original
