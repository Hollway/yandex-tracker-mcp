import re

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import YandexTrackerError
from mcp_tracker.tracker.proto.types.entities import EntityType
from tests.aioresponses_utils import RequestCapture

ENTITY_TYPES: list[EntityType] = ["project", "portfolio", "goal"]

ATTACHMENT = {
    "self": "https://api.tracker.yandex.net/v3/attachments/8021",
    "id": "8021",
    "name": "mcp-test.txt",
    "content": "https://api.tracker.yandex.net/v3/attachments/8021/mcp-test.txt",
    "createdBy": {"id": "1", "display": "Author"},
    "createdAt": "2026-10-26T14:54:11.542+0000",
    "mimetype": "text/plain",
    "size": 13,
    "commentId": "6adf6999886bbf472fec4443",
}


class TestEntityGetAttachments:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_parses_attachments(
        self, tracker_client: TrackerClient, entity_type: EntityType
    ) -> None:
        with aioresponses() as m:
            m.get(
                f"https://api.tracker.yandex.net/v3/entities/{entity_type}/e1/attachments",
                payload=[ATTACHMENT],
            )
            attachments = await tracker_client.entity_get_attachments(entity_type, "e1")

        assert len(attachments) == 1
        assert attachments[0].id == "8021"
        assert attachments[0].mimetype == "text/plain"
        assert attachments[0].comment_id == "6adf6999886bbf472fec4443"
        assert attachments[0].model_dump(by_alias=True)["commentId"] == (
            "6adf6999886bbf472fec4443"
        )


class TestEntityDeleteAttachment:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_deletes(
        self, tracker_client: TrackerClient, entity_type: EntityType
    ) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(
                re.compile(
                    rf"^https://api\.tracker\.yandex\.net/v3/entities/{entity_type}/"
                    r"e1/attachments/8021$"
                ),
                callback=capture.callback,
            )
            await tracker_client.entity_delete_attachment(entity_type, "e1", "8021")

        capture.assert_called_once()

    async def test_unknown_attachment_raises_tracker_text(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(
                "https://api.tracker.yandex.net/v3/entities/goal/g1/attachments/9",
                status=404,
                payload={"errorMessages": ["Вложений 9 не существуют."]},
            )
            with pytest.raises(YandexTrackerError, match="Вложений 9"):
                await tracker_client.entity_delete_attachment("goal", "g1", "9")
