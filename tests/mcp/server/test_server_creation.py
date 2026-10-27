import pytest
from mcp import Client

from mcp_tracker.mcp.server import create_mcp_server
from tests.mcp.conftest import create_test_settings
from tests.test_release_metadata import VERSION

# Read-only tool names (35 tools) - always registered
READ_ONLY_TOOL_NAMES = [
    "workflows_get_all",
    "workflow_get",
    "queue_get_workflows",
    "screen_get",
    # Queue tools (6)
    "queues_get_all",
    "queue_get_tags",
    "queue_get_forms",
    "queue_get_local_field",
    "queue_get_versions",
    "queue_get_triggers",
    "queue_get_components",
    "queue_get_fields",
    "queue_get_metadata",
    # Queue automation tools (7)
    "queue_get_trigger",
    "queue_get_trigger_logs",
    "queue_get_autoactions",
    "queue_get_autoaction",
    "queue_get_autoaction_logs",
    "queue_get_macros",
    "queue_get_macro",
    # Component tools (1)
    "component_get",
    "component_get_user_permissions",
    "component_get_group_permissions",
    "queue_get_permissions",
    "queue_get_user_permissions",
    "queue_get_group_permissions",
    "groups_get_all",
    # Field tools (12)
    "get_global_fields",
    "field_get",
    "fields_get_categories",
    "fields_find",
    "field_get_values",
    "get_statuses",
    "get_issue_types",
    "get_priorities",
    "get_resolutions",
    "issue_templates_get_all",
    "issue_template_get",
    "comment_templates_get_all",
    "comment_template_get",
    "issue_get_url",
    # Board tools (4)
    "boards_get_all",
    "board_get",
    "board_get_columns",
    "board_get_column",
    "board_get_sprints",
    "board_get_sprint_issues",
    # Issue read tools (10)
    "issue_get",
    "issue_get_comments",
    "issue_get_comment",
    "issue_get_links",
    "issue_get_remote_links",
    "applications_get_all",
    "issues_find",
    "issues_count",
    "issues_suggest",
    "filter_get",
    "issue_get_worklogs",
    "issue_get_attachments",
    "issue_get_checklist",
    "issue_get_transitions",
    "issue_get_changelog",
    # Worklog tools (1)
    "worklogs_find",
    # User tools (5)
    "users_get_all",
    "users_search",
    "user_get",
    "user_get_current",
    "users_get_absences",
]

# Entity read tools - registered only when TRACKER_ENTITIES_ENABLED is set
ENTITY_READ_ONLY_TOOL_NAMES = [
    # Project entity tools
    "project_get",
    "project_find",
    "project_get_comments",
    "project_get_links",
    "project_get_attachments",
    "project_get_permissions",
    # Portfolio entity tools
    "portfolio_get",
    "portfolio_find",
    "portfolio_get_comments",
    "portfolio_get_links",
    "portfolio_get_attachments",
    "portfolio_get_permissions",
    # Goal entity tools
    "goal_get",
    "goal_find",
    "goal_get_comments",
    "goal_get_links",
    "goal_get_attachments",
    "goal_get_permissions",
]

# Write tool names - only registered when not in read-only mode
WRITE_TOOL_NAMES = [
    "board_create",
    "board_update",
    "board_delete",
    "board_create_column",
    "board_update_column",
    "board_delete_column",
    "board_create_sprint",
    "board_update_sprint",
    "board_start_sprint",
    "board_archive_sprint",
    "board_delete_sprint",
    "issue_add_remote_link",
    "issue_delete_remote_link",
    "issue_delete_attachment",
    "queue_create_version",
    "queue_update_version",
    "queue_delete_version",
    "queue_create_trigger",
    "queue_update_trigger",
    "queue_delete_trigger",
    "queue_create_autoaction",
    "queue_create_macro",
    "queue_update_macro",
    "queue_delete_macro",
    "queue_create_local_field",
    "queue_update_local_field",
    "queue_delete_tag",
    "queue_create",
    "queue_delete",
    "queue_restore",
    "queue_update_permissions",
    "queue_set_issue_type_workflow",
    "queue_remove_issue_type",
    "component_create",
    "component_update",
    "component_delete",
    "issue_execute_transition",
    "issue_close",
    "issue_create",
    "issue_update",
    "issue_add_worklog",
    "issue_update_worklog",
    "issue_delete_worklog",
    "issue_add_comment",
    "issue_update_comment",
    "issue_delete_comment",
    "issue_add_comment_reaction",
    "issue_delete_comment_reaction",
    "filter_create",
    "filter_update",
    "filter_delete",
    "issue_add_link",
    "issue_delete_link",
    "issue_move",
    "issue_add_checklist_items",
    "issue_update_checklist_item",
    "issue_delete_checklist_item",
]

