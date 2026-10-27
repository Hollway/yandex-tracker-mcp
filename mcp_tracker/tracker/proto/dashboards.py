from typing import Protocol, runtime_checkable

from .common import YandexAuth
from .types.dashboards import (
    CycleTimeWidget,
    CycleTimeWidgetInput,
    Dashboard,
    DashboardLayout,
)
from .types.pagination import PaginatedResult


@runtime_checkable
class DashboardsProtocol(Protocol):
    async def dashboard_create(
        self,
        name: str,
        *,
        layout: DashboardLayout | None = None,
        owner: str | None = None,
        auth: YandexAuth | None = None,
    ) -> Dashboard: ...

    async def dashboard_get(
        self, dashboard_id: int, *, auth: YandexAuth | None = None
    ) -> Dashboard: ...

    async def dashboards_list(
        self, *, auth: YandexAuth | None = None
    ) -> PaginatedResult[Dashboard]: ...

    async def dashboard_delete(
        self, dashboard_id: int, *, auth: YandexAuth | None = None
    ) -> None: ...

    async def dashboard_add_cycle_time_widget(
        self,
        dashboard_id: int,
        widget: CycleTimeWidgetInput,
        *,
        auth: YandexAuth | None = None,
    ) -> CycleTimeWidget: ...


class DashboardsProtocolWrap(DashboardsProtocol):
    def __init__(self, original: DashboardsProtocol):
        self._original = original
