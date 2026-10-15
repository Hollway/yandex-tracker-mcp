import datetime
from typing import Protocol, runtime_checkable

from .common import YandexAuth
from .types.pagination import PaginatedResult
from .types.users import User, UserAbsences


@runtime_checkable
class UsersProtocol(Protocol):
    async def users_list(
        self, per_page: int = 50, page: int = 1, *, auth: YandexAuth | None = None
    ) -> PaginatedResult[User]: ...

    async def user_get(
        self, user_id: str, *, auth: YandexAuth | None = None
    ) -> User | None: ...

    async def user_get_current(self, *, auth: YandexAuth | None = None) -> User: ...

    async def users_get_absences(
        self,
        users: list[str],
        *,
        date_from: datetime.datetime | None = None,
        date_to: datetime.datetime | None = None,
        auth: YandexAuth | None = None,
    ) -> list[UserAbsences]: ...


class UsersProtocolWrap(UsersProtocol):
    def __init__(self, original: UsersProtocol):
        self._original = original
