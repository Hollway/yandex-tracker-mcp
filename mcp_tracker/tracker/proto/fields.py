from typing import Protocol, runtime_checkable

from .common import YandexAuth
from .types.fields import FieldCategory, FieldLanguage, FieldType, GlobalField
from .types.issue_types import IssueType
from .types.priorities import Priority
from .types.resolutions import Resolution
from .types.statuses import Status, StatusType
from .types.workflows import LocalizedText


@runtime_checkable
class GlobalDataProtocol(Protocol):
    async def get_global_fields(
        self,
        *,
        language: FieldLanguage | None = None,
        auth: YandexAuth | None = None,
    ) -> list[GlobalField]: ...
    async def get_statuses(self, *, auth: YandexAuth | None = None) -> list[Status]: ...
    async def get_issue_types(
        self, *, auth: YandexAuth | None = None
    ) -> list[IssueType]: ...
    async def get_priorities(
        self, *, auth: YandexAuth | None = None
    ) -> list[Priority]: ...
    async def get_resolutions(
        self, *, auth: YandexAuth | None = None
    ) -> list[Resolution]: ...

    # The organization's catalogue: one object by id or key, and its writes.
    # `version` on an update is required by the API (a query parameter).
    async def status_get(
        self, status_id: str, *, auth: YandexAuth | None = None
    ) -> Status: ...
    async def status_create(
        self,
        *,
        key: str,
        name: LocalizedText,
        type: StatusType,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> Status: ...
    async def status_update(
        self,
        status_id: str,
        *,
        version: int,
        name: LocalizedText | None = None,
        description: str | None = None,
        order: int | None = None,
        type: StatusType | None = None,
        auth: YandexAuth | None = None,
    ) -> Status: ...

    async def resolution_get(
        self, resolution_id: str, *, auth: YandexAuth | None = None
    ) -> Resolution: ...
    async def resolution_create(
        self,
        *,
        key: str,
        name: LocalizedText,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> Resolution: ...
    async def resolution_update(
        self,
        resolution_id: str,
        *,
        version: int,
        name: LocalizedText | None = None,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> Resolution: ...

    async def issue_type_get(
        self, issue_type_id: str, *, auth: YandexAuth | None = None
    ) -> IssueType: ...
    async def issue_type_create(
        self,
        *,
        key: str,
        name: LocalizedText,
        description: str | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueType: ...
    async def issue_type_update(
        self,
        issue_type_id: str,
        *,
        version: int,
        name: LocalizedText | None = None,
        description: str | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueType: ...

    async def priority_get(
        self, priority_id: str, *, auth: YandexAuth | None = None
    ) -> Priority: ...
    async def priority_create(
        self,
        *,
        key: str,
        name: LocalizedText,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> Priority: ...
    async def priority_update(
        self,
        priority_id: str,
        *,
        version: int,
        name: LocalizedText | None = None,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> Priority: ...

    # Issue fields and their categories. Neither can be deleted.
    async def field_get(
        self, field_id: str, *, auth: YandexAuth | None = None
    ) -> GlobalField: ...
    async def field_create(
        self,
        *,
        field_id: str,
        name: LocalizedText,
        category: str,
        type: FieldType,
        description: str | None = None,
        order: int | None = None,
        readonly: bool | None = None,
        visible: bool | None = None,
        hidden: bool | None = None,
        container: bool | None = None,
        options: list[str | int | float] | None = None,
        auth: YandexAuth | None = None,
    ) -> GlobalField: ...
    async def field_update(
        self,
        field_id: str,
        *,
        version: int,
        name: LocalizedText | None = None,
        description: str | None = None,
        category: str | None = None,
        order: int | None = None,
        readonly: bool | None = None,
        visible: bool | None = None,
        hidden: bool | None = None,
        options: list[str | int | float] | None = None,
        user_options: bool = False,
        auth: YandexAuth | None = None,
    ) -> GlobalField: ...
    async def fields_get_categories(
        self, *, auth: YandexAuth | None = None
    ) -> list[FieldCategory]: ...
    async def field_category_get(
        self, category_id: str, *, auth: YandexAuth | None = None
    ) -> FieldCategory: ...
    async def field_category_create(
        self,
        *,
        name: LocalizedText,
        order: int,
        description: str | None = None,
        auth: YandexAuth | None = None,
    ) -> FieldCategory: ...
    async def field_category_update(
        self,
        category_id: str,
        *,
        version: int,
        name: LocalizedText | None = None,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> FieldCategory: ...


class GlobalDataProtocolWrap(GlobalDataProtocol):
    def __init__(self, original: GlobalDataProtocol):
        self._original = original