# Entity write tools - require both write mode and TRACKER_ENTITIES_ENABLED
ENTITY_WRITE_TOOL_NAMES = [
    "project_create",
    "project_update",
    "project_delete",
    "project_add_comment",
    "project_update_comment",
    "project_delete_comment",
    "project_add_checklist_item",
    "project_update_checklist_item",
    "project_move_checklist_item",
    "project_delete_checklist_item",
    "project_update_checklist",
    "project_delete_checklist",
    "project_delete_link",
    "project_delete_attachment",
    "project_add_metric",
    "project_update_metric",
    "project_delete_metric",
    "project_update_permissions",
    "portfolio_create",
    "portfolio_update",
    "portfolio_delete",
    "portfolio_add_comment",
    "portfolio_update_comment",
    "portfolio_delete_comment",
    "portfolio_add_checklist_item",
    "portfolio_update_checklist_item",
    "portfolio_move_checklist_item",
    "portfolio_delete_checklist_item",
    "portfolio_update_checklist",
    "portfolio_delete_checklist",
    "portfolio_delete_link",
    "portfolio_delete_attachment",
    "portfolio_add_metric",
    "portfolio_update_metric",
    "portfolio_delete_metric",
    "portfolio_update_permissions",
    "goal_create",
    "goal_update",
    "goal_delete",
    "goal_add_comment",
    "goal_update_comment",
    "goal_delete_comment",
    "goal_delete_link",
    "goal_delete_attachment",
    "goal_add_metric",
    "goal_update_metric",
    "goal_delete_metric",
    "goal_update_permissions",
    "goal_add_key_result",
    "goal_update_key_result",
    "goal_move_key_result",
    "goal_delete_key_result",
    "goal_delete_all_key_results",
]

# Tools that read local files - require both write mode and TRACKER_FILE_UPLOAD_ENABLED
FILE_UPLOAD_TOOL_NAMES = [
    "issue_add_attachment",
    "attachment_create",
]

# Tools that write to the server's disk without changing Tracker - require
# TRACKER_ATTACHMENT_DOWNLOAD_ENABLED, and stay registered in read-only mode
ATTACHMENT_DOWNLOAD_TOOL_NAMES = [
    "issue_download_attachment",
]

# Bulk changes - require both write mode and TRACKER_BULK_ENABLED
BULK_TOOL_NAMES = [
    "issues_bulk_update",
    "issues_bulk_transition",
    "issues_bulk_move",
    "issues_get_bulk_change",
]

# Workflow writes - require both write mode and TRACKER_WORKFLOWS_WRITE_ENABLED
WORKFLOW_WRITE_TOOL_NAMES = [
    "workflow_create",
    "workflow_delete",
    "workflow_add_action",
    "workflow_update_action",
    "workflow_delete_action",
    "workflow_add_status",
    "workflow_delete_status",
    "workflow_update",
    "workflow_update_status",
    "status_create",
    "status_update",
    "resolution_create",
    "resolution_update",
    "issue_type_create",
    "issue_type_update",
    "priority_create",
    "priority_update",
    "field_create",
    "field_update",
    "field_create_category",
    "field_update_category",
]

ALL_READ_ONLY_TOOL_NAMES = READ_ONLY_TOOL_NAMES + ENTITY_READ_ONLY_TOOL_NAMES
ALL_WRITE_TOOL_NAMES = (
    WRITE_TOOL_NAMES
    + ENTITY_WRITE_TOOL_NAMES
    + FILE_UPLOAD_TOOL_NAMES
    + BULK_TOOL_NAMES
    + WORKFLOW_WRITE_TOOL_NAMES
)

