"""TrackerClient methods for the organization's catalogue: statuses,
resolutions, issue types and priorities.

Payloads follow the API reference (not checked against the live API): a write
takes the name as `{"ru", "en"}` and an update its `version` as a query
parameter. The reference shows some answers as an object and others as a
one-element array holding it, so both are tested.
"""

from typing import Any

import pytest
from aioresponses import aioresponses
from pydantic import BaseModel

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    CatalogEmptyUpdate,
    CatalogObjectNotFound,
    CatalogVersionConflict,
)
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.issue_types import IssueType
from mcp_tracker.tracker.proto.types.priorities import Priority
from mcp_tracker.tracker.proto.types.resolutions import Resolution
from mcp_tracker.tracker.proto.types.statuses import Status
from mcp_tracker.tracker.proto.types.workflows import LocalizedText
from tests.aioresponses_utils import RequestCapture

BASE = "https://api.tracker.yandex.net"
NAME = LocalizedText(ru="Приостановлен", en="On pause")

STATUS = {
    "self": f"{BASE}/v3/statuses/29",
    "id": 29,
    "version": 2,
    "key": "pause",
    "name": "Приостановлен",
    "description": "Issue is paused",
    "order": 350,
    "type": "paused",
}
RESOLUTION = {
    "self": f"{BASE}/v3/resolutions/9",
    "id": 9,
    "key": "wontFix",
    "version": 2,
    "name": "Не будет исправлено",
    "description": "Issue won't be fixed",
    "order": 90,
}
ISSUE_TYPE = {
    "self": f"{BASE}/v3/issuetypes/23",
    "id": 23,
    "version": 2,
    "key": "client",
    "name": "Покупатель",
}
PRIORITY = {
    "self": f"{BASE}/v3/priorities/6",
    "id": 6,
    "key": "one",
    "version": 2,
    "name": "Низкий",
    "description": "Описание",
    "order": 60,
}

# (method prefix, API path, payload, model)
CATALOGS = [
    pytest.param("status", "statuses", STATUS, Status, id="status"),
    pytest.param("resolution", "resolutions", RESOLUTION, Resolution, id="resolution"),
    pytest.param("issue_type", "issuetypes", ISSUE_TYPE, IssueType, id="issue_type"),
    pytest.param("priority", "priorities", PRIORITY, Priority, id="priority"),
]


class TestCatalogGet:
    @pytest.mark.parametrize("wrapped", [False, True], ids=["object", "array"])
    @pytest.mark.parametrize(("prefix", "path", "payload", "model"), CATALOGS)
    async def test_reads_one_object(
        self,
        tracker_client: TrackerClient,
        yandex_auth: YandexAuth,
        prefix: str,
        path: str,
        payload: dict[str, Any],
        model: type[BaseModel],
        wrapped: bool,
    ) -> None:
        capture = RequestCapture(payload=[payload] if wrapped else payload)

        with aioresponses() as m:
            m.get(f"{BASE}/v3/{path}/{payload['key']}", callback=capture.callback)
            result = await getattr(tracker_client, f"{prefix}_get")(
                payload["key"], auth=yandex_auth
            )

        assert isinstance(result, model)
        assert result.model_dump()["version"] == 2
        capture.assert_called_once()
        capture.last_request.assert_header("Authorization", "OAuth auth-token")

    @pytest.mark.parametrize(("prefix", "path", "payload", "model"), CATALOGS)
    async def test_404_raises_not_found(
        self,
        tracker_client: TrackerClient,
        prefix: str,
        path: str,
        payload: dict[str, Any],
        model: type[BaseModel],
    ) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/{path}/nope", status=404)
            with pytest.raises(CatalogObjectNotFound) as exc_info:
                await getattr(tracker_client, f"{prefix}_get")("nope")

        assert exc_info.value.object_id == "nope"
        assert "nope" in str(exc_info.value)


