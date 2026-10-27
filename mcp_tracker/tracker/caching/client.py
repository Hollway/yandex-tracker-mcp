import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiocache import cached

from mcp_tracker.tracker.proto.boards import BoardsProtocolWrap
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.components import ComponentsProtocolWrap
from mcp_tracker.tracker.proto.entities import EntitiesProtocolWrap
from mcp_tracker.tracker.proto.fields import GlobalDataProtocolWrap
from mcp_tracker.tracker.proto.issues import IssueProtocolWrap
from mcp_tracker.tracker.proto.queues import QueuesProtocolWrap
from mcp_tracker.tracker.proto.templates import TemplatesProtocolWrap
from mcp_tracker.tracker.proto.types.boards import Board, BoardColumnDetail, Sprint
from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.entities import (
    GoalEntity,
    GoalSearchResult,
    GoalStatus,
    PortfolioEntity,
    PortfolioSearchResult,
    ProjectEntity,
    ProjectPortfolioStatus,
    ProjectSearchResult,
)
from mcp_tracker.tracker.proto.types.fields import (
    FieldCategory,
    FieldLanguage,
    FieldType,
    GlobalField,
    LocalField,
)
from mcp_tracker.tracker.proto.types.inputs import (
    ChecklistItemDeadlineInput,
    ChecklistItemInput,
    EntityChecklistItemUpdateInput,
    EntityParentEntityInput,
    GoalLinkInput,
    IssueComponentRef,
    IssueFollowerRef,
    IssueParentRef,
    IssuePriorityRef,
    IssueProjectRef,
    IssueSprintRef,
    IssueTypeRef,
    ProjectPortfolioLinkInput,
)
from mcp_tracker.tracker.proto.types.issue_types import IssueType
from mcp_tracker.tracker.proto.types.issues import (
    BulkChange,
    BulkChangeFailure,
    ChangelogPage,
    ChecklistItem,
    CommentsPage,
    ExternalApplication,
    Issue,
    IssueAttachment,
    IssueComment,
    IssueLink,
    IssueLinkRelationship,
    IssueTransition,
    RemoteLink,
    Worklog,
)
from mcp_tracker.tracker.proto.types.pagination import PaginatedResult
from mcp_tracker.tracker.proto.types.permissions import (
    Group,
    PermissionAction,
    PermissionChange,
    QueuePermissions,
    SubjectPermissions,
)
from mcp_tracker.tracker.proto.types.priorities import Priority
from mcp_tracker.tracker.proto.types.queue_automation import (
    QueueAutoaction,
    QueueAutoactionRun,
    QueueAutoactionRunIssue,
    QueueIssueTypeConfigInput,
    QueueMacro,
    QueueTriggerLog,
)
from mcp_tracker.tracker.proto.types.queues import (
    Queue,
    QueueExpandOption,
    QueueTrigger,
    QueueVersion,
)
from mcp_tracker.tracker.proto.types.refs import IssueTypeReference
from mcp_tracker.tracker.proto.types.resolutions import Resolution
from mcp_tracker.tracker.proto.types.statuses import Status, StatusType
from mcp_tracker.tracker.proto.types.templates import CommentTemplate, IssueTemplate
from mcp_tracker.tracker.proto.types.users import User, UserAbsences
from mcp_tracker.tracker.proto.types.workflows import (
    IssueTypeResolutionsDraft,
    LocalizedText,
    Screen,
    Workflow,
    WorkflowActionDraft,
    WorkflowDraft,
    WorkflowStepDraft,
)
from mcp_tracker.tracker.proto.users import UsersProtocolWrap
from mcp_tracker.tracker.proto.workflows import WorkflowsProtocolWrap


@dataclass
class CacheCollection:
    queues: type[QueuesProtocolWrap]
    issues: type[IssueProtocolWrap]
    global_data: type[GlobalDataProtocolWrap]
    templates: type[TemplatesProtocolWrap]
    users: type[UsersProtocolWrap]
    entities: type[EntitiesProtocolWrap]
    boards: type[BoardsProtocolWrap]
    components: type[ComponentsProtocolWrap]
    workflows: type[WorkflowsProtocolWrap]


