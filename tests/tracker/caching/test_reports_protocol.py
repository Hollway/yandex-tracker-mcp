from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_tracker.tracker.caching.client import make_cached_protocols
from mcp_tracker.tracker.proto.common import YandexAuth


class TestCachingReportsProtocol:
    @pytest.fixture
    def mock_original(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def caching_reports_protocol(self, mock_original: AsyncMock) -> Any:
        return make_cached_protocols({"ttl": 300}).reports(mock_original)

    async def test_report_create_calls_original(
        self,
        caching_reports_protocol: Any,
        mock_original: AsyncMock,
        yandex_auth: YandexAuth,
    ) -> None:
        result = await caching_reports_protocol.report_create(
            "Export",
            format="csv",
            fields=["key"],
            query="Queue: TEST",
            auth=yandex_auth,
        )

        mock_original.report_create.assert_called_once_with(
            "Export",
            format="csv",
            fields=["key"],
            query="Queue: TEST",
            filter=None,
            filter_id=None,
            sorts=None,
            auth=yandex_auth,
        )
        assert result == mock_original.report_create.return_value

    async def test_report_get_is_not_cached(
        self, caching_reports_protocol: Any, mock_original: AsyncMock
    ) -> None:
        await caching_reports_protocol.report_get("160")
        await caching_reports_protocol.report_get("160")

        assert mock_original.report_get.call_count == 2

    async def test_reports_find_calls_original(
        self, caching_reports_protocol: Any, mock_original: AsyncMock
    ) -> None:
        result = await caching_reports_protocol.reports_find(author="1", page=2)

        mock_original.reports_find.assert_called_once_with(
            author="1", per_page=50, page=2, auth=None
        )
        assert result == mock_original.reports_find.return_value

    async def test_report_delete_calls_original(
        self, caching_reports_protocol: Any, mock_original: AsyncMock
    ) -> None:
        await caching_reports_protocol.report_delete("160")

        mock_original.report_delete.assert_called_once_with("160", auth=None)
