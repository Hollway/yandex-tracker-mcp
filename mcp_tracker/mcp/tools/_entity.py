"""Tools that projects, portfolios and goals share.

The entities API serves the three types under the same paths, so these tools are
registered once per type from `project.py`, `portfolio.py`, `goal.py` and their
`*_write.py` modules - each name still starts with its own entity.
"""

from dataclasses import dataclass

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import EntityID, EntityLinkedIDParam, EntityLinkFieldsParam
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.tracker.proto.types.entities import EntityLink, EntityType


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
