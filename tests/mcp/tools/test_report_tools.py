from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from mcp_tracker.tracker.proto.types.reports import Report, ReportSort
from mcp_tracker.tracker.proto.types.users import User
from tests.mcp.conftest import get_tool_result_content

REPORT = Report.model_validate(
    {
        "id": "6adf76fc",
        "shortId": 160,
        "fields": {"summary": "Export", "entityStatus": "done"},
    }
)
CREATE_ARGS: dict[str, Any] = {
    "summary": "Export",
    "format": "csv",
    "fields": ["key", "summary"],
    "query": "Queue: TEST",
}


class TestReportGet:
    async def test_returns_the_report(
        self, client_session: Client, mock_reports_protocol: AsyncMock
    ) -> None:
        mock_reports_protocol.report_get.return_value = REPORT

        result = await client_session.call_tool("report_get", {"report_id": "160"})

        assert not result.is_error
        assert mock_reports_protocol.report_get.call_args.args == ("160",)
        content = get_tool_result_content(result)
        assert (content["shortId"], content["summary"]) == (160, "Export")


class TestReportsFind:
    async def test_a_login_is_turned_into_a_uid(
        self,
        client_session: Client,
        mock_reports_protocol: AsyncMock,
        mock_users_protocol: AsyncMock,
    ) -> None:
        mock_users_protocol.user_get.return_value = User(uid=1767417737, login="v.k")
        mock_reports_protocol.reports_find.return_value = PaginatedResult[Report](
            values=[REPORT], hits=1, pages=1
        )

        result = await client_session.call_tool(
            "reports_find", {"author": "v.k", "per_page": 10}
        )

        assert not result.is_error
        assert mock_users_protocol.user_get.call_args.args == ("v.k",)
        call = mock_reports_protocol.reports_find.call_args
        assert call.kwargs["author"] == "1767417737"
        assert (call.kwargs["per_page"], call.kwargs["page"]) == (10, 1)
        assert get_tool_result_content(result)["hits"] == 1

    @pytest.mark.parametrize("author", [None, "1767417737"])
    async def test_no_lookup_for_a_uid_or_no_author(
        self,
        client_session: Client,
        mock_reports_protocol: AsyncMock,
        mock_users_protocol: AsyncMock,
        author: str | None,
    ) -> None:
        mock_reports_protocol.reports_find.return_value = PaginatedResult[Report]()

        args = {} if author is None else {"author": author}
        result = await client_session.call_tool("reports_find", args)

        assert not result.is_error
        mock_users_protocol.user_get.assert_not_called()
        assert mock_reports_protocol.reports_find.call_args.kwargs["author"] == author

    async def test_an_unknown_login_is_refused(
        self,
        client_session: Client,
        mock_reports_protocol: AsyncMock,
        mock_users_protocol: AsyncMock,
    ) -> None:
        mock_users_protocol.user_get.return_value = None

        result = await client_session.call_tool("reports_find", {"author": "nobody"})

        assert result.is_error
        mock_reports_protocol.reports_find.assert_not_called()


class TestReportCreate:
    async def test_passes_the_export(
        self, client_session: Client, mock_reports_protocol: AsyncMock
    ) -> None:
        mock_reports_protocol.report_create.return_value = REPORT

        result = await client_session.call_tool(
            "report_create",
            {**CREATE_ARGS, "sorts": [{"order_by": "updated", "order_asc": False}]},
        )

        assert not result.is_error
        call = mock_reports_protocol.report_create.call_args
        assert call.args == ("Export",)
        assert call.kwargs["format"] == "csv"
        assert call.kwargs["fields"] == ["key", "summary"]
        assert call.kwargs["query"] == "Queue: TEST"
        assert (call.kwargs["filter"], call.kwargs["filter_id"]) == (None, None)
        assert call.kwargs["sorts"] == [ReportSort(order_by="updated", order_asc=False)]

    @pytest.mark.parametrize(
        "sources",
        [{}, {"query": "Queue: TEST", "filter_id": 1}],
        ids=["none", "two"],
    )
    async def test_exactly_one_issue_source_is_required(
        self,
        client_session: Client,
        mock_reports_protocol: AsyncMock,
        sources: dict[str, Any],
    ) -> None:
        args = {key: CREATE_ARGS[key] for key in ("summary", "format", "fields")}

        result = await client_session.call_tool("report_create", {**args, **sources})

        assert result.is_error
        mock_reports_protocol.report_create.assert_not_called()

    async def test_unknown_format_is_refused(
        self, client_session: Client, mock_reports_protocol: AsyncMock
    ) -> None:
        result = await client_session.call_tool(
            "report_create", {**CREATE_ARGS, "format": "pdf"}
        )

        assert result.is_error
        mock_reports_protocol.report_create.assert_not_called()

    async def test_refused_under_queue_limits(
        self, client_session_with_limits: Client, mock_reports_protocol: AsyncMock
    ) -> None:
        result = await client_session_with_limits.call_tool(
            "report_create", CREATE_ARGS
        )

        assert result.is_error
        mock_reports_protocol.report_create.assert_not_called()

    async def test_read_only_mode_tool_not_registered(
        self, client_session_read_only: Client, mock_reports_protocol: AsyncMock
    ) -> None:
        result = await client_session_read_only.call_tool("report_create", CREATE_ARGS)

        assert result.is_error
        mock_reports_protocol.report_create.assert_not_called()


class TestReportDelete:
    async def test_deletes(
        self, client_session: Client, mock_reports_protocol: AsyncMock
    ) -> None:
        mock_reports_protocol.report_delete.return_value = None

        result = await client_session.call_tool("report_delete", {"report_id": "160"})

        assert not result.is_error
        assert mock_reports_protocol.report_delete.call_args.args == ("160",)

    async def test_read_only_mode_tool_not_registered(
        self, client_session_read_only: Client, mock_reports_protocol: AsyncMock
    ) -> None:
        result = await client_session_read_only.call_tool(
            "report_delete", {"report_id": "160"}
        )

        assert result.is_error
        mock_reports_protocol.report_delete.assert_not_called()
