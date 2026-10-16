"""Sprint write tools (conditionally registered based on read-only mode).

A sprint belongs to a board, and a board to no queue, so TRACKER_LIMIT_QUEUES
and TRACKER_READ_ONLY_QUEUES do not apply to these tools - only
TRACKER_READ_ONLY does.
"""

import asyncio
import datetime
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import BoardID
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import SprintVersionConflict
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


# Waits before re-reading the version and writing again, when Tracker refused a
# write made with the version just read.
SPURIOUS_CONFLICT_WAITS = (2.0, 5.0, 10.0)


async def _write_current(
    boards: BoardsProtocol,
    sprint_id: int,
    version: int | None,
    auth: YandexAuth,
    write: Callable[[int], Awaitable[Sprint]],
) -> Sprint:
    """Run `write` with the caller's version, or with the sprint's current one.

    Right after a sprint changes, Tracker refuses a write made with its current
    version now and then - 412 "не удалось сохранить изменения, попробуйте ещё
    раз", word for word what a stale version gets (live API, 2026-10-16), and
    the same request goes through 15 seconds to a minute later. A version the
    caller gave is theirs to judge, so its conflict is raised; one read here a
    moment ago is current, so its conflict is that hiccup, and the write is
    tried again on a fresh read.
    """
    if version is not None:
        return await write(version)

    async def write_current() -> Sprint:
        sprint = await boards.sprint_get(sprint_id, auth=auth)
        return await write(sprint.version or 0)

    for wait in SPURIOUS_CONFLICT_WAITS:
        try:
            return await write_current()
        except SprintVersionConflict:
            await asyncio.sleep(wait)
    return await write_current()


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
        return await _write_current(
            boards,
            sprint_id,
            version,
            auth,
            lambda v: boards.sprint_update(
                sprint_id,
                version=v,
                name=name,
                start_date=start_date,
                end_date=end_date,
                status=status,
                auth=auth,
            ),
        )

    @mcp.tool(
        title="Start Sprint",
        description="Start a sprint of a Yandex Tracker board: its status becomes "
        "`in_progress` and Tracker moves its start to now, whatever date it was "
        "planned for. Not covered by the queue restrictions.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def board_start_sprint(
        ctx: Context[AppContext],
        sprint_id: SprintIDParam,
        version: SprintVersionParam = None,
    ) -> Sprint:
        boards = ctx.request_context.lifespan_context.boards
        auth = get_yandex_auth(ctx)
        return await _write_current(
            boards,
            sprint_id,
            version,
            auth,
            lambda v: boards.sprint_start(sprint_id, version=v, auth=auth),
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
        return await _write_current(
            boards,
            sprint_id,
            version,
            auth,
            lambda v: boards.sprint_archive(sprint_id, version=v, auth=auth),
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
