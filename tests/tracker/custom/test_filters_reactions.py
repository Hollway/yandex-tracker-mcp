"""Saved filters, comment reactions, issue suggest, queue forms and trigger
delete on the HTTP layer.

Payloads are what the live API answered on 2026-10-26 (AGENTS.md, *Saved
filters* and the neighbouring bullets).
"""

import re
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    CommentNotFound,
    FilterConditionsConflict,
    FilterEmptyUpdate,
    FilterNotFound,
    QueueNotFound,
    TrackerAPIError,
    TriggerNotFound,
)
from mcp_tracker.tracker.proto.types.filters import FilterSort
from tests.aioresponses_utils import RequestCapture

API = "https://api.tracker.yandex.net/v3"
FILTER_URL = f"{API}/filters/10"
COMMENT_URL = f"{API}/issues/ORG-14/comments/64399"
USER = {"self": f"{API}/users/1", "id": "1", "display": "Валерий Криворот"}


@pytest.fixture
def filter_data() -> dict[str, Any]:
    return {
        "id": 10,
        "self": FILTER_URL,
        "name": "mcp temp filter",
        "filter": {"queue": "MCPTMT"},
        "sorts": [
            {
                "field": {
                    "self": f"{API}/fields/createdAt",
                    "id": "createdAt",
                    "display": "Создано",
                },
                "isAscending": False,
            }
        ],
        "fields": [{"self": f"{API}/fields/key", "id": "key", "display": "Ключ"}],
        "favorite": False,
        "permissions": {
            "WRITE": {"users": [USER], "groups": [], "roles": []},
            "READ": {"users": [], "groups": [], "roles": []},
        },
        "owner": USER,
    }


@pytest.fixture
def comment_data() -> dict[str, Any]:
    return {
        "self": COMMENT_URL,
        "id": 64399,
        "longId": "6ad1d17fdc7d9f59dec682e2",
        "text": "Проверка",
        "createdBy": USER,
        "reactionsCount": {"like": 1},
        "ownReactions": ["like"],
        "version": 2,
        "type": "standard",
        "transport": "internal",
    }


