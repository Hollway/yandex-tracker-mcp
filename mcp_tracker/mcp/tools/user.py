"""User-related MCP tools (read-only)."""

import datetime
from typing import Annotated, Any

from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field
from thefuzz import process

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import PageParam, PerPageParam, UserID
from mcp_tracker.mcp.tools._pagination import iter_pages
from mcp_tracker.mcp.utils import (
    get_yandex_auth,
    local_day_end,
    local_day_start,
    set_non_needed_fields_null,
)
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from mcp_tracker.tracker.proto.types.users import User, UserAbsences, UserFieldsEnum


def register_user_tools(_settings: Settings, mcp: FastMCP[Any]) -> None:
    """Register user-related tools (all read-only)."""

    @mcp.tool(
        title="Get All Users",
        description="Get information about user accounts registered in the organization.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def users_get_all(
        ctx: Context[Any, AppContext],
        page: PageParam = 1,
        per_page: PerPageParam = 50,
        fields: Annotated[
            list[UserFieldsEnum] | None,
            Field(
                description="Fields to include in each user; omit to get all. Select "
                "only what you need.",
            ),
        ] = None,
    ) -> PaginatedResult[User]:
        result = await ctx.request_context.lifespan_context.users.users_list(
            per_page=per_page,
            page=page,
            auth=get_yandex_auth(ctx),
        )

        if fields is not None:
            set_non_needed_fields_null(result.values, {f.name for f in fields})

        return result

    @mcp.tool(
        title="Search Users",
        description="Search user based on login, email or real name (first or last name, or both). "
        "Returns either single user or multiple users if several match the query or an empty list "
        "if no users matched.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def users_search(
        ctx: Context[Any, AppContext],
        login_or_email_or_name: Annotated[
            str, Field(description="User login, email or real name to search for")
        ],
    ) -> list[User]:
        per_page = 100

        login_or_email_or_name = login_or_email_or_name.strip().lower()

        all_users: list[User] = []

        async for batch in iter_pages(
            lambda current_page: ctx.request_context.lifespan_context.users.users_list(
                per_page=per_page,
                page=current_page,
                auth=get_yandex_auth(ctx),
            ),
            page=None,
            per_page=per_page,
        ):
            for user in batch.values:
                if user.login and login_or_email_or_name == user.login.strip().lower():
                    return [user]

                if user.email and login_or_email_or_name == user.email.strip().lower():
                    return [user]

            all_users.extend(batch.values)

        names = {
            idx: f"{u.first_name} {u.last_name}" for idx, u in enumerate(all_users)
        }
        results = process.extractBests(
            login_or_email_or_name, names, score_cutoff=80, limit=3
        )
        matched_users = [all_users[idx] for name, score, idx in results]
        return matched_users

    @mcp.tool(
        title="Get User",
        description="Get information about a specific user by login or UID",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def user_get(
        ctx: Context[Any, AppContext],
        user_id: UserID,
    ) -> User:
        user = await ctx.request_context.lifespan_context.users.user_get(
            user_id,
            auth=get_yandex_auth(ctx),
        )
        if user is None:
            raise TrackerError(f"User `{user_id}` not found.")

        return user

    @mcp.tool(
        title="Get Current User",
        description="Get information about the current authenticated user",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def user_get_current(
        ctx: Context[Any, AppContext],
    ) -> User:
        return await ctx.request_context.lifespan_context.users.user_get_current(
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Get User Absences",
        description="Vacations, sick leave, business trips and other absences "
        "('отсутствия', 'отпуск') of up to 100 users that overlap a period - check "
        "before assigning work or planning a sprint. Needs organization "
        "administrator rights.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def users_get_absences(
        ctx: Context[Any, AppContext],
        users: Annotated[
            list[str],
            Field(
                min_length=1,
                max_length=100,
                description="Logins or uids, at most 100.",
            ),
        ],
        date_from: Annotated[
            datetime.date | None,
            Field(description="First day of the period, YYYY-MM-DD; omit for now."),
        ] = None,
        date_to: Annotated[
            datetime.date | None,
            Field(description="Last day of the period, YYYY-MM-DD, inclusive."),
        ] = None,
    ) -> list[UserAbsences]:
        if date_from is not None and date_to is not None and date_to < date_from:
            raise TrackerError("`date_to` is before `date_from`.")

        return await ctx.request_context.lifespan_context.users.users_get_absences(
            users,
            date_from=local_day_start(date_from) if date_from else None,
            date_to=local_day_end(date_to) if date_to else None,
            auth=get_yandex_auth(ctx),
        )
