"""Sprint write tools (conditionally registered based on read-only mode).

A sprint belongs to a board, and a board to no queue, so TRACKER_LIMIT_QUEUES
and TRACKER_READ_ONLY_QUEUES do not apply to these tools - only
TRACKER_READ_ONLY does.
"""

import datetime
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import BoardID
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.boards import BoardsProtocol
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.boards import Sprint

SprintIDParam = Annotated[int, Field(description="Sprint `id` from board_get_sprints.")]

SprintVersionParam = Annotated[
    int | None,
    Field(
        description="The sprint's `version` for optimistic locking. Omit it to act "
        "on the current version, which is read first."
    ),
]


async def _current_version(
    boards: BoardsProtocol, sprint_id: int, version: int | None, auth: YandexAuth
) -> int:
    """The version the If-Match needs: the caller's, or the sprint's current one."""
    if version is not None:
        return version
    sprint = await boards.sprint_get(sprint_id, auth=auth)
    return sprint.version or 0


def register_board_write_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register sprint write tools (not registered in read-only mode)."""

    @mcp.tool(
        title="Create Sprint",
        description="Create a sprint ('спринт') on a Yandex Tracker scrum board "
        "for a range of dates. It starts as `draft`; board_start_sprint runs it. "
        "Not covered by the queue restrictions.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def board_create_sprint(
        ctx: Context[AppContext],
        board_id: BoardID,
        name: Annotated[str, Field(description="Sprint name.")],
        start_date: Annotated[datetime.date, Field(description="YYYY-MM-DD.")],
        end_date: Annotated[datetime.date, Field(description="YYYY-MM-DD.")],
    ) -> Sprint:
        return await ctx.request_context.lifespan_context.boards.sprint_create(
            board_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Sprint",
        description="Rename or reschedule a sprint of a Yandex Tracker board, or "
        "change its status. Only the arguments passed change. Not covered by the "
        "queue restrictions.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def board_update_sprint(
        ctx: Context[AppContext],
        sprint_id: SprintIDParam,
        name: Annotated[str | None, Field(description="New name.")] = None,
        start_date: Annotated[
            datetime.date | None, Field(description="New start date, YYYY-MM-DD.")
        ] = None,
        end_date: Annotated[
            datetime.date | None, Field(description="New end date, YYYY-MM-DD.")
        ] = None,
        status: Annotated[
            Literal["draft", "in_progress", "released", "archived"] | None,
            Field(description="New status."),
        ] = None,
        version: SprintVersionParam = None,
    ) -> Sprint:
        boards = ctx.request_context.lifespan_context.boards
        auth = get_yandex_auth(ctx)
        return await boards.sprint_update(
            sprint_id,
            version=await _current_version(boards, sprint_id, version, auth),
            name=name,
            start_date=start_date,
            end_date=end_date,
            status=status,
            auth=auth,
        )

    @mcp.tool(
        title="Start Sprint",
        description="Start a sprint of a Yandex Tracker board: its status becomes "
        "`in_progress`. Not covered by the queue restrictions.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def board_start_sprint(
        ctx: Context[AppContext],
        sprint_id: SprintIDParam,
        version: SprintVersionParam = None,
    ) -> Sprint:
        boards = ctx.request_context.lifespan_context.boards
        auth = get_yandex_auth(ctx)
        return await boards.sprint_start(
            sprint_id,
            version=await _current_version(boards, sprint_id, version, auth),
            auth=auth,
        )

    @mcp.tool(
        title="Archive Sprint",
        description="Move a sprint of a Yandex Tracker board to the archive. Not "
        "covered by the queue restrictions.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def board_archive_sprint(
        ctx: Context[AppContext],
        sprint_id: SprintIDParam,
        version: SprintVersionParam = None,
    ) -> Sprint:
        boards = ctx.request_context.lifespan_context.boards
        auth = get_yandex_auth(ctx)
        return await boards.sprint_archive(
            sprint_id,
            version=await _current_version(boards, sprint_id, version, auth),
            auth=auth,
        )

    @mcp.tool(
        title="Delete Sprint",
        description="Permanently delete a sprint of a Yandex Tracker board; its "
        "issues stay and lose the sprint. Not covered by the queue restrictions.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def board_delete_sprint(
        ctx: Context[AppContext],
        sprint_id: SprintIDParam,
    ) -> None:
        await ctx.request_context.lifespan_context.boards.sprint_delete(
            sprint_id, auth=get_yandex_auth(ctx)
        )
