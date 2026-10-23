from typing import Literal

from pydantic import Field

from mcp_tracker.tracker.proto.types.base import BaseTrackerEntity, none_excluder

StatusType = Literal["new", "inProgress", "paused", "done", "cancelled"]


class Status(BaseTrackerEntity):
    # A number from `v3/statuses`, but a board's auto-filter settings name
    # statuses by a string id ('584fb66ba6cd6166fee4c008').
    id: int | str | None = Field(
        default=None, description="Status ID", exclude_if=none_excluder
    )
    version: int = Field(description="Status version")
    key: str = Field(description="Status key")
    name: str = Field(description="Displayed status name")
    description: str | None = Field(default=None, description="Status description")
    order: int = Field(description="Status order")
    type: StatusType | None = Field(default=None, description="Status type")
