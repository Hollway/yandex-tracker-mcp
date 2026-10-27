"""Tools that projects, portfolios and goals share.

The entities API serves the three types under the same paths, so these tools are
registered once per type from `project.py`, `portfolio.py`, `goal.py` and their
`*_write.py` modules - each name still starts with its own entity.
"""

from dataclasses import dataclass
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import (
    EntityID,
    EntityLinkedIDParam,
    EntityLinkFieldsParam,
    EntityMetricIDParam,
    EntityMetricTextOptionalParam,
    EntityMetricTextParam,
    EntityMetricUrlParam,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.tracker.proto.types.entities import (
    EntityAttachment,
    EntityLink,
    EntityMetricItem,
    EntityType,
)


@dataclass(frozen=True)
class EntityKind:
    type: EntityType
    # How a description names it: the Tracker term, then the Russian one.
    noun: str
    russian: str

    def tool(self, action: str) -> str:
        return f"{self.type}_{action}"


PROJECT = EntityKind("project", "project", "проект")
PORTFOLIO = EntityKind("portfolio", "portfolio", "портфель")
GOAL = EntityKind("goal", "goal", "цель")


def register_entity_read_tools(kind: EntityKind, mcp: MCPServer[AppContext]) -> None:
    """Register the shared read tools of one entity type."""

    @mcp.tool(
        name=kind.tool("get_links"),
        title=f"Get {kind.noun.title()} Links",
        description=f"Get the links ('связи') of a Yandex Tracker {kind.noun} "
        f"('{kind.russian}') to other projects, portfolios and goals: the "
        "relationship and the linked entity's id and fields.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def get_links(
        ctx: Context[AppContext],
        entity_id: EntityID,
        fields: EntityLinkFieldsParam = None,
    ) -> list[EntityLink]:
        return await ctx.request_context.lifespan_context.entities.entity_get_links(
            kind.type, entity_id, fields=fields, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        name=kind.tool("get_attachments"),
        title=f"Get {kind.noun.title()} Attachments",
        description=f"List the files attached to a Yandex Tracker {kind.noun} "
        f"('{kind.russian}', 'вложения') with name, size and the comment each "
        "came with.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    async def get_attachments(
        ctx: Context[AppContext],
        entity_id: EntityID,
    ) -> list[EntityAttachment]:
        entities = ctx.request_context.lifespan_context.entities
        return await entities.entity_get_attachments(
            kind.type, entity_id, auth=get_yandex_auth(ctx)
        )


def register_entity_write_tools(kind: EntityKind, mcp: MCPServer[AppContext]) -> None:
    """Register the shared write tools of one entity type."""

    @mcp.tool(
        name=kind.tool("delete_link"),
        title=f"Delete {kind.noun.title()} Link",
        description=f"Delete the link ('связь') between a Yandex Tracker "
        f"{kind.noun} ('{kind.russian}') and another project, portfolio or goal. "
        "The link disappears from both sides.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def delete_link(
        ctx: Context[AppContext],
        entity_id: EntityID,
        linked_entity_id: EntityLinkedIDParam,
    ) -> None:
        await ctx.request_context.lifespan_context.entities.entity_delete_link(
            kind.type, entity_id, linked_entity_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        name=kind.tool("delete_attachment"),
        title=f"Delete {kind.noun.title()} Attachment",
        description=f"Delete a file attached to a Yandex Tracker {kind.noun} "
        f"('{kind.russian}'). Cannot be undone; the comment it came with stays.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def delete_attachment(
        ctx: Context[AppContext],
        entity_id: EntityID,
        attachment_id: Annotated[
            str,
            Field(description=f"Attachment `id` from {kind.tool('get_attachments')}."),
        ],
    ) -> None:
        entities = ctx.request_context.lifespan_context.entities
        await entities.entity_delete_attachment(
            kind.type, entity_id, attachment_id, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        name=kind.tool("add_metric"),
        title=f"Add {kind.noun.title()} Metric",
        description=f"Add a metric ('метрика') - a dashboard widget shown on the "
        f"page - to a Yandex Tracker {kind.noun} ('{kind.russian}') and return all "
        "its metrics.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def add_metric(
        ctx: Context[AppContext],
        entity_id: EntityID,
        text: EntityMetricTextParam,
        url: EntityMetricUrlParam = None,
    ) -> list[EntityMetricItem]:
        return await ctx.request_context.lifespan_context.entities.entity_add_metric(
            kind.type, entity_id, text=text, url=url, auth=get_yandex_auth(ctx)
        )

    @mcp.tool(
        name=kind.tool("update_metric"),
        title=f"Update {kind.noun.title()} Metric",
        description=f"Change the name or widget link of one metric ('метрика') of "
        f"a Yandex Tracker {kind.noun} ('{kind.russian}'). Tracker rewrites the "
        "list, so every metric gets a new id - use the ids returned.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def update_metric(
        ctx: Context[AppContext],
        entity_id: EntityID,
        metric_id: EntityMetricIDParam,
        text: EntityMetricTextOptionalParam = None,
        url: EntityMetricUrlParam = None,
    ) -> list[EntityMetricItem]:
        entities = ctx.request_context.lifespan_context.entities
        return await entities.entity_update_metric(
            kind.type,
            entity_id,
            metric_id,
            text=text,
            url=url,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        name=kind.tool("delete_metric"),
        title=f"Delete {kind.noun.title()} Metric",
        description=f"Delete one metric ('метрика') of a Yandex Tracker {kind.noun} "
        f"('{kind.russian}') and return the rest.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def delete_metric(
        ctx: Context[AppContext],
        entity_id: EntityID,
        metric_id: EntityMetricIDParam,
    ) -> list[EntityMetricItem]:
        entities = ctx.request_context.lifespan_context.entities
        return await entities.entity_delete_metric(
            kind.type, entity_id, metric_id, auth=get_yandex_auth(ctx)
        )
