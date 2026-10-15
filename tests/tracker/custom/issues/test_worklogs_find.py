import datetime
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import WorklogSearchTooLarge
from tests.aioresponses_utils import RequestCapture

SEARCH_URL = "https://api.tracker.yandex.net/v3/worklog/_search"


def worklog_data(worklog_id: int, issue_key: str) -> dict[str, Any]:
    """A record as `POST v3/worklog/_search` answers it (documentation example)."""
    return {
        "self": f"https://api.tracker.yandex.net/v3/issues/{issue_key}/worklog/{worklog_id}",
        "id": worklog_id,
        "version": 1402121720882,
        "issue": {
            "self": f"https://api.tracker.yandex.net/v3/issues/{issue_key}",
            "id": "515ec9eae4b09cfa00000000",
            "key": issue_key,
            "display": "My issue",
        },
        "comment": "My comment",
        "createdBy": {
            "self": "https://api.tracker.yandex.net/v3/users/1100000000",
            "id": "1100000000",
            "display": "Имя Фамилия",
        },
        "createdAt": "2026-10-06T08:42:06.258+0000",
        "updatedAt": "2026-10-06T08:42:06.258+0000",
        "start": "2026-10-06T08:41:58.000+0000",
        "duration": "PT1H30M",
    }


class TestWorklogsFind:
    async def test_sends_the_author_and_the_entry_window(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=[worklog_data(1, "TEST-1")])

        with aioresponses() as m:
            m.post(SEARCH_URL, callback=capture.callback)

            result = await tracker_client.worklogs_find(
                created_by="i.ivanov",
                created_from=datetime.datetime(2026, 10, 6, tzinfo=datetime.UTC),
                created_to=datetime.datetime(2026, 10, 13, tzinfo=datetime.UTC),
            )

        capture.assert_called_once()
        capture.last_request.assert_json_body(
            {
                "createdBy": "i.ivanov",
                "createdAt": {
                    "from": "2026-10-06T00:00:00.000000+0000",
                    "to": "2026-10-13T00:00:00.000000+0000",
                },
            }
        )
        assert [(w.id, w.issue.key if w.issue else None) for w in result] == [
            (1, "TEST-1")
        ]
        assert result[0].duration == datetime.timedelta(hours=1, minutes=30)

    async def test_omitted_filters_are_not_sent(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=[])

        with aioresponses() as m:
            m.post(SEARCH_URL, callback=capture.callback)

            result = await tracker_client.worklogs_find(created_by="i.ivanov")

        capture.last_request.assert_json_body({"createdBy": "i.ivanov"})
        assert result == []

    async def test_follows_the_next_link_with_the_same_body(
        self, tracker_client: TrackerClient
    ) -> None:
        second = RequestCapture(payload=[worklog_data(2, "TEST-2")])

        with aioresponses() as m:
            # A callback's result drops the mocked headers, so the first page is
            # a plain payload: its Link header is what is under test.
            m.post(
                SEARCH_URL,
                payload=[worklog_data(1, "TEST-1")],
                headers={"Link": f'<{SEARCH_URL}?page=2&perPage=50>; rel="next"'},
            )
            m.post(f"{SEARCH_URL}?page=2&perPage=50", callback=second.callback)

            result = await tracker_client.worklogs_find(created_by="i.ivanov")

        assert [w.id for w in result] == [1, 2]
        second.last_request.assert_json_body({"createdBy": "i.ivanov"})
        second.last_request.assert_params({"page": "2", "perPage": "50"})

    async def test_a_next_link_that_never_ends_is_cut_off(
        self, tracker_client: TrackerClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "mcp_tracker.tracker.custom.client._MAX_WORKLOG_SEARCH_PAGES", 2
        )

        with aioresponses() as m:
            m.post(
                SEARCH_URL,
                payload=[],
                headers={"Link": f'<{SEARCH_URL}?page=2>; rel="next"'},
            )
            m.post(
                f"{SEARCH_URL}?page=2",
                payload=[],
                headers={"Link": f'<{SEARCH_URL}?page=2>; rel="next"'},
                repeat=True,
            )

            with pytest.raises(WorklogSearchTooLarge) as exc_info:
                await tracker_client.worklogs_find(created_by="i.ivanov")

        assert exc_info.value.pages == 2
