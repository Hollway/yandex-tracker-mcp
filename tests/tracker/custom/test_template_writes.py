"""Issue and comment template writes - undocumented endpoints, verified on the
live API on 2026-10-27."""

import re
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    CommentTemplateNotFound,
    IssueTemplateNotFound,
    QueueNotFound,
    TemplateEmptyUpdate,
    TemplateVersionConflict,
)
from mcp_tracker.tracker.proto.types.inputs import ChecklistItemInput
from tests.aioresponses_utils import RequestCapture

API = "https://api.tracker.yandex.net/v3"

ISSUE_TEMPLATE: dict[str, Any] = {
    "id": 1,
    "version": 2,
    "name": "Bug report",
    "queue": {"id": "14", "key": "TEST", "display": "Test"},
    "fieldTemplates": {"summary": "[Bug] "},
    "checklistItems": [],
    "metricItems": [],
}

COMMENT_TEMPLATE: dict[str, Any] = {
    "id": 1,
    "version": 1,
    "name": "Ack",
    "template": "Looking into it",
    "summonees": [{"id": "1", "display": "User"}],
    "maillistSummonees": [],
}


class TestIssueTemplateWrites:
    async def test_create_sends_the_template(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(status=201, payload=ISSUE_TEMPLATE)
        with aioresponses() as m:
            m.post(f"{API}/issueTemplates", callback=capture.callback)

            result = await tracker_client.issue_template_create(
                name="Bug report",
                queue="TEST",
                field_templates={"summary": "[Bug] ", "type": "bug"},
                checklist_items=[
                    ChecklistItemInput(text="Reproduce"),
                    ChecklistItemInput(text="Fix", checked=True, assignee="login"),
                ],
            )

        assert result.id == 1
        capture.last_request.assert_json_body(
            {
                "name": "Bug report",
                "queue": "TEST",
                "fieldTemplates": {"summary": "[Bug] ", "type": "bug"},
                "checklistItems": [
                    {"text": "Reproduce"},
                    {"text": "Fix", "checked": True, "assignee": "login"},
                ],
            }
        )

    async def test_create_without_a_queue_sends_none(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(status=201, payload=ISSUE_TEMPLATE)
        with aioresponses() as m:
            m.post(f"{API}/issueTemplates", callback=capture.callback)

            await tracker_client.issue_template_create(name="Mine")

        capture.last_request.assert_json_body({"name": "Mine"})

    async def test_create_in_an_unknown_queue(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(f"{API}/issueTemplates", status=404)

            with pytest.raises(QueueNotFound):
                await tracker_client.issue_template_create(name="x", queue="NOPE")

    async def test_update_sends_the_version_and_the_change(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=ISSUE_TEMPLATE)
        with aioresponses() as m:
            m.patch(
                re.compile(rf"{API}/issueTemplates/1\?version=2$"),
                callback=capture.callback,
            )

            await tracker_client.issue_template_update(
                "1", version=2, field_templates={"tags": ["x"]}
            )

        capture.last_request.assert_param("version", 2)
        capture.last_request.assert_json_body({"fieldTemplates": {"tags": ["x"]}})

    async def test_an_empty_update_is_refused_unsent(
        self, tracker_client: TrackerClient
    ) -> None:
        with pytest.raises(TemplateEmptyUpdate):
            await tracker_client.issue_template_update("1", version=2)

    @pytest.mark.parametrize("status", [409, 412])
    async def test_a_stale_version_is_a_conflict(
        self, tracker_client: TrackerClient, status: int
    ) -> None:
        with aioresponses() as m:
            m.patch(re.compile(rf"{API}/issueTemplates/1\?.*"), status=status)

            with pytest.raises(TemplateVersionConflict) as exc_info:
                await tracker_client.issue_template_update("1", version=1, name="x")

        assert "issue_template_get" in str(exc_info.value)

    async def test_delete_sends_the_version(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(status=204)
        with aioresponses() as m:
            m.delete(
                re.compile(rf"{API}/issueTemplates/1\?version=2$"),
                callback=capture.callback,
            )

            await tracker_client.issue_template_delete("1", version=2)

        capture.assert_called_once()

    async def test_delete_of_an_unknown_template(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(re.compile(rf"{API}/issueTemplates/9\?.*"), status=404)

            with pytest.raises(IssueTemplateNotFound):
                await tracker_client.issue_template_delete("9", version=1)


class TestCommentTemplateWrites:
    async def test_create_sends_the_template(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(status=201, payload=COMMENT_TEMPLATE)
        with aioresponses() as m:
            m.post(f"{API}/commentTemplates", callback=capture.callback)

            result = await tracker_client.comment_template_create(
                name="Ack",
                queue="TEST",
                text="Looking into it",
                summonees=["login"],
                maillist_summonees=["team@example.com"],
            )

        assert result.template == "Looking into it"
        capture.last_request.assert_json_body(
            {
                "name": "Ack",
                "queue": "TEST",
                "template": "Looking into it",
                "summonees": ["login"],
                "maillistSummonees": ["team@example.com"],
            }
        )

    async def test_update_sends_the_version_and_the_change(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=COMMENT_TEMPLATE)
        with aioresponses() as m:
            m.patch(
                re.compile(rf"{API}/commentTemplates/1\?version=1$"),
                callback=capture.callback,
            )

            await tracker_client.comment_template_update("1", version=1, text="New")

        capture.last_request.assert_json_body({"template": "New"})

    async def test_an_empty_update_is_refused_unsent(
        self, tracker_client: TrackerClient
    ) -> None:
        with pytest.raises(TemplateEmptyUpdate):
            await tracker_client.comment_template_update("1", version=1)

    async def test_a_stale_version_on_delete_is_a_conflict(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(re.compile(rf"{API}/commentTemplates/1\?.*"), status=412)

            with pytest.raises(TemplateVersionConflict) as exc_info:
                await tracker_client.comment_template_delete("1", version=1)

        assert "comment_template_get" in str(exc_info.value)

    async def test_update_of_an_unknown_template(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.patch(re.compile(rf"{API}/commentTemplates/9\?.*"), status=404)

            with pytest.raises(CommentTemplateNotFound):
                await tracker_client.comment_template_update("9", version=1, name="x")
