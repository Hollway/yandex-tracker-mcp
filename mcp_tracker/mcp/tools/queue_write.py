"""Queue write MCP tools (conditionally registered based on read-only mode)."""

import datetime
from typing import Annotated, Any

from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import QueueID
from mcp_tracker.mcp.tools._access import (
    check_queue_access,
    check_version_access,
    queue_checks_needed,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.queues import QueueVersion


def register_queue_write_tools(settings: Settings, mcp: FastMCP[Any]) -> None:
    """Register queue write tools (not registered in read-only mode)."""

    @mcp.tool(
        title="Create Queue Version",
        description="Create a new version in a Yandex Tracker queue.",
        annotations=ToolAnnotations(readOnlyHint=False),
    )
    async def queue_create_version(
        ctx: Context[Any, AppContext],
        queue_id: QueueID,
        name: Annotated[str, Field(description="Version name")],
        description: Annotated[
            str | None,
            Field(description="Optional version description"),
        ] = None,
        start_date: Annotated[
            datetime.date | None,
            Field(description="Optional version start date in YYYY-MM-DD format"),
        ] = None,
        due_date: Annotated[
            datetime.date | None,
            Field(description="Optional version due date in YYYY-MM-DD format"),
        ] = None,
    ) -> QueueVersion:
        check_queue_access(settings, queue_id, write=True)
        return await ctx.request_context.lifespan_context.queues.queue_create_version(
            queue_id,
            name=name,
            description=description,
            start_date=start_date,
            due_date=due_date,
            auth=get_yandex_auth(ctx),
        )

    VersionIDParam = Annotated[
        int, Field(description="Version `id` from queue_get_versions.")
    ]

    @mcp.tool(
        title="Update Queue Version",
        description="Rename a version of a Yandex Tracker queue or change its "
        "description or dates. Only the arguments passed change.",
        annotations=ToolAnnotations(readOnlyHint=False),
    )
    async def queue_update_version(
        ctx: Context[Any, AppContext],
        version_id: VersionIDParam,
        name: Annotated[str | None, Field(description="New name.")] = None,
        description: Annotated[
            str | None, Field(description="New description.")
        ] = None,
        start_date: Annotated[
            datetime.date | None, Field(description="New start date, YYYY-MM-DD.")
        ] = None,
        due_date: Annotated[
            datetime.date | None, Field(description="New due date, YYYY-MM-DD.")
        ] = None,
    ) -> QueueVersion:
        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)

        # The id names no queue: read the version for it only when there is a
        # restriction to check.
        if queue_checks_needed(settings, write=True):
            current = await queues.queue_get_version(version_id, auth=auth)
            check_version_access(settings, current, write=True)

        return await queues.queue_update_version(
            version_id,
            name=name,
            description=description,
            start_date=start_date,
            due_date=due_date,
            auth=auth,
        )

    @mcp.tool(
        title="Delete Queue Version",
        description="Permanently delete a version of a Yandex Tracker queue. Issues "
        "that had it in their fix or affected versions lose it.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )
    async def queue_delete_version(
        ctx: Context[Any, AppContext],
        version_id: VersionIDParam,
    ) -> None:
        queues = ctx.request_context.lifespan_context.queues
        auth = get_yandex_auth(ctx)

        if queue_checks_needed(settings, write=True):
            current = await queues.queue_get_version(version_id, auth=auth)
            check_version_access(settings, current, write=True)

        await queues.queue_delete_version(version_id, auth=auth)