class TestFilters:
    async def test_reads_a_filter(
        self, tracker_client: TrackerClient, filter_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(FILTER_URL, payload=filter_data)

            result = await tracker_client.filter_get(10)

        assert result.id == 10
        assert result.filter == {"queue": "MCPTMT"}
        assert result.owner is not None and result.owner.id == "1"
        # Sort keys and columns come back as field references.
        assert result.sorts is not None and result.sorts[0].field is not None
        assert result.sorts[0].field.id == "createdAt"
        assert result.fields is not None and result.fields[0].id == "key"

    async def test_unknown_filter(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(FILTER_URL, status=404)

            with pytest.raises(FilterNotFound):
                await tracker_client.filter_get(10)

    async def test_creates_a_filter(
        self, tracker_client: TrackerClient, filter_data: dict[str, Any]
    ) -> None:
        # The live API answers 200, not the 201 of the reference.
        capture = RequestCapture(payload=filter_data)

        with aioresponses() as m:
            m.post(f"{API}/filters", callback=capture.callback)

            result = await tracker_client.filter_create(
                name="mcp temp filter",
                query="Queue: MCPTMT",
                sorts=[FilterSort(field="created", isAscending=False)],
                fields=["key", "summary"],
            )

        assert result.id == 10
        capture.last_request.assert_json_body(
            {
                "name": "mcp temp filter",
                "query": "Queue: MCPTMT",
                "sorts": [{"field": "created", "isAscending": False}],
                "fields": ["key", "summary"],
            }
        )

    async def test_query_and_filter_together_are_refused(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses():
            with pytest.raises(FilterConditionsConflict):
                await tracker_client.filter_create(
                    name="F", query="Queue: Q", filter={"queue": "Q"}
                )

    async def test_updates_only_what_is_passed(
        self, tracker_client: TrackerClient, filter_data: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload=filter_data)

        with aioresponses() as m:
            m.patch(FILTER_URL, callback=capture.callback)

            await tracker_client.filter_update(10, filter={"queue": "ORG"})

        capture.last_request.assert_json_body({"filter": {"queue": "ORG"}})
        assert not capture.last_request.params

    async def test_empty_update_is_refused(self, tracker_client: TrackerClient) -> None:
        with aioresponses():
            with pytest.raises(FilterEmptyUpdate):
                await tracker_client.filter_update(10)

    async def test_update_of_an_unknown_filter(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.patch(FILTER_URL, status=404)

            with pytest.raises(FilterNotFound):
                await tracker_client.filter_update(10, name="x")

    async def test_deletes_through_v3(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(FILTER_URL, callback=capture.callback)

            await tracker_client.filter_delete(10)

        capture.assert_called_once()

    async def test_delete_of_an_unknown_filter(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(FILTER_URL, status=404)

            with pytest.raises(FilterNotFound):
                await tracker_client.filter_delete(10)


class TestSearchByFilter:
    @pytest.mark.parametrize(
        ("query", "filter_id", "body"),
        [
            pytest.param(None, 10, {"filterId": 10}, id="filter"),
            pytest.param(
                "Queue: ORG",
                10,
                {"query": "Queue: ORG", "filterId": 10},
                id="both",
            ),
            pytest.param("Queue: ORG", None, {"query": "Queue: ORG"}, id="query"),
        ],
    )
    async def test_find_sends_the_filter_id(
        self,
        tracker_client: TrackerClient,
        query: str | None,
        filter_id: int | None,
        body: dict[str, Any],
    ) -> None:
        capture = RequestCapture(payload=[])

        with aioresponses() as m:
            m.post(re.compile(rf"{API}/issues/_search.*"), callback=capture.callback)

            await tracker_client.issues_find(query, filter_id=filter_id)

        capture.last_request.assert_json_body(body)

    async def test_count_sends_the_filter_id(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(body="4")

        with aioresponses() as m:
            m.post(f"{API}/issues/_count", callback=capture.callback)

            assert await tracker_client.issues_count(filter_id=10) == 4

        capture.last_request.assert_json_body({"filterId": 10})

    async def test_unknown_filter_id_passes_trackers_text(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                re.compile(rf"{API}/issues/_search.*"),
                status=422,
                payload={"errorMessages": ["Фильтр не существует."]},
            )

            with pytest.raises(TrackerAPIError, match="Фильтр не существует"):
                await tracker_client.issues_find(filter_id=999)


class TestCommentReactions:
    @pytest.mark.parametrize(
        ("method", "http_method"),
        [
            pytest.param("issue_add_comment_reaction", "post", id="add"),
            pytest.param("issue_delete_comment_reaction", "delete", id="delete"),
        ],
    )
    async def test_returns_the_comment_with_its_reactions(
        self,
        tracker_client: TrackerClient,
        comment_data: dict[str, Any],
        method: str,
        http_method: str,
    ) -> None:
        capture = RequestCapture(payload=comment_data)

        with aioresponses() as m:
            getattr(m, http_method)(
                f"{COMMENT_URL}/reactions/LIKE", callback=capture.callback
            )

            result = await getattr(tracker_client, method)("ORG-14", 64399, "LIKE")

        capture.assert_called_once()
        assert result.reactions_count == {"like": 1}
        assert result.own_reactions == ["like"]

    async def test_reacts_by_long_id(
        self, tracker_client: TrackerClient, comment_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.post(
                f"{API}/issues/ORG-14/comments/6ad1d17fdc7d9f59dec682e2/reactions/OK",
                payload=comment_data,
            )

            result = await tracker_client.issue_add_comment_reaction(
                "ORG-14", "6ad1d17fdc7d9f59dec682e2", "OK"
            )

        assert result.id == 64399

    async def test_unknown_comment(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(f"{COMMENT_URL}/reactions/LIKE", status=404)

            with pytest.raises(CommentNotFound):
                await tracker_client.issue_add_comment_reaction("ORG-14", 64399, "LIKE")

    async def test_a_repeated_reaction_passes_trackers_text(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                f"{COMMENT_URL}/reactions/LIKE",
                status=422,
                payload={
                    "errorMessages": [
                        "Эта реакция уже была добавлена к комментарию, или "
                        "комментарий был удалён."
                    ]
                },
            )

            with pytest.raises(TrackerAPIError, match="уже была добавлена"):
                await tracker_client.issue_add_comment_reaction("ORG-14", 64399, "LIKE")


class TestIssuesSuggest:
    async def test_asks_for_key_summary_and_status(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(
            payload=[
                {
                    "self": f"{API}/issues/ORG-14",
                    "id": "6ad1d166dc7d9f59dec67d79",
                    "key": "ORG-14",
                    "version": 3,
                    "summary": "Тест MCP",
                    "status": {"id": "1", "key": "open", "display": "Открыт"},
                    "favorite": False,
                }
            ]
        )

        with aioresponses() as m:
            m.get(re.compile(rf"{API}/issues/_suggest.*"), callback=capture.callback)

            result = await tracker_client.issues_suggest("Тест")

        capture.last_request.assert_params(
            {"input": "Тест", "full": "true", "fields": "key,summary,status"}
        )
        assert [issue.key for issue in result] == ["ORG-14"]
        assert result[0].summary == "Тест MCP"


class TestQueueFormsAndTriggerDelete:
    async def test_reads_the_forms(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{API}/queues/ORG/forms",
                payload={
                    "queue": {"id": "1", "key": "ORG", "display": "spro-it"},
                    "forms": [{"id": 7, "name": "Заявка", "path": "abc", "extra": 1}],
                    "version": 0,
                    "showDefaultCreationForm": True,
                },
            )

            result = await tracker_client.queue_get_forms("ORG")

        assert result.showDefaultCreationForm is True
        assert result.forms[0].name == "Заявка"
        # A form's other keys are passed through as they come.
        assert result.forms[0].model_dump()["extra"] == 1

    async def test_forms_of_an_unknown_queue(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(f"{API}/queues/NOPE/forms", status=404)

            with pytest.raises(QueueNotFound):
                await tracker_client.queue_get_forms("NOPE")

    async def test_deletes_a_trigger(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(f"{API}/queues/MCPTMT/triggers/15", callback=capture.callback)

            await tracker_client.queue_delete_trigger("MCPTMT", 15)

        capture.assert_called_once()
        assert not capture.last_request.params

    async def test_delete_of_an_unknown_trigger(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(f"{API}/queues/MCPTMT/triggers/15", status=404)

            with pytest.raises(TriggerNotFound):
                await tracker_client.queue_delete_trigger("MCPTMT", 15)
