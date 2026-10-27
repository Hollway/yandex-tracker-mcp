"""User absence write MCP tools (conditionally registered based on read-only mode)."""

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.users import AbsenceInput, CreatedAbsence


def register_user_write_tools(_settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register absence write tools (not registered in read-only mode)."""

    @mcp.tool(
        title="Create User Absences",
        description="Record vacations, sick leave, business trips, duty and other "
        "absences ('отсутствия', 'отпуск') of users and return them with their ids. "
        "Needs organization administrator rights; an absence cannot be edited, "
        "only deleted and created again.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def users_create_absences(
        ctx: Context[AppContext],
        absences: Annotated[
            list[AbsenceInput],
            Field(min_length=1, max_length=100, description="At most 100."),
        ],
    ) -> list[CreatedAbsence]:
        return await ctx.request_context.lifespan_context.users.users_create_absences(
            absences, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Delete User Absences",
        description="Delete user absences ('отсутствия') by id, as "
        "users_get_absences returns it. Needs organization administrator rights; "
        "an unknown or already deleted id is ignored without an error.",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=True
        ),
    )
    async def users_delete_absences(
        ctx: Context[AppContext],
        absence_ids: Annotated[
            list[Annotated[str, Field(min_length=1, max_length=128)]],
            Field(
                min_length=1, max_length=100, description="Absence ids, at most 100."
            ),
        ],
    ) -> None:
        await ctx.request_context.lifespan_context.users.users_delete_absences(
            absence_ids, auth=get_yandex_auth(ctx)
        )
