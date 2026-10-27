from typing import Protocol, runtime_checkable

from .common import YandexAuth
from .types.components import Component
from .types.permissions import PermissionChange, QueuePermissions, SubjectPermissions


@runtime_checkable
class ComponentsProtocol(Protocol):
    async def component_get_user_permissions(
        self, component_id: int, user: str, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions: ...

    async def component_get_group_permissions(
        self, component_id: int, group_id: int, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions: ...

    async def component_get_permissions(
        self, component_id: int, *, auth: YandexAuth | None = None
    ) -> QueuePermissions: ...

    async def component_update_permissions(
        self,
        component_id: int,
        changes: dict[str, PermissionChange],
        *,
        version: int,
        auth: YandexAuth | None = None,
    ) -> QueuePermissions: ...

    async def component_get(
        self, component_id: int, *, auth: YandexAuth | None = None
    ) -> Component: ...

    async def component_create(
        self,
        queue_id: str,
        *,
        name: str,
        description: str | None = None,
        lead: str | None = None,
        assign_auto: bool | None = None,
        auth: YandexAuth | None = None,
    ) -> Component: ...

    async def component_update(
        self,
        component_id: int,
        *,
        version: int,
        name: str | None = None,
        description: str | None = None,
        lead: str | None = None,
        assign_auto: bool | None = None,
        clear_lead: bool = False,
        auth: YandexAuth | None = None,
    ) -> Component: ...

    async def component_delete(
        self, component_id: int, *, auth: YandexAuth | None = None
    ) -> None: ...


class ComponentsProtocolWrap(ComponentsProtocol):
    def __init__(self, original: ComponentsProtocol):
        self._original = original
