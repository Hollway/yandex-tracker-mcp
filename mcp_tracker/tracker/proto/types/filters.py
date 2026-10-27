"""Saved issue filters (`v3/filters`)."""

from typing import Any

from pydantic import Field

from mcp_tracker.tracker.proto.types.base import BaseTrackerEntity, NoneExcludedField
from mcp_tracker.tracker.proto.types.refs import BaseReference, UserReference


class FilterSort(BaseTrackerEntity):
    """One sort key of a saved filter, as a write takes it."""

    field: str = Field(description="Issue field key to sort by, e.g. 'created'.")
    isAscending: bool = Field(True, description="False sorts newest/largest first.")


class FilterFieldReference(BaseReference):
    display: str | None = None


class FilterSortRead(BaseTrackerEntity):
    """One sort key as Tracker answers it: the field as a reference, resolved to
    its id (`created` comes back as `createdAt`)."""

    field: FilterFieldReference | None = NoneExcludedField
    isAscending: bool | None = NoneExcludedField


class IssueFilter(BaseTrackerEntity):
    """A saved issue filter: its conditions as a query or as field values.

    Exactly one of `query` and `filter` is set - a write of the other replaces it.
    """

    id: int
    name: str | None = NoneExcludedField
    query: str | None = NoneExcludedField
    filter: dict[str, Any] | None = NoneExcludedField
    sorts: list[FilterSortRead] | None = NoneExcludedField
    fields: list[FilterFieldReference] | None = NoneExcludedField
    favorite: bool | None = NoneExcludedField
    owner: UserReference | None = NoneExcludedField
    permissions: dict[str, Any] | None = NoneExcludedField
