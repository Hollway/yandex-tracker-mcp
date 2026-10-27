from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import DashboardNotFound
from mcp_tracker.tracker.proto.types.dashboards import (
    CycleTimeBucket,
    CycleTimeLines,
    CycleTimeWidgetInput,
)
from tests.aioresponses_utils import RequestCapture

DASHBOARDS_URL = "https://api.tracker.yandex.net/v3/dashboards"
DASHBOARD_URL = "https://api.tracker.yandex.net/v3/dashboards/107"
WIDGET_URL = "https://api.tracker.yandex.net/v3/dashboards/107/widgets/cycleTime"

USER = {
    "self": "https://api.tracker.yandex.net/v3/users/1767417737",
    "id": "1767417737",
    "display": "Валерий Криворот",
}


def dashboard_data(**extra: Any) -> dict[str, Any]:
    """A dashboard as Tracker answers it (verified 2026-10-27)."""
    return {
        "id": 107,
        "self": "https://api.tracker.yandex.net/v3/dashboards/107",
        "version": 1,
        "name": "MCP probe",
        "createdBy": USER,
        "createdAt": "2026-10-27T06:53:16.448+0000",
        "layout": "one-column",
        "owner": USER,
        **extra,
    }


class TestDashboardCreate:
    async def test_sends_name_layout_and_owner(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(status=201, payload=dashboard_data())

        with aioresponses() as m:
            m.post(DASHBOARDS_URL, callback=capture.callback)

            dashboard = await tracker_client.dashboard_create(
                "MCP probe", layout="two-columns", owner="i.ivanov"
            )

        capture.last_request.assert_json_body(
            {"name": "MCP probe", "layout": "two-columns", "owner": "i.ivanov"}
        )
        assert (dashboard.id, dashboard.name) == (107, "MCP probe")

    async def test_omitted_options_are_not_sent(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(status=201, payload=dashboard_data())

        with aioresponses() as m:
            m.post(DASHBOARDS_URL, callback=capture.callback)

            await tracker_client.dashboard_create("MCP probe")

        capture.last_request.assert_json_body({"name": "MCP probe"})


class TestDashboardGet:
    async def test_reads_the_widgets(self, tracker_client: TrackerClient) -> None:
        payload = dashboard_data(
            widgets=[{"self": "...", "id": "751", "display": "MCP cycle"}]
        )

        with aioresponses() as m:
            m.get(DASHBOARD_URL, payload=payload)

            dashboard = await tracker_client.dashboard_get(107)

        assert dashboard.widgets is not None
        assert [(w.id, w.display) for w in dashboard.widgets] == [("751", "MCP cycle")]

    @pytest.mark.parametrize("method", ["get", "delete"])
    async def test_unknown_dashboard_raises_dashboard_not_found(
        self, tracker_client: TrackerClient, method: str
    ) -> None:
        with aioresponses() as m:
            getattr(m, method)(DASHBOARD_URL, status=404)

            with pytest.raises(DashboardNotFound):
                if method == "get":
                    await tracker_client.dashboard_get(107)
                else:
                    await tracker_client.dashboard_delete(107)


class TestDashboardsList:
    async def test_one_page_of_500_with_the_total(
        self, tracker_client: TrackerClient
    ) -> None:
        """`page` is ignored by Tracker and `perPage` capped at 500 (2026-10-27)."""
        with aioresponses() as m:
            m.post(
                f"{DASHBOARDS_URL}/_search?perPage=500",
                payload=[dashboard_data()],
                headers={"X-Total-Count": "32"},
            )

            found = await tracker_client.dashboards_list()

        assert found.hits == 32
        assert [d.id for d in found.values] == [107]


class TestDashboardDelete:
    async def test_deletes(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(DASHBOARD_URL, callback=capture.callback)

            await tracker_client.dashboard_delete(107)

        capture.assert_request_count(1)


class TestDashboardAddCycleTimeWidget:
    async def test_sends_statuses_as_keys_and_drops_what_is_unset(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(
            status=201,
            payload={
                "id": 751,
                "version": 1,
                "description": "MCP cycle",
                "dashboard": {"id": "107", "display": "MCP probe"},
                "fromStatuses": [{"id": "1", "key": "open", "display": "Открыт"}],
                "toStatuses": [{"id": "8", "key": "closed", "display": "Закрыт"}],
                "bucket": {"type": "days", "count": 1},
                "query": "Queue: TEST",
                "datasetInfo": {"status": "created"},
                "lines": {"movingAverage": True, "percentile": [90.0, 75.0]},
                "start": "now()-2w",
                "mode": "common-lines",
            },
        )

        with aioresponses() as m:
            m.post(WIDGET_URL, callback=capture.callback)

            widget = await tracker_client.dashboard_add_cycle_time_widget(
                107,
                CycleTimeWidgetInput(
                    description="MCP cycle",
                    query="Queue: TEST",
                    from_statuses=["open"],
                    to_statuses=["closed"],
                    excluded_statuses=["paused"],
                    bucket=CycleTimeBucket(unit="days", count=1),
                    lines=CycleTimeLines(moving_average=True, percentile=[75, 90]),
                    calendar_id=3,
                    start="now()-2w",
                    mode="common-lines",
                ),
            )

        capture.last_request.assert_json_body(
            {
                "description": "MCP cycle",
                "query": "Queue: TEST",
                "fromStatuses": [{"key": "open"}],
                "toStatuses": [{"key": "closed"}],
                "excludedStatuses": [{"key": "paused"}],
                "bucket": {"unit": "days", "count": 1},
                "lines": {"movingAverage": True, "percentile": [75.0, 90.0]},
                "calendar": 3,
                "start": "now()-2w",
                "mode": "common-lines",
            }
        )
        assert widget.id == 751
        assert widget.to_statuses is not None
        assert widget.to_statuses[0].key == "closed"

    async def test_unknown_dashboard_raises_dashboard_not_found(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(WIDGET_URL, status=404)

            with pytest.raises(DashboardNotFound):
                await tracker_client.dashboard_add_cycle_time_widget(
                    107, CycleTimeWidgetInput(description="x", query="Queue: TEST")
                )
