"""The queue setting «Доступ для AI инструментов» is honoured as Tracker's own MCP
server honours it: an issue of a queue that forbids AI tools is returned as its
key and `restricted`, single-issue reads are refused, writes still work."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from mcp import Client
from mcp.types import TextContent

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.server import create_mcp_server
from mcp_tracker.mcp.tools._ai_access import queue_forbids_ai
from mcp_tracker.tracker.custom.errors import (
    QueueNotFound,
    TrackerAPIError,
    TrackerAPITimeout,
    TrackerRateLimited,
)
from mcp_tracker.tracker.proto.types.issues import (
    ChangelogEntry,
    ChangelogPage,
    ChecklistItem,
    Issue,
    IssueComment,
    IssueLink,
    Worklog,
)
from mcp_tracker.tracker.proto.types.queues import Queue
from tests.mcp.conftest import (
    create_test_settings,
    get_tool_result_content,
    make_test_lifespan,
    page,
    safe_client_session,
)


def queue(key: str, **settings: Any) -> Queue:
    """A queue as `GET v3/queues/{key}` answers it, with the AI settings given."""
    return Queue.model_validate({"key": key, **settings})


@pytest.fixture
def queues_by_key(mock_queues_protocol: AsyncMock) -> dict[str, Any]:
    """CLOSED forbids AI tools, OPEN allows them."""
    known = {
        "CLOSED": queue("CLOSED", aiAccessLevel="none", noMcp=False),
        "OPEN": queue("OPEN", aiAccessLevel="full", noMcp=False),
    }

    async def queue_get(key: str, **_: Any) -> Any:
        return known[key]

    mock_queues_protocol.queue_get.side_effect = queue_get
    mock_queues_protocol.queues_list.return_value = page(list(known.values()))
    return known


@pytest_asyncio.fixture(loop_scope="function")
async def session(
    mock_app_context: AppContext, queues_by_key: dict[str, Any]
) -> AsyncIterator[Client]:
    server = create_mcp_server(
        settings=create_test_settings(),
        lifespan=make_test_lifespan(mock_app_context),
    )
    async with safe_client_session(server) as connected:
        yield connected


def text(result: Any) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


@pytest.mark.parametrize(
    ("settings", "forbids"),
    [
        pytest.param({"aiAccessLevel": "full", "noMcp": False}, False, id="full"),
        pytest.param({"aiAccessLevel": "none", "noMcp": False}, True, id="none"),
        pytest.param({"aiAccessLevel": "full", "noMcp": True}, True, id="no-mcp"),
        pytest.param({}, False, id="not-reported"),
    ],
)
def test_queue_forbids_ai(settings: dict[str, Any], forbids: bool) -> None:
    assert queue_forbids_ai(queue("Q", **settings)) is forbids


class TestSingleIssueReads:
    async def test_a_forbidding_queue_is_refused(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        result = await session.call_tool("issue_get", {"issue_id": "CLOSED-1"})

        assert result.is_error
        assert "Доступ для AI инструментов" in text(result)
        mock_issues_protocol.issue_get.assert_not_called()

    async def test_an_allowing_queue_is_read(
        self,
        session: Client,
        mock_issues_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_issues_protocol.issue_get_comment.return_value = sample_comment

        result = await session.call_tool(
            "issue_get_comment", {"issue_id": "OPEN-1", "comment_id": 1}
        )

        assert not result.is_error

    async def test_the_setting_is_read_once_per_queue(
        self,
        session: Client,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        for _ in range(3):
            await session.call_tool("issue_get_checklist", {"issue_id": "CLOSED-1"})

        assert mock_queues_protocol.queue_get.call_count == 1

    async def test_writes_still_work(
        self,
        session: Client,
        mock_issues_protocol: AsyncMock,
        sample_comment: IssueComment,
    ) -> None:
        mock_issues_protocol.issue_add_comment.return_value = sample_comment

        result = await session.call_tool(
            "issue_add_comment", {"issue_id": "CLOSED-1", "text": "x"}
        )

        assert not result.is_error

    async def test_an_unreadable_queue_does_not_block(
        self,
        session: Client,
        mock_queues_protocol: AsyncMock,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queue_get.side_effect = QueueNotFound("OTHER")
        mock_issues_protocol.issue_get_checklist.return_value = []

        result = await session.call_tool("issue_get_checklist", {"issue_id": "OTHER-1"})

        assert not result.is_error


INTERNAL_ID = "6ad1d166dc7d9f59dec67d79"


class TestTheQueueTheIssueIsIn:
    """The queue is the one the issue is in, not the one the caller's id names:
    an internal id names none and an old key of a moved issue the wrong one."""

    async def test_issue_get_by_internal_id_is_refused(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-5")

        result = await session.call_tool("issue_get", {"issue_id": INTERNAL_ID})

        assert result.is_error
        assert "Доступ для AI инструментов" in text(result)

    async def test_issue_get_by_the_old_key_of_a_moved_issue_is_refused(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-7")

        result = await session.call_tool("issue_get", {"issue_id": "OPEN-1"})

        assert result.is_error
        assert "`CLOSED`" in text(result)

    async def test_another_read_by_internal_id_reads_the_issue_for_its_queue(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-5")

        result = await session.call_tool(
            "issue_get_checklist", {"issue_id": INTERNAL_ID}
        )

        assert result.is_error
        mock_issues_protocol.issue_get.assert_awaited_once()
        mock_issues_protocol.issue_get_checklist.assert_not_called()

    @pytest.mark.parametrize("tool", ["issue_get_links", "issue_get_remote_links"])
    async def test_links_are_refused(
        self, session: Client, mock_issues_protocol: AsyncMock, tool: str
    ) -> None:
        result = await session.call_tool(tool, {"issue_id": "CLOSED-1"})

        assert result.is_error
        assert "Доступ для AI инструментов" in text(result)


class TestUnreadableSetting:
    """Only "the token cannot read the queue" counts as allowed; any other failure
    says nothing about the setting."""

    async def test_a_403_does_not_block(
        self,
        session: Client,
        mock_queues_protocol: AsyncMock,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queue_get.side_effect = TrackerAPIError(
            status=403, method="GET", url="v3/queues/OTHER", body=""
        )
        mock_issues_protocol.issue_get_checklist.return_value = []

        result = await session.call_tool("issue_get_checklist", {"issue_id": "OTHER-1"})

        assert not result.is_error

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(
                TrackerRateLimited(
                    method="GET",
                    url="v3/queues/OTHER",
                    body="",
                    retries=3,
                    retry_after=None,
                ),
                id="429",
            ),
            pytest.param(
                TrackerAPITimeout(method="GET", url="v3/queues/OTHER", timeout=10),
                id="timeout",
            ),
        ],
    )
    async def test_a_passing_failure_is_raised_and_not_remembered(
        self,
        session: Client,
        mock_queues_protocol: AsyncMock,
        mock_issues_protocol: AsyncMock,
        error: Exception,
    ) -> None:
        mock_queues_protocol.queue_get.side_effect = error
        mock_issues_protocol.issue_get_checklist.return_value = []

        first = await session.call_tool("issue_get_checklist", {"issue_id": "OTHER-1"})
        second = await session.call_tool("issue_get_checklist", {"issue_id": "OTHER-1"})

        assert first.is_error
        assert second.is_error
        assert mock_queues_protocol.queue_get.await_count == 2
        mock_issues_protocol.issue_get_checklist.assert_not_called()


class TestListings:
    async def test_issues_find_keeps_only_the_key(
        self,
        session: Client,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(
            [
                Issue(key="OPEN-1", summary="visible"),
                Issue(key="CLOSED-1", summary="secret"),
            ]
        )

        result = await session.call_tool(
            "issues_find", {"query": "Queue: OPEN, CLOSED", "fields": ["summary"]}
        )

        assert not result.is_error
        values = get_tool_result_content(result)["values"]
        assert values[0]["summary"] == "visible"
        assert values[1] == {"key": "CLOSED-1", "restricted": True}

    async def test_ignored_queues_are_read(
        self,
        mock_app_context: AppContext,
        queues_by_key: dict[str, Any],
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.issue_get_checklist.return_value = []
        server = create_mcp_server(
            settings=create_test_settings().model_copy(
                update={"tracker_ai_access_ignored_queues": {"CLOSED"}}
            ),
            lifespan=make_test_lifespan(mock_app_context),
        )

        async with safe_client_session(server) as connected:
            result = await connected.call_tool(
                "issue_get_checklist", {"issue_id": "CLOSED-1"}
            )

        assert not result.is_error


SECRET = "secret summary"


def ref(key: str) -> dict[str, Any]:
    """An issue as another record names it: id, key and its summary."""
    return {"id": f"id-{key}", "key": key, "display": SECRET}


HIDDEN_REF = {
    "id": "id-CLOSED-7",
    "key": "CLOSED-7",
    "display": None,
    "restricted": True,
}


class TestReferences:
    """An issue that may be read can name one that may not; the summary it
    carries of that one is left out, its key and id stay."""

    async def test_issue_get_hides_a_forbidden_parent(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue.model_validate(
            {"key": "OPEN-1", "parent": ref("CLOSED-7"), "epic": ref("OPEN-2")}
        )

        result = await session.call_tool("issue_get", {"issue_id": "OPEN-1"})

        content = get_tool_result_content(result)
        assert content["parent"] == HIDDEN_REF
        assert content["epic"]["display"] == SECRET

    async def test_issues_find_hides_a_forbidden_parent(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issues_find.return_value = page(
            [Issue.model_validate({"key": "OPEN-1", "parent": ref("CLOSED-7")})]
        )

        result = await session.call_tool(
            "issues_find", {"query": "Queue: OPEN", "fields": ["parent"]}
        )

        assert get_tool_result_content(result)["values"][0]["parent"] == HIDDEN_REF

    async def test_links_hide_a_forbidden_linked_issue(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issues_get_links.return_value = [
            IssueLink.model_validate({"id": 1, "object": ref("CLOSED-7")}),
            IssueLink.model_validate({"id": 2, "object": ref("OPEN-2")}),
        ]

        result = await session.call_tool("issue_get_links", {"issue_id": "OPEN-1"})

        links = get_tool_result_content(result)
        assert links[0]["object"] == HIDDEN_REF
        assert links[1]["object"]["display"] == SECRET

    async def test_changelog_hides_a_forbidden_issue_in_a_field_change(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get_changelog.return_value = ChangelogPage(
            entries=[
                ChangelogEntry.model_validate(
                    {
                        "id": "c1",
                        "fields": [
                            {
                                "field": {"id": "parent"},
                                "from": None,
                                "to": ref("CLOSED-7"),
                            }
                        ],
                    }
                )
            ]
        )

        result = await session.call_tool("issue_get_changelog", {"issue_id": "OPEN-1"})

        change = get_tool_result_content(result)["entries"][0]["fields"][0]
        assert change["to"] == HIDDEN_REF

    async def test_worklogs_find_hides_the_summary(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.worklogs_find.return_value = [
            Worklog.model_validate(
                {"id": 1, "issue": ref("CLOSED-7"), "comment": "secret comment"}
            )
        ]

        result = await session.call_tool(
            "worklogs_find", {"author": "someone", "created_from": "2026-10-28"}
        )

        worklog = get_tool_result_content(result)[0]
        assert worklog["issue"] == HIDDEN_REF
        assert "comment" not in worklog

    async def test_nothing_is_hidden_when_no_queue_forbids_ai(
        self,
        session: Client,
        mock_issues_protocol: AsyncMock,
        mock_queues_protocol: AsyncMock,
    ) -> None:
        mock_queues_protocol.queues_list.return_value = page([])
        mock_issues_protocol.issue_get.return_value = Issue.model_validate(
            {"key": "OPEN-1", "parent": ref("OPEN-7")}
        )

        result = await session.call_tool("issue_get", {"issue_id": "OPEN-1"})

        assert get_tool_result_content(result)["parent"]["display"] == SECRET


class TestWriteAnswers:
    """A write to an issue of a forbidding queue goes through, but its answer
    leaves the content out - otherwise any write would read the issue."""

    async def test_update_answers_with_key_id_and_version(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_update.return_value = Issue.model_validate(
            {
                "key": "CLOSED-1",
                "id": "abc",
                "version": 7,
                "summary": SECRET,
                "description": "secret description",
            }
        )

        result = await session.call_tool(
            "issue_update", {"issue_id": "CLOSED-1", "tags": ["x"]}
        )

        assert not result.is_error
        assert get_tool_result_content(result) == {
            "key": "CLOSED-1",
            "id": "abc",
            "version": 7,
            "restricted": True,
        }
        mock_issues_protocol.issue_update.assert_awaited_once()

    async def test_create_in_a_forbidding_queue_answers_with_the_key(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_create.return_value = Issue.model_validate(
            {"key": "CLOSED-5", "version": 1, "summary": SECRET}
        )

        result = await session.call_tool(
            "issue_create", {"queue": "CLOSED", "summary": SECRET}
        )

        assert get_tool_result_content(result) == {
            "key": "CLOSED-5",
            "version": 1,
            "restricted": True,
        }

    async def test_update_of_an_allowed_issue_hides_a_forbidden_parent(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_update.return_value = Issue.model_validate(
            {"key": "OPEN-1", "summary": "visible", "parent": ref("CLOSED-7")}
        )

        result = await session.call_tool(
            "issue_update", {"issue_id": "OPEN-1", "parent": "CLOSED-7"}
        )

        content = get_tool_result_content(result)
        assert content["summary"] == "visible"
        assert content["parent"] == HIDDEN_REF

    async def test_checklist_write_keeps_only_ids_and_checks(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-1")
        mock_issues_protocol.issue_add_checklist_items.return_value = [
            ChecklistItem.model_validate(
                {
                    "id": "i1",
                    "text": "secret item",
                    "checked": True,
                    "assignee": {"id": "1"},
                }
            )
        ]

        result = await session.call_tool(
            "issue_add_checklist_items",
            {"issue_id": "CLOSED-1", "items": [{"text": "new"}]},
        )

        assert get_tool_result_content(result) == [
            {"id": "i1", "text": "", "checked": True}
        ]

    async def test_worklog_write_hides_comment_and_summary(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_get.return_value = Issue(key="CLOSED-7")
        mock_issues_protocol.issue_add_worklog.return_value = Worklog.model_validate(
            {"id": 1, "issue": ref("CLOSED-7"), "comment": "secret comment"}
        )

        result = await session.call_tool(
            "issue_add_worklog", {"issue_id": "CLOSED-7", "duration": "PT1H"}
        )

        worklog = get_tool_result_content(result)
        assert worklog["issue"] == HIDDEN_REF
        assert "comment" not in worklog

    async def test_link_to_a_forbidden_issue_hides_its_summary(
        self, session: Client, mock_issues_protocol: AsyncMock
    ) -> None:
        mock_issues_protocol.issue_add_link.return_value = IssueLink.model_validate(
            {"id": 1, "object": ref("CLOSED-7")}
        )

        result = await session.call_tool(
            "issue_add_link",
            {"issue_id": "OPEN-1", "relationship": "relates", "issue": "CLOSED-7"},
        )

        assert get_tool_result_content(result)["object"] == HIDDEN_REF
