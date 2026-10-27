"""MCP tools package for Yandex Tracker.

This package organizes MCP tools by category:
- queue.py: Queue-related tools (read-only)
- queue_write.py: Queue write tools (conditional on read-only mode)
- field.py: Global field and metadata tools (read-only)
- template.py: Issue and comment template tools (read-only)
- application.py: External application tools (read-only)
- board.py: Board and sprint tools (read-only)
- board_write.py: Sprint write tools (conditional on read-only mode)
- component.py: Queue component tools (read-only)
- component_write.py: Queue component write tools (conditional on read-only mode)
- issue_read.py: Issue read-only tools; the attachment download tool additionally
  needs tracker_attachment_download_enabled
- attachment_write.py: Temporary attachment upload (conditional on read-only
  mode and tracker_file_upload_enabled)
- issue_write.py: Issue write tools (conditional on read-only mode); the file upload
  tool additionally needs tracker_file_upload_enabled
- dashboard.py: Dashboard tools (read-only)
- dashboard_write.py: Dashboard write tools (conditional on read-only mode)
- report.py: Issue report tools (read-only)
- report_write.py: Issue report write tools (conditional on read-only mode)
- user.py: User-related tools (read-only)
- user_write.py: User absence write tools (conditional on read-only mode)
- worklog.py: Worklog search across issues (read-only)
- workflow.py: Workflow and transition screen tools (read-only)
- workflow_write.py: Workflow write tools (conditional on read-only mode and
  tracker_workflows_write_enabled)
- catalog_write.py: Status, resolution, issue type and priority write tools
  (conditional on read-only mode and tracker_workflows_write_enabled)
- field_write.py: Issue field and field category write tools (the same
  conditions as catalog_write.py)
- filter.py: Saved issue filter tools (read-only)
- filter_write.py: Saved issue filter write tools (conditional on read-only mode)
- project.py: Project entity tools (read-only)
- project_write.py: Project entity write tools (conditional on read-only mode)
- portfolio.py: Portfolio entity tools (read-only)
- portfolio_write.py: Portfolio entity write tools (conditional on read-only mode)
- goal.py: Goal entity tools (read-only)
- goal_write.py: Goal entity write tools (conditional on read-only mode)
"""

from mcp.server.mcpserver import MCPServer

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.tools.application import register_application_tools
from mcp_tracker.mcp.tools.attachment_write import (
    register_attachment_file_upload_tools,
)
from mcp_tracker.mcp.tools.board import register_board_tools
from mcp_tracker.mcp.tools.board_write import register_board_write_tools
from mcp_tracker.mcp.tools.catalog_write import register_catalog_write_tools
from mcp_tracker.mcp.tools.component import register_component_tools
from mcp_tracker.mcp.tools.component_write import register_component_write_tools
from mcp_tracker.mcp.tools.dashboard import register_dashboard_tools
from mcp_tracker.mcp.tools.dashboard_write import register_dashboard_write_tools
from mcp_tracker.mcp.tools.field import register_field_tools
from mcp_tracker.mcp.tools.field_write import register_field_write_tools
from mcp_tracker.mcp.tools.filter import register_filter_tools
from mcp_tracker.mcp.tools.filter_write import register_filter_write_tools
from mcp_tracker.mcp.tools.goal import register_goal_tools
from mcp_tracker.mcp.tools.goal_write import register_goal_write_tools
from mcp_tracker.mcp.tools.issue_read import (
    register_issue_attachment_download_tools,
    register_issue_read_tools,
)
from mcp_tracker.mcp.tools.issue_write import (
    register_issue_bulk_tools,
    register_issue_file_upload_tools,
    register_issue_write_tools,
)
from mcp_tracker.mcp.tools.portfolio import register_portfolio_tools
from mcp_tracker.mcp.tools.portfolio_write import register_portfolio_write_tools
from mcp_tracker.mcp.tools.project import register_project_tools
from mcp_tracker.mcp.tools.project_write import register_project_write_tools
from mcp_tracker.mcp.tools.queue import register_queue_tools
from mcp_tracker.mcp.tools.queue_write import register_queue_write_tools
from mcp_tracker.mcp.tools.report import register_report_tools
from mcp_tracker.mcp.tools.report_write import register_report_write_tools
from mcp_tracker.mcp.tools.template import register_template_tools
from mcp_tracker.mcp.tools.user import register_user_tools
from mcp_tracker.mcp.tools.user_write import register_user_write_tools
from mcp_tracker.mcp.tools.workflow import register_workflow_tools
from mcp_tracker.mcp.tools.workflow_write import register_workflow_write_tools
from mcp_tracker.mcp.tools.worklog import register_worklog_tools
from mcp_tracker.settings import Settings


def register_all_tools(settings: Settings, mcp: MCPServer[AppContext]) -> None:
    """Register all MCP tools based on settings.

    Args:
        settings: Application settings. If tracker_read_only is True,
            write tools will not be registered. Project/portfolio/goal tools
            are registered only if tracker_entities_enabled is True, and the
            file upload tools only if tracker_file_upload_enabled is True. The
            attachment download tool needs tracker_attachment_download_enabled,
            in read-only mode as well.
        mcp: MCPServer instance.
    """
    # Always register read-only tools
    register_queue_tools(settings, mcp)
    register_field_tools(settings, mcp)
    register_template_tools(settings, mcp)
    register_board_tools(settings, mcp)
    register_application_tools(settings, mcp)
    register_component_tools(settings, mcp)
    register_issue_read_tools(settings, mcp)
    register_user_tools(settings, mcp)
    register_worklog_tools(settings, mcp)
    register_workflow_tools(settings, mcp)
    register_filter_tools(settings, mcp)
    register_report_tools(settings, mcp)
    register_dashboard_tools(settings, mcp)

    # Changes nothing in Tracker, so it does not depend on tracker_read_only.
    if settings.tracker_attachment_download_enabled:
        register_issue_attachment_download_tools(settings, mcp)

    if settings.tracker_entities_enabled:
        register_project_tools(settings, mcp)
        register_portfolio_tools(settings, mcp)
        register_goal_tools(settings, mcp)

    # Only register write tools if not in read-only mode
    if not settings.tracker_read_only:
        register_queue_write_tools(settings, mcp)
        register_board_write_tools(settings, mcp)
        register_component_write_tools(settings, mcp)
        register_issue_write_tools(settings, mcp)
        register_filter_write_tools(settings, mcp)
        register_user_write_tools(settings, mcp)
        register_report_write_tools(settings, mcp)
        register_dashboard_write_tools(settings, mcp)

        if settings.tracker_bulk_enabled:
            register_issue_bulk_tools(settings, mcp)

        if settings.tracker_workflows_write_enabled:
            register_workflow_write_tools(settings, mcp)
            register_catalog_write_tools(settings, mcp)
            register_field_write_tools(settings, mcp)

        if settings.tracker_file_upload_enabled:
            register_issue_file_upload_tools(settings, mcp)
            register_attachment_file_upload_tools(settings, mcp)

        if settings.tracker_entities_enabled:
            register_project_write_tools(settings, mcp)
            register_portfolio_write_tools(settings, mcp)
            register_goal_write_tools(settings, mcp)


__all__ = ["register_all_tools"]
