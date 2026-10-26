"""TrackerClient methods for the organization's issue fields and their
categories (`v3/fields`, `v3/fields/categories`).

Payloads as the live API answered them on 2026-10-26: a create answers 200
(the reference says 201), an update wants `?version=` (428 without it, 412
for a stale one), and neither a field nor a category can be deleted.
"""

from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    CatalogEmptyUpdate,
    CatalogObjectNotFound,
    CatalogVersionConflict,
    LocalFieldNotFound,
    QueueNotFound,
    TrackerAPIError,
)
from mcp_tracker.tracker.proto.types.fields import FieldCategory, GlobalField
from mcp_tracker.tracker.proto.types.workflows import LocalizedText
from tests.aioresponses_utils import RequestCapture

BASE = "https://api.tracker.yandex.net"
NAME = LocalizedText(ru="MCP test", en="MCP test")
CATEGORY_ID = "6adf5611c2dc6e1bb4414db1"

FIELD = {
    "self": f"{BASE}/v3/fields/mcpTestField",
    "id": "mcpTestField",
    "name": "MCP test",
    "description": "Полигон MCP-сервера",
    "key": "mcpTestField",
    "version": 1,
    "schema": {"type": "string", "required": False},
    "readonly": False,
    "options": True,
    "suggest": False,
    "optionsProvider": {
        "type": "FixedListOptionsProvider",
        "needValidation": True,
        "values": ["альфа", "бета"],
    },
    "queryProvider": {"type": "StringOptionalQueryProvider"},
    "order": 10,
    "category": {
        "self": f"{BASE}/v3/fields/categories/{CATEGORY_ID}",
        "id": CATEGORY_ID,
        "display": "MCP test",
    },
    "hidden": True,
    "type": "standard",
}
CATEGORY = {
    "id": CATEGORY_ID,
    "name": "MCP test",
    "self": f"{BASE}/v3/fields/categories/{CATEGORY_ID}",
    "version": 1,
}


