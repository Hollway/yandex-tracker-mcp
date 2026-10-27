from dataclasses import dataclass, field

from mcp_tracker.tracker.proto.boards import BoardsProtocol
from mcp_tracker.tracker.proto.components import ComponentsProtocol
from mcp_tracker.tracker.proto.dashboards import DashboardsProtocol
from mcp_tracker.tracker.proto.entities import EntitiesProtocol
from mcp_tracker.tracker.proto.fields import GlobalDataProtocol
from mcp_tracker.tracker.proto.issues import IssueProtocol
from mcp_tracker.tracker.proto.queues import QueuesProtocol
from mcp_tracker.tracker.proto.reports import ReportsProtocol
from mcp_tracker.tracker.proto.templates import TemplatesProtocol
from mcp_tracker.tracker.proto.users import UsersProtocol
from mcp_tracker.tracker.proto.workflows import WorkflowsProtocol


@dataclass
class AppContext:
    queues: QueuesProtocol
    issues: IssueProtocol
    fields: GlobalDataProtocol
    templates: TemplatesProtocol
    users: UsersProtocol
    entities: EntitiesProtocol
    boards: BoardsProtocol
    components: ComponentsProtocol
    workflows: WorkflowsProtocol
    reports: ReportsProtocol
    dashboards: DashboardsProtocol
    # Queue key -> (forbids AI tools, monotonic time the answer expires).
    ai_access: dict[str, tuple[bool, float]] = field(default_factory=dict)
    # Whether any queue the token sees forbids AI tools, and when that expires.
    ai_forbidden_anywhere: tuple[bool, float] | None = None
