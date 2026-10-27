import re
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import TrackerAPIError
from mcp_tracker.tracker.proto.types.reports import ReportSort
from tests.aioresponses_utils import RequestCapture

REPORTS_URL = "https://api.tracker.yandex.net/v3/entities/report/"
REPORT_URL = re.compile(
    r"^https://api\.tracker\.yandex\.net/v3/entities/report/6adf76fc(\?.*)?$"
)
SEARCH_URL = re.compile(
    r"^https://api\.tracker\.yandex\.net/v3/entities/report/_search(\?.*)?$"
)

CREATED_BY = {
    "self": "https://api.tracker.yandex.net/v3/users/1767417737",
    "id": "1767417737",
    "display": "Валерий Криворот",
}


def report_data(**fields: Any) -> dict[str, Any]:
    """A report as Tracker answers it (verified 2026-10-26), `fields` nested."""
    data: dict[str, Any] = {
        "self": "https://api.tracker.yandex.net/v3/entities/report/6adf76fc",
        "id": "6adf76fc",
        "version": 7,
        "shortId": 160,
        "entityType": "report",
        "createdBy": CREATED_BY,
        "createdAt": "2026-10-26T15:51:24.788+0000",
        "updatedAt": "2026-10-26T15:51:25.393+0000",
    }
    if fields:
        data["fields"] = fields
    return data


class TestReportCreate:
    async def test_sends_an_issue_export(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=report_data())

        with aioresponses() as m:
            m.post(REPORTS_URL, callback=capture.callback)

            report = await tracker_client.report_create(
                "Export",
                format="csv",
                fields=["key", "summary"],
                query="Queue: TEST",
                sorts=[ReportSort(order_by="key", order_asc=False)],
            )

        capture.last_request.assert_json_body(
            {
                "fields": {
                    "summary": "Export",
                    "parameters": {
                        "type": "issueFilterExport",
                        "format": "csv",
                        "filter": {
                            "query": "Queue: TEST",
                            "sorts": [{"orderBy": "key", "orderAsc": False}],
                        },
                        "fields": ["key", "summary"],
                    },
                }
            }
        )
        # The create answer carries no `fields`; the name is the one sent.
        assert (report.id, report.short_id, report.summary) == (
            "6adf76fc",
            160,
            "Export",
        )

    @pytest.mark.parametrize(
        ("kwargs", "issue_filter"),
        [
            ({"filter": {"queue": "TEST"}}, {"filter": {"queue": "TEST"}}),
            ({"filter_id": 12345}, {"filterId": 12345}),
        ],
        ids=["filter", "filter-id"],
    )
    async def test_the_other_issue_sources(
        self,
        tracker_client: TrackerClient,
        kwargs: dict[str, Any],
        issue_filter: dict[str, Any],
    ) -> None:
        capture = RequestCapture(payload=report_data())

        with aioresponses() as m:
            m.post(REPORTS_URL, callback=capture.callback)

            await tracker_client.report_create(
                "Export", format="xlsx", fields=["key"], **kwargs
            )

        body = capture.last_request.get_json_body()
        assert body["fields"]["parameters"]["filter"] == issue_filter


class TestReportGet:
    async def test_lifts_the_nested_fields(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(
            payload=report_data(
                summary="Export",
                entityStatus="done",
                parameters={"format": "csv", "type": "issueFilterExport"},
            )
        )

        with aioresponses() as m:
            m.get(REPORT_URL, callback=capture.callback)

            report = await tracker_client.report_get("6adf76fc")

        assert capture.last_request.params["fields"] == (
            "summary,entityStatus,parameters"
        )
        dumped = report.model_dump(mode="json", by_alias=True)
        assert dumped["summary"] == "Export"
        assert dumped["entityStatus"] == "done"
        assert dumped["parameters"]["format"] == "csv"
        assert "fields" not in dumped

    async def test_unknown_report_keeps_trackers_message(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(
                REPORT_URL,
                status=404,
                payload={"errorMessages": ["сущность [6adf76fc] не существуют"]},
            )

            with pytest.raises(TrackerAPIError) as exc_info:
                await tracker_client.report_get("6adf76fc")

        assert "не существуют" in str(exc_info.value)


class TestReportsFind:
    async def test_newest_first_with_totals_from_the_body(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(
            payload={
                "hits": 3,
                "pages": 2,
                "values": [report_data(summary="Export", entityStatus="done")],
            }
        )

        with aioresponses() as m:
            m.post(SEARCH_URL, callback=capture.callback)

            found = await tracker_client.reports_find(
                author="1767417737", per_page=2, page=1
            )

        capture.last_request.assert_json_body(
            {
                "orderBy": "createdAt",
                "orderAsc": False,
                "filter": {"author": "1767417737"},
            }
        )
        assert capture.last_request.params["fields"] == "summary,entityStatus"
        assert str(capture.last_request.params["perPage"]) == "2"
        assert (found.hits, found.pages) == (3, 2)
        assert found.values[0].summary == "Export"

    async def test_without_author_sends_no_filter(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload={"hits": 0, "pages": 0})

        with aioresponses() as m:
            m.post(SEARCH_URL, callback=capture.callback)

            found = await tracker_client.reports_find()

        assert "filter" not in capture.last_request.get_json_body()
        assert found.values == []


class TestReportDelete:
    async def test_deletes(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(REPORT_URL, callback=capture.callback)

            await tracker_client.report_delete("6adf76fc")

        capture.assert_request_count(1)