class TestCatalogCreate:
    @pytest.mark.parametrize("wrapped", [False, True], ids=["object", "array"])
    async def test_status_create(
        self, tracker_client: TrackerClient, wrapped: bool
    ) -> None:
        capture = RequestCapture(status=201, payload=[STATUS] if wrapped else STATUS)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/statuses", callback=capture.callback)
            status = await tracker_client.status_create(
                key="pause",
                name=NAME,
                type="paused",
                description="Issue is paused",
                order=350,
            )

        assert isinstance(status, Status)
        assert status.id == 29
        assert status.type == "paused"
        capture.assert_called_once()
        capture.last_request.assert_json_body(
            {
                "key": "pause",
                "name": {"ru": "Приостановлен", "en": "On pause"},
                "type": "paused",
                "description": "Issue is paused",
                "order": 350,
            }
        )

    @pytest.mark.parametrize(
        ("prefix", "path", "payload", "model", "extra"),
        [
            pytest.param(
                "resolution",
                "resolutions",
                RESOLUTION,
                Resolution,
                {"order": 90},
                id="resolution",
            ),
            pytest.param(
                "issue_type", "issuetypes", ISSUE_TYPE, IssueType, {}, id="issue_type"
            ),
            pytest.param(
                "priority",
                "priorities",
                PRIORITY,
                Priority,
                {"order": 60},
                id="priority",
            ),
        ],
    )
    async def test_create_sends_the_fields_passed(
        self,
        tracker_client: TrackerClient,
        prefix: str,
        path: str,
        payload: dict[str, Any],
        model: type[BaseModel],
        extra: dict[str, Any],
    ) -> None:
        capture = RequestCapture(status=201, payload=payload)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/{path}", callback=capture.callback)
            result = await getattr(tracker_client, f"{prefix}_create")(
                key=payload["key"], name=NAME, description="Описание", **extra
            )

        assert isinstance(result, model)
        capture.last_request.assert_json_body(
            {
                "key": payload["key"],
                "name": {"ru": "Приостановлен", "en": "On pause"},
                "description": "Описание",
                **extra,
            }
        )

    async def test_create_leaves_out_what_is_not_passed(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(status=201, payload=RESOLUTION)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/resolutions", callback=capture.callback)
            await tracker_client.resolution_create(key="wontFix", name=NAME)

        capture.last_request.assert_json_body(
            {"key": "wontFix", "name": {"ru": "Приостановлен", "en": "On pause"}}
        )


class TestCatalogUpdate:
    @pytest.mark.parametrize("wrapped", [False, True], ids=["object", "array"])
    @pytest.mark.parametrize(("prefix", "path", "payload", "model"), CATALOGS)
    async def test_update_sends_version_and_body(
        self,
        tracker_client: TrackerClient,
        prefix: str,
        path: str,
        payload: dict[str, Any],
        model: type[BaseModel],
        wrapped: bool,
    ) -> None:
        capture = RequestCapture(payload=[payload] if wrapped else payload)

        with aioresponses() as m:
            m.patch(
                f"{BASE}/v3/{path}/{payload['key']}?version=1",
                callback=capture.callback,
            )
            result = await getattr(tracker_client, f"{prefix}_update")(
                payload["key"], version=1, name=NAME, description="Описание"
            )

        assert isinstance(result, model)
        capture.assert_called_once()
        capture.last_request.assert_param("version", 1)
        capture.last_request.assert_json_body(
            {
                "name": {"ru": "Приостановлен", "en": "On pause"},
                "description": "Описание",
            }
        )

    async def test_status_update_sends_order_and_type(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=STATUS)

        with aioresponses() as m:
            m.patch(f"{BASE}/v3/statuses/29?version=1", callback=capture.callback)
            await tracker_client.status_update(
                "29", version=1, order=400, type="inProgress"
            )

        capture.last_request.assert_json_body({"order": 400, "type": "inProgress"})

    @pytest.mark.parametrize(("prefix", "path", "payload", "model"), CATALOGS)
    async def test_empty_update_is_refused_without_a_request(
        self,
        tracker_client: TrackerClient,
        prefix: str,
        path: str,
        payload: dict[str, Any],
        model: type[BaseModel],
    ) -> None:
        with aioresponses():
            with pytest.raises(CatalogEmptyUpdate):
                await getattr(tracker_client, f"{prefix}_update")(
                    payload["key"], version=1
                )

    @pytest.mark.parametrize("http_status", [409, 412])
    @pytest.mark.parametrize(("prefix", "path", "payload", "model"), CATALOGS)
    async def test_stale_version_raises_conflict(
        self,
        tracker_client: TrackerClient,
        prefix: str,
        path: str,
        payload: dict[str, Any],
        model: type[BaseModel],
        http_status: int,
    ) -> None:
        with aioresponses() as m:
            m.patch(f"{BASE}/v3/{path}/{payload['key']}?version=1", status=http_status)
            with pytest.raises(CatalogVersionConflict) as exc_info:
                await getattr(tracker_client, f"{prefix}_update")(
                    payload["key"], version=1, description="x"
                )

        assert exc_info.value.version == 1
        assert exc_info.value.object_id == payload["key"]

    @pytest.mark.parametrize(("prefix", "path", "payload", "model"), CATALOGS)
    async def test_404_raises_not_found(
        self,
        tracker_client: TrackerClient,
        prefix: str,
        path: str,
        payload: dict[str, Any],
        model: type[BaseModel],
    ) -> None:
        with aioresponses() as m:
            m.patch(f"{BASE}/v3/{path}/nope?version=1", status=404)
            with pytest.raises(CatalogObjectNotFound):
                await getattr(tracker_client, f"{prefix}_update")(
                    "nope", version=1, description="x"
                )