# All tool names that should be registered in normal mode (entity tools enabled)
EXPECTED_TOOL_NAMES = (
    ALL_READ_ONLY_TOOL_NAMES + ALL_WRITE_TOOL_NAMES + ATTACHMENT_DOWNLOAD_TOOL_NAMES
)


class TestToolRegistration:
    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    async def test_tool_is_registered(
        self,
        client_session: Client,
        tool_name: str,
    ) -> None:
        result = await client_session.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name in tool_names, f"Tool '{tool_name}' is not registered"


class TestReadOnlyModeToolRegistration:
    """Test tool registration in read-only mode."""

    @pytest.mark.parametrize(
        "tool_name", ALL_READ_ONLY_TOOL_NAMES + ATTACHMENT_DOWNLOAD_TOOL_NAMES
    )
    async def test_read_only_tools_are_registered(
        self,
        client_session_read_only: Client,
        tool_name: str,
    ) -> None:
        """Read-only tools should be registered in read-only mode."""
        result = await client_session_read_only.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name in tool_names, (
            f"Read-only tool '{tool_name}' should be registered in read-only mode"
        )

    @pytest.mark.parametrize("tool_name", ALL_WRITE_TOOL_NAMES)
    async def test_write_tools_are_not_registered(
        self,
        client_session_read_only: Client,
        tool_name: str,
    ) -> None:
        """Write tools should NOT be registered in read-only mode."""
        result = await client_session_read_only.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name not in tool_names, (
            f"Write tool '{tool_name}' should NOT be registered in read-only mode"
        )

    async def test_correct_tool_count_in_read_only_mode(
        self,
        client_session_read_only: Client,
    ) -> None:
        """Read-only mode keeps the read-only tools and the attachment download,
        which changes nothing in Tracker."""
        result = await client_session_read_only.list_tools()

        expected = len(ALL_READ_ONLY_TOOL_NAMES) + len(ATTACHMENT_DOWNLOAD_TOOL_NAMES)
        assert len(result.tools) == expected, (
            f"Expected {expected} tools in read-only mode, got {len(result.tools)}"
        )

    async def test_correct_tool_count_in_normal_mode(
        self,
        client_session: Client,
    ) -> None:
        """Normal mode should have all tools (read-only + write)."""
        result = await client_session.list_tools()

        assert len(result.tools) == len(EXPECTED_TOOL_NAMES), (
            f"Expected {len(EXPECTED_TOOL_NAMES)} tools in normal mode, "
            f"got {len(result.tools)}"
        )


class TestEntityToolRegistration:
    """Entity tools are opt-in via TRACKER_ENTITIES_ENABLED (default off)."""

    @pytest.mark.parametrize(
        "tool_name", ENTITY_READ_ONLY_TOOL_NAMES + ENTITY_WRITE_TOOL_NAMES
    )
    async def test_entity_tools_are_not_registered_by_default(
        self,
        client_session_entities_disabled: Client,
        tool_name: str,
    ) -> None:
        result = await client_session_entities_disabled.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name not in tool_names, (
            f"Entity tool '{tool_name}' should NOT be registered when "
            f"tracker_entities_enabled is False"
        )

    @pytest.mark.parametrize(
        "tool_name",
        READ_ONLY_TOOL_NAMES
        + WRITE_TOOL_NAMES
        + FILE_UPLOAD_TOOL_NAMES
        + BULK_TOOL_NAMES
        + ATTACHMENT_DOWNLOAD_TOOL_NAMES
        + WORKFLOW_WRITE_TOOL_NAMES,
    )
    async def test_non_entity_tools_stay_registered(
        self,
        client_session_entities_disabled: Client,
        tool_name: str,
    ) -> None:
        result = await client_session_entities_disabled.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name in tool_names

    async def test_correct_tool_count_with_entities_disabled(
        self,
        client_session_entities_disabled: Client,
    ) -> None:
        result = await client_session_entities_disabled.list_tools()

        expected = (
            len(READ_ONLY_TOOL_NAMES)
            + len(WRITE_TOOL_NAMES)
            + len(FILE_UPLOAD_TOOL_NAMES)
            + len(BULK_TOOL_NAMES)
            + len(ATTACHMENT_DOWNLOAD_TOOL_NAMES)
            + len(WORKFLOW_WRITE_TOOL_NAMES)
        )
        assert len(result.tools) == expected, (
            f"Expected {expected} tools with entity tools disabled, "
            f"got {len(result.tools)}"
        )


