import datetime
from typing import Protocol, runtime_checkable

from .common import YandexAuth
from .types.boards import Board, BoardColumnDetail, Sprint


@runtime_checkable
class BoardsProtocol(Protocol):
    async def boards_list(
        self,
        *,
        per_page: int = 100,
        cursor: int | None = None,
        auth: YandexAuth | None = None,
    ) -> list[Board]: ...

    async def board_get(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> Board: ...

    async def board_get_columns(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[BoardColumnDetail]: ...

    async def board_get_sprints(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[Sprint]: ...

    async def sprint_get(
        self, sprint_id: int, *, auth: YandexAuth | None = None
    ) -> Sprint: ...

    async def sprint_create(
        self,
        board_id: int,
        *,
        name: str,
        start_date: datetime.date,
        end_date: datetime.date,
        auth: YandexAuth | None = None,
    ) -> Sprint: ...

    async def sprint_update(
        self,
        sprint_id: int,
        *,
        version: int,
        name: str | None = None,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
        status: str | None = None,
        auth: YandexAuth | None = None,
    ) -> Sprint: ...

    async def sprint_start(
        self, sprint_id: int, *, version: int, auth: YandexAuth | None = None
    ) -> Sprint: ...

    async def sprint_archive(
        self, sprint_id: int, *, version: int, auth: YandexAuth | None = None
    ) -> Sprint: ...

    async def sprint_delete(
        self, sprint_id: int, *, auth: YandexAuth | None = None
    ) -> None: ...


class BoardsProtocolWrap(BoardsProtocol):
    def __init__(self, original: BoardsProtocol):
        self._original = original
