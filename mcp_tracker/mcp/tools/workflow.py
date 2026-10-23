"""Workflow and transition screen MCP tools (read-only)."""

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import WorkflowID
from mcp_tracker.mcp.tools._access import check_workflow_access, is_queue_allowed
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.base import BaseTrackerEntity, NoneExcludedField
from mcp_tracker.tracker.proto.types.workflows import Screen, Workflow


class WorkflowSummary(BaseTrackerEntity):
    """One row of `workflows_get_all`: a whole workflow is too big for a listing
    (a single one can carry close to a hundred transitions)."""

    id: str
    name: str
    version: int
    queue: str | None = Field(
        None, description="Key of the queue the workflow belongs to; none if shared."
    )
    statuses: list[str] = Field(
        default_factory=list, description="Keys of the workflow's statuses."
    )
    deleted: bool | None = NoneExcludedField


def _summary(workflow: Workflow) -> WorkflowSummary:
    return WorkflowSummary(
        id=workflow.id,
        name=workflow.name,
        version=workflow.version,
        queue=workflow.queue.key if workflow.queue else None,
        statuses=[s.status.key for s in workflow.steps if s.status.key],
        deleted=workflow.deleted or None,
    )


def register_workflow_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register workflow and transition screen tools (read-only)."""

    @mcp.tool(
        title="Get All Workflows",
        description="List the Yandex Tracker workflows (in russian - 'рабочие "
        "процессы', 'воркфлоу') with their queue, version and status keys; "
        "`workflow_get` reads one with its transitions. A workflow bound to no "
        "queue is shared by every queue that runs on it.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def workflows_get_all(
        ctx: Context[AppContext],
    ) -> list[WorkflowSummary]:
        workflows = (
            await ctx.request_context.lifespan_context.workflows.workflows_get_all(
                auth=get_yandex_auth(ctx),
            )
        )
        return [
            _summary(w)
            for w in workflows
            if w.queue is None
            or w.queue.key is None
            or is_queue_allowed(settings, w.queue.key)
        ]

    @mcp.tool(
        title="Get Workflow",
        description="Get a Yandex Tracker workflow ('рабочий процесс') with its "
        "statuses and the transitions ('переходы') out of each: target status, "
        "screen, post-functions, conditions. A transition's `screen.id` is what "
        "`screen_get` takes.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def workflow_get(
        ctx: Context[AppContext],
        workflow_id: WorkflowID,
    ) -> Workflow:
        workflow = await ctx.request_context.lifespan_context.workflows.workflow_get(
            workflow_id,
            auth=get_yandex_auth(ctx),
        )
        # The id names no queue, so the check runs on what came back.
        check_workflow_access(
            settings, workflow_id, workflow.queue.key if workflow.queue else None
        )
        return workflow

    @mcp.tool(
        title="Get Transition Screen",
        description="Get a Yandex Tracker transition screen ('экран перехода'): "
        "the fields a user is asked to fill when the transition runs, and which "
        "of them are required. Screen ids come from a transition's `screen.id` "
        "in `workflow_get`.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def screen_get(
        ctx: Context[AppContext],
        screen_id: Annotated[
            int,
            Field(description="Numeric screen id, e.g. 704."),
        ],
    ) -> Screen:
        return await ctx.request_context.lifespan_context.workflows.screen_get(
            screen_id,
            auth=get_yandex_auth(ctx),
        )