class TestFileUploadToolRegistration:
    """`issue_add_attachment` reads local files, so it needs its own opt-in
    (TRACKER_FILE_UPLOAD_ENABLED, default off) on top of a writable server."""

    @pytest.mark.parametrize(
        ("read_only", "file_upload_enabled", "registered"),
        [
            pytest.param(False, False, False, id="default-flag-off"),
            pytest.param(True, True, False, id="read-only-despite-flag"),
            pytest.param(True, False, False, id="read-only-flag-off"),
            pytest.param(False, True, True, id="enabled"),
        ],
    )
    @pytest.mark.parametrize("tool_name", FILE_UPLOAD_TOOL_NAMES)
    async def test_registered_only_when_enabled_and_writable(
        self,
        tool_name: str,
        read_only: bool,
        file_upload_enabled: bool,
        registered: bool,
    ) -> None:
        server = create_mcp_server(
            settings=create_test_settings(
                read_only=read_only, file_upload_enabled=file_upload_enabled
            )
        )

        tool_names = {tool.name for tool in await server.list_tools()}

        assert (tool_name in tool_names) is registered

    async def test_the_flag_gates_nothing_else(self) -> None:
        enabled = create_mcp_server(settings=create_test_settings())
        disabled = create_mcp_server(
            settings=create_test_settings(file_upload_enabled=False)
        )

        enabled_names = {tool.name for tool in await enabled.list_tools()}
        disabled_names = {tool.name for tool in await disabled.list_tools()}

        assert enabled_names - disabled_names == set(FILE_UPLOAD_TOOL_NAMES)


class TestAttachmentDownloadToolRegistration:
    """`issue_download_attachment` writes to the server's disk, so it needs its own
    opt-in (TRACKER_ATTACHMENT_DOWNLOAD_ENABLED, default off). It changes nothing
    in Tracker, so read-only mode does not remove it."""

    @pytest.mark.parametrize(
        ("read_only", "download_enabled", "registered"),
        [
            pytest.param(False, False, False, id="default-flag-off"),
            pytest.param(True, False, False, id="read-only-flag-off"),
            pytest.param(True, True, True, id="read-only-with-flag"),
            pytest.param(False, True, True, id="enabled"),
        ],
    )
    @pytest.mark.parametrize("tool_name", ATTACHMENT_DOWNLOAD_TOOL_NAMES)
    async def test_registered_only_when_enabled(
        self,
        tool_name: str,
        read_only: bool,
        download_enabled: bool,
        registered: bool,
    ) -> None:
        server = create_mcp_server(
            settings=create_test_settings(
                read_only=read_only, attachment_download_enabled=download_enabled
            )
        )

        tool_names = {tool.name for tool in await server.list_tools()}

        assert (tool_name in tool_names) is registered

    async def test_the_flag_gates_nothing_else(self) -> None:
        enabled = create_mcp_server(settings=create_test_settings())
        disabled = create_mcp_server(
            settings=create_test_settings(attachment_download_enabled=False)
        )

        enabled_names = {tool.name for tool in await enabled.list_tools()}
        disabled_names = {tool.name for tool in await disabled.list_tools()}

        assert enabled_names - disabled_names == set(ATTACHMENT_DOWNLOAD_TOOL_NAMES)


