import datetime
from enum import Enum

from pydantic import AliasChoices, ConfigDict, Field

from mcp_tracker.tracker.proto.types.base import (
    BaseTrackerEntity,
    NoneExcludedField,
    none_excluder,
)


class User(BaseTrackerEntity):
    model_config = ConfigDict(extra="ignore")

    uid: int
    login: str
    first_name: str | None = Field(None, alias="firstName", exclude_if=none_excluder)
    last_name: str | None = Field(None, alias="lastName", exclude_if=none_excluder)
    display: str | None = NoneExcludedField
    email: str | None = NoneExcludedField
    external: bool | None = NoneExcludedField
    dismissed: bool | None = NoneExcludedField


UserFieldsEnum = Enum(  # type: ignore[misc]
    "UserFieldsEnum",
    {key: key for key in User.model_fields.keys()},
)


class Absence(BaseTrackerEntity):
    """One absence of a user: a vacation, sick leave, business trip and so on."""

    id: str
    workflow: str | None = Field(
        None,
        description="Kind of absence: vacation, paid_day_off, illness, absence, "
        "trip, conference_trip, conference, learning, maternity or duty.",
    )
    from_: datetime.datetime = Field(
        validation_alias=AliasChoices("from", "from_"), serialization_alias="from"
    )
    to: datetime.datetime
    full_day: bool | None = Field(
        None,
        validation_alias=AliasChoices("fullDay", "full_day"),
        serialization_alias="fullDay",
        exclude_if=none_excluder,
    )
    work_in_absence: bool | None = Field(
        None,
        validation_alias=AliasChoices("workInAbsence", "work_in_absence"),
        serialization_alias="workInAbsence",
        exclude_if=none_excluder,
    )


class AbsenceUser(BaseTrackerEntity):
    """The user an absence list belongs to - who, not the whole profile."""

    login: str
    display: str | None = NoneExcludedField


class UserAbsences(BaseTrackerEntity):
    user: AbsenceUser
    gaps: list[Absence] = Field(
        default_factory=list, description="Absences overlapping the period."
    )