class TestFieldRead:
    async def test_field_get(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/fields/mcpTestField", payload=FIELD)
            field = await tracker_client.field_get("mcpTestField")

        assert isinstance(field, GlobalField)
        assert field.version == 1
        assert field.hidden is True
        assert field.description == "Полигон MCP-сервера"
        assert field.optionsProvider is not None
        assert field.optionsProvider.values == ["альфа", "бета"]

    async def test_field_get_404(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{BASE}/v3/fields/nope",
                status=404,
                payload={"errorMessages": ["Поле не существует."]},
            )
            with pytest.raises(CatalogObjectNotFound) as exc_info:
                await tracker_client.field_get("nope")

        assert exc_info.value.kind == "field"

    async def test_fields_get_categories(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/fields/categories", payload=[CATEGORY])
            categories = await tracker_client.fields_get_categories()

        assert categories == [FieldCategory.model_validate(CATEGORY)]

    async def test_field_category_get(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/fields/categories/{CATEGORY_ID}", payload=CATEGORY)
            category = await tracker_client.field_category_get(CATEGORY_ID)

        assert category.version == 1


class TestFieldCreate:
    async def test_create_sends_the_type_in_full(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=FIELD)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/fields", callback=capture.callback)
            field = await tracker_client.field_create(
                field_id="mcpTestField",
                name=NAME,
                category=CATEGORY_ID,
                type="string",
                description="Полигон MCP-сервера",
                hidden=True,
                options=["альфа", "бета"],
            )

        assert field.id == "mcpTestField"
        capture.assert_called_once()
        capture.last_request.assert_json_body(
            {
                "id": "mcpTestField",
                "name": {"ru": "MCP test", "en": "MCP test"},
                "category": CATEGORY_ID,
                "type": "ru.yandex.startrek.core.fields.StringFieldType",
                "description": "Полигон MCP-сервера",
                "hidden": True,
                "optionsProvider": {
                    "type": "FixedListOptionsProvider",
                    "values": ["альфа", "бета"],
                },
            }
        )

    @pytest.mark.parametrize(
        ("field_type", "api_type", "provider"),
        [
            ("user", "UserFieldType", "FixedUserListOptionsProvider"),
            ("integer", "IntegerFieldType", "FixedListOptionsProvider"),
        ],
    )
    async def test_options_provider_follows_the_type(
        self,
        tracker_client: TrackerClient,
        field_type: Any,
        api_type: str,
        provider: str,
    ) -> None:
        capture = RequestCapture(payload=FIELD)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/fields", callback=capture.callback)
            await tracker_client.field_create(
                field_id="f",
                name=NAME,
                category=CATEGORY_ID,
                type=field_type,
                container=True,
                options=["a"],
            )

        body = capture.last_request.get_json_body()
        assert body["type"] == f"ru.yandex.startrek.core.fields.{api_type}"
        assert body["container"] is True
        assert body["optionsProvider"] == {"type": provider, "values": ["a"]}

    async def test_create_leaves_out_what_is_not_passed(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=FIELD)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/fields", callback=capture.callback)
            await tracker_client.field_create(
                field_id="f", name=NAME, category=CATEGORY_ID, type="duration"
            )

        capture.last_request.assert_json_body(
            {
                "id": "f",
                "name": {"ru": "MCP test", "en": "MCP test"},
                "category": CATEGORY_ID,
                "type": "ru.yandex.startrek.core.fields.TimeTrackingDurationFieldType",
            }
        )

    async def test_category_create(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=201, payload=CATEGORY)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/fields/categories", callback=capture.callback)
            category = await tracker_client.field_category_create(
                name=NAME, order=900, description="Полигон"
            )

        assert category.id == CATEGORY_ID
        capture.last_request.assert_json_body(
            {
                "name": {"ru": "MCP test", "en": "MCP test"},
                "order": 900,
                "description": "Полигон",
            }
        )


class TestFieldUpdate:
    async def test_update_sends_version_and_body(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=FIELD)

        with aioresponses() as m:
            m.patch(
                f"{BASE}/v3/fields/mcpTestField?version=3", callback=capture.callback
            )
            await tracker_client.field_update(
                "mcpTestField",
                version=3,
                category=CATEGORY_ID,
                readonly=False,
                options=["x"],
                user_options=True,
            )

        capture.last_request.assert_param("version", 3)
        capture.last_request.assert_json_body(
            {
                "category": CATEGORY_ID,
                "readonly": False,
                "optionsProvider": {
                    "type": "FixedUserListOptionsProvider",
                    "values": ["x"],
                },
            }
        )

    async def test_category_update(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=CATEGORY)

        with aioresponses() as m:
            m.patch(
                f"{BASE}/v3/fields/categories/{CATEGORY_ID}?version=2",
                callback=capture.callback,
            )
            await tracker_client.field_category_update(
                CATEGORY_ID, version=2, name=NAME, order=901
            )

        capture.last_request.assert_json_body(
            {"name": {"ru": "MCP test", "en": "MCP test"}, "order": 901}
        )

    @pytest.mark.parametrize("method", ["field_update", "field_category_update"])
    async def test_empty_update_is_refused_without_a_request(
        self, tracker_client: TrackerClient, method: str
    ) -> None:
        with aioresponses():
            with pytest.raises(CatalogEmptyUpdate):
                await getattr(tracker_client, method)("x", version=1)

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("field_update", "v3/fields/x"),
            ("field_category_update", "v3/fields/categories/x"),
        ],
    )
    async def test_stale_version_raises_conflict(
        self, tracker_client: TrackerClient, method: str, path: str
    ) -> None:
        with aioresponses() as m:
            m.patch(
                f"{BASE}/{path}?version=1",
                status=412,
                payload={
                    "errorMessages": [
                        "Поле: не удалось сохранить изменения, попробуйте ещё раз."
                    ]
                },
            )
            with pytest.raises(CatalogVersionConflict) as exc_info:
                await getattr(tracker_client, method)("x", version=1, description="d")

        assert exc_info.value.version == 1


LOCAL_FIELD = {
    **FIELD,
    "self": f"{BASE}/v3/localFields/6adf5b36c2dc6e1bb442dffa--locTest",
    "id": "6adf5b36c2dc6e1bb442dffa--locTest",
    "key": "locTest",
    "queue": {"self": f"{BASE}/v3/queues/MCPTMR", "id": "9", "key": "MCPTMR"},
    "type": "local",
}


class TestLocalFields:
    async def test_get_by_key(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/queues/MCPTMR/localFields/locTest", payload=LOCAL_FIELD)
            field = await tracker_client.queue_get_local_field("MCPTMR", "locTest")

        assert field.id == "6adf5b36c2dc6e1bb442dffa--locTest"
        assert field.key == "locTest"

    async def test_get_404(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/queues/MCPTMR/localFields/nope", status=404)
            with pytest.raises(LocalFieldNotFound) as exc_info:
                await tracker_client.queue_get_local_field("MCPTMR", "nope")

        assert exc_info.value.field_key == "nope"

    async def test_create(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=LOCAL_FIELD)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/queues/MCPTMR/localFields", callback=capture.callback)
            await tracker_client.queue_create_local_field(
                "MCPTMR",
                field_key="locTest",
                name=NAME,
                category=CATEGORY_ID,
                type="user",
                options=["i.ivanov"],
            )

        capture.last_request.assert_json_body(
            {
                "id": "locTest",
                "name": {"ru": "MCP test", "en": "MCP test"},
                "category": CATEGORY_ID,
                "type": "ru.yandex.startrek.core.fields.UserFieldType",
                "optionsProvider": {
                    "type": "FixedUserListOptionsProvider",
                    "values": ["i.ivanov"],
                },
            }
        )

    async def test_create_in_unknown_queue(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(f"{BASE}/v3/queues/NOPE/localFields", status=404)
            with pytest.raises(QueueNotFound):
                await tracker_client.queue_create_local_field(
                    "NOPE", field_key="x", name=NAME, category="c", type="date"
                )

    async def test_update_sends_no_version(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=LOCAL_FIELD)

        with aioresponses() as m:
            m.patch(
                f"{BASE}/v3/queues/MCPTMR/localFields/locTest",
                callback=capture.callback,
            )
            await tracker_client.queue_update_local_field(
                "MCPTMR", "locTest", description="d", options=["a", "b", "c"]
            )

        assert not capture.last_request.params
        capture.last_request.assert_json_body(
            {
                "description": "d",
                "optionsProvider": {
                    "type": "FixedListOptionsProvider",
                    "values": ["a", "b", "c"],
                },
            }
        )

    async def test_empty_update_is_refused_without_a_request(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses():
            with pytest.raises(CatalogEmptyUpdate):
                await tracker_client.queue_update_local_field("MCPTMR", "locTest")

    async def test_update_404(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.patch(f"{BASE}/v3/queues/MCPTMR/localFields/nope", status=404)
            with pytest.raises(LocalFieldNotFound):
                await tracker_client.queue_update_local_field(
                    "MCPTMR", "nope", description="d"
                )


class TestQueueDeleteTag:
    async def test_delete_tag(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.post(f"{BASE}/v3/queues/MCPTMR/tags/_remove", callback=capture.callback)
            await tracker_client.queue_delete_tag("MCPTMR", "старый")

        capture.last_request.assert_json_body({"tag": "старый"})

    async def test_tag_in_use_is_passed_through(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                f"{BASE}/v3/queues/MCPTMR/tags/_remove",
                status=422,
                payload={"errorMessages": ["Тег ещё используется."]},
            )
            with pytest.raises(TrackerAPIError) as exc_info:
                await tracker_client.queue_delete_tag("MCPTMR", "x")

        assert "Тег ещё используется" in str(exc_info.value)