def make_cached_protocols(
    cache_config: dict[str, Any],
) -> CacheCollection:
    class CachingQueuesProtocol(QueuesProtocolWrap):
        @cached(**cache_config)
        async def queues_list(
            self, per_page: int = 100, page: int = 1, *, auth: YandexAuth | None = None
        ) -> PaginatedResult[Queue]:
            return await self._original.queues_list(
                per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def queues_get_local_fields(
            self,
            queue_id: str,
            *,
            language: FieldLanguage | None = None,
            auth: YandexAuth | None = None,
        ) -> list[LocalField]:
            return await self._original.queues_get_local_fields(
                queue_id, language=language, auth=auth
            )

        @cached(**cache_config)
        async def queues_get_tags(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[str]:
            return await self._original.queues_get_tags(queue_id, auth=auth)

        async def queue_get_local_field(
            self, queue_id: str, field_key: str, *, auth: YandexAuth | None = None
        ) -> LocalField:
            return await self._original.queue_get_local_field(
                queue_id, field_key, auth=auth
            )

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
        ) -> LocalField:
            return await self._original.queue_create_local_field(
                queue_id,
                field_key=field_key,
                name=name,
                category=category,
                type=type,
                description=description,
                order=order,
                readonly=readonly,
                visible=visible,
                hidden=hidden,
                container=container,
                options=options,
                auth=auth,
            )

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
        ) -> LocalField:
            return await self._original.queue_update_local_field(
                queue_id,
                field_key,
                name=name,
                description=description,
                category=category,
                order=order,
                readonly=readonly,
                visible=visible,
                hidden=hidden,
                options=options,
                user_options=user_options,
                auth=auth,
            )

        async def queue_delete_tag(
            self, queue_id: str, tag: str, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.queue_delete_tag(queue_id, tag, auth=auth)

        # Permissions are not cached: they are read to be checked or changed.
        async def queue_get_permissions(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> QueuePermissions:
            return await self._original.queue_get_permissions(queue_id, auth=auth)

        async def queue_get_user_permissions(
            self, queue_id: str, user: str, *, auth: YandexAuth | None = None
        ) -> SubjectPermissions:
            return await self._original.queue_get_user_permissions(
                queue_id, user, auth=auth
            )

        async def queue_get_group_permissions(
            self, queue_id: str, group_id: int, *, auth: YandexAuth | None = None
        ) -> SubjectPermissions:
            return await self._original.queue_get_group_permissions(
                queue_id, group_id, auth=auth
            )

        async def queue_update_permissions(
            self,
            queue_id: str,
            changes: dict[PermissionAction, PermissionChange],
            *,
            auth: YandexAuth | None = None,
        ) -> QueuePermissions:
            return await self._original.queue_update_permissions(
                queue_id, changes, auth=auth
            )

        @cached(**cache_config)
        async def queues_get_triggers(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[QueueTrigger]:
            return await self._original.queues_get_triggers(queue_id, auth=auth)

        @cached(**cache_config)
        async def queues_get_versions(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[QueueVersion]:
            return await self._original.queues_get_versions(queue_id, auth=auth)

        # Not cached - see `CachingComponentsProtocol`.
        async def queues_get_components(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[Component]:
            return await self._original.queues_get_components(queue_id, auth=auth)

        async def queue_create_version(
            self,
            queue_id: str,
            *,
            name: str,
            description: str | None = None,
            start_date: datetime.date | None = None,
            due_date: datetime.date | None = None,
            auth: YandexAuth | None = None,
        ) -> QueueVersion:
            return await self._original.queue_create_version(
                queue_id,
                name=name,
                description=description,
                start_date=start_date,
                due_date=due_date,
                auth=auth,
            )

        # Not cached: the write tools read the version for its queue.
        async def queue_get_version(
            self, version_id: int, *, auth: YandexAuth | None = None
        ) -> QueueVersion:
            return await self._original.queue_get_version(version_id, auth=auth)

        async def queue_update_version(
            self,
            version_id: int,
            *,
            name: str | None = None,
            description: str | None = None,
            start_date: datetime.date | None = None,
            due_date: datetime.date | None = None,
            auth: YandexAuth | None = None,
        ) -> QueueVersion:
            return await self._original.queue_update_version(
                version_id,
                name=name,
                description=description,
                start_date=start_date,
                due_date=due_date,
                auth=auth,
            )

        async def queue_delete_version(
            self, version_id: int, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.queue_delete_version(version_id, auth=auth)

        @cached(**cache_config)
        async def queues_get_fields(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[GlobalField]:
            return await self._original.queues_get_fields(queue_id, auth=auth)

        @cached(**cache_config)
        async def queue_get(
            self,
            queue_id: str,
            *,
            expand: list[QueueExpandOption] | None = None,
            auth: YandexAuth | None = None,
        ) -> Queue:
            return await self._original.queue_get(queue_id, expand=expand, auth=auth)

        # Not cached: the trigger and macro writes read the current object for
        # its `version` / `name`, and a stale one would be written back.
        async def queue_get_trigger(
            self, queue_id: str, trigger_id: int, *, auth: YandexAuth | None = None
        ) -> QueueTrigger:
            return await self._original.queue_get_trigger(
                queue_id, trigger_id, auth=auth
            )

        async def queue_create_trigger(
            self,
            queue_id: str,
            *,
            name: str,
            actions: list[dict[str, Any]],
            conditions: list[dict[str, Any]] | dict[str, Any] | None = None,
            active: bool | None = None,
            auth: YandexAuth | None = None,
        ) -> QueueTrigger:
            return await self._original.queue_create_trigger(
                queue_id,
                name=name,
                actions=actions,
                conditions=conditions,
                active=active,
                auth=auth,
            )

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
        ) -> QueueTrigger:
            return await self._original.queue_update_trigger(
                queue_id,
                trigger_id,
                version=version,
                name=name,
                actions=actions,
                conditions=conditions,
                active=active,
                before=before,
                auth=auth,
            )

        # Logs are not cached: they are read to see what just happened.
        async def queue_get_trigger_logs(
            self,
            queue_id: str,
            trigger_id: int,
            *,
            issue_id: str | None = None,
            limit: int | None = None,
            created_from: datetime.datetime | None = None,
            created_to: datetime.datetime | None = None,
            auth: YandexAuth | None = None,
        ) -> list[QueueTriggerLog]:
            return await self._original.queue_get_trigger_logs(
                queue_id,
                trigger_id,
                issue_id=issue_id,
                limit=limit,
                created_from=created_from,
                created_to=created_to,
                auth=auth,
            )

        @cached(**cache_config)
        async def queues_get_autoactions(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[QueueAutoaction]:
            return await self._original.queues_get_autoactions(queue_id, auth=auth)

        @cached(**cache_config)
        async def queue_get_autoaction(
            self, queue_id: str, autoaction_id: int, *, auth: YandexAuth | None = None
        ) -> QueueAutoaction:
            return await self._original.queue_get_autoaction(
                queue_id, autoaction_id, auth=auth
            )

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
        ) -> QueueAutoaction:
            return await self._original.queue_create_autoaction(
                queue_id,
                name=name,
                actions=actions,
                filter=filter,
                query=query,
                active=active,
                enable_notifications=enable_notifications,
                interval_millis=interval_millis,
                calendar_id=calendar_id,
                auth=auth,
            )

        async def queue_get_autoaction_runs(
            self, queue_id: str, autoaction_id: int, *, auth: YandexAuth | None = None
        ) -> list[QueueAutoactionRun]:
            return await self._original.queue_get_autoaction_runs(
                queue_id, autoaction_id, auth=auth
            )

        async def queue_get_autoaction_run(
            self,
            queue_id: str,
            autoaction_id: int,
            run_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> list[QueueAutoactionRunIssue]:
            return await self._original.queue_get_autoaction_run(
                queue_id, autoaction_id, run_id, auth=auth
            )

        @cached(**cache_config)
        async def queues_get_macros(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[QueueMacro]:
            return await self._original.queues_get_macros(queue_id, auth=auth)

        async def queue_get_macro(
            self, queue_id: str, macro_id: int, *, auth: YandexAuth | None = None
        ) -> QueueMacro:
            return await self._original.queue_get_macro(queue_id, macro_id, auth=auth)

        async def queue_create_macro(
            self,
            queue_id: str,
            *,
            name: str,
            body: str | None = None,
            issue_update: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> QueueMacro:
            return await self._original.queue_create_macro(
                queue_id, name=name, body=body, issue_update=issue_update, auth=auth
            )

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
        ) -> QueueMacro:
            return await self._original.queue_update_macro(
                queue_id,
                macro_id,
                name=name,
                body=body,
                issue_update=issue_update,
                clear_body=clear_body,
                auth=auth,
            )

        async def queue_delete_macro(
            self, queue_id: str, macro_id: int, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.queue_delete_macro(
                queue_id, macro_id, auth=auth
            )

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
        ) -> Queue:
            return await self._original.queue_create(
                key=key,
                name=name,
                lead=lead,
                default_type=default_type,
                default_priority=default_priority,
                issue_types_config=issue_types_config,
                auth=auth,
            )

        async def queue_delete(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.queue_delete(queue_id, auth=auth)

        async def queue_restore(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> Queue:
            return await self._original.queue_restore(queue_id, auth=auth)

        # Not cached: the whole list is written back, so a stale read would undo
        # whatever changed in between.
        async def queue_get_fresh(
            self,
            queue_id: str,
            *,
            expand: list[QueueExpandOption] | None = None,
            auth: YandexAuth | None = None,
        ) -> Queue:
            return await self._original.queue_get_fresh(
                queue_id, expand=expand, auth=auth
            )

        async def queue_update_issue_types_config(
            self,
            queue_id: str,
            *,
            issue_types_config: list[QueueIssueTypeConfigInput],
            default_type: str | None = None,
            auth: YandexAuth | None = None,
        ) -> Queue:
            return await self._original.queue_update_issue_types_config(
                queue_id,
                issue_types_config=issue_types_config,
                default_type=default_type,
                auth=auth,
            )

    class CachingIssuesProtocol(IssueProtocolWrap):
        @cached(**cache_config)
        async def issue_get(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> Issue:
            return await self._original.issue_get(issue_id, auth=auth)

        @cached(**cache_config)
        async def issues_get_links(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[IssueLink]:
            return await self._original.issues_get_links(issue_id, auth=auth)

        async def issue_add_link(
            self,
            issue_id: str,
            *,
            relationship: IssueLinkRelationship,
            issue: str,
            auth: YandexAuth | None = None,
        ) -> IssueLink:
            return await self._original.issue_add_link(
                issue_id,
                relationship=relationship,
                issue=issue,
                auth=auth,
            )

        async def issue_delete_link(
            self,
            issue_id: str,
            link_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.issue_delete_link(issue_id, link_id, auth=auth)

        @cached(**cache_config)
        async def issue_get_comments(
            self,
            issue_id: str,
            *,
            per_page: int = 50,
            cursor: str | None = None,
            auth: YandexAuth | None = None,
        ) -> CommentsPage:
            return await self._original.issue_get_comments(
                issue_id, per_page=per_page, cursor=cursor, auth=auth
            )

        async def issue_add_comment(
            self,
            issue_id: str,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            markup_type: str | None = None,
            is_add_to_followers: bool = True,
            attachment_ids: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.issue_add_comment(
                issue_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                markup_type=markup_type,
                is_add_to_followers=is_add_to_followers,
                attachment_ids=attachment_ids,
                auth=auth,
            )

        async def issue_update_comment(
            self,
            issue_id: str,
            comment_id: int,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            markup_type: str | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.issue_update_comment(
                issue_id,
                comment_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                markup_type=markup_type,
                auth=auth,
            )

        async def issues_bulk_update(
            self,
            issues: list[str],
            *,
            values: dict[str, Any],
            notify: bool = False,
            auth: YandexAuth | None = None,
        ) -> BulkChange:
            return await self._original.issues_bulk_update(
                issues, values=values, notify=notify, auth=auth
            )

        async def issues_bulk_transition(
            self,
            issues: list[str],
            *,
            transition: str,
            values: dict[str, Any] | None = None,
            notify: bool = False,
            auth: YandexAuth | None = None,
        ) -> BulkChange:
            return await self._original.issues_bulk_transition(
                issues, transition=transition, values=values, notify=notify, auth=auth
            )

        async def issues_bulk_move(
            self,
            issues: list[str],
            *,
            queue: str,
            values: dict[str, Any] | None = None,
            move_all_fields: bool = False,
            initial_status: bool = False,
            notify: bool = False,
            auth: YandexAuth | None = None,
        ) -> BulkChange:
            return await self._original.issues_bulk_move(
                issues,
                queue=queue,
                values=values,
                move_all_fields=move_all_fields,
                initial_status=initial_status,
                notify=notify,
                auth=auth,
            )

        # Not cached: a bulk change is polled until it ends.
        async def bulk_change_get(
            self, bulk_change_id: str, *, auth: YandexAuth | None = None
        ) -> BulkChange:
            return await self._original.bulk_change_get(bulk_change_id, auth=auth)

        async def bulk_change_get_failures(
            self, bulk_change_id: str, *, auth: YandexAuth | None = None
        ) -> list[BulkChangeFailure]:
            return await self._original.bulk_change_get_failures(
                bulk_change_id, auth=auth
            )

        @cached(**cache_config)
        async def applications_list(
            self, *, auth: YandexAuth | None = None
        ) -> list[ExternalApplication]:
            return await self._original.applications_list(auth=auth)

        @cached(**cache_config)
        async def issue_get_remote_links(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[RemoteLink]:
            return await self._original.issue_get_remote_links(issue_id, auth=auth)

        async def issue_add_remote_link(
            self,
            issue_id: str,
            *,
            origin: str,
            key: str,
            relationship: str = "relates",
            backlink: bool = False,
            auth: YandexAuth | None = None,
        ) -> RemoteLink:
            return await self._original.issue_add_remote_link(
                issue_id,
                origin=origin,
                key=key,
                relationship=relationship,
                backlink=backlink,
                auth=auth,
            )

        async def issue_delete_remote_link(
            self, issue_id: str, link_id: int, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.issue_delete_remote_link(
                issue_id, link_id, auth=auth
            )

        @cached(**cache_config)
        async def issue_get_comment(
            self,
            issue_id: str,
            comment_id: int | str,
            *,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.issue_get_comment(
                issue_id, comment_id, auth=auth
            )

        async def issue_delete_comment(
            self,
            issue_id: str,
            comment_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.issue_delete_comment(
                issue_id, comment_id, auth=auth
            )

        @cached(**cache_config)
        async def issues_find(
            self,
            query: str,
            *,
            per_page: int = 15,
            page: int = 1,
            fields: Sequence[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PaginatedResult[Issue]:
            return await self._original.issues_find(
                query=query,
                per_page=per_page,
                page=page,
                fields=fields,
                auth=auth,
            )

        @cached(**cache_config)
        async def issue_get_worklogs(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[Worklog]:
            return await self._original.issue_get_worklogs(issue_id, auth=auth)

        @cached(**cache_config)
        async def worklogs_find(
            self,
            *,
            created_by: str | None = None,
            created_from: datetime.datetime | None = None,
            created_to: datetime.datetime | None = None,
            auth: YandexAuth | None = None,
        ) -> list[Worklog]:
            return await self._original.worklogs_find(
                created_by=created_by,
                created_from=created_from,
                created_to=created_to,
                auth=auth,
            )

        async def issue_add_worklog(
            self,
            issue_id: str,
            *,
            duration: str,
            comment: str | None = None,
            start: datetime.datetime | None = None,
            auth: YandexAuth | None = None,
        ) -> Worklog:
            return await self._original.issue_add_worklog(
                issue_id,
                duration=duration,
                comment=comment,
                start=start,
                auth=auth,
            )

        async def issue_update_worklog(
            self,
            issue_id: str,
            worklog_id: int,
            *,
            duration: str | None = None,
            comment: str | None = None,
            start: datetime.datetime | None = None,
            auth: YandexAuth | None = None,
        ) -> Worklog:
            return await self._original.issue_update_worklog(
                issue_id,
                worklog_id,
                duration=duration,
                comment=comment,
                start=start,
                auth=auth,
            )

        async def issue_delete_worklog(
            self,
            issue_id: str,
            worklog_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.issue_delete_worklog(
                issue_id,
                worklog_id,
                auth=auth,
            )

        @cached(**cache_config)
        async def issue_get_attachments(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[IssueAttachment]:
            return await self._original.issue_get_attachments(issue_id, auth=auth)

        @cached(**cache_config)
        async def issue_get_attachment(
            self,
            issue_id: str,
            attachment_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> IssueAttachment:
            return await self._original.issue_get_attachment(
                issue_id, attachment_id, auth=auth
            )

        async def issue_delete_attachment(
            self,
            issue_id: str,
            attachment_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.issue_delete_attachment(
                issue_id, attachment_id, auth=auth
            )

        async def issue_add_attachment(
            self,
            issue_id: str,
            *,
            content: bytes,
            filename: str,
            auth: YandexAuth | None = None,
        ) -> IssueAttachment:
            return await self._original.issue_add_attachment(
                issue_id, content=content, filename=filename, auth=auth
            )

        async def attachment_create(
            self,
            *,
            content: bytes,
            filename: str,
            auth: YandexAuth | None = None,
        ) -> IssueAttachment:
            return await self._original.attachment_create(
                content=content, filename=filename, auth=auth
            )

        async def issue_download_attachment(
            self,
            issue_id: str,
            attachment_id: str,
            file_name: str,
            destination: Path,
            *,
            auth: YandexAuth | None = None,
        ) -> int:
            return await self._original.issue_download_attachment(
                issue_id, attachment_id, file_name, destination, auth=auth
            )

        @cached(**cache_config)
        async def issues_count(
            self, query: str, *, auth: YandexAuth | None = None
        ) -> int:
            return await self._original.issues_count(query, auth=auth)

        @cached(**cache_config)
        async def issue_get_checklist(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[ChecklistItem]:
            return await self._original.issue_get_checklist(issue_id, auth=auth)

        async def issue_add_checklist_items(
            self,
            issue_id: str,
            *,
            items: list[ChecklistItemInput],
            auth: YandexAuth | None = None,
        ) -> list[ChecklistItem]:
            return await self._original.issue_add_checklist_items(
                issue_id,
                items=items,
                auth=auth,
            )

        async def issue_update_checklist_item(
            self,
            issue_id: str,
            checklist_item_id: str,
            *,
            text: str | None = None,
            checked: bool | None = None,
            assignee: str | int | None = None,
            deadline: ChecklistItemDeadlineInput | None = None,
            clear_assignee: bool = False,
            clear_deadline: bool = False,
            auth: YandexAuth | None = None,
        ) -> list[ChecklistItem]:
            return await self._original.issue_update_checklist_item(
                issue_id,
                checklist_item_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                clear_assignee=clear_assignee,
                clear_deadline=clear_deadline,
                auth=auth,
            )

        async def issue_delete_checklist_item(
            self,
            issue_id: str,
            checklist_item_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> list[ChecklistItem]:
            return await self._original.issue_delete_checklist_item(
                issue_id,
                checklist_item_id,
                auth=auth,
            )

        async def issue_create(
            self,
            queue: str,
            summary: str,
            *,
            type: IssueTypeRef | str | int | None = None,
            description: str | None = None,
            markup_type: str | None = None,
            assignee: str | int | None = None,
            priority: IssuePriorityRef | str | int | None = None,
            parent: IssueParentRef | str | None = None,
            sprint: Sequence[IssueSprintRef | str | int] | None = None,
            followers: list[IssueFollowerRef] | None = None,
            components: list[IssueComponentRef] | None = None,
            tags: list[str] | None = None,
            project: IssueProjectRef | None = None,
            auth: YandexAuth | None = None,
            fields: dict[str, Any] | None = None,
        ) -> Issue:
            return await self._original.issue_create(
                queue,
                summary,
                type=type,
                description=description,
                markup_type=markup_type,
                assignee=assignee,
                priority=priority,
                parent=parent,
                sprint=sprint,
                followers=followers,
                components=components,
                tags=tags,
                project=project,
                auth=auth,
                fields=fields,
            )

        @cached(**cache_config)
        async def issue_get_transitions(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[IssueTransition]:
            return await self._original.issue_get_transitions(issue_id, auth=auth)

        # Not cached: the changelog is an append-only, growing history. Caching the
        # first page (cursor=None) would keep serving a stale page that misses the
        # most recent changes until the TTL expires.
        async def issue_get_changelog(
            self,
            issue_id: str,
            *,
            per_page: int = 50,
            cursor: str | None = None,
            field: str | None = None,
            type: str | None = None,
            auth: YandexAuth | None = None,
        ) -> ChangelogPage:
            return await self._original.issue_get_changelog(
                issue_id,
                per_page=per_page,
                cursor=cursor,
                field=field,
                type=type,
                auth=auth,
            )

        async def issue_execute_transition(
            self,
            issue_id: str,
            transition_id: str,
            *,
            comment: str | None = None,
            fields: dict[str, str | int | list[str]] | None = None,
            auth: YandexAuth | None = None,
        ) -> list[IssueTransition]:
            return await self._original.issue_execute_transition(
                issue_id,
                transition_id,
                comment=comment,
                fields=fields,
                auth=auth,
            )

        async def issue_close(
            self,
            issue_id: str,
            resolution_id: str,
            *,
            comment: str | None = None,
            fields: dict[str, str | int | list[str]] | None = None,
            auth: YandexAuth | None = None,
        ) -> list[IssueTransition]:
            return await self._original.issue_close(
                issue_id,
                resolution_id,
                comment=comment,
                fields=fields,
                auth=auth,
            )

        async def issue_update(
            self,
            issue_id: str,
            *,
            summary: str | None = None,
            description: str | None = None,
            markup_type: str | None = None,
            parent: IssueParentRef | str | None = None,
            sprint: Sequence[IssueSprintRef | str | int] | None = None,
            type: IssueTypeRef | str | int | None = None,
            priority: IssuePriorityRef | str | int | None = None,
            assignee: str | int | None = None,
            followers: list[IssueFollowerRef] | None = None,
            components: list[IssueComponentRef] | None = None,
            project: IssueProjectRef | None = None,
            attachment_ids: list[str] | None = None,
            description_attachment_ids: list[str] | None = None,
            tags: list[str] | None = None,
            version: int | None = None,
            auth: YandexAuth | None = None,
            fields: dict[str, Any] | None = None,
        ) -> Issue:
            return await self._original.issue_update(
                issue_id,
                summary=summary,
                description=description,
                markup_type=markup_type,
                parent=parent,
                sprint=sprint,
                type=type,
                priority=priority,
                assignee=assignee,
                followers=followers,
                components=components,
                project=project,
                attachment_ids=attachment_ids,
                description_attachment_ids=description_attachment_ids,
                tags=tags,
                version=version,
                auth=auth,
                fields=fields,
            )

        async def issue_move(
            self,
            issue_id: str,
            queue: str,
            *,
            notify: bool = True,
            notify_author: bool = False,
            move_all_fields: bool = False,
            initial_status: bool = False,
            auth: YandexAuth | None = None,
        ) -> Issue:
            return await self._original.issue_move(
                issue_id,
                queue,
                notify=notify,
                notify_author=notify_author,
                move_all_fields=move_all_fields,
                initial_status=initial_status,
                auth=auth,
            )

    class CachingGlobalDataProtocol(GlobalDataProtocolWrap):
        @cached(**cache_config)
        async def get_global_fields(
            self,
            *,
            language: FieldLanguage | None = None,
            auth: YandexAuth | None = None,
        ) -> list[GlobalField]:
            return await self._original.get_global_fields(language=language, auth=auth)

        @cached(**cache_config)
        async def get_statuses(self, *, auth: YandexAuth | None = None) -> list[Status]:
            return await self._original.get_statuses(auth=auth)

        @cached(**cache_config)
        async def get_issue_types(
            self, *, auth: YandexAuth | None = None
        ) -> list[IssueType]:
            return await self._original.get_issue_types(auth=auth)

        @cached(**cache_config)
        async def get_priorities(
            self, *, auth: YandexAuth | None = None
        ) -> list[Priority]:
            return await self._original.get_priorities(auth=auth)

        @cached(**cache_config)
        async def get_resolutions(
            self, *, auth: YandexAuth | None = None
        ) -> list[Resolution]:
            return await self._original.get_resolutions(auth=auth)

        # The single reads are not cached, for the reason component reads are
        # not: the update tools read the current `version` through them.
        async def status_get(
            self, status_id: str, *, auth: YandexAuth | None = None
        ) -> Status:
            return await self._original.status_get(status_id, auth=auth)

        async def status_create(
            self,
            *,
            key: str,
            name: LocalizedText,
            type: StatusType,
            description: str | None = None,
            order: int | None = None,
            auth: YandexAuth | None = None,
        ) -> Status:
            return await self._original.status_create(
                key=key,
                name=name,
                type=type,
                description=description,
                order=order,
                auth=auth,
            )

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
        ) -> Status:
            return await self._original.status_update(
                status_id,
                version=version,
                name=name,
                description=description,
                order=order,
                type=type,
                auth=auth,
            )

        async def resolution_get(
            self, resolution_id: str, *, auth: YandexAuth | None = None
        ) -> Resolution:
            return await self._original.resolution_get(resolution_id, auth=auth)

        async def resolution_create(
            self,
            *,
            key: str,
            name: LocalizedText,
            description: str | None = None,
            order: int | None = None,
            auth: YandexAuth | None = None,
        ) -> Resolution:
            return await self._original.resolution_create(
                key=key, name=name, description=description, order=order, auth=auth
            )

        async def resolution_update(
            self,
            resolution_id: str,
            *,
            version: int,
            name: LocalizedText | None = None,
            description: str | None = None,
            order: int | None = None,
            auth: YandexAuth | None = None,
        ) -> Resolution:
            return await self._original.resolution_update(
                resolution_id,
                version=version,
                name=name,
                description=description,
                order=order,
                auth=auth,
            )

        async def issue_type_get(
            self, issue_type_id: str, *, auth: YandexAuth | None = None
        ) -> IssueType:
            return await self._original.issue_type_get(issue_type_id, auth=auth)

        async def issue_type_create(
            self,
            *,
            key: str,
            name: LocalizedText,
            description: str | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueType:
            return await self._original.issue_type_create(
                key=key, name=name, description=description, auth=auth
            )

        async def issue_type_update(
            self,
            issue_type_id: str,
            *,
            version: int,
            name: LocalizedText | None = None,
            description: str | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueType:
            return await self._original.issue_type_update(
                issue_type_id,
                version=version,
                name=name,
                description=description,
                auth=auth,
            )

        async def priority_get(
            self, priority_id: str, *, auth: YandexAuth | None = None
        ) -> Priority:
            return await self._original.priority_get(priority_id, auth=auth)

        async def priority_create(
            self,
            *,
            key: str,
            name: LocalizedText,
            description: str | None = None,
            order: int | None = None,
            auth: YandexAuth | None = None,
        ) -> Priority:
            return await self._original.priority_create(
                key=key, name=name, description=description, order=order, auth=auth
            )

        async def priority_update(
            self,
            priority_id: str,
            *,
            version: int,
            name: LocalizedText | None = None,
            description: str | None = None,
            order: int | None = None,
            auth: YandexAuth | None = None,
        ) -> Priority:
            return await self._original.priority_update(
                priority_id,
                version=version,
                name=name,
                description=description,
                order=order,
                auth=auth,
            )

        async def field_get(
            self, field_id: str, *, auth: YandexAuth | None = None
        ) -> GlobalField:
            return await self._original.field_get(field_id, auth=auth)

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
        ) -> GlobalField:
            return await self._original.field_create(
                field_id=field_id,
                name=name,
                category=category,
                type=type,
                description=description,
                order=order,
                readonly=readonly,
                visible=visible,
                hidden=hidden,
                container=container,
                options=options,
                auth=auth,
            )

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
        ) -> GlobalField:
            return await self._original.field_update(
                field_id,
                version=version,
                name=name,
                description=description,
                category=category,
                order=order,
                readonly=readonly,
                visible=visible,
                hidden=hidden,
                options=options,
                user_options=user_options,
                auth=auth,
            )

        @cached(**cache_config)
        async def fields_get_categories(
            self, *, auth: YandexAuth | None = None
        ) -> list[FieldCategory]:
            return await self._original.fields_get_categories(auth=auth)

        async def field_category_get(
            self, category_id: str, *, auth: YandexAuth | None = None
        ) -> FieldCategory:
            return await self._original.field_category_get(category_id, auth=auth)

        async def field_category_create(
            self,
            *,
            name: LocalizedText,
            order: int,
            description: str | None = None,
            auth: YandexAuth | None = None,
        ) -> FieldCategory:
            return await self._original.field_category_create(
                name=name, order=order, description=description, auth=auth
            )

        async def field_category_update(
            self,
            category_id: str,
            *,
            version: int,
            name: LocalizedText | None = None,
            description: str | None = None,
            order: int | None = None,
            auth: YandexAuth | None = None,
        ) -> FieldCategory:
            return await self._original.field_category_update(
                category_id,
                version=version,
                name=name,
                description=description,
                order=order,
                auth=auth,
            )

    class CachingTemplatesProtocol(TemplatesProtocolWrap):
        @cached(**cache_config)
        async def get_issue_templates(
            self,
            *,
            queue: str | None = None,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> PaginatedResult[IssueTemplate]:
            return await self._original.get_issue_templates(
                queue=queue, per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def get_issue_template(
            self, template_id: str, *, auth: YandexAuth | None = None
        ) -> IssueTemplate:
            return await self._original.get_issue_template(template_id, auth=auth)

        @cached(**cache_config)
        async def get_comment_templates(
            self,
            *,
            queue: str | None = None,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> PaginatedResult[CommentTemplate]:
            return await self._original.get_comment_templates(
                queue=queue, per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def get_comment_template(
            self, template_id: str, *, auth: YandexAuth | None = None
        ) -> CommentTemplate:
            return await self._original.get_comment_template(template_id, auth=auth)

    class CachingUsersProtocol(UsersProtocolWrap):
        @cached(**cache_config)
        async def groups_list(
            self, per_page: int = 50, page: int = 1, *, auth: YandexAuth | None = None
        ) -> PaginatedResult[Group]:
            return await self._original.groups_list(
                per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def users_get_absences(
            self,
            users: list[str],
            *,
            date_from: datetime.datetime | None = None,
            date_to: datetime.datetime | None = None,
            auth: YandexAuth | None = None,
        ) -> list[UserAbsences]:
            return await self._original.users_get_absences(
                users, date_from=date_from, date_to=date_to, auth=auth
            )

        @cached(**cache_config)
        async def users_list(
            self, per_page: int = 50, page: int = 1, *, auth: YandexAuth | None = None
        ) -> PaginatedResult[User]:
            return await self._original.users_list(
                per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def user_get(
            self, user_id: str, *, auth: YandexAuth | None = None
        ) -> User | None:
            return await self._original.user_get(user_id, auth=auth)

        @cached(**cache_config)
        async def user_get_current(self, *, auth: YandexAuth | None = None) -> User:
            return await self._original.user_get_current(auth=auth)

    class CachingEntitiesProtocol(EntitiesProtocolWrap):
        @cached(**cache_config)
        async def project_get(
            self,
            entity_id: str,
            *,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_get(entity_id, fields=fields, auth=auth)

        @cached(**cache_config)
        async def project_find(
            self,
            *,
            input: str | None = None,
            filter: dict[str, str | list[str]] | None = None,
            order_by: str | None = None,
            order_asc: bool | None = None,
            root_only: bool | None = None,
            per_page: int = 50,
            page: int = 1,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectSearchResult:
            return await self._original.project_find(
                input=input,
                filter=filter,
                order_by=order_by,
                order_asc=order_asc,
                root_only=root_only,
                per_page=per_page,
                page=page,
                fields=fields,
                auth=auth,
            )

        @cached(**cache_config)
        async def portfolio_get(
            self,
            entity_id: str,
            *,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_get(
                entity_id, fields=fields, auth=auth
            )

        @cached(**cache_config)
        async def portfolio_find(
            self,
            *,
            input: str | None = None,
            filter: dict[str, str | list[str]] | None = None,
            order_by: str | None = None,
            order_asc: bool | None = None,
            root_only: bool | None = None,
            per_page: int = 50,
            page: int = 1,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioSearchResult:
            return await self._original.portfolio_find(
                input=input,
                filter=filter,
                order_by=order_by,
                order_asc=order_asc,
                root_only=root_only,
                per_page=per_page,
                page=page,
                fields=fields,
                auth=auth,
            )

        @cached(**cache_config)
        async def goal_get(
            self,
            entity_id: str,
            *,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> GoalEntity:
            return await self._original.goal_get(entity_id, fields=fields, auth=auth)

        @cached(**cache_config)
        async def goal_find(
            self,
            *,
            input: str | None = None,
            filter: dict[str, str | list[str]] | None = None,
            order_by: str | None = None,
            order_asc: bool | None = None,
            root_only: bool | None = None,
            per_page: int = 50,
            page: int = 1,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> GoalSearchResult:
            return await self._original.goal_find(
                input=input,
                filter=filter,
                order_by=order_by,
                order_asc=order_asc,
                root_only=root_only,
                per_page=per_page,
                page=page,
                fields=fields,
                auth=auth,
            )

        async def project_create(
            self,
            *,
            summary: str,
            description: str | None = None,
            lead: str | None = None,
            team_users: list[str] | None = None,
            clients: list[str] | None = None,
            followers: list[str] | None = None,
            start: datetime.date | datetime.datetime | None = None,
            end: datetime.date | datetime.datetime | None = None,
            tags: list[str] | None = None,
            entity_status: ProjectPortfolioStatus | None = None,
            parent_entity: EntityParentEntityInput | None = None,
            team_access: bool | None = None,
            links: list[ProjectPortfolioLinkInput] | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_create(
                summary=summary,
                description=description,
                lead=lead,
                team_users=team_users,
                clients=clients,
                followers=followers,
                start=start,
                end=end,
                tags=tags,
                entity_status=entity_status,
                parent_entity=parent_entity,
                team_access=team_access,
                links=links,
                fields=fields,
                auth=auth,
            )

        async def project_update(
            self,
            entity_id: str,
            *,
            summary: str | None = None,
            description: str | None = None,
            lead: str | None = None,
            team_users: list[str] | None = None,
            clients: list[str] | None = None,
            followers: list[str] | None = None,
            start: datetime.date | datetime.datetime | None = None,
            end: datetime.date | datetime.datetime | None = None,
            tags: list[str] | None = None,
            entity_status: ProjectPortfolioStatus | None = None,
            parent_entity: EntityParentEntityInput | None = None,
            team_access: bool | None = None,
            links: list[ProjectPortfolioLinkInput] | None = None,
            comment: str | None = None,
            version: int | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_update(
                entity_id,
                summary=summary,
                description=description,
                lead=lead,
                team_users=team_users,
                clients=clients,
                followers=followers,
                start=start,
                end=end,
                tags=tags,
                entity_status=entity_status,
                parent_entity=parent_entity,
                team_access=team_access,
                links=links,
                comment=comment,
                version=version,
                fields=fields,
                auth=auth,
            )

        async def project_delete(
            self,
            entity_id: str,
            *,
            with_board: bool = False,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.project_delete(
                entity_id, with_board=with_board, auth=auth
            )

        async def portfolio_create(
            self,
            *,
            summary: str,
            description: str | None = None,
            lead: str | None = None,
            team_users: list[str] | None = None,
            clients: list[str] | None = None,
            followers: list[str] | None = None,
            start: datetime.date | datetime.datetime | None = None,
            end: datetime.date | datetime.datetime | None = None,
            tags: list[str] | None = None,
            entity_status: ProjectPortfolioStatus | None = None,
            parent_entity: EntityParentEntityInput | None = None,
            team_access: bool | None = None,
            links: list[ProjectPortfolioLinkInput] | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_create(
                summary=summary,
                description=description,
                lead=lead,
                team_users=team_users,
                clients=clients,
                followers=followers,
                start=start,
                end=end,
                tags=tags,
                entity_status=entity_status,
                parent_entity=parent_entity,
                team_access=team_access,
                links=links,
                fields=fields,
                auth=auth,
            )

        async def portfolio_update(
            self,
            entity_id: str,
            *,
            summary: str | None = None,
            description: str | None = None,
            lead: str | None = None,
            team_users: list[str] | None = None,
            clients: list[str] | None = None,
            followers: list[str] | None = None,
            start: datetime.date | datetime.datetime | None = None,
            end: datetime.date | datetime.datetime | None = None,
            tags: list[str] | None = None,
            entity_status: ProjectPortfolioStatus | None = None,
            parent_entity: EntityParentEntityInput | None = None,
            team_access: bool | None = None,
            links: list[ProjectPortfolioLinkInput] | None = None,
            comment: str | None = None,
            version: int | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_update(
                entity_id,
                summary=summary,
                description=description,
                lead=lead,
                team_users=team_users,
                clients=clients,
                followers=followers,
                start=start,
                end=end,
                tags=tags,
                entity_status=entity_status,
                parent_entity=parent_entity,
                team_access=team_access,
                links=links,
                comment=comment,
                version=version,
                fields=fields,
                auth=auth,
            )

        async def portfolio_delete(
            self,
            entity_id: str,
            *,
            with_board: bool = False,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.portfolio_delete(
                entity_id, with_board=with_board, auth=auth
            )

        async def goal_create(
            self,
            *,
            summary: str,
            description: str | None = None,
            lead: str | None = None,
            team_users: list[str] | None = None,
            clients: list[str] | None = None,
            followers: list[str] | None = None,
            end: datetime.date | datetime.datetime | None = None,
            tags: list[str] | None = None,
            entity_status: GoalStatus | None = None,
            parent_entity: EntityParentEntityInput | None = None,
            team_access: bool | None = None,
            links: list[GoalLinkInput] | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> GoalEntity:
            return await self._original.goal_create(
                summary=summary,
                description=description,
                lead=lead,
                team_users=team_users,
                clients=clients,
                followers=followers,
                end=end,
                tags=tags,
                entity_status=entity_status,
                parent_entity=parent_entity,
                team_access=team_access,
                links=links,
                fields=fields,
                auth=auth,
            )

        async def goal_update(
            self,
            entity_id: str,
            *,
            summary: str | None = None,
            description: str | None = None,
            lead: str | None = None,
            team_users: list[str] | None = None,
            clients: list[str] | None = None,
            followers: list[str] | None = None,
            end: datetime.date | datetime.datetime | None = None,
            tags: list[str] | None = None,
            entity_status: GoalStatus | None = None,
            parent_entity: EntityParentEntityInput | None = None,
            team_access: bool | None = None,
            links: list[GoalLinkInput] | None = None,
            comment: str | None = None,
            version: int | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> GoalEntity:
            return await self._original.goal_update(
                entity_id,
                summary=summary,
                description=description,
                lead=lead,
                team_users=team_users,
                clients=clients,
                followers=followers,
                end=end,
                tags=tags,
                entity_status=entity_status,
                parent_entity=parent_entity,
                team_access=team_access,
                links=links,
                comment=comment,
                version=version,
                fields=fields,
                auth=auth,
            )

        async def goal_delete(
            self,
            entity_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.goal_delete(entity_id, auth=auth)

        # Comments are never cached: they mutate frequently and caching would
        # risk serving stale conversation state.
        async def project_get_comments(
            self,
            entity_id: str,
            *,
            per_page: int = 50,
            cursor: str | None = None,
            auth: YandexAuth | None = None,
        ) -> CommentsPage:
            return await self._original.project_get_comments(
                entity_id, per_page=per_page, cursor=cursor, auth=auth
            )

        async def project_add_comment(
            self,
            entity_id: str,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.project_add_comment(
                entity_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                auth=auth,
            )

        async def project_update_comment(
            self,
            entity_id: str,
            comment_id: int,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.project_update_comment(
                entity_id,
                comment_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                auth=auth,
            )

        async def project_delete_comment(
            self,
            entity_id: str,
            comment_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.project_delete_comment(
                entity_id, comment_id, auth=auth
            )

        async def portfolio_get_comments(
            self,
            entity_id: str,
            *,
            per_page: int = 50,
            cursor: str | None = None,
            auth: YandexAuth | None = None,
        ) -> CommentsPage:
            return await self._original.portfolio_get_comments(
                entity_id, per_page=per_page, cursor=cursor, auth=auth
            )

        async def portfolio_add_comment(
            self,
            entity_id: str,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.portfolio_add_comment(
                entity_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                auth=auth,
            )

        async def portfolio_update_comment(
            self,
            entity_id: str,
            comment_id: int,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.portfolio_update_comment(
                entity_id,
                comment_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                auth=auth,
            )

        async def portfolio_delete_comment(
            self,
            entity_id: str,
            comment_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.portfolio_delete_comment(
                entity_id, comment_id, auth=auth
            )

        async def goal_get_comments(
            self,
            entity_id: str,
            *,
            per_page: int = 50,
            cursor: str | None = None,
            auth: YandexAuth | None = None,
        ) -> CommentsPage:
            return await self._original.goal_get_comments(
                entity_id, per_page=per_page, cursor=cursor, auth=auth
            )

        async def goal_add_comment(
            self,
            entity_id: str,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.goal_add_comment(
                entity_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                auth=auth,
            )

        async def goal_update_comment(
            self,
            entity_id: str,
            comment_id: int,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            return await self._original.goal_update_comment(
                entity_id,
                comment_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                auth=auth,
            )

        async def goal_delete_comment(
            self,
            entity_id: str,
            comment_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.goal_delete_comment(
                entity_id, comment_id, auth=auth
            )

        async def project_add_checklist_item(
            self,
            entity_id: str,
            *,
            text: str,
            checked: bool | None = None,
            assignee: str | None = None,
            deadline: dict[str, Any] | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_add_checklist_item(
                entity_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )

        async def project_update_checklist_item(
            self,
            entity_id: str,
            checklist_item_id: str,
            *,
            text: str | None = None,
            checked: bool | None = None,
            assignee: str | None = None,
            deadline: dict[str, Any] | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_update_checklist_item(
                entity_id,
                checklist_item_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )

        async def project_move_checklist_item(
            self,
            entity_id: str,
            checklist_item_id: str,
            *,
            before: str,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_move_checklist_item(
                entity_id,
                checklist_item_id,
                before=before,
                fields=fields,
                auth=auth,
            )

        async def project_delete_checklist_item(
            self,
            entity_id: str,
            checklist_item_id: str,
            *,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_delete_checklist_item(
                entity_id,
                checklist_item_id,
                fields=fields,
                auth=auth,
            )

        async def project_update_checklist(
            self,
            entity_id: str,
            *,
            items: list[EntityChecklistItemUpdateInput],
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_update_checklist(
                entity_id,
                items=items,
                fields=fields,
                auth=auth,
            )

        async def project_delete_checklist(
            self,
            entity_id: str,
            *,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> ProjectEntity:
            return await self._original.project_delete_checklist(
                entity_id, fields=fields, auth=auth
            )

        async def portfolio_add_checklist_item(
            self,
            entity_id: str,
            *,
            text: str,
            checked: bool | None = None,
            assignee: str | None = None,
            deadline: dict[str, Any] | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_add_checklist_item(
                entity_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )

        async def portfolio_update_checklist_item(
            self,
            entity_id: str,
            checklist_item_id: str,
            *,
            text: str | None = None,
            checked: bool | None = None,
            assignee: str | None = None,
            deadline: dict[str, Any] | None = None,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_update_checklist_item(
                entity_id,
                checklist_item_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )

        async def portfolio_move_checklist_item(
            self,
            entity_id: str,
            checklist_item_id: str,
            *,
            before: str,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_move_checklist_item(
                entity_id,
                checklist_item_id,
                before=before,
                fields=fields,
                auth=auth,
            )

        async def portfolio_delete_checklist_item(
            self,
            entity_id: str,
            checklist_item_id: str,
            *,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_delete_checklist_item(
                entity_id,
                checklist_item_id,
                fields=fields,
                auth=auth,
            )

        async def portfolio_update_checklist(
            self,
            entity_id: str,
            *,
            items: list[EntityChecklistItemUpdateInput],
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_update_checklist(
                entity_id,
                items=items,
                fields=fields,
                auth=auth,
            )

        async def portfolio_delete_checklist(
            self,
            entity_id: str,
            *,
            fields: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> PortfolioEntity:
            return await self._original.portfolio_delete_checklist(
                entity_id, fields=fields, auth=auth
            )

    class CachingBoardsProtocol(BoardsProtocolWrap):
        @cached(**cache_config)
        async def boards_list(
            self,
            *,
            per_page: int = 100,
            cursor: int | None = None,
            auth: YandexAuth | None = None,
        ) -> list[Board]:
            return await self._original.boards_list(
                per_page=per_page, cursor=cursor, auth=auth
            )

        @cached(**cache_config)
        async def board_get(
            self, board_id: int, *, auth: YandexAuth | None = None
        ) -> Board:
            return await self._original.board_get(board_id, auth=auth)

        @cached(**cache_config)
        async def board_get_columns(
            self, board_id: int, *, auth: YandexAuth | None = None
        ) -> list[BoardColumnDetail]:
            return await self._original.board_get_columns(board_id, auth=auth)

        @cached(**cache_config)
        async def board_get_sprints(
            self, board_id: int, *, auth: YandexAuth | None = None
        ) -> list[Sprint]:
            return await self._original.board_get_sprints(board_id, auth=auth)

        # Sprint reads are not cached: the write tools read the sprint for the
        # `version` its If-Match needs, and a cached one would be stale.
        async def sprint_get(
            self, sprint_id: int, *, auth: YandexAuth | None = None
        ) -> Sprint:
            return await self._original.sprint_get(sprint_id, auth=auth)

        async def sprint_create(
            self,
            board_id: int,
            *,
            name: str,
            start_date: datetime.date,
            end_date: datetime.date,
            auth: YandexAuth | None = None,
        ) -> Sprint:
            return await self._original.sprint_create(
                board_id,
                name=name,
                start_date=start_date,
                end_date=end_date,
                auth=auth,
            )

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
        ) -> Sprint:
            return await self._original.sprint_update(
                sprint_id,
                version=version,
                name=name,
                start_date=start_date,
                end_date=end_date,
                status=status,
                auth=auth,
            )

        async def sprint_start(
            self, sprint_id: int, *, version: int, auth: YandexAuth | None = None
        ) -> Sprint:
            return await self._original.sprint_start(
                sprint_id, version=version, auth=auth
            )

        async def sprint_archive(
            self, sprint_id: int, *, version: int, auth: YandexAuth | None = None
        ) -> Sprint:
            return await self._original.sprint_archive(
                sprint_id, version=version, auth=auth
            )

        async def sprint_delete(
            self, sprint_id: int, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.sprint_delete(sprint_id, auth=auth)

    class CachingComponentsProtocol(ComponentsProtocolWrap):
        async def component_get_user_permissions(
            self, component_id: int, user: str, *, auth: YandexAuth | None = None
        ) -> SubjectPermissions:
            return await self._original.component_get_user_permissions(
                component_id, user, auth=auth
            )

        async def component_get_group_permissions(
            self, component_id: int, group_id: int, *, auth: YandexAuth | None = None
        ) -> SubjectPermissions:
            return await self._original.component_get_group_permissions(
                component_id, group_id, auth=auth
            )

        # Component reads are not cached. The `component_update` /
        # `component_delete` tools read through this protocol to get the
        # `version` the API demands (428 without one) and to learn the queue,
        # and there is no omit-version escape as there is for issues, so a
        # cached read would feed the PATCH a stale version for the rest of the
        # TTL. Every protocol method is still overridden - a wrapper that
        # forgets one answers `None` for it under TOOLS_CACHE_ENABLED.
        async def component_get(
            self, component_id: int, *, auth: YandexAuth | None = None
        ) -> Component:
            return await self._original.component_get(component_id, auth=auth)

        async def component_create(
            self,
            queue_id: str,
            *,
            name: str,
            description: str | None = None,
            lead: str | None = None,
            assign_auto: bool | None = None,
            auth: YandexAuth | None = None,
        ) -> Component:
            return await self._original.component_create(
                queue_id,
                name=name,
                description=description,
                lead=lead,
                assign_auto=assign_auto,
                auth=auth,
            )

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
        ) -> Component:
            return await self._original.component_update(
                component_id,
                version=version,
                name=name,
                description=description,
                lead=lead,
                assign_auto=assign_auto,
                clear_lead=clear_lead,
                auth=auth,
            )

        async def component_delete(
            self, component_id: int, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.component_delete(component_id, auth=auth)

    class CachingWorkflowsProtocol(WorkflowsProtocolWrap):
        # Workflow reads are not cached, for the reason component reads are
        # not: the write tools read the current `version` (required, 412 when
        # stale) and the current transitions to rewrite them, and a cached
        # read would hand them a stale workflow for the rest of the TTL.
        async def workflows_get_all(
            self, *, auth: YandexAuth | None = None
        ) -> list[Workflow]:
            return await self._original.workflows_get_all(auth=auth)

        async def workflow_get(
            self, workflow_id: str, *, auth: YandexAuth | None = None
        ) -> Workflow:
            return await self._original.workflow_get(workflow_id, auth=auth)

        async def queues_get_workflows(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> dict[str, list[IssueTypeReference]]:
            return await self._original.queues_get_workflows(queue_id, auth=auth)

        async def screen_get(
            self, screen_id: int, *, auth: YandexAuth | None = None
        ) -> Screen:
            return await self._original.screen_get(screen_id, auth=auth)

        async def workflow_get_draft(
            self, workflow_id: str, *, auth: YandexAuth | None = None
        ) -> WorkflowDraft:
            return await self._original.workflow_get_draft(workflow_id, auth=auth)

        async def workflow_create(
            self,
            *,
            name: str,
            initial_action: WorkflowActionDraft,
            steps: list[WorkflowStepDraft],
            queue: str | None = None,
            auth: YandexAuth | None = None,
        ) -> Workflow:
            return await self._original.workflow_create(
                name=name,
                initial_action=initial_action,
                steps=steps,
                queue=queue,
                auth=auth,
            )

        async def workflow_update(
            self,
            workflow_id: str,
            *,
            version: int,
            name: str | None = None,
            initial_action: WorkflowActionDraft | None = None,
            steps: list[WorkflowStepDraft] | None = None,
            issue_type_resolutions: list[IssueTypeResolutionsDraft] | None = None,
            auth: YandexAuth | None = None,
        ) -> Workflow:
            return await self._original.workflow_update(
                workflow_id,
                version=version,
                name=name,
                initial_action=initial_action,
                steps=steps,
                issue_type_resolutions=issue_type_resolutions,
                auth=auth,
            )

        async def workflow_add_action(
            self,
            workflow_id: str,
            status: str,
            *,
            version: int,
            action: WorkflowActionDraft,
            auth: YandexAuth | None = None,
        ) -> Workflow:
            return await self._original.workflow_add_action(
                workflow_id, status, version=version, action=action, auth=auth
            )

        async def workflow_update_action(
            self,
            workflow_id: str,
            status: str,
            action_id: str,
            *,
            version: int,
            action: WorkflowActionDraft,
            auth: YandexAuth | None = None,
        ) -> Workflow:
            return await self._original.workflow_update_action(
                workflow_id,
                status,
                action_id,
                version=version,
                action=action,
                auth=auth,
            )

        async def workflow_delete(
            self, workflow_id: str, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.workflow_delete(workflow_id, auth=auth)

    return CacheCollection(
        queues=CachingQueuesProtocol,
        issues=CachingIssuesProtocol,
        global_data=CachingGlobalDataProtocol,
        templates=CachingTemplatesProtocol,
        users=CachingUsersProtocol,
        entities=CachingEntitiesProtocol,
        boards=CachingBoardsProtocol,
        components=CachingComponentsProtocol,
        workflows=CachingWorkflowsProtocol,
    )
