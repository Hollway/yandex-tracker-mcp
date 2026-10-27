from typing import Any, Literal

from pydantic import AliasChoices, Field

from mcp_tracker.tracker.proto.types.base import (
    BaseTrackerEntity,
    NoneExcludedField,
    none_excluder,
)
from mcp_tracker.tracker.proto.types.mixins import CreatedMixin
from mcp_tracker.tracker.proto.types.refs import (
    BoardReference,
    StatusReference,
    UserReference,
)

DashboardLayout = Literal[
    "one-column",
    "two-columns",
    "three-columns",
    "narrow-left-wide-right",
    "one-top-two-bottom",
]

CycleTimeMode = Literal["common-lines", "common-lines-and-points", "status-lines"]


class WidgetReference(BoardReference):
    """A widget of a dashboard: its id and title."""


class Dashboard(CreatedMixin, BaseTrackerEntity):
    """A dashboard ('дашборд'): a page of widgets with charts and issue lists."""

    id: int
    version: int | None = NoneExcludedField
    name: str
    layout: str | None = NoneExcludedField
    owner: UserReference | None = NoneExcludedField
    widgets: list[WidgetReference] | None = Field(
        None,
        exclude_if=none_excluder,
        description="Present on a single dashboard read, absent from the listing.",
    )


class CycleTimeBucket(BaseTrackerEntity):
    """How the chart groups dates."""

    unit: Literal["days", "weeks", "months", "sprints"] = Field(
        description="Grouping period."
    )
    count: int | None = Field(
        None, ge=1, description="Periods per step; always 1 for sprints."
    )
    board_id: str | None = Field(
        None,
        validation_alias=AliasChoices("board_id", "boardId"),
        serialization_alias="boardId",
        description="Board whose sprints to use; for unit 'sprints' only.",
    )


class CycleTimeLines(BaseTrackerEntity):
    """Which lines the chart draws."""

    moving_average: bool | None = Field(
        None,
        validation_alias=AliasChoices("moving_average", "movingAverage"),
        serialization_alias="movingAverage",
    )
    standard_deviation: bool | None = Field(
        None,
        validation_alias=AliasChoices("standard_deviation", "standardDeviation"),
        serialization_alias="standardDeviation",
    )
    percentile: list[float] | None = Field(
        None, description="Percentiles to draw, e.g. [75, 90]."
    )
    cake_percentile: float | None = Field(
        None,
        validation_alias=AliasChoices("cake_percentile", "cakePercentile"),
        serialization_alias="cakePercentile",
        description="Percentile of the per-status breakdown.",
    )


class CycleTimeWidgetInput(BaseTrackerEntity):
    """A 'Время цикла' widget to add to a dashboard; exactly one issue source."""

    description: str
    query: str | None = None
    filter: dict[str, Any] | None = None
    filter_id: int | None = None
    from_statuses: list[str] | None = None
    to_statuses: list[str] | None = None
    excluded_statuses: list[str] | None = None
    included_statuses: list[str] | None = None
    bucket: CycleTimeBucket | None = None
    lines: CycleTimeLines | None = None
    calendar_id: int | None = None
    start: str | None = None
    end: str | None = None
    mode: CycleTimeMode | None = None


class CycleTimeWidget(CreatedMixin, BaseTrackerEntity):
    """A 'Время цикла' (cycle time) widget as Tracker returns it."""

    id: int
    version: int | None = NoneExcludedField
    description: str | None = NoneExcludedField
    dashboard: BoardReference | None = NoneExcludedField
    query: str | None = NoneExcludedField
    from_statuses: list[StatusReference] | None = Field(
        None,
        validation_alias=AliasChoices("fromStatuses", "from_statuses"),
        serialization_alias="fromStatuses",
        exclude_if=none_excluder,
    )
    to_statuses: list[StatusReference] | None = Field(
        None,
        validation_alias=AliasChoices("toStatuses", "to_statuses"),
        serialization_alias="toStatuses",
        exclude_if=none_excluder,
    )
    bucket: dict[str, Any] | None = NoneExcludedField
    lines: dict[str, Any] | None = NoneExcludedField
    start: str | None = NoneExcludedField
    end: str | None = NoneExcludedField
    mode: str | None = NoneExcludedField
