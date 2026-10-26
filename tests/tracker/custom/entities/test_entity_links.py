import re

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import YandexTrackerError
from mcp_tracker.tracker.proto.types.entities import EntityType
from tests.aioresponses_utils import RequestCapture

ENTITY_TYPES: list[EntityType] = ["project", "portfolio", "goal"]


def links_url(entity_type: str, entity_id: str) -> re.Pattern[str]:
    return re.compile(
        rf"^https://api\.tracker\.yandex\.net/v3/entities/{entity_type}/"
        rf"{entity_id}/links(\?.*)?$"
    )


class TestEntityGetLinks:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_parses_links(
        self, tracker_client: TrackerClient, entity_type: EntityType
    ) -> None:
        capture = RequestCapture(
            payload=[
                {
                    "type": "depends on",
                    "linkFieldValues": {"id": "b1", "shortId": 2, "summary": "B"},
                },
                {"type": "works towards", "linkFieldValues": {"id": "g1"}},
            ]
        )

        with aioresponses() as m:
            m.get(links_url(entity_type, "e1"), callback=capture.callback)
            links = await tracker_client.entity_get_links(entity_type, "e1")

        assert [link.type for link in links] == ["depends on", "works towards"]
        assert links[0].linkFieldValues == {"id": "b1", "shortId": 2, "summary": "B"}
        capture.last_request.assert_param("fields", "id,shortId,summary,entityStatus")

    @pytest.mark.parametrize(
        "fields,expected",
        [
            (["summary", "lead"], "id,summary,lead"),
            (["lead", "id"], "lead,id"),
        ],
    )
    async def test_always_asks_for_the_id(
        self, tracker_client: TrackerClient, fields: list[str], expected: str
    ) -> None:
        capture = RequestCapture(payload=[])

        with aioresponses() as m:
            m.get(links_url("project", "e1"), callback=capture.callback)
            await tracker_client.entity_get_links("project", "e1", fields=fields)

        capture.last_request.assert_param("fields", expected)

    async def test_unknown_field_raises_tracker_text(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(
                links_url("goal", "g1"),
                status=422,
                payload={"errorMessages": ["поля [bogus] не существуют"]},
            )
            with pytest.raises(YandexTrackerError, match=r"поля \[bogus\]"):
                await tracker_client.entity_get_links("goal", "g1", fields=["bogus"])


class TestEntityDeleteLink:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_sends_right(
        self, tracker_client: TrackerClient, entity_type: EntityType
    ) -> None:
        # Tracker answers a deleted link with 200 and a `null` body.
        capture = RequestCapture(body="null")

        with aioresponses() as m:
            m.delete(links_url(entity_type, "e1"), callback=capture.callback)
            await tracker_client.entity_delete_link(entity_type, "e1", "e2")

        capture.last_request.assert_param("right", "e2")

    async def test_missing_link_raises_tracker_text(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(
                links_url("project", "e1"),
                status=422,
                payload={"errorMessages": ["Связь не существует."]},
            )
            with pytest.raises(YandexTrackerError, match="Связь не существует"):
                await tracker_client.entity_delete_link("project", "e1", "e2")
