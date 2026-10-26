import datetime
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import AbsencesForbidden, TrackerAPIError
from mcp_tracker.tracker.proto.types.users import AbsenceInput
from tests.aioresponses_utils import RequestCapture

SEARCH_URL = "https://api.tracker.yandex.net/v3/gaps/_search"


def user_gaps(login: str, gaps: list[dict[str, Any]]) -> dict[str, Any]:
    """One `userGaps` row as the documentation shows it (07.2026)."""
    return {
        "user": {
            "self": "https://api.tracker.yandex.net/v3/users/1234567890123456",
            "uid": 1234567890123456,
            "login": login,
            "trackerUid": 1234567890123456,
            "passportUid": 1234567890,
            "cloudUid": "ajehs6sinuiii1234567",
            "firstName": "Имя",
            "lastName": "Фамилия",
            "display": "Иван Иванов",
            "email": "username@example.com",
            "external": False,
            "dismissed": False,
            "sources": ["directory"],
        },
        "gaps": gaps,
    }


VACATION = {
    "id": "68340a1f2b4c1a3d5e7f9011",
    "workflow": "vacation",
    "from": "2026-07-01T00:00:00.000+0000",
    "to": "2026-07-15T00:00:00.000+0000",
    "fullDay": True,
    "workInAbsence": False,
}


class TestUsersGetAbsences:
    async def test_sends_the_users_and_the_period(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(
            payload={
                "userGaps": [user_gaps("username1", [VACATION])],
                "hasMore": False,
            }
        )

        with aioresponses() as m:
            m.post(f"{SEARCH_URL}?page=1&perPage=100", callback=capture.callback)

            result = await tracker_client.users_get_absences(
                ["username1"],
                date_from=datetime.datetime(2026, 7, 1, tzinfo=datetime.UTC),
                date_to=datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC),
            )

        capture.last_request.assert_json_body(
            {
                "users": ["username1"],
                "from": "2026-07-01T00:00:00.000000+0000",
                "to": "2026-09-01T00:00:00.000000+0000",
            }
        )
        assert len(result) == 1
        assert result[0].user.login == "username1"
        gap = result[0].gaps[0]
        assert (gap.workflow, gap.full_day, gap.work_in_absence) == (
            "vacation",
            True,
            False,
        )
        assert gap.from_ == datetime.datetime(2026, 7, 1, tzinfo=datetime.UTC)

    async def test_the_answer_is_compact_and_in_trackers_spelling(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                f"{SEARCH_URL}?page=1&perPage=100",
                payload={"userGaps": [user_gaps("username1", [VACATION])]},
            )

            result = await tracker_client.users_get_absences(["username1"])

        dumped = result[0].model_dump(mode="json", by_alias=True)
        assert dumped["user"] == {"login": "username1", "display": "Иван Иванов"}
        assert set(dumped["gaps"][0]) == {
            "id",
            "workflow",
            "from",
            "to",
            "fullDay",
            "workInAbsence",
        }

    async def test_has_more_is_followed(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                f"{SEARCH_URL}?page=1&perPage=100",
                payload={"userGaps": [user_gaps("a", [])], "hasMore": True},
            )
            m.post(
                f"{SEARCH_URL}?page=2&perPage=100",
                payload={"userGaps": [user_gaps("b", [])], "hasMore": False},
            )

            result = await tracker_client.users_get_absences(["a", "b"])

        assert [row.user.login for row in result] == ["a", "b"]

    async def test_forbidden_says_admin_rights_are_needed(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(f"{SEARCH_URL}?page=1&perPage=100", status=403, payload={})

            with pytest.raises(AbsencesForbidden) as exc_info:
                await tracker_client.users_get_absences(["username1"])

        assert "organization administrator" in str(exc_info.value)

    async def test_other_errors_keep_trackers_message(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                f"{SEARCH_URL}?page=1&perPage=100",
                status=422,
                payload={"errorMessages": ["Пользователь не найден"]},
            )

            with pytest.raises(TrackerAPIError) as exc_info:
                await tracker_client.users_get_absences(["nobody"])

        assert "Пользователь не найден" in str(exc_info.value)


GAPS_URL = "https://api.tracker.yandex.net/v3/gaps"


class TestUsersCreateAbsences:
    async def test_sends_the_absences_in_trackers_spelling(
        self, tracker_client: TrackerClient
    ) -> None:
        created = {**VACATION, "user": user_gaps("username1", [])["user"]}
        capture = RequestCapture(payload={"gaps": [created]})

        with aioresponses() as m:
            m.post(GAPS_URL, callback=capture.callback)

            result = await tracker_client.users_create_absences(
                [
                    AbsenceInput(
                        user="username1",
                        workflow="vacation",
                        date_from=datetime.datetime(2026, 7, 1, tzinfo=datetime.UTC),
                        date_to=datetime.datetime(2026, 7, 15, tzinfo=datetime.UTC),
                        full_day=True,
                    ),
                    AbsenceInput(
                        user="username2",
                        workflow="duty",
                        date_from=datetime.datetime(2026, 7, 2, 9),
                        date_to=datetime.datetime(2026, 7, 2, 12),
                        work_in_absence=True,
                    ),
                ]
            )

        capture.last_request.assert_json_body(
            {
                "gaps": [
                    {
                        "user": "username1",
                        "workflow": "vacation",
                        "from": "2026-07-01T00:00:00.000000+0000",
                        "to": "2026-07-15T00:00:00.000000+0000",
                        "fullDay": True,
                    },
                    {
                        "user": "username2",
                        "workflow": "duty",
                        "from": "2026-07-02T09:00:00.000000+0000",
                        "to": "2026-07-02T12:00:00.000000+0000",
                        "workInAbsence": True,
                    },
                ]
            }
        )
        assert [gap.id for gap in result] == [VACATION["id"]]
        assert result[0].user.login == "username1"
        assert result[0].model_dump(mode="json", by_alias=True)["user"] == {
            "login": "username1",
            "display": "Иван Иванов",
        }

    @pytest.mark.parametrize(
        ("status", "error"), [(403, AbsencesForbidden), (422, TrackerAPIError)]
    )
    async def test_errors(
        self, tracker_client: TrackerClient, status: int, error: type[Exception]
    ) -> None:
        with aioresponses() as m:
            m.post(
                GAPS_URL,
                status=status,
                payload={"errorMessages": ["пользователи [x] не существуют"]},
            )

            with pytest.raises(error) as exc_info:
                await tracker_client.users_create_absences(
                    [
                        AbsenceInput(
                            user="x",
                            workflow="trip",
                            date_from=datetime.datetime(2026, 7, 1),
                            date_to=datetime.datetime(2026, 7, 2),
                        )
                    ]
                )

        expected = "create absences" if status == 403 else "не существуют"
        assert expected in str(exc_info.value)


class TestUsersDeleteAbsences:
    async def test_sends_the_ids_comma_separated(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(f"{GAPS_URL}?gapIds=a1%2Cb2", status=204)

            await tracker_client.users_delete_absences(["a1", "b2"])

    async def test_forbidden_says_admin_rights_are_needed(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(f"{GAPS_URL}?gapIds=a1", status=403, payload={})

            with pytest.raises(AbsencesForbidden) as exc_info:
                await tracker_client.users_delete_absences(["a1"])

        assert "delete absences" in str(exc_info.value)