class TestBulkToolRegistration:
    """Bulk changes are irreversible over up to 10 000 issues: opt-in through
    TRACKER_BULK_ENABLED, on top of a writable server."""

    @pytest.mark.parametrize(
        ("read_only", "bulk_enabled", "registered"),
        [
            pytest.param(False, False, False, id="default-flag-off"),
            pytest.param(True, True, False, id="read-only-despite-flag"),
            pytest.param(False, True, True, id="enabled"),
        ],
    )
    @pytest.mark.parametrize("tool_name", BULK_TOOL_NAMES)
    async def test_registered_only_when_enabled_and_writable(
        self,
        tool_name: str,
        read_only: bool,
        bulk_enabled: bool,
        registered: bool,
    ) -> None:
        server = create_mcp_server(
            settings=create_test_settings(
                read_only=read_only, bulk_enabled=bulk_enabled
            )
        )

        tool_names = {tool.name for tool in await server.list_tools()}

        assert (tool_name in tool_names) is registered

    async def test_the_flag_gates_nothing_else(self) -> None:
        enabled = create_mcp_server(settings=create_test_settings())
        disabled = create_mcp_server(settings=create_test_settings(bulk_enabled=False))

        enabled_names = {tool.name for tool in await enabled.list_tools()}
        disabled_names = {tool.name for tool in await disabled.list_tools()}

        assert enabled_names - disabled_names == set(BULK_TOOL_NAMES)


class TestWorkflowWriteToolRegistration:
    """A workflow is often shared by several queues and a change applies to all
    of them: opt-in through TRACKER_WORKFLOWS_WRITE_ENABLED, on top of a
    writable server."""

    @pytest.mark.parametrize(
        ("read_only", "workflows_write_enabled", "registered"),
        [
            pytest.param(False, False, False, id="default-flag-off"),
            pytest.param(True, True, False, id="read-only-despite-flag"),
            pytest.param(False, True, True, id="enabled"),
        ],
    )
    @pytest.mark.parametrize("tool_name", WORKFLOW_WRITE_TOOL_NAMES)
    async def test_registered_only_when_enabled_and_writable(
        self,
        tool_name: str,
        read_only: bool,
        workflows_write_enabled: bool,
        registered: bool,
    ) -> None:
        server = create_mcp_server(
            settings=create_test_settings(
                read_only=read_only, workflows_write_enabled=workflows_write_enabled
            )
        )

        tool_names = {tool.name for tool in await server.list_tools()}

        assert (tool_name in tool_names) is registered

    async def test_the_flag_gates_nothing_else(self) -> None:
        enabled = create_mcp_server(settings=create_test_settings())
        disabled = create_mcp_server(
            settings=create_test_settings(workflows_write_enabled=False)
        )

        enabled_names = {tool.name for tool in await enabled.list_tools()}
        disabled_names = {tool.name for tool in await disabled.list_tools()}

        assert enabled_names - disabled_names == set(WORKFLOW_WRITE_TOOL_NAMES)


class TestResourceRegistration:
    async def test_configuration_resource_is_registered(
        self,
        client_session: Client,
    ) -> None:
        """The configuration resource is a template (optional query variables),
        so it is listed under `resources/templates/list`, not `resources/list`."""
        result = await client_session.list_resource_templates()

        templates = [t.uri_template for t in result.resource_templates]
        assert "tracker-mcp://configuration{?cloudOrgId,orgId}" in templates


class TestServerConfiguration:
    async def test_server_has_correct_name(
        self,
        client_session: Client,
    ) -> None:
        # `Client.__aenter__` already negotiated the connection; on a modern
        # (2026-07-28) connection the identity arrives as a `_meta` stamp,
        # which is optional - so `server_info` is `None` for an anonymous
        # server, and the first assert is what tells that apart from a rename.
        assert client_session.server_info is not None
        assert client_session.server_info.name == "Yandex Tracker MCP Server"

    async def test_server_reports_the_package_version(
        self,
        client_session: Client,
    ) -> None:
        """`serverInfo.version` is read from the installed package metadata and
        is deliberately empty when that is missing - so a distribution name
        drifting from `pyproject.toml` would report "" with every test green."""
        assert client_session.server_info is not None
        assert client_session.server_info.version == VERSION

    async def test_server_has_instructions(
        self,
        client_session: Client,
    ) -> None:
        instructions = client_session.instructions

        assert instructions is not None
        assert len(instructions) > 0
