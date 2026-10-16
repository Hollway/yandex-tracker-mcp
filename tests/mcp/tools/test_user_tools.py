import datetime
from unittest.mock import AsyncMock

from mcp import Client

from mcp_tracker.mcp.utils import local_day_end, local_day_start
from mcp_tracker.tracker.proto.types.users import (
    Absence,
    AbsenceUser,
    User,
    UserAbsences,
)
from tests.mcp.conftest import get_tool_result_content, page


class TestUsersGetAll:
    async def test_returns_users(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_users: list[User],
    ) -> None:
        mock_users_protocol.users_list.return_value = page(
            sample_users, hits=489, pages=10
        )

        result = await client_session.call_tool("users_get_all", {})

        assert not result.is_error
        mock_users_protocol.users_list.assert_called_once()
        content = get_tool_result_content(result)
        assert len(content["values"]) == len(sample_users)
        assert content["values"][0]["login"] == sample_users[0].login
        assert content["values"][0]["display"] == sample_users[0].display
        assert content["hits"] == 489
        assert content["pages"] == 10

    async def test_with_pagination(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_users: list[User],
    ) -> None:
        mock_users_protocol.users_list.return_value = page(
            sample_users, hits=489, pages=10
        )

        result = await client_session.call_tool(
            "users_get_all", {"page": 2, "per_page": 25}
        )

        assert not result.is_error
        call_kwargs = mock_users_protocol.users_list.call_args.kwargs
        assert call_kwargs["page"] == 2
        assert call_kwargs["per_page"] == 25
        content = get_tool_result_content(result)
        assert len(content["values"]) == len(sample_users)

    async def test_fields_filters_response(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_users: list[User],
    ) -> None:
        mock_users_protocol.users_list.return_value = page(
            sample_users, hits=489, pages=10
        )

        result = await client_session.call_tool("users_get_all", {"fields": ["login"]})

        assert not result.is_error
        content = get_tool_result_content(result)
        assert content["values"][0]["login"] == sample_users[0].login
        assert content["values"][0].get("display") is None


class TestUsersSearch:
    async def test_finds_user_by_exact_login(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_users: list[User],
    ) -> None:
        mock_users_protocol.users_list.side_effect = [page(sample_users), page([])]

        result = await client_session.call_tool(
            "users_search", {"login_or_email_or_name": "testuser"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["login"] == "testuser"

    async def test_finds_user_by_exact_email(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_users: list[User],
    ) -> None:
        mock_users_protocol.users_list.side_effect = [page(sample_users), page([])]

        result = await client_session.call_tool(
            "users_search", {"login_or_email_or_name": "testuser@example.com"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["email"] == "testuser@example.com"

    async def test_fuzzy_matches_by_name(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_users: list[User],
    ) -> None:
        mock_users_protocol.users_list.side_effect = [page(sample_users), page([])]

        result = await client_session.call_tool(
            "users_search", {"login_or_email_or_name": "Test User"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        # Should find at least one user matching "Test User"
        assert len(content) >= 1

    async def test_returns_empty_list_when_no_match(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
    ) -> None:
        mock_users_protocol.users_list.side_effect = [page([]), page([])]

        result = await client_session.call_tool(
            "users_search", {"login_or_email_or_name": "nonexistent"}
        )

        assert not result.is_error
        content = get_tool_result_content(result)
        assert isinstance(content, list)
        assert len(content) == 0


class TestUserGet:
    async def test_returns_user(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_user: User,
    ) -> None:
        mock_users_protocol.user_get.return_value = sample_user

        result = await client_session.call_tool("user_get", {"user_id": "testuser"})

        assert not result.is_error
        mock_users_protocol.user_get.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, dict)
        assert content["login"] == sample_user.login
        assert content["display"] == sample_user.display
        assert content["email"] == sample_user.email

    async def test_user_not_found_raises_error(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
    ) -> None:
        mock_users_protocol.user_get.return_value = None

        result = await client_session.call_tool("user_get", {"user_id": "nonexistent"})

        assert result.is_error


class TestUserGetCurrent:
    async def test_returns_current_user(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        sample_user: User,
    ) -> None:
        mock_users_protocol.user_get_current.return_value = sample_user

        result = await client_session.call_tool("user_get_current", {})

        assert not result.is_error
        mock_users_protocol.user_get_current.assert_called_once()
        content = get_tool_result_content(result)
        assert isinstance(content, dict)
        assert content["login"] == sample_user.login
        assert content["display"] == sample_user.display


class TestUsersGetAbsences:
    async def test_passes_the_users_and_the_period_as_local_days(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
    ) -> None:
        mock_users_protocol.users_get_absences.return_value = [
            UserAbsences(
                user=AbsenceUser(login="i.ivanov", display="Иван Иванов"),
                gaps=[
                    Absence.model_validate(
                        {
                            "id": "1",
                            "workflow": "vacation",
                            "from": "2026-07-01T00:00:00.000+0000",
                            "to": "2026-07-15T00:00:00.000+0000",
                            "fullDay": True,
                        }
                    )
                ],
            )
        ]

        result = await client_session.call_tool(
            "users_get_absences",
            {
                "users": ["i.ivanov"],
                "date_from": "2026-07-01",
                "date_to": "2026-08-31",
            },
        )

        assert not result.is_error
        call = mock_users_protocol.users_get_absences.call_args
        assert call.args == (["i.ivanov"],)
        assert call.kwargs["date_from"] == local_day_start(datetime.date(2026, 7, 1))
        assert call.kwargs["date_to"] == local_day_end(datetime.date(2026, 8, 31))
        content = get_tool_result_content(result)
        assert content[0]["user"]["login"] == "i.ivanov"
        assert content[0]["gaps"][0]["workflow"] == "vacation"
        assert content[0]["gaps"][0]["fullDay"] is True
        assert "from" in content[0]["gaps"][0]

    async def test_an_omitted_period_is_not_sent(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
    ) -> None:
        mock_users_protocol.users_get_absences.return_value = []

        await client_session.call_tool("users_get_absences", {"users": ["a"]})

        call = mock_users_protocol.users_get_absences.call_args
        assert (call.kwargs["date_from"], call.kwargs["date_to"]) == (None, None)

    async def test_a_reversed_period_is_refused(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "users_get_absences",
            {"users": ["a"], "date_from": "2026-08-01", "date_to": "2026-07-01"},
        )

        assert result.is_error
        mock_users_protocol.users_get_absences.assert_not_called()

    async def test_more_than_100_users_are_refused(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
    ) -> None:
        result = await client_session.call_tool(
            "users_get_absences", {"users": [f"u{i}" for i in range(101)]}
        )

        assert result.is_error
        mock_users_protocol.users_get_absences.assert_not_called()
