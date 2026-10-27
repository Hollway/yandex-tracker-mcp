from typing import Any, Protocol, runtime_checkable

from .common import YandexAuth
from .types.pagination import PaginatedResult
from .types.reports import Report, ReportFormat, ReportSort


@runtime_checkable
class ReportsProtocol(Protocol):
    async def report_create(
        self,
        summary: str,
        *,
        format: ReportFormat,
        fields: list[str],
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        filter_id: int | None = None,
        sorts: list[ReportSort] | None = None,
        auth: YandexAuth | None = None,
    ) -> Report: ...

    async def report_get(
        self, report_id: str, *, auth: YandexAuth | None = None
    ) -> Report: ...

    async def reports_find(
        self,
        *,
        author: str | None = None,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> PaginatedResult[Report]: ...

    async def report_delete(
        self, report_id: str, *, auth: YandexAuth | None = None
    ) -> None: ...


class ReportsProtocolWrap(ReportsProtocol):
    def __init__(self, original: ReportsProtocol):
        self._original = original
