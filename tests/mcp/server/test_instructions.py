"""Guard: the server instructions must not name tools or arguments that do not exist.

The instructions are the first thing an agent reads about this server, and they
drifted behind the tools once already - they described a read-only server long
after the write tools landed. A stale tool name there sends agents looking for
something that is not registered.

They also have to fit the client: Claude Code cuts them at 4096 characters, which
once dropped the whole pagination section off the end.
"""

import re

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.tools import Tool

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import INSTRUCTIONS_LIMIT, make_instructions

# Backticked names in the instructions that are arguments, fields or literals
# rather than tools.
NON_TOOL_NAMES = frozenset(
    {
        "page",
        "per_page",
        "cursor",
        "next_cursor",
        "fields",
        "version",
        "summonees",
        "maillistSummonees",
        "boards",
        "queue",
        "@login",
        "text",
        "hits",
        "pages",
        "comment",
        "links",
        "project",
        "shortId",
        "parent_entity",
        # A literal queue key used as an example, not a tool.
        "SOMEPROJECT",
    }
)


# The server fixture of each configuration the instructions vary with.
CONFIGURATIONS = [
    pytest.param("mcp_server", True, id="entities"),
    pytest.param("mcp_server_entities_disabled", False, id="no-entities"),
]


def _quoted_names(instructions: str) -> set[str]:
    return set(re.findall(r"`([A-Za-z_@][A-Za-z_]*)`", instructions))


class TestInstructions:
    @pytest.mark.parametrize(("server_fixture", "entities"), CONFIGURATIONS)
    def test_every_named_tool_exists(
        self, request: pytest.FixtureRequest, server_fixture: str, entities: bool
    ) -> None:
        server: MCPServer[AppContext] = request.getfixturevalue(server_fixture)
        tool_names = {tool.name for tool in server._tool_manager.list_tools()}

        named = _quoted_names(make_instructions(entities=entities)) - NON_TOOL_NAMES
        assert named, "no tool names quoted in the instructions - the sweep is vacuous"
        assert named <= tool_names, (
            f"instructions name tools that are not registered: "
            f"{sorted(named - tool_names)}"
        )

    @pytest.mark.parametrize(("server_fixture", "entities"), CONFIGURATIONS)
    def test_server_sends_the_instructions_of_its_configuration(
        self, request: pytest.FixtureRequest, server_fixture: str, entities: bool
    ) -> None:
        server: MCPServer[AppContext] = request.getfixturevalue(server_fixture)

        assert server.instructions == make_instructions(entities=entities)

    @pytest.mark.parametrize("entities", [True, False])
    def test_instructions_fit_the_client_limit(self, entities: bool) -> None:
        text = make_instructions(entities=entities)

        assert len(text) <= INSTRUCTIONS_LIMIT, (
            f"{len(text)} characters; Claude Code drops everything past "
            f"{INSTRUCTIONS_LIMIT}"
        )

    def test_pagination_rules_are_kept_without_entities(self) -> None:
        """The pagination section sat behind the entity sections and was cut off."""
        text = make_instructions(entities=False)

        assert "next_cursor" in text
        assert "`pages`" in text

    def test_entities_are_not_mentioned_without_their_tools(self) -> None:
        assert "project_" not in make_instructions(entities=False)

    @pytest.mark.parametrize(
        ("tool_name", "argument"),
        [
            ("issue_update", "version"),
            ("issue_add_comment", "summonees"),
            ("issue_update_comment", "summonees"),
            ("issues_find", "fields"),
            ("queues_get_all", "fields"),
            ("boards_get_all", "fields"),
            ("boards_get_all", "queue"),
            ("board_get", "fields"),
            ("board_get_sprints", "fields"),
            ("issue_get_changelog", "cursor"),
        ],
    )
    def test_arguments_the_instructions_promise_exist(
        self, mcp_server: MCPServer[AppContext], tool_name: str, argument: str
    ) -> None:
        tools: list[Tool] = mcp_server._tool_manager.list_tools()
        tool = next(t for t in tools if t.name == tool_name)

        assert argument in (tool.parameters or {}).get("properties", {})

    def test_write_capability_is_mentioned(self) -> None:
        """The instructions described a read-only server long after writes landed."""
        assert "Create and edit issues" in make_instructions(entities=False)
