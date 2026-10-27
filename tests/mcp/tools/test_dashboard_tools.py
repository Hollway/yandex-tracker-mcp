from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.types.dashboards import (
    CycleTimeBucket,
    CycleTimeWidget,
    CycleTimeWidgetInput,
    Dashboard,
)
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from tests.mcp.conftest import get_tool_result_content

DASHBOARD = Dashboard.model_validate(
    {
        "id": 107,
        "name": "MCP probe",
        "layout": "one-column",
        "widgets": [{"id": "751", "display": "MCP cycle"}],
    }
)
WIDGET = CycleTimeWidget.model_validate(
    {"id": 751, "description": "MCP cycle", "query": "Queue: TEST"}
)
WIDGET_ARGS: dict[str, Any] = {
    "dashboard_id": 107,
    "description": "MCP cycle",
    "query": "Queue: TEST",
}


class TestDashboardGet:
    async def test_returns_the_dashboard(
        self, client_session: Client, mock_dashboards_protocol: AsyncMock
    ) -> None:
        mock_dashboards_protocol.dashboard_get.return_value = DASHBOARD

        result = await client_session.call_tool("dashboard_get", {"dashboard_id": 107})

        assert not result.is_error
        assert mock_dashboards_protocol.dashboard_get.call_args.args == (107,)
        content = get_tool_result_content(result)
        assert content["widgets"] == [{"id": "751", "display": "MCP cycle"}]


class TestDashboardsGetAll:
    async def test_returns_the_listing(
        self, client_session: Client, mock_dashboards_protocol: AsyncMock
    ) -> None:
        mock_dashboards_protocol.dashboards_list.return_value = PaginatedResult[
            Dashboard
        ](values=[DASHBOARD], hits=1, pages=1)

        result = await client_session.call_tool("dashboards_get_all", {})

        assert not result.is_error
        assert get_tool_result_content(result)["values"][0]["id"] == 107


class TestDashboardCreate:
    async def test_passes_the_options(
        self, client_session: Client, mock_dashboards_protocol: AsyncMock
    ) -> None:
        mock_dashboards_protocol.dashboard_create.return_value = DASHBOARD

        result = await client_session.call_tool(
            "dashboard_create",
            {"name": "MCP probe", "layout": "two-columns", "owner": "i.ivanov"},
        )

        assert not result.is_error
        call = mock_dashboards_protocol.dashboard_create.call_args
        assert call.args == ("MCP probe",)
        assert (call.kwargs["layout"], call.kwargs["owner"]) == (
            "two-columns",
            "i.ivanov",
        )

    async def test_unknown_layout_is_refused(
        self, client_session: Client, mock_dashboards_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "dashboard_create", {"name": "x", "layout": "bad-layout"}
        )

        assert result.is_error
        mock_dashboards_protocol.dashboard_create.assert_not_called()

    async def test_read_only_mode_tool_not_registered(
        self, client_session_read_only: Client, mock_dashboards_protocol: AsyncMock
    ) -> None:
        result = await client_session_read_only.call_tool(
            "dashboard_create", {"name": "x"}
        )

        assert result.is_error
        mock_dashboards_protocol.dashboard_create.assert_not_called()


class TestDashboardDelete:
    async def test_deletes(
        self, client_session: Client, mock_dashboards_protocol: AsyncMock
    ) -> None:
        mock_dashboards_protocol.dashboard_delete.return_value = None

        result = await client_session.call_tool(
            "dashboard_delete", {"dashboard_id": 107}
        )

        assert not result.is_error
        assert mock_dashboards_protocol.dashboard_delete.call_args.args == (107,)


class TestDashboardAddCycleTimeWidget:
    async def test_builds_the_widget(
        self, client_session: Client, mock_dashboards_protocol: AsyncMock
    ) -> None:
        mock_dashboards_protocol.dashboard_add_cycle_time_widget.return_value = WIDGET

        result = await client_session.call_tool(
            "dashboard_add_cycle_time_widget",
            {
                **WIDGET_ARGS,
                "from_statuses": ["open"],
                "to_statuses": ["closed"],
                "bucket": {"unit": "weeks", "count": 2},
                "mode": "status-lines",
            },
        )

        assert not result.is_error
        call = mock_dashboards_protocol.dashboard_add_cycle_time_widget.call_args
        assert call.args == (
            107,
            CycleTimeWidgetInput(
                description="MCP cycle",
                query="Queue: TEST",
                from_statuses=["open"],
                to_statuses=["closed"],
                bucket=CycleTimeBucket(unit="weeks", count=2),
                mode="status-lines",
            ),
        )
        assert get_tool_result_content(result)["id"] == 751

    @pytest.mark.parametrize(
        "sources",
        [{"query": None}, {"filter_id": 5}],
        ids=["none", "two"],
    )
    async def test_exactly_one_issue_source_is_required(
        self,
        client_session: Client,
        mock_dashboards_protocol: AsyncMock,
        sources: dict[str, Any],
    ) -> None:
        args = {**WIDGET_ARGS, **sources}

        result = await client_session.call_tool(
            "dashboard_add_cycle_time_widget",
            {key: value for key, value in args.items() if value is not None},
        )

        assert result.is_error
        mock_dashboards_protocol.dashboard_add_cycle_time_widget.assert_not_called()

    async def test_refused_under_queue_limits(
        self,
        client_session_with_limits: Client,
        mock_dashboards_protocol: AsyncMock,
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "dashboard_add_cycle_time_widget", WIDGET_ARGS
        )

        assert result.is_error
        mock_dashboards_protocol.dashboard_add_cycle_time_widget.assert_not_called()
