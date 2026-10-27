"""Goal write MCP tools (conditionally registered based on read-only mode)."""

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import (
    EntityClientsParam,
    EntityCommentIDParam,
    EntityCommentMaillistSummoneesParam,
    EntityCommentParam,
    EntityCommentSummoneesParam,
    EntityCommentTextParam,
    EntityDescriptionParam,
    EntityEndParam,
    EntityFollowersParam,
    EntityID,
    EntityLeadParam,
    EntityParentEntityParam,
    EntitySummaryParam,
    EntitySummaryRequiredParam,
    EntityTagsParam,
    EntityTeamAccessParam,
    EntityTeamUsersParam,
    EntityVersionParam,
    GoalFieldsParam,
    GoalKeyResultAchievedParam,
    GoalKeyResultAssigneeParam,
    GoalKeyResultDeadlineParam,
    GoalKeyResultIDParam,
    GoalKeyResultProgressParam,
    GoalKeyResultStatusParam,
    GoalKeyResultTextOptionalParam,
    GoalKeyResultTextParam,
    GoalKeyResultTypeOptionalParam,
    GoalKeyResultTypeParam,
    GoalLinksParam,
    GoalStatusParam,
)
from mcp_tracker.mcp.tools._entity import GOAL, register_entity_write_tools
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.entities import GoalEntity
from mcp_tracker.tracker.proto.types.issues import IssueComment


