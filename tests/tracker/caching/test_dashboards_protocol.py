from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_tracker.tracker.caching.client import make_cached_protocols
from mcp_tracker.tracker.proto.types.dashboards import CycleTimeWidgetInput


class TestCachingDashboardsProtocol:
    @pytest.fixture
    def mock_original(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def caching_dashboards_protocol(self, mock_original: AsyncMock) -> Any:
        return make_cached_protocols({"ttl": 300}).dashboards(mock_original)

    async def test_dashboard_create_calls_original(
        self, caching_dashboards_protocol: Any, mock_original: AsyncMock
    ) -> None:
        result = await caching_dashboards_protocol.dashboard_create(
            "MCP probe", layout="two-columns"
        )

        mock_original.dashboard_create.assert_called_once_with(
            "MCP probe", layout="two-columns", owner=None, auth=None
        )
        assert result == mock_original.dashboard_create.return_value

    async def test_reads_are_not_cached(
        self, caching_dashboards_protocol: Any, mock_original: AsyncMock
    ) -> None:
        await caching_dashboards_protocol.dashboard_get(107)
        await caching_dashboards_protocol.dashboard_get(107)
        await caching_dashboards_protocol.dashboards_list()
        await caching_dashboards_protocol.dashboards_list()

        assert mock_original.dashboard_get.call_count == 2
        assert mock_original.dashboards_list.call_count == 2

    async def test_dashboard_delete_calls_original(
        self, caching_dashboards_protocol: Any, mock_original: AsyncMock
    ) -> None:
        await caching_dashboards_protocol.dashboard_delete(107)

        mock_original.dashboard_delete.assert_called_once_with(107, auth=None)

    async def test_add_cycle_time_widget_calls_original(
        self, caching_dashboards_protocol: Any, mock_original: AsyncMock
    ) -> None:
        widget = CycleTimeWidgetInput(description="x", query="Queue: TEST")

        result = await caching_dashboards_protocol.dashboard_add_cycle_time_widget(
            107, widget
        )

        mock_original.dashboard_add_cycle_time_widget.assert_called_once_with(
            107, widget, auth=None
        )
        assert result == mock_original.dashboard_add_cycle_time_widget.return_value
