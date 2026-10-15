from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import IssueNotFound
from tests.aioresponses_utils import RequestCapture

LINKS_URL = "https://api.tracker.yandex.net/v3/issues/TEST-1/remotelinks"


@pytest.fixture
def remote_link_data() -> dict[str, Any]:
    """A remote link as the documentation shows it."""
    return {
        "self": f"{LINKS_URL}/51",
        "id": 51,
        "type": {"id": "relates", "inward": "Связана", "outward": "Связана"},
        "direction": "outward",
        "object": {
            "self": "https://api.tracker.yandex.net/v3/applications/ru.yandex.bitbucket/objects/repo/pr/7",
            "id": "repo/pr/7",
            "key": "repo/pr/7",
            "application": {
                "id": "ru.yandex.bitbucket",
                "type": "ru.yandex.bitbucket",
                "name": "Bitbucket",
            },
        },
    }


class TestApplicationsList:
    async def test_lists_applications(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/applications",
                payload=[
                    {
                        "self": "https://api.tracker.yandex.net/v3/applications/my-app",
                        "id": "my-app",
                        "type": "my-app",
                        "name": "Application name",
                    }
                ],
            )

            result = await tracker_client.applications_list()

        assert [(a.id, a.name) for a in result] == [("my-app", "Application name")]


class TestIssueRemoteLinks:
    async def test_get(
        self, tracker_client: TrackerClient, remote_link_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(LINKS_URL, payload=[remote_link_data])

            result = await tracker_client.issue_get_remote_links("TEST-1")

        assert result[0].id == 51
        assert result[0].object is not None
        assert result[0].object["key"] == "repo/pr/7"

    async def test_add_sends_the_documented_body(
        self, tracker_client: TrackerClient, remote_link_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=remote_link_data)

        with aioresponses() as m:
            m.post(LINKS_URL, callback=capture.callback)

            result = await tracker_client.issue_add_remote_link(
                "TEST-1", origin="ru.yandex.bitbucket", key="repo/pr/7"
            )

        capture.last_request.assert_json_body(
            {
                "relationship": "RELATES",
                "key": "repo/pr/7",
                "origin": "ru.yandex.bitbucket",
            }
        )
        assert not capture.last_request.params
        assert result.id == 51

    async def test_add_with_backlink(
        self, tracker_client: TrackerClient, remote_link_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(status=201, payload=remote_link_data)

        with aioresponses() as m:
            m.post(f"{LINKS_URL}?backlink=true", callback=capture.callback)

            await tracker_client.issue_add_remote_link(
                "TEST-1", origin="ru.yandex.bitbucket", key="repo/pr/7", backlink=True
            )

        capture.last_request.assert_param("backlink", "true")

    async def test_delete(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(f"{LINKS_URL}/51", callback=capture.callback)

            await tracker_client.issue_delete_remote_link("TEST-1", 51)

        capture.assert_called_once()

    async def test_unknown_issue(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(LINKS_URL, status=404)

            with pytest.raises(IssueNotFound):
                await tracker_client.issue_get_remote_links("TEST-1")