def register_goal_write_tools(_settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register goal write tools (not registered in read-only mode)."""

    register_entity_write_tools(GOAL, mcp)

    @mcp.tool(
        title="Create Goal",
        description="Create a Yandex Tracker goal (in russian - 'цель') - an entity of the "
        "goals API, unrelated to queues and issues.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def goal_create(
        ctx: Context[AppContext],
        summary: EntitySummaryRequiredParam,
        description: EntityDescriptionParam = None,
        lead: EntityLeadParam = None,
        team_users: EntityTeamUsersParam = None,
        clients: EntityClientsParam = None,
        followers: EntityFollowersParam = None,
        end: EntityEndParam = None,
        tags: EntityTagsParam = None,
        entity_status: GoalStatusParam = None,
        parent_entity: EntityParentEntityParam = None,
        team_access: EntityTeamAccessParam = None,
        links: GoalLinksParam = None,
        fields: GoalFieldsParam = None,
    ) -> GoalEntity:
        return await ctx.request_context.lifespan_context.entities.goal_create(
            summary=summary,
            description=description,
            lead=lead,
            team_users=team_users,
            clients=clients,
            followers=followers,
            end=end,
            tags=tags,
            entity_status=entity_status,
            parent_entity=parent_entity,
            team_access=team_access,
            links=links,
            fields=[f.value for f in fields] if fields is not None else None,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Goal",
        description="Update fields of an existing Yandex Tracker goal.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def goal_update(
        ctx: Context[AppContext],
        entity_id: EntityID,
        summary: EntitySummaryParam = None,
        description: EntityDescriptionParam = None,
        lead: EntityLeadParam = None,
        team_users: EntityTeamUsersParam = None,
        clients: EntityClientsParam = None,
        followers: EntityFollowersParam = None,
        end: EntityEndParam = None,
        tags: EntityTagsParam = None,
        entity_status: GoalStatusParam = None,
        parent_entity: EntityParentEntityParam = None,
        team_access: EntityTeamAccessParam = None,
        comment: EntityCommentParam = None,
        version: EntityVersionParam = None,
        links: GoalLinksParam = None,
        fields: GoalFieldsParam = None,
    ) -> GoalEntity:
        return await ctx.request_context.lifespan_context.entities.goal_update(
            entity_id,
            summary=summary,
            description=description,
            lead=lead,
            team_users=team_users,
            clients=clients,
            followers=followers,
            end=end,
            tags=tags,
            entity_status=entity_status,
            parent_entity=parent_entity,
            team_access=team_access,
            comment=comment,
            version=version,
            links=links,
            fields=[f.value for f in fields] if fields is not None else None,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Delete Goal",
        description="Delete a Yandex Tracker goal (in russian - 'цель'). Cannot be undone.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def goal_delete(
        ctx: Context[AppContext],
        entity_id: EntityID,
    ) -> None:
        await ctx.request_context.lifespan_context.entities.goal_delete(
            entity_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Add Goal Comment",
        description="Add a comment to a Yandex Tracker goal, e.g. entity_id='ghi789'. "
        "To mention or call people so they get notified, use `summonees` - '@login' in "
        "the text notifies nobody.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def goal_add_comment(
        ctx: Context[AppContext],
        entity_id: EntityID,
        text: EntityCommentTextParam,
        summonees: EntityCommentSummoneesParam = None,
        maillist_summonees: EntityCommentMaillistSummoneesParam = None,
    ) -> IssueComment:
        return await ctx.request_context.lifespan_context.entities.goal_add_comment(
            entity_id,
            text=text,
            summonees=summonees,
            maillist_summonees=maillist_summonees,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Goal Comment",
        description="Update an existing comment on a Yandex Tracker goal. To mention "
        "or call people, use `summonees`, not '@login' in the text.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def goal_update_comment(
        ctx: Context[AppContext],
        entity_id: EntityID,
        comment_id: EntityCommentIDParam,
        text: EntityCommentTextParam,
        summonees: EntityCommentSummoneesParam = None,
        maillist_summonees: EntityCommentMaillistSummoneesParam = None,
    ) -> IssueComment:
        return await ctx.request_context.lifespan_context.entities.goal_update_comment(
            entity_id,
            comment_id,
            text=text,
            summonees=summonees,
            maillist_summonees=maillist_summonees,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Delete Goal Comment",
        description="Delete a comment from a Yandex Tracker goal.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def goal_delete_comment(
        ctx: Context[AppContext],
        entity_id: EntityID,
        comment_id: EntityCommentIDParam,
    ) -> None:
        return await ctx.request_context.lifespan_context.entities.goal_delete_comment(
            entity_id,
            comment_id,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Add Goal Key Result",
        description="Add a key result ('ключевой результат') to the end of a Yandex "
        "Tracker goal ('цель') and return the goal's key results and progress.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def goal_add_key_result(
        ctx: Context[AppContext],
        entity_id: EntityID,
        text: GoalKeyResultTextParam,
        type: GoalKeyResultTypeParam,
        assignee: GoalKeyResultAssigneeParam = None,
        deadline: GoalKeyResultDeadlineParam = None,
        progress: GoalKeyResultProgressParam = None,
        achieved: GoalKeyResultAchievedParam = None,
        status: GoalKeyResultStatusParam = None,
    ) -> GoalEntity:
        return await ctx.request_context.lifespan_context.entities.goal_add_key_result(
            entity_id,
            text=text,
            type=type,
            assignee=assignee,
            deadline=deadline,
            progress=progress,
            achieved=achieved,
            status=status,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Goal Key Result",
        description="Change one key result ('ключевой результат') of a Yandex "
        "Tracker goal, keeping the fields you omit. Tracker rewrites the whole "
        "list, so every key result gets a new id - use the ids returned.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def goal_update_key_result(
        ctx: Context[AppContext],
        entity_id: EntityID,
        key_result_id: GoalKeyResultIDParam,
        text: GoalKeyResultTextOptionalParam = None,
        type: GoalKeyResultTypeOptionalParam = None,
        assignee: GoalKeyResultAssigneeParam = None,
        deadline: GoalKeyResultDeadlineParam = None,
        progress: GoalKeyResultProgressParam = None,
        achieved: GoalKeyResultAchievedParam = None,
        status: GoalKeyResultStatusParam = None,
    ) -> GoalEntity:
        entities = ctx.request_context.lifespan_context.entities
        return await entities.goal_update_key_result(
            entity_id,
            key_result_id,
            text=text,
            type=type,
            assignee=assignee,
            deadline=deadline,
            progress=progress,
            achieved=achieved,
            status=status,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Move Goal Key Result",
        description="Move a key result ('ключевой результат') of a Yandex Tracker "
        "goal before another one, or to the end. Every key result gets a new id - "
        "use the ids returned.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def goal_move_key_result(
        ctx: Context[AppContext],
        entity_id: EntityID,
        key_result_id: GoalKeyResultIDParam,
        before: Annotated[
            str | None,
            Field(
                description="Id of the key result to put it before; omit for the end."
            ),
        ] = None,
    ) -> GoalEntity:
        entities = ctx.request_context.lifespan_context.entities
        return await entities.goal_move_key_result(
            entity_id, key_result_id, before=before, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Delete Goal Key Result",
        description="Delete one key result ('ключевой результат') of a Yandex "
        "Tracker goal and return the rest. Cannot be undone.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def goal_delete_key_result(
        ctx: Context[AppContext],
        entity_id: EntityID,
        key_result_id: GoalKeyResultIDParam,
    ) -> GoalEntity:
        entities = ctx.request_context.lifespan_context.entities
        return await entities.goal_delete_key_result(
            entity_id, key_result_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        title="Delete All Goal Key Results",
        description="Delete every key result ('ключевые результаты') of a Yandex "
        "Tracker goal. Cannot be undone.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def goal_delete_all_key_results(
        ctx: Context[AppContext],
        entity_id: EntityID,
    ) -> GoalEntity:
        entities = ctx.request_context.lifespan_context.entities
        return await entities.goal_delete_all_key_results(
            entity_id, auth=get_yandex_auth(ctx)
        )
