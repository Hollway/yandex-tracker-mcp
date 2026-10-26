import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from mcp_tracker.tracker.proto.types.users import (
    AbsenceInput,
    AbsenceUser,
    CreatedAbsence,
)
from tests.mcp.conftest import get_tool_result_content

TRIP = {
    "user": "i.ivanov",
    "workflow": "trip",
    "date_from": "2030-01-10T00:00:00+03:00",
    "date_to": "2030-01-11T00:00:00+03:00",
}


class TestUsersCreateAbsences:
    async def test_passes_the_absences_and_returns_the_created_ones(
        self, client_session: Client, mock_users_protocol: AsyncMock
    ) -> None:
        mock_users_protocol.users_create_absences.return_value = [
            CreatedAbsence(
                id="6adf6865",
                user=AbsenceUser(login="i.ivanov", display="Иван Иванов"),
                workflow="trip",
                from_=datetime.datetime(2030, 1, 9, 21, tzinfo=datetime.UTC),
                to=datetime.datetime(2030, 1, 10, 21, tzinfo=datetime.UTC),
                full_day=True,
            )
        ]

        result = await client_session.call_tool(
            "users_create_absences", {"absences": [{**TRIP, "full_day": True}]}
        )

        assert not result.is_error
        call = mock_users_protocol.users_create_absences.call_args
        (absence,) = call.args[0]
        assert absence == AbsenceInput(
            user="i.ivanov",
            workflow="trip",
            date_from=datetime.datetime(
                2030, 1, 10, tzinfo=datetime.timezone(datetime.timedelta(hours=3))
            ),
            date_to=datetime.datetime(
                2030, 1, 11, tzinfo=datetime.timezone(datetime.timedelta(hours=3))
            ),
            full_day=True,
        )
        assert absence.work_in_absence is None
        content = get_tool_result_content(result)
        assert content[0]["id"] == "6adf6865"
        assert content[0]["user"]["login"] == "i.ivanov"
        assert content[0]["fullDay"] is True

    @pytest.mark.parametrize(
        "absences",
        [
            [],
            [{**TRIP, "workflow": "holiday"}],
            [{key: value for key, value in TRIP.items() if key != "date_to"}],
            [TRIP] * 101,
        ],
        ids=["empty", "unknown-kind", "no-end", "over-100"],
    )
    async def test_invalid_input_is_refused(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        absences: list[dict[str, Any]],
    ) -> None:
        result = await client_session.call_tool(
            "users_create_absences", {"absences": absences}
        )

        assert result.is_error
        mock_users_protocol.users_create_absences.assert_not_called()

    async def test_read_only_mode_tool_not_registered(
        self, client_session_read_only: Client, mock_users_protocol: AsyncMock
    ) -> None:
        result = await client_session_read_only.call_tool(
            "users_create_absences", {"absences": [TRIP]}
        )

        assert result.is_error
        mock_users_protocol.users_create_absences.assert_not_called()


class TestUsersDeleteAbsences:
    async def test_passes_the_ids(
        self, client_session: Client, mock_users_protocol: AsyncMock
    ) -> None:
        mock_users_protocol.users_delete_absences.return_value = None

        result = await client_session.call_tool(
            "users_delete_absences", {"absence_ids": ["a1", "b2"]}
        )

        assert not result.is_error
        call = mock_users_protocol.users_delete_absences.call_args
        assert call.args == (["a1", "b2"],)

    @pytest.mark.parametrize(
        "absence_ids",
        [[], [""], ["x" * 129], [f"id{i}" for i in range(101)]],
        ids=["empty", "blank-id", "long-id", "over-100"],
    )
    async def test_invalid_ids_are_refused(
        self,
        client_session: Client,
        mock_users_protocol: AsyncMock,
        absence_ids: list[str],
    ) -> None:
        result = await client_session.call_tool(
            "users_delete_absences", {"absence_ids": absence_ids}
        )

        assert result.is_error
        mock_users_protocol.users_delete_absences.assert_not_called()

    async def test_read_only_mode_tool_not_registered(
        self, client_session_read_only: Client, mock_users_protocol: AsyncMock
    ) -> None:
        result = await client_session_read_only.call_tool(
            "users_delete_absences", {"absence_ids": ["a1"]}
        )

        assert result.is_error
        mock_users_protocol.users_delete_absences.assert_not_called()
