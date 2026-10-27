import re
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    EntityItemEmptyUpdate,
    EntityItemNotFound,
)
from mcp_tracker.tracker.proto.types.entities import EntityType
from tests.aioresponses_utils import RequestCapture

ENTITY_TYPES: list[EntityType] = ["project", "portfolio", "goal"]

WIDGET = {"id": "m1", "text": "Burndown", "url": "https://example.com/w"}
NOTE = {"id": "m2", "text": "Note", "url": None}


def entity_url(entity_type: str) -> re.Pattern[str]:
    return re.compile(
        rf"^https://api\.tracker\.yandex\.net/v3/entities/{entity_type}/e1(\?.*)?$"
    )


def entity(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": "e1", "fields": {"metricItems": items}}


class TestEntityAddMetric:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_sends_add_and_returns_the_list(
        self, tracker_client: TrackerClient, entity_type: EntityType
    ) -> None:
        capture = RequestCapture(payload=entity([WIDGET]))

        with aioresponses() as m:
            m.patch(entity_url(entity_type), callback=capture.callback)
            metrics = await tracker_client.entity_add_metric(
                entity_type, "e1", text="Burndown", url="https://example.com/w"
            )

        capture.last_request.assert_param("fields", "metricItems")
        capture.last_request.assert_json_body(
            {
                "fields": {
                    "metricItems": {
                        "add": {"text": "Burndown", "url": "https://example.com/w"}
                    }
                }
            }
        )
        assert [metric.id for metric in metrics] == ["m1"]

    async def test_without_url(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=entity([NOTE]))

        with aioresponses() as m:
            m.patch(entity_url("goal"), callback=capture.callback)
            await tracker_client.entity_add_metric("goal", "e1", text="Note")

        capture.last_request.assert_json_body(
            {"fields": {"metricItems": {"add": {"text": "Note"}}}}
        )


class TestEntityUpdateMetric:
    async def test_rewrites_the_list(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=entity([WIDGET, NOTE]))

        with aioresponses() as m:
            m.get(entity_url("project"), payload=entity([WIDGET, NOTE]))
            m.patch(entity_url("project"), callback=capture.callback)
            await tracker_client.entity_update_metric(
                "project", "e1", "m2", url="https://example.com/n"
            )

        capture.last_request.assert_json_body(
            {
                "fields": {
                    "metricItems": [
                        {"text": "Burndown", "url": "https://example.com/w"},
                        {"text": "Note", "url": "https://example.com/n"},
                    ]
                }
            }
        )

    async def test_unknown_id_is_refused(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(entity_url("project"), payload=entity([WIDGET]))
            with pytest.raises(EntityItemNotFound, match="No metric 'm9'"):
                await tracker_client.entity_update_metric(
                    "project", "e1", "m9", text="x"
                )

    async def test_empty_update_is_refused(self, tracker_client: TrackerClient) -> None:
        with pytest.raises(EntityItemEmptyUpdate):
            await tracker_client.entity_update_metric("project", "e1", "m1")


class TestEntityDeleteMetric:
    @pytest.mark.parametrize("item", [WIDGET, NOTE], ids=["with-url", "no-url"])
    async def test_removes_the_whole_object(
        self, tracker_client: TrackerClient, item: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=entity([]))

        with aioresponses() as m:
            m.get(entity_url("portfolio"), payload=entity([WIDGET, NOTE]))
            m.patch(entity_url("portfolio"), callback=capture.callback)
            metrics = await tracker_client.entity_delete_metric(
                "portfolio", "e1", item["id"]
            )

        capture.last_request.assert_json_body(
            {"fields": {"metricItems": {"remove": item}}}
        )
        assert metrics == []

    async def test_unknown_id_is_refused(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(entity_url("portfolio"), payload={"id": "e1"})
            with pytest.raises(EntityItemNotFound):
                await tracker_client.entity_delete_metric("portfolio", "e1", "m1")
