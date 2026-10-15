import datetime
from unittest.mock import AsyncMock

import pytest
from mcp.client.session import ClientSession
from mcp.types import TextContent

from mcp_tracker.mcp.utils import local_day_end, local_day_start
from mcp_tracker.tracker.proto.types.issues import Worklog
from mcp_tracker.tracker.proto.types.refs import IssueReference
from mcp_tracker.tracker.proto.types.users import User
from tests.mcp.conftest import get_tool_result_content


def worklog(worklog_id: int, issue_key: str, start: datetime.datetime) -> Worklog:
    return Worklog.model_construct(
        id=worklog_id,
        issue=IssueReference.model_construct(key=issue_key),
        start=start,
        duration=datetime.timedelta(hours=1),
    )


def at(day: datetime.date, hour: int) -> datetime.datetime:
    """`hour` o'clock on `day`, local time - the clock the tool counts days by."""
    return local_day_start(day) + datetime.timedelta(hours=hour)


MONDAY = datetime.date(2026, 10, 5)
FRIDAY = datetime.date(2026, 10, 9)


class TestWorklogsFind:
    async def test_defaults_to_the_current_user(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
        mock_users_protocol: AsyncMock,
        sample_user: User,
    ) -> None:
        mock_users_protocol.user_get_current.return_value = sample_user
        mock_issues_protocol.worklogs_find.return_value = []

        result = await client_session.call_tool(
            "worklogs_find", {"start_from": MONDAY.isoformat()}
        )

        assert not result.isError
        call_kwargs = mock_issues_protocol.worklogs_find.call_args.kwargs
        assert call_kwargs["created_by"] == sample_user.login

    async def test_start_days_pick_the_work_done_in_them(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.worklogs_find.return_value = [
            worklog(3, "TEST-3", at(FRIDAY + datetime.timedelta(days=1), 10)),
            worklog(1, "TEST-1", at(MONDAY, 9)),
            worklog(2, "TEST-2", at(FRIDAY, 23)),
            worklog(0, "TEST-0", at(MONDAY, 0) - datetime.timedelta(minutes=1)),
        ]

        result = await client_session.call_tool(
            "worklogs_find",
            {
                "author": "i.ivanov",
                "start_from": MONDAY.isoformat(),
                "start_to": FRIDAY.isoformat(),
            },
        )

        assert not result.isError
        # Records entered from Monday on are asked for; their work days are
        # checked here, and the result comes back in the order of the work.
        call_kwargs = mock_issues_protocol.worklogs_find.call_args.kwargs
        assert call_kwargs == {
            "created_by": "i.ivanov",
            "created_from": local_day_start(MONDAY),
            "created_to": None,
            "auth": call_kwargs["auth"],
        }
        assert [w["id"] for w in get_tool_result_content(result)] == [1, 2]

    async def test_created_days_are_passed_to_the_api(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.worklogs_find.return_value = [
            worklog(1, "TEST-1", at(MONDAY, 9))
        ]

        result = await client_session.call_tool(
            "worklogs_find",
            {
                "author": "i.ivanov",
                "created_from": MONDAY.isoformat(),
                "created_to": FRIDAY.isoformat(),
            },
        )

        assert not result.isError
        call_kwargs = mock_issues_protocol.worklogs_find.call_args.kwargs
        assert call_kwargs["created_from"] == local_day_start(MONDAY)
        assert call_kwargs["created_to"] == local_day_end(FRIDAY)
        assert len(get_tool_result_content(result)) == 1

    async def test_a_first_day_is_required(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool("worklogs_find", {"author": "i.ivanov"})

        assert result.isError
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "start_from" in content.text
        mock_issues_protocol.worklogs_find.assert_not_called()

    async def test_issues_outside_the_allowed_queues_are_dropped(
        self,
        client_session_with_limits: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.worklogs_find.return_value = [
            worklog(1, "ALLOWED-1", at(MONDAY, 9)),
            worklog(2, "RESTRICTED-1", at(MONDAY, 10)),
            worklog(3, "permitted-7", at(MONDAY, 11)),
        ]

        result = await client_session_with_limits.call_tool(
            "worklogs_find", {"author": "i.ivanov", "start_from": MONDAY.isoformat()}
        )

        assert not result.isError
        assert [w["id"] for w in get_tool_result_content(result)] == [1, 3]

    @pytest.mark.parametrize("field", ["issue", "duration"])
    async def test_fields_trim_each_entry(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
        field: str,
    ) -> None:
        mock_issues_protocol.worklogs_find.return_value = [
            worklog(1, "TEST-1", at(MONDAY, 9))
        ]

        result = await client_session.call_tool(
            "worklogs_find",
            {
                "author": "i.ivanov",
                "start_from": MONDAY.isoformat(),
                "fields": [field],
            },
        )

        entry = get_tool_result_content(result)[0]
        assert field in entry
        assert "start" not in entry
