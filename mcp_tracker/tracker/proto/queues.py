from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from .common import YandexAuth
from .types.components import Component
from .types.fields import FieldType, GlobalField, LocalField
from .types.pagination import PaginatedResult
from .types.permissions import (
    PermissionAction,
    PermissionChange,
    QueuePermissions,
    SubjectPermissions,
)
from .types.queue_automation import (
    QueueAutoaction,
    QueueAutoactionRun,
    QueueAutoactionRunIssue,
    QueueIssueTypeConfigInput,
    QueueMacro,
    QueueTriggerLog,
)
from .types.queues import (
    Queue,
    QueueExpandOption,
    QueueTrigger,
    QueueVersion,
)
from .types.workflows import LocalizedText


@runtime_checkable
class QueuesProtocol(Protocol):
    async def queues_list(
        self, per_page: int = 100, page: int = 1, *, auth: YandexAuth | None = None
    ) -> PaginatedResult[Queue]: ...

    async def queue_get(
        self,
        queue_id: str,
        *,
        expand: list[QueueExpandOption] | None = None,
        auth: YandexAuth | None = None,
    ) -> Queue: ...

    async def queues_get_local_fields(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[LocalField]: ...

    async def queues_get_tags(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[str]: ...

    # A local field is addressed by its key; none can be deleted.
    async def queue_get_local_field(
        self, queue_id: str, field_key: str, *, auth: YandexAuth | None = None
    ) -> LocalField: ...

    async def queue_create_local_field(
        self,
        queue_id: str,
        *,
        field_key: str,
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
    ) -> LocalField: ...

    async def queue_update_local_field(
        self,
        queue_id: str,
        field_key: str,
        *,
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
    ) -> LocalField: ...

    async def queue_delete_tag(
        self, queue_id: str, tag: str, *, auth: YandexAuth | None = None
    ) -> None: ...

    # Access permissions. `user` is a login or a uid.
    async def queue_get_permissions(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> QueuePermissions: ...

    async def queue_get_user_permissions(
        self, queue_id: str, user: str, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions: ...

    async def queue_get_group_permissions(
        self, queue_id: str, group_id: int, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions: ...

    async def queue_update_permissions(
        self,
        queue_id: str,
        changes: dict[PermissionAction, PermissionChange],
        *,
        auth: YandexAuth | None = None,
    ) -> QueuePermissions: ...

    async def queues_get_triggers(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueTrigger]: ...

    async def queues_get_versions(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueVersion]: ...

    async def queues_get_components(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[Component]: ...

    async def queue_create_version(
        self,
        queue_id: str,
        *,
        name: str,
        description: str | None = None,
        start_date: date | None = None,
        due_date: date | None = None,
        auth: YandexAuth | None = None,
    ) -> QueueVersion: ...

    async def queue_get_version(
        self, version_id: int, *, auth: YandexAuth | None = None
    ) -> QueueVersion: ...

    async def queue_update_version(
        self,
        version_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        start_date: date | None = None,
        due_date: date | None = None,
        auth: YandexAuth | None = None,
    ) -> QueueVersion: ...

    async def queue_delete_version(
        self, version_id: int, *, auth: YandexAuth | None = None
    ) -> None: ...

    async def queues_get_fields(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[GlobalField]: ...

    # Triggers, autoactions and macros - see AGENTS.md, *Triggers, autoactions,
    # macros*.
    async def queue_get_trigger(
        self, queue_id: str, trigger_id: int, *, auth: YandexAuth | None = None
    ) -> QueueTrigger: ...

    async def queue_create_trigger(
        self,
        queue_id: str,
        *,
        name: str,
        actions: list[dict[str, Any]],
        conditions: list[dict[str, Any]] | dict[str, Any] | None = None,
        active: bool | None = None,
        auth: YandexAuth | None = None,
    ) -> QueueTrigger: ...

    async def queue_update_trigger(
        self,
        queue_id: str,
        trigger_id: int,
        *,
        version: int,
        name: str | None = None,
        actions: list[dict[str, Any]] | None = None,
        conditions: list[dict[str, Any]] | dict[str, Any] | None = None,
        active: bool | None = None,
        before: int | None = None,
        auth: YandexAuth | None = None,
    ) -> QueueTrigger: ...

    async def queue_get_trigger_logs(
        self,
        queue_id: str,
        trigger_id: int,
        *,
        issue_id: str | None = None,
        limit: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        auth: YandexAuth | None = None,
    ) -> list[QueueTriggerLog]: ...

    async def queues_get_autoactions(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueAutoaction]: ...

    async def queue_get_autoaction(
        self, queue_id: str, autoaction_id: int, *, auth: YandexAuth | None = None
    ) -> QueueAutoaction: ...

    async def queue_create_autoaction(
        self,
        queue_id: str,
        *,
        name: str,
        actions: list[dict[str, Any]],
        filter: dict[str, Any] | list[dict[str, Any]] | None = None,
        query: str | None = None,
        active: bool | None = None,
        enable_notifications: bool | None = None,
        interval_millis: int | None = None,
        calendar_id: int | None = None,
        auth: YandexAuth | None = None,
    ) -> QueueAutoaction: ...

    async def queue_get_autoaction_runs(
        self, queue_id: str, autoaction_id: int, *, auth: YandexAuth | None = None
    ) -> list[QueueAutoactionRun]: ...

    async def queue_get_autoaction_run(
        self,
        queue_id: str,
        autoaction_id: int,
        run_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> list[QueueAutoactionRunIssue]: ...

    async def queues_get_macros(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueMacro]: ...

    async def queue_get_macro(
        self, queue_id: str, macro_id: int, *, auth: YandexAuth | None = None
    ) -> QueueMacro: ...

    async def queue_create_macro(
        self,
        queue_id: str,
        *,
        name: str,
        body: str | None = None,
        issue_update: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> QueueMacro: ...

    async def queue_update_macro(
        self,
        queue_id: str,
        macro_id: int,
        *,
        name: str,
        body: str | None = None,
        issue_update: dict[str, Any] | None = None,
        clear_body: bool = False,
        auth: YandexAuth | None = None,
    ) -> QueueMacro: ...

    async def queue_delete_macro(
        self, queue_id: str, macro_id: int, *, auth: YandexAuth | None = None
    ) -> None: ...

    # Queue administration.
    async def queue_create(
        self,
        *,
        key: str,
        name: str,
        lead: str,
        default_type: str,
        default_priority: str,
        issue_types_config: list[QueueIssueTypeConfigInput],
        auth: YandexAuth | None = None,
    ) -> Queue: ...

    async def queue_delete(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> None: ...

    async def queue_restore(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> Queue: ...

    async def queue_get_fresh(
        self,
        queue_id: str,
        *,
        expand: list[QueueExpandOption] | None = None,
        auth: YandexAuth | None = None,
    ) -> Queue: ...

    async def queue_update_issue_types_config(
        self,
        queue_id: str,
        *,
        issue_types_config: list[QueueIssueTypeConfigInput],
        default_type: str | None = None,
        auth: YandexAuth | None = None,
    ) -> Queue: ...


class QueuesProtocolWrap(QueuesProtocol):
    def __init__(self, original: QueuesProtocol):
        self._original = original
