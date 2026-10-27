import asyncio
import datetime
import json
import logging
import mimetypes
import random
import time
from asyncio import CancelledError
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal, TypeVar
from urllib.parse import quote

import jwt
import yandexcloud
from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout, FormData
from pydantic import BaseModel, Field, RootModel
from yandex.cloud.iam.v1.iam_token_service_pb2 import CreateIamTokenRequest
from yandex.cloud.iam.v1.iam_token_service_pb2_grpc import IamTokenServiceStub
from yarl import URL

from mcp_tracker.tracker.custom.errors import (
    AbsencesForbidden,
    AttachmentNotFound,
    AttachmentTooLarge,
    AutoactionNotFound,
    BoardColumnEmptyUpdate,
    BoardEmptyUpdate,
    BoardNotFound,
    BoardVersionConflict,
    BulkChangeNotFound,
    CatalogEmptyUpdate,
    CatalogObjectNotFound,
    CatalogVersionConflict,
    ChecklistBatchPartiallyAdded,
    ChecklistItemEmptyUpdate,
    ChecklistItemNotFound,
    CommentNotFound,
    CommentTemplateNotFound,
    ComponentEmptyUpdate,
    ComponentNotFound,
    ComponentVersionConflict,
    EntityLinksOnlyUpdate,
    FieldClearConflict,
    FilterConditionsConflict,
    FilterEmptyUpdate,
    FilterNotFound,
    IssueNotFound,
    IssueTemplateNotFound,
    IssueVersionConflict,
    LocalFieldNotFound,
    MacroNotFound,
    NoDoneTransition,
    PermissionsEmptyUpdate,
    QueueNotFound,
    ScreenNotFound,
    SprintEmptyUpdate,
    SprintNotFound,
    SprintVersionConflict,
    TrackerAPIConnectionError,
    TrackerAPIError,
    TrackerAPITimeout,
    TrackerAuthConfigError,
    TrackerRateLimited,
    TriggerEmptyUpdate,
    TriggerNotFound,
    TriggerVersionConflict,
    VersionEmptyUpdate,
    VersionNotFound,
    WorkflowNotFound,
    WorkflowVersionConflict,
    WorklogSearchTooLarge,
    YandexTrackerError,
)
from mcp_tracker.tracker.proto.boards import BoardsProtocol
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.components import ComponentsProtocol
from mcp_tracker.tracker.proto.entities import EntitiesProtocol
from mcp_tracker.tracker.proto.fields import GlobalDataProtocol
from mcp_tracker.tracker.proto.issues import IssueProtocol
from mcp_tracker.tracker.proto.queues import QueuesProtocol
from mcp_tracker.tracker.proto.templates import TemplatesProtocol
from mcp_tracker.tracker.proto.types.boards import Board, BoardColumnDetail, Sprint
from mcp_tracker.tracker.proto.types.components import Component
from mcp_tracker.tracker.proto.types.entities import (
    DEFAULT_ENTITY_FIELDS_PARAM,
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
    FIELD_TYPES,
    FieldCategory,
    FieldLanguage,
    FieldType,
    GlobalField,
    LocalField,
)
from mcp_tracker.tracker.proto.types.filters import FilterSort, IssueFilter
from mcp_tracker.tracker.proto.types.inputs import (
    BoardColumnInput,
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
    ChangelogEntry,
    ChangelogPage,
    ChecklistItem,
    CommentReaction,
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
from mcp_tracker.tracker.proto.types.pagination import ItemT, PaginatedResult
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
    QueueForms,
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
from mcp_tracker.tracker.proto.types.users import (
    User,
    UserAbsences,
)
from mcp_tracker.tracker.proto.types.workflows import (
    IssueTypeResolutionsDraft,
    LocalizedText,
    Screen,
    ScreenDraft,
    ScreenElementDraft,
    Workflow,
    WorkflowAction,
    WorkflowActionDraft,
    WorkflowDraft,
    WorkflowStepDraft,
)
from mcp_tracker.tracker.proto.users import UsersProtocol
from mcp_tracker.tracker.proto.workflows import WorkflowsProtocol

QueueList = RootModel[list[Queue]]
LocalFieldList = RootModel[list[LocalField]]
QueueTagList = RootModel[list[str]]
QueueTriggerList = RootModel[list[QueueTrigger]]
QueueTriggerLogList = RootModel[list[QueueTriggerLog]]
QueueAutoactionList = RootModel[list[QueueAutoaction]]
QueueAutoactionRunList = RootModel[list[QueueAutoactionRun]]
QueueAutoactionRunIssueList = RootModel[list[QueueAutoactionRunIssue]]
QueueMacroList = RootModel[list[QueueMacro]]
VersionList = RootModel[list[QueueVersion]]
ComponentList = RootModel[list[Component]]
WorkflowList = RootModel[list[Workflow]]
QueueWorkflows = RootModel[dict[str, list[IssueTypeReference]]]
IssueLinkList = RootModel[list[IssueLink]]
IssueList = RootModel[list[Issue]]
IssueCommentList = RootModel[list[IssueComment]]
WorklogList = RootModel[list[Worklog]]
IssueAttachmentList = RootModel[list[IssueAttachment]]
BulkChangeFailureList = RootModel[list[BulkChangeFailure]]
ExternalApplicationList = RootModel[list[ExternalApplication]]
RemoteLinkList = RootModel[list[RemoteLink]]


class AbsenceSearchPage(BaseModel):
    user_gaps: list[UserAbsences] = Field(default_factory=list, alias="userGaps")
    has_more: bool = Field(False, alias="hasMore")


ChecklistItemList = RootModel[list[ChecklistItem]]


class EntityCommentsRelativePage(BaseModel):
    """Raw response of `GET /v3/entities/<type>/<id>/comments/_relative`.

    Unlike the issue comment endpoint, entity comments paginate through a
    dedicated `_relative` endpoint that answers with an object and signals more
    pages via `hasNext` rather than a `Link` header.
    """

    comments: list[IssueComment] = Field(default_factory=list)
    hasNext: bool = False
    hasPrev: bool = False


class _ChecklistSnapshotFields(BaseModel):
    checklistItems: list[ChecklistItem] = Field(default_factory=list)


class _ChecklistSnapshot(BaseModel):
    """Minimal parse of a `GET /v3/entities/<type>/<id>?fields=checklistItems`
    response, used to reconcile a partial `*_update_checklist` call - see
    `TrackerClient._reconcile_checklist_update`.
    """

    fields: _ChecklistSnapshotFields = Field(default_factory=_ChecklistSnapshotFields)


class _IssueChecklist(_ChecklistSnapshotFields):
    """Minimal parse of the issue payload the issue checklist write endpoints
    answer with - only the resulting checklist is of interest to the caller.

    The key is absent once the last item is deleted, hence the default.
    """


GlobalFieldList = RootModel[list[GlobalField]]
FieldCategoryList = RootModel[list[FieldCategory]]
GroupList = RootModel[list[Group]]
StatusList = RootModel[list[Status]]
IssueTypeList = RootModel[list[IssueType]]
PriorityList = RootModel[list[Priority]]
ResolutionList = RootModel[list[Resolution]]
IssueTemplateList = RootModel[list[IssueTemplate]]
CommentTemplateList = RootModel[list[CommentTemplate]]
UserList = RootModel[list[User]]
IssueTransitionList = RootModel[list[IssueTransition]]
ChangelogList = RootModel[list[ChangelogEntry]]
BoardList = RootModel[list[Board]]
BoardColumnList = RootModel[list[BoardColumnDetail]]
SprintList = RootModel[list[Sprint]]


logger = logging.getLogger(__name__)


def _ref_body(value: BaseModel | str | int) -> Any:
    """Serialize a reference field value for an issue create/update body.

    Reference models are sent as `{"id": ...}` / `{"key": ...}` objects, which
    Tracker resolves by identifier; bare scalars are passed through untouched
    and are resolved by Tracker as a key/login (string) or id (number).
    """
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    return value


def _issue_types_config_body(
    config: Sequence[QueueIssueTypeConfigInput],
) -> list[dict[str, Any]]:
    """`issueTypesConfig` as `POST v3/queues` and `PATCH v3/queues/{key}` take it."""
    return [
        {
            "issueType": item.issue_type,
            "workflow": item.workflow,
            "resolutions": list(item.resolutions),
        }
        for item in config
    ]


def _column_body(column: BoardColumnInput) -> dict[str, Any]:
    """A board column as `POST v3/liveBoards` and the column writes take it."""
    return column.model_dump(exclude_none=True)


def _sprints_body(enabled: bool) -> dict[str, bool]:
    """Sprints and backlog go together: the API documents them as one switch."""
    return {"sprintsAvailable": enabled, "backlogAvailable": enabled}


def _if_match(version: int | None) -> dict[str, str] | None:
    """The `If-Match` header of a versioned write, or none for an unconditional one.

    The quotes are part of the value: a bare number answers 400.
    """
    return None if version is None else {"If-Match": f'"{version}"'}


def _board_conflict(board_id: int, version: int | None) -> BoardVersionConflict | None:
    return None if version is None else BoardVersionConflict(board_id, version)


def _tracker_datetime(value: datetime.datetime) -> str:
    """Format a datetime the way Tracker wants it: `YYYY-MM-DDThh:mm:ss.ffffff+0000`.

    A naive datetime is read as UTC, and the offset is emitted without a colon -
    the form the API accepts.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f%z")


class ServiceAccountSettings(BaseModel):
    key_id: str
    service_account_id: str
    private_key: str

    def to_yandexcloud_dict(self) -> dict[str, str]:
        return {
            "id": self.key_id,
            "service_account_id": self.service_account_id,
            "private_key": self.private_key,
        }


class IAMTokenInfo(BaseModel):
    token: str


class ServiceAccountStore:
    DEFAULT_REFRESH_INTERVAL: float = 3500.0
    DEFAULT_RETRY_INTERVAL: float = 10.0

    def __init__(
        self,
        settings: ServiceAccountSettings,
        *,
        refresh_interval: float | None = None,
        retry_interval: float | None = None,
    ):
        self._settings = settings
        self._refresh_interval = refresh_interval or self.DEFAULT_REFRESH_INTERVAL
        self._retry_interval = retry_interval or self.DEFAULT_RETRY_INTERVAL

        self._yc_sdk = yandexcloud.SDK(
            service_account_key=self._settings.to_yandexcloud_dict()
        )
        self._iam_service = self._yc_sdk.client(IamTokenServiceStub)
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._iam_token: IAMTokenInfo | None = None
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[None] | None = None

    async def prepare(self):
        self._refresh_task = asyncio.create_task(self._refresher())

    async def close(self):
        try:
            if self._refresh_task is not None:
                self._refresh_task.cancel()
                await self._refresh_task
                self._refresh_task = None
        except CancelledError:
            return
        except Exception as e:  # pragma: no cover
            logger.error("error while closing ServiceAccountStore: %s", e)

    async def get_iam_token(self, *, force_refresh: bool = False) -> str:
        if force_refresh or self._iam_token is None:
            async with self._lock:
                if not force_refresh and self._iam_token is not None:
                    return self._iam_token.token

                iam_token = await asyncio.get_running_loop().run_in_executor(
                    self._executor, self._fetch_iam_token, self._settings
                )

                self._iam_token = iam_token
                logger.info("Successfully fetched new IAM token.")

        return self._iam_token.token

    async def _refresher(self):
        while True:
            try:
                await self.get_iam_token(force_refresh=True)
                interval = self._refresh_interval
            except asyncio.CancelledError:  # pragma: no cover
                return
            except Exception as e:
                logger.error("Error refreshing IAM token: %s", e)
                interval = self._retry_interval

            jitter = random.random() * min(interval * 0.1, 100)
            await asyncio.sleep(interval + jitter)

    def _fetch_iam_token(self, service_account: ServiceAccountSettings) -> IAMTokenInfo:
        now = int(time.time())
        payload = {
            "aud": "https://iam.api.cloud.yandex.net/iam/v1/tokens",
            "iss": service_account.service_account_id,
            "iat": now,
            "exp": now + 3600,
        }

        jwt_token = jwt.encode(
            payload=payload,
            key=service_account.private_key,
            algorithm="PS256",
            headers={"kid": service_account.key_id},
        )

        iam_token = self._iam_service.Create(CreateIamTokenRequest(jwt=jwt_token))
        return IAMTokenInfo(token=iam_token.iam_token)


# `GET /v3/boards/_paginate` documents `perPage` as no more than 500.
BOARDS_PAGE_MAX = 500


def _attachment_form(content: bytes, filename: str) -> FormData:
    """The multipart body of an attachment upload.

    The part is named `file`, as the API requires, and carries the name too -
    the callers also send it as the documented `filename` query parameter.
    """
    form = FormData()
    form.add_field(
        "file",
        content,
        filename=filename,
        content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
    )
    return form


# 429 Too Many Requests: the waits before each retry when Tracker sends no
# `Retry-After`, and the longest `Retry-After` still sat out rather than raised.
_RATE_LIMIT_BACKOFF = (1.0, 2.0, 4.0)
_RATE_LIMIT_MAX_WAIT = 10.0


def _retry_after(response: ClientResponse) -> float | None:
    """Seconds the `Retry-After` header asks for - a number or an HTTP date."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.UTC)
    return max((when - datetime.datetime.now(datetime.UTC)).total_seconds(), 0.0)


_TRIGGERS_PER_PAGE = 100

# A guard against a `next` link that never ends, not a page size.
_MAX_WORKLOG_SEARCH_PAGES = 50


_CatalogT = TypeVar("_CatalogT", bound=BaseModel)


@dataclass(frozen=True)
class _Catalog:
    """One of the organization's catalogues: where it lives in the API, what
    an error calls it and which tool lists it."""

    path: str
    kind: str
    listing: str
    update_fields: tuple[str, ...]

    def not_found(self, object_id: str) -> CatalogObjectNotFound:
        return CatalogObjectNotFound(self.kind, object_id, self.listing)

    def conflict(self, object_id: str, version: int) -> CatalogVersionConflict:
        return CatalogVersionConflict(self.kind, object_id, version, self.listing)


_STATUSES = _Catalog(
    "v3/statuses",
    "status",
    "get_statuses",
    ("name", "name_en", "description", "order", "type"),
)
_RESOLUTIONS = _Catalog(
    "v3/resolutions",
    "resolution",
    "get_resolutions",
    ("name", "name_en", "description", "order"),
)
_ISSUE_TYPES = _Catalog(
    "v3/issuetypes", "issue type", "get_issue_types", ("name", "name_en", "description")
)
_PRIORITIES = _Catalog(
    "v3/priorities",
    "priority",
    "get_priorities",
    ("name", "name_en", "description", "order"),
)
_FIELDS = _Catalog(
    "v3/fields",
    "field",
    "get_global_fields",
    (
        "name",
        "name_en",
        "description",
        "category",
        "order",
        "readonly",
        "visible",
        "hidden",
        "options",
    ),
)
_FIELD_CATEGORIES = _Catalog(
    "v3/fields/categories",
    "field category",
    "fields_get_categories",
    ("name", "name_en", "description", "order"),
)


def _catalog_body(name: LocalizedText | None, **fields: Any) -> dict[str, Any]:
    """The body of a catalogue write: the fields passed, the name in both
    languages. Always an object - the documentation shows some of these
    request bodies as a one-element array, taken here for a slip in it."""
    body = {k: v for k, v in fields.items() if v is not None}
    if name is not None:
        body["name"] = name.model_dump()
    return body


_FIELD_TYPE_PREFIX = "ru.yandex.startrek.core.fields."


def _options_provider(
    users: bool, options: list[str | int | float] | None
) -> dict[str, Any] | None:
    """The drop-down list of a field, which replaces the whole list - a user
    field takes a list of users, any other a list of values."""
    if options is None:
        return None
    kind = "FixedUserListOptionsProvider" if users else "FixedListOptionsProvider"
    return {"type": kind, "values": options}


def _one_catalog_object(model: type[_CatalogT], raw: bytes) -> _CatalogT:
    """A catalogue object from the body of a read or a write.

    The documentation shows some of these answers as an object and others
    (status and issue type create and update) as a one-element array holding
    it. Not checked against the live API, so both are accepted.
    """
    data = json.loads(raw)
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    return model.model_validate(data)


class TrackerClient(
    QueuesProtocol,
    IssueProtocol,
    GlobalDataProtocol,
    TemplatesProtocol,
    UsersProtocol,
    EntitiesProtocol,
    BoardsProtocol,
    ComponentsProtocol,
    WorkflowsProtocol,
):
    def __init__(
        self,
        *,
        token: str | None,
        iam_token: str | None = None,
        token_type: Literal["Bearer", "OAuth"] | None = None,
        service_account: ServiceAccountSettings | None = None,
        org_id: str | None = None,
        cloud_org_id: str | None = None,
        base_url: str = "https://api.tracker.yandex.net",
        timeout: float = 10,
        attachment_timeout: float = 300,
        max_attachment_bytes: int = 50 * 1024 * 1024,
    ):
        self._token = token
        self._token_type = token_type
        self._static_iam_token = iam_token
        self._service_account_store: ServiceAccountStore | None = (
            ServiceAccountStore(service_account) if service_account else None
        )
        self._org_id = org_id
        self._cloud_org_id = cloud_org_id

        self._timeout = timeout
        self._attachment_timeout = attachment_timeout
        self._max_attachment_bytes = max_attachment_bytes
        self._session = ClientSession(
            base_url=base_url,
            timeout=ClientTimeout(total=timeout),
        )

    async def prepare(self):
        if self._service_account_store:
            await self._service_account_store.prepare()

    async def close(self):
        if self._service_account_store:
            await self._service_account_store.close()
        await self._session.close()

    async def _build_headers(self, auth: YandexAuth | None = None) -> dict[str, str]:
        # Priority: OAuth from auth > static OAuth > static IAM token > service account
        auth_header = None

        if auth and auth.token:
            token_type = self._token_type or "OAuth"
            auth_header = f"{token_type} {auth.token}"
        elif self._token:
            token_type = self._token_type or "OAuth"
            auth_header = f"{token_type} {self._token}"
        elif self._static_iam_token:
            auth_header = f"Bearer {self._static_iam_token}"
        elif self._service_account_store is not None:
            iam_token = await self._service_account_store.get_iam_token()
            auth_header = f"Bearer {iam_token}"

        if not auth_header:
            raise TrackerAuthConfigError(
                "No authentication method provided. "
                "Provide either OAuth token, IAM token, or use OAuth flow."
            )

        headers = {"Authorization": auth_header}

        # Handle org_id logic
        org_id = auth.org_id if auth and auth.org_id else self._org_id
        cloud_org_id = (
            auth.cloud_org_id if auth and auth.cloud_org_id else self._cloud_org_id
        )

        if org_id and cloud_org_id:
            raise TrackerAuthConfigError(
                "Only one of org_id or cloud_org_id should be provided."
            )

        if org_id:
            headers["X-Org-ID"] = org_id
        elif cloud_org_id:
            headers["X-Cloud-Org-ID"] = cloud_org_id
        else:
            raise TrackerAuthConfigError(
                "Either org_id or cloud_org_id must be provided."
            )

        return headers

    @staticmethod
    async def _raise_for_status(response: ClientResponse) -> None:
        """Raise `TrackerAPIError` carrying the API's own explanation of the failure.

        `ClientResponse.raise_for_status()` discards the response body, which is
        where Tracker says *what* it did not like (e.g. which field of an
        issue_create call was rejected with 422), leaving the caller with a bare
        "Unprocessable Entity".
        """
        if response.status < 400:
            return

        try:
            body = await response.text()
        except Exception:  # pragma: no cover - body already consumed/aborted
            body = ""

        raise TrackerAPIError(
            status=response.status,
            method=response.method,
            url=str(response.url),
            body=body,
        )

    @asynccontextmanager
    async def _request(
        self,
        method: str,
        url: str,
        *,
        auth: YandexAuth | None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        not_found: YandexTrackerError | None = None,
        conflict: YandexTrackerError | None = None,
        allow_statuses: Collection[int] = (),
        timeout: float | None = None,
        timeout_setting: str = "TRACKER_API_TIMEOUT",
        extra_headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[ClientResponse]:
        """Every request to the Tracker API goes through here.

        What is handled once here used to be repeated at each of the sixty call
        sites, which is one forgotten line away from a method that reports a
        failure worse than the rest: the timeout below reached the caller from a
        single method until this existed, and a missing `not_found` turns "no
        such issue" back into a bare 404.

        `conflict` covers 409 and 412 alike: an issue update answers a stale
        `version` with 409, a component update with 412, and both mean the same
        thing - the precondition the caller sent no longer holds.

        `allow_statuses` hands a status back to the caller instead of raising -
        for the one method that answers a 404 with `None` rather than an error.

        `timeout` replaces the session's per-request budget for this request, and
        `timeout_setting` names the variable that sets it in the timeout error.
        Only a file upload needs this: the budget covers sending the body, and the
        default one fails any sizable file.

        A 429 is sent again, writes included - Tracker refuses it before running
        it - after the `Retry-After` it asks for or 1, 2 and 4 seconds, then
        raises `TrackerRateLimited`. Agents call tools in parallel and Tracker's
        per-user limit is low enough for four calls at once to hit it.
        """
        # Built before the `try`: the service account's IAM fetch is not a
        # Tracker request and must not be reported as one timing out.
        headers = await self._build_headers(auth)
        if extra_headers:
            headers = {**headers, **extra_headers}
        budget = self._timeout if timeout is None else timeout
        # A multipart body is not sent twice: aiohttp's `FormData` appends its
        # parts to one writer, so a second send is not the same request.
        retries = 0 if data is not None else len(_RATE_LIMIT_BACKOFF)

        try:
            for attempt in range(retries + 1):
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    timeout=ClientTimeout(total=budget),
                ) as response:
                    if response.status == 429 and 429 not in allow_statuses:
                        retry_after = _retry_after(response)
                        # A wait longer than the cap is not sat out here: the
                        # tool call would hang for it with nothing to show.
                        if attempt == retries or (
                            retry_after is not None
                            and retry_after > _RATE_LIMIT_MAX_WAIT
                        ):
                            raise TrackerRateLimited(
                                method=method,
                                url=str(response.url),
                                body=await response.text(),
                                retries=attempt,
                                retry_after=retry_after,
                            )
                        delay = (
                            retry_after
                            if retry_after is not None
                            else _RATE_LIMIT_BACKOFF[attempt]
                        )
                        logger.info("429 on %s %s, retrying in %gs", method, url, delay)
                    else:
                        if response.status not in allow_statuses:
                            if not_found is not None and response.status == 404:
                                raise not_found
                            if conflict is not None and response.status in (409, 412):
                                raise conflict
                            await self._raise_for_status(response)
                        yield response
                        return
                # Outside the `async with`, so the connection is released first.
                await asyncio.sleep(delay)
        except TimeoutError as exc:
            # A body read that times out lands here too: it runs inside the
            # caller's `async with`, and that exception is thrown back in at the
            # `yield` above.
            raise TrackerAPITimeout(
                method=method, url=url, timeout=budget, setting=timeout_setting
            ) from exc
        except ClientError as exc:
            # After the timeout: aiohttp's own timeouts subclass both, and time
            # is the more useful thing to report. `TrackerAPIError` is not a
            # `ClientError`, so a non-2xx is not caught here.
            raise TrackerAPIConnectionError(method=method, url=url, cause=exc) from exc

    async def _read(
        self,
        method: str,
        url: str,
        *,
        auth: YandexAuth | None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        not_found: YandexTrackerError | None = None,
        conflict: YandexTrackerError | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> bytes:
        """The body of a request whose caller needs nothing else from the response."""
        async with self._request(
            method,
            url,
            auth=auth,
            params=params,
            json=json,
            not_found=not_found,
            conflict=conflict,
            extra_headers=extra_headers,
        ) as response:
            return await response.read()

    async def queues_list(
        self, per_page: int = 100, page: int = 1, *, auth: YandexAuth | None = None
    ) -> PaginatedResult[Queue]:
        params = {
            "perPage": per_page,
            "page": page,
        }
        async with self._request(
            "GET", "v3/queues", auth=auth, params=params
        ) as response:
            return self._paginated(
                response, QueueList.model_validate_json(await response.read()).root
            )

    async def queues_get_local_fields(
        self,
        queue_id: str,
        *,
        language: FieldLanguage | None = None,
        auth: YandexAuth | None = None,
    ) -> list[LocalField]:
        return LocalFieldList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/localFields",
                auth=auth,
                not_found=QueueNotFound(queue_id),
                extra_headers={"Accept-Language": language} if language else None,
            )
        ).root

    async def queues_get_tags(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[str]:
        return QueueTagList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/tags",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        ).root

    async def queue_get_forms(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> QueueForms:
        return QueueForms.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/forms",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        )

    # Local fields (verified 2026-10-26): read and changed by their key, while
    # the `id` that comes back is `<hash>--<key>` - the name an issue write
    # takes. An update ignores `version` (a stale one is accepted), and there
    # is no DELETE (405).

    async def queue_get_local_field(
        self, queue_id: str, field_key: str, *, auth: YandexAuth | None = None
    ) -> LocalField:
        return LocalField.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/localFields/{quote(field_key, safe='')}",
                auth=auth,
                not_found=LocalFieldNotFound(queue_id, field_key),
            )
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
        body = _catalog_body(
            name,
            id=field_key,
            category=category,
            type=_FIELD_TYPE_PREFIX + FIELD_TYPES[type],
            description=description,
            order=order,
            readonly=readonly,
            visible=visible,
            hidden=hidden,
            container=container,
            optionsProvider=_options_provider(type == "user", options),
        )
        return LocalField.model_validate_json(
            await self._read(
                "POST",
                f"v3/queues/{queue_id}/localFields",
                auth=auth,
                json=body,
                not_found=QueueNotFound(queue_id),
            )
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
        body = _catalog_body(
            name,
            description=description,
            category=category,
            order=order,
            readonly=readonly,
            visible=visible,
            hidden=hidden,
            optionsProvider=_options_provider(user_options, options),
        )
        if not body:
            raise CatalogEmptyUpdate("local field", _FIELDS.update_fields)
        return LocalField.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/queues/{queue_id}/localFields/{quote(field_key, safe='')}",
                auth=auth,
                json=body,
                not_found=LocalFieldNotFound(queue_id, field_key),
            )
        )

    # Queue permissions (verified 2026-10-26 on the temporary queue MCPTMS).
    # The whole object is read with the undocumented GET of the path the
    # reference documents a PATCH for. A PATCH ignores `version` (a stale one
    # is accepted), answers an empty body with no change, and takes a role in
    # `deny` although the reference says roles cannot be denied; an unknown
    # user or group answers 422.

    async def queue_get_permissions(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> QueuePermissions:
        return QueuePermissions.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/permissions",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        )

    async def queue_get_user_permissions(
        self, queue_id: str, user: str, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions:
        return SubjectPermissions.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/permissions/users/{quote(user, safe='')}",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        )

    async def queue_get_group_permissions(
        self, queue_id: str, group_id: int, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions:
        return SubjectPermissions.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/permissions/groups/{group_id}",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        )

    async def queue_update_permissions(
        self,
        queue_id: str,
        changes: dict[PermissionAction, PermissionChange],
        *,
        auth: YandexAuth | None = None,
    ) -> QueuePermissions:
        if not changes:
            raise PermissionsEmptyUpdate()
        body = {action: change.to_api() for action, change in changes.items()}
        return QueuePermissions.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/queues/{queue_id}/permissions",
                auth=auth,
                json=body,
                not_found=QueueNotFound(queue_id),
            )
        )

    async def queue_delete_tag(
        self, queue_id: str, tag: str, *, auth: YandexAuth | None = None
    ) -> None:
        """Remove a tag from a queue's list. A tag still on an issue answers
        422 "Тег ещё используется", an unknown one 204 like a removal."""
        await self._read(
            "POST",
            f"v3/queues/{queue_id}/tags/_remove",
            auth=auth,
            json={"tag": tag},
            not_found=QueueNotFound(queue_id),
        )

    async def queues_get_triggers(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueTrigger]:
        """Every trigger of a queue. The listing pages relatively: ascending by
        id, the next page starting after the `id` passed."""
        triggers: list[QueueTrigger] = []
        params: dict[str, Any] = {"perPage": _TRIGGERS_PER_PAGE}
        while True:
            page = QueueTriggerList.model_validate_json(
                await self._read(
                    "GET",
                    f"v3/queues/{queue_id}/triggers",
                    auth=auth,
                    params=params,
                    not_found=QueueNotFound(queue_id),
                )
            ).root
            triggers.extend(page)
            if len(page) < _TRIGGERS_PER_PAGE:
                return triggers
            params = {"perPage": _TRIGGERS_PER_PAGE, "id": page[-1].id}

    async def queues_get_versions(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueVersion]:
        return VersionList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/versions",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        ).root

    async def queues_get_components(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[Component]:
        """The components of one queue, as full objects: the queue-scoped endpoint
        is undocumented and not paginated - see AGENTS.md, *Queue components*."""
        return ComponentList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/components",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        ).root

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
        body: dict[str, Any] = {"queue": queue_id, "name": name}
        if description is not None:
            body["description"] = description
        if start_date is not None:
            body["startDate"] = start_date.isoformat()
        if due_date is not None:
            body["dueDate"] = due_date.isoformat()

        return QueueVersion.model_validate_json(
            await self._read("POST", "v3/versions/", auth=auth, json=body)
        )

    async def queue_get_version(
        self, version_id: int, *, auth: YandexAuth | None = None
    ) -> QueueVersion:
        return QueueVersion.model_validate_json(
            await self._read(
                "GET",
                f"v3/versions/{version_id}",
                auth=auth,
                not_found=VersionNotFound(version_id),
            )
        )

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
        """Change a version; only what is passed is sent (`PATCH v3/versions/{id}`)."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if start_date is not None:
            body["startDate"] = start_date.isoformat()
        if due_date is not None:
            body["dueDate"] = due_date.isoformat()
        if not body:
            raise VersionEmptyUpdate()

        return QueueVersion.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/versions/{version_id}",
                auth=auth,
                json=body,
                not_found=VersionNotFound(version_id),
            )
        )

    async def queue_delete_version(
        self, version_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/versions/{version_id}",
            auth=auth,
            not_found=VersionNotFound(version_id),
        )

    async def queues_get_fields(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[GlobalField]:
        return GlobalFieldList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/fields",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        ).root

    async def queue_get(
        self,
        queue_id: str,
        *,
        expand: list[QueueExpandOption] | None = None,
        auth: YandexAuth | None = None,
    ) -> Queue:
        params: dict[str, str] = {}
        if expand:
            params["expand"] = ",".join(expand)

        return Queue.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}",
                auth=auth,
                params=params,
                not_found=QueueNotFound(queue_id),
            )
        )

    # Triggers, autoactions, macros and queue administration - see AGENTS.md,
    # *Triggers, autoactions, macros*.

    async def queue_get_trigger(
        self, queue_id: str, trigger_id: int, *, auth: YandexAuth | None = None
    ) -> QueueTrigger:
        return QueueTrigger.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/triggers/{trigger_id}",
                auth=auth,
                not_found=TriggerNotFound(queue_id, trigger_id),
            )
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
        body: dict[str, Any] = {"name": name, "actions": actions}
        if conditions is not None:
            body["conditions"] = conditions
        if active is not None:
            body["active"] = active
        return QueueTrigger.model_validate_json(
            await self._read(
                "POST",
                f"v3/queues/{queue_id}/triggers",
                auth=auth,
                json=body,
                not_found=QueueNotFound(queue_id),
            )
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
        """Change what is passed; `version` goes as a query parameter, and a
        stale one answers 409 or 412."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if actions is not None:
            body["actions"] = actions
        if conditions is not None:
            body["conditions"] = conditions
        if active is not None:
            body["active"] = active
        if before is not None:
            body["before"] = before
        if not body:
            raise TriggerEmptyUpdate()

        return QueueTrigger.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/queues/{queue_id}/triggers/{trigger_id}",
                auth=auth,
                params={"version": version},
                json=body,
                not_found=TriggerNotFound(queue_id, trigger_id),
                conflict=TriggerVersionConflict(queue_id, trigger_id, version),
            )
        )

    async def queue_delete_trigger(
        self, queue_id: str, trigger_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        """Undocumented, verified 2026-10-26: 204, no `version`; 404 afterwards."""
        await self._read(
            "DELETE",
            f"v3/queues/{queue_id}/triggers/{trigger_id}",
            auth=auth,
            not_found=TriggerNotFound(queue_id, trigger_id),
        )

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
        """The runs of a trigger's HTTP request actions, the latest 10 unless
        `limit` (at most 100) says otherwise."""
        params: dict[str, Any] = {}
        if issue_id is not None:
            params["issueId"] = issue_id
        if limit is not None:
            params["limit"] = limit
        if created_from is not None:
            params["from"] = _tracker_datetime(created_from)
        if created_to is not None:
            params["to"] = _tracker_datetime(created_to)
        return QueueTriggerLogList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/triggers/{trigger_id}/webhooks/log",
                auth=auth,
                params=params,
                not_found=TriggerNotFound(queue_id, trigger_id),
            )
        ).root

    async def queues_get_autoactions(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueAutoaction]:
        """Undocumented listing; the live API answers it with an array."""
        return QueueAutoactionList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/autoactions",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        ).root

    async def queue_get_autoaction(
        self, queue_id: str, autoaction_id: int, *, auth: YandexAuth | None = None
    ) -> QueueAutoaction:
        return QueueAutoaction.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/autoactions/{autoaction_id}",
                auth=auth,
                not_found=AutoactionNotFound(queue_id, autoaction_id),
            )
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
        body: dict[str, Any] = {"name": name, "actions": actions}
        if filter is not None:
            body["filter"] = filter
        if query is not None:
            body["query"] = query
        if active is not None:
            body["active"] = active
        if enable_notifications is not None:
            body["enableNotifications"] = enable_notifications
        if interval_millis is not None:
            body["intervalMillis"] = interval_millis
        if calendar_id is not None:
            body["calendar"] = {"id": calendar_id}
        return QueueAutoaction.model_validate_json(
            await self._read(
                "POST",
                f"v3/queues/{queue_id}/autoactions",
                auth=auth,
                json=body,
                not_found=QueueNotFound(queue_id),
            )
        )

    async def queue_get_autoaction_runs(
        self, queue_id: str, autoaction_id: int, *, auth: YandexAuth | None = None
    ) -> list[QueueAutoactionRun]:
        return QueueAutoactionRunList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/autoactions/{autoaction_id}/logs",
                auth=auth,
                not_found=AutoactionNotFound(queue_id, autoaction_id),
            )
        ).root

    async def queue_get_autoaction_run(
        self,
        queue_id: str,
        autoaction_id: int,
        run_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> list[QueueAutoactionRunIssue]:
        return QueueAutoactionRunIssueList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/autoactions/{autoaction_id}/logs/{run_id}",
                auth=auth,
                not_found=AutoactionNotFound(queue_id, autoaction_id),
            )
        ).root

    async def queues_get_macros(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueMacro]:
        return QueueMacroList.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/macros",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        ).root

    async def queue_get_macro(
        self, queue_id: str, macro_id: int, *, auth: YandexAuth | None = None
    ) -> QueueMacro:
        return QueueMacro.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/macros/{macro_id}",
                auth=auth,
                not_found=MacroNotFound(queue_id, macro_id),
            )
        )

    async def queue_create_macro(
        self,
        queue_id: str,
        *,
        name: str,
        body: str | None = None,
        issue_update: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> QueueMacro:
        payload: dict[str, Any] = {"name": name}
        if body is not None:
            payload["body"] = body
        if issue_update is not None:
            payload["issueUpdate"] = issue_update
        return QueueMacro.model_validate_json(
            await self._read(
                "POST",
                f"v3/queues/{queue_id}/macros",
                auth=auth,
                json=payload,
                not_found=QueueNotFound(queue_id),
            )
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
        """`name` is always sent: the reference lists it as required on `PATCH`
        too. `{"unset": 1}` is the documented way to clear the body."""
        if clear_body and body is not None:
            raise FieldClearConflict("body")

        payload: dict[str, Any] = {"name": name}
        if clear_body:
            payload["body"] = {"unset": 1}
        elif body is not None:
            payload["body"] = body
        if issue_update is not None:
            payload["issueUpdate"] = issue_update
        return QueueMacro.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/queues/{queue_id}/macros/{macro_id}",
                auth=auth,
                json=payload,
                not_found=MacroNotFound(queue_id, macro_id),
            )
        )

    async def queue_delete_macro(
        self, queue_id: str, macro_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/queues/{queue_id}/macros/{macro_id}",
            auth=auth,
            not_found=MacroNotFound(queue_id, macro_id),
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
        body: dict[str, Any] = {
            "key": key,
            "name": name,
            "lead": lead,
            "defaultType": default_type,
            "defaultPriority": default_priority,
            "issueTypesConfig": _issue_types_config_body(issue_types_config),
        }
        return Queue.model_validate_json(
            await self._read("POST", "v3/queues", auth=auth, json=body)
        )

    async def queue_delete(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> None:
        """Delete a queue. Right after the queue changes Tracker now and then
        refuses this with 412 "не удалось сохранить изменения, попробуйте ещё
        раз" (seen on the live API 2026-10-23, as with sprints) - a request
        that takes no version, so the 412 is only ever that, and it is sent
        again after `_QUEUE_DELETE_RETRY_WAITS`."""
        for wait in (*_QUEUE_DELETE_RETRY_WAITS, None):
            try:
                await self._read(
                    "DELETE",
                    f"v3/queues/{queue_id}",
                    auth=auth,
                    not_found=QueueNotFound(queue_id),
                )
                return
            except TrackerAPIError as e:
                if e.status != 412 or wait is None:
                    raise
            await asyncio.sleep(wait)

    async def queue_restore(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> Queue:
        return Queue.model_validate_json(
            await self._read(
                "POST",
                f"v3/queues/{queue_id}/_restore",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        )

    async def queue_get_fresh(
        self,
        queue_id: str,
        *,
        expand: list[QueueExpandOption] | None = None,
        auth: YandexAuth | None = None,
    ) -> Queue:
        """`queue_get`, which the caching layer passes through uncached: a write
        that sends back the whole `issueTypesConfig` must start from the
        current one."""
        return await self.queue_get(queue_id, expand=expand, auth=auth)

    async def queue_update_issue_types_config(
        self,
        queue_id: str,
        *,
        issue_types_config: list[QueueIssueTypeConfigInput],
        default_type: str | None = None,
        auth: YandexAuth | None = None,
    ) -> Queue:
        """Replace the queue's whole `issueTypesConfig` through the undocumented
        `PATCH v3/queues/{key}`; it takes no `version` (a stale one is ignored)."""
        body: dict[str, Any] = {
            "issueTypesConfig": _issue_types_config_body(issue_types_config)
        }
        if default_type is not None:
            body["defaultType"] = default_type
        return Queue.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/queues/{queue_id}",
                auth=auth,
                json=body,
                not_found=QueueNotFound(queue_id),
            )
        )

    async def get_global_fields(
        self,
        *,
        language: FieldLanguage | None = None,
        auth: YandexAuth | None = None,
    ) -> list[GlobalField]:
        return GlobalFieldList.model_validate_json(
            await self._read(
                "GET",
                "v3/fields",
                auth=auth,
                extra_headers={"Accept-Language": language} if language else None,
            )
        ).root

    async def get_statuses(self, *, auth: YandexAuth | None = None) -> list[Status]:
        return StatusList.model_validate_json(
            await self._read("GET", "v3/statuses", auth=auth)
        ).root

    async def get_issue_types(
        self, *, auth: YandexAuth | None = None
    ) -> list[IssueType]:
        return IssueTypeList.model_validate_json(
            await self._read("GET", "v3/issuetypes", auth=auth)
        ).root

    async def get_priorities(self, *, auth: YandexAuth | None = None) -> list[Priority]:
        return PriorityList.model_validate_json(
            await self._read("GET", "v3/priorities", auth=auth)
        ).root

    async def get_resolutions(
        self, *, auth: YandexAuth | None = None
    ) -> list[Resolution]:
        return ResolutionList.model_validate_json(
            await self._read("GET", "v3/resolutions", auth=auth)
        ).root

    # The organization's catalogue - statuses, resolutions, issue types and
    # priorities. A write wants the name as `{"ru": ..., "en": ...}` and an
    # update its `version` as a query parameter; `_one_catalog_object` says
    # what comes back. None of them can be deleted through the API.

    async def _catalog_get(
        self,
        catalog: "_Catalog",
        model: type[_CatalogT],
        object_id: str,
        *,
        auth: YandexAuth | None,
    ) -> _CatalogT:
        return _one_catalog_object(
            model,
            await self._read(
                "GET",
                f"{catalog.path}/{quote(object_id, safe='')}",
                auth=auth,
                not_found=catalog.not_found(object_id),
            ),
        )

    async def _catalog_create(
        self,
        catalog: "_Catalog",
        model: type[_CatalogT],
        body: dict[str, Any],
        *,
        auth: YandexAuth | None,
    ) -> _CatalogT:
        return _one_catalog_object(
            model, await self._read("POST", catalog.path, auth=auth, json=body)
        )

    async def _catalog_update(
        self,
        catalog: "_Catalog",
        model: type[_CatalogT],
        object_id: str,
        version: int,
        body: dict[str, Any],
        *,
        auth: YandexAuth | None,
    ) -> _CatalogT:
        if not body:
            raise CatalogEmptyUpdate(catalog.kind, catalog.update_fields)
        return _one_catalog_object(
            model,
            await self._read(
                "PATCH",
                f"{catalog.path}/{quote(object_id, safe='')}",
                auth=auth,
                params={"version": version},
                json=body,
                not_found=catalog.not_found(object_id),
                conflict=catalog.conflict(object_id, version),
            ),
        )

    async def status_get(
        self, status_id: str, *, auth: YandexAuth | None = None
    ) -> Status:
        return await self._catalog_get(_STATUSES, Status, status_id, auth=auth)

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
        body = _catalog_body(
            name, key=key, type=type, description=description, order=order
        )
        return await self._catalog_create(_STATUSES, Status, body, auth=auth)

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
        body = _catalog_body(name, description=description, order=order, type=type)
        return await self._catalog_update(
            _STATUSES, Status, status_id, version, body, auth=auth
        )

    async def resolution_get(
        self, resolution_id: str, *, auth: YandexAuth | None = None
    ) -> Resolution:
        return await self._catalog_get(
            _RESOLUTIONS, Resolution, resolution_id, auth=auth
        )

    async def resolution_create(
        self,
        *,
        key: str,
        name: LocalizedText,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> Resolution:
        body = _catalog_body(name, key=key, description=description, order=order)
        return await self._catalog_create(_RESOLUTIONS, Resolution, body, auth=auth)

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
        body = _catalog_body(name, description=description, order=order)
        return await self._catalog_update(
            _RESOLUTIONS, Resolution, resolution_id, version, body, auth=auth
        )

    async def issue_type_get(
        self, issue_type_id: str, *, auth: YandexAuth | None = None
    ) -> IssueType:
        return await self._catalog_get(
            _ISSUE_TYPES, IssueType, issue_type_id, auth=auth
        )

    async def issue_type_create(
        self,
        *,
        key: str,
        name: LocalizedText,
        description: str | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueType:
        body = _catalog_body(name, key=key, description=description)
        return await self._catalog_create(_ISSUE_TYPES, IssueType, body, auth=auth)

    async def issue_type_update(
        self,
        issue_type_id: str,
        *,
        version: int,
        name: LocalizedText | None = None,
        description: str | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueType:
        body = _catalog_body(name, description=description)
        return await self._catalog_update(
            _ISSUE_TYPES, IssueType, issue_type_id, version, body, auth=auth
        )

    async def priority_get(
        self, priority_id: str, *, auth: YandexAuth | None = None
    ) -> Priority:
        return await self._catalog_get(_PRIORITIES, Priority, priority_id, auth=auth)

    async def priority_create(
        self,
        *,
        key: str,
        name: LocalizedText,
        description: str | None = None,
        order: int | None = None,
        auth: YandexAuth | None = None,
    ) -> Priority:
        body = _catalog_body(name, key=key, description=description, order=order)
        return await self._catalog_create(_PRIORITIES, Priority, body, auth=auth)

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
        body = _catalog_body(name, description=description, order=order)
        return await self._catalog_update(
            _PRIORITIES, Priority, priority_id, version, body, auth=auth
        )

    # Issue fields and their categories go through the catalogue helpers too:
    # the same `{"ru", "en"}` name, `?version=` on an update (428 without it,
    # 412 for a stale one) and no DELETE (405 on both, verified 2026-10-26).
    # A create answers 200, not the documented 201.

    async def field_get(
        self, field_id: str, *, auth: YandexAuth | None = None
    ) -> GlobalField:
        return await self._catalog_get(_FIELDS, GlobalField, field_id, auth=auth)

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
        body = _catalog_body(
            name,
            id=field_id,
            category=category,
            type=_FIELD_TYPE_PREFIX + FIELD_TYPES[type],
            description=description,
            order=order,
            readonly=readonly,
            visible=visible,
            hidden=hidden,
            container=container,
            optionsProvider=_options_provider(type == "user", options),
        )
        return await self._catalog_create(_FIELDS, GlobalField, body, auth=auth)

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
        body = _catalog_body(
            name,
            description=description,
            category=category,
            order=order,
            readonly=readonly,
            visible=visible,
            hidden=hidden,
            optionsProvider=_options_provider(user_options, options),
        )
        return await self._catalog_update(
            _FIELDS, GlobalField, field_id, version, body, auth=auth
        )

    async def fields_get_categories(
        self, *, auth: YandexAuth | None = None
    ) -> list[FieldCategory]:
        return FieldCategoryList.model_validate_json(
            await self._read("GET", _FIELD_CATEGORIES.path, auth=auth)
        ).root

    async def field_category_get(
        self, category_id: str, *, auth: YandexAuth | None = None
    ) -> FieldCategory:
        return await self._catalog_get(
            _FIELD_CATEGORIES, FieldCategory, category_id, auth=auth
        )

    async def field_category_create(
        self,
        *,
        name: LocalizedText,
        order: int,
        description: str | None = None,
        auth: YandexAuth | None = None,
    ) -> FieldCategory:
        body = _catalog_body(name, order=order, description=description)
        return await self._catalog_create(
            _FIELD_CATEGORIES, FieldCategory, body, auth=auth
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
        body = _catalog_body(name, description=description, order=order)
        return await self._catalog_update(
            _FIELD_CATEGORIES, FieldCategory, category_id, version, body, auth=auth
        )

    async def get_issue_templates(
        self,
        *,
        queue: str | None = None,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> PaginatedResult[IssueTemplate]:
        # The queue-scoped endpoint returns the templates of that queue plus the
        # ones not bound to any queue, which are usable in every queue.
        path = (
            "v3/issueTemplates"
            if queue is None
            else f"v3/queues/{queue}/issueTemplates"
        )
        params = {
            "perPage": per_page,
            "page": page,
        }
        async with self._request(
            "GET",
            path,
            auth=auth,
            params=params,
            not_found=QueueNotFound(queue) if queue is not None else None,
        ) as response:
            return self._paginated(
                response,
                IssueTemplateList.model_validate_json(await response.read()).root,
            )

    async def get_issue_template(
        self, template_id: str, *, auth: YandexAuth | None = None
    ) -> IssueTemplate:
        return IssueTemplate.model_validate_json(
            await self._read(
                "GET",
                f"v3/issueTemplates/{template_id}",
                auth=auth,
                not_found=IssueTemplateNotFound(template_id),
            )
        )

    async def get_comment_templates(
        self,
        *,
        queue: str | None = None,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> PaginatedResult[CommentTemplate]:
        # The queue-scoped endpoint returns the templates of that queue plus the
        # ones not bound to any queue, which are usable in every queue.
        path = (
            "v3/commentTemplates"
            if queue is None
            else f"v3/queues/{queue}/commentTemplates"
        )
        params = {
            "perPage": per_page,
            "page": page,
        }
        async with self._request(
            "GET",
            path,
            auth=auth,
            params=params,
            not_found=QueueNotFound(queue) if queue is not None else None,
        ) as response:
            return self._paginated(
                response,
                CommentTemplateList.model_validate_json(await response.read()).root,
            )

    async def get_comment_template(
        self, template_id: str, *, auth: YandexAuth | None = None
    ) -> CommentTemplate:
        return CommentTemplate.model_validate_json(
            await self._read(
                "GET",
                f"v3/commentTemplates/{template_id}",
                auth=auth,
                not_found=CommentTemplateNotFound(template_id),
            )
        )

    async def issue_get(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> Issue:
        return Issue.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}",
                auth=auth,
                not_found=IssueNotFound(issue_id),
            )
        )

    async def issues_get_links(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[IssueLink]:
        return IssueLinkList.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}/links",
                auth=auth,
                not_found=IssueNotFound(issue_id),
            )
        ).root

    async def issue_add_link(
        self,
        issue_id: str,
        *,
        relationship: IssueLinkRelationship,
        issue: str,
        auth: YandexAuth | None = None,
    ) -> IssueLink:
        """Создать связь задачи с другой задачей."""
        body: dict[str, Any] = {"relationship": relationship, "issue": issue}

        return IssueLink.model_validate_json(
            await self._read(
                "POST",
                f"v3/issues/{issue_id}/links",
                auth=auth,
                json=body,
                not_found=IssueNotFound(issue_id),
            )
        )

    async def issue_delete_link(
        self,
        issue_id: str,
        link_id: int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        """Удалить связь задачи с другой задачей."""
        await self._read(
            "DELETE",
            f"v3/issues/{issue_id}/links/{link_id}",
            auth=auth,
            not_found=IssueNotFound(issue_id),
        )

    async def issue_get_comments(
        self,
        issue_id: str,
        *,
        per_page: int = 50,
        cursor: str | None = None,
        auth: YandexAuth | None = None,
    ) -> CommentsPage:
        params: dict[str, Any] = {"perPage": per_page}
        if cursor is not None:
            # `id` is exclusive: the page starts after that comment.
            params["id"] = cursor

        async with self._request(
            "GET",
            f"v3/issues/{issue_id}/comments",
            auth=auth,
            params=params,
            not_found=IssueNotFound(issue_id),
        ) as response:
            comments = IssueCommentList.model_validate_json(await response.read()).root
            return CommentsPage(
                comments=comments,
                next_cursor=self._parse_next_cursor(response),
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
        """Добавить комментарий к задаче."""
        body: dict[str, Any] = {"text": text}
        if summonees is not None:
            body["summonees"] = summonees
        if maillist_summonees is not None:
            body["maillistSummonees"] = maillist_summonees
        if markup_type is not None:
            body["markupType"] = markup_type
        if attachment_ids is not None:
            body["attachmentIds"] = attachment_ids

        # Параметр опциональный, по умолчанию true на стороне API.
        # Чтобы не менять URL (и поведение по умолчанию), передаём его только при false.
        params = {"isAddToFollowers": "false"} if not is_add_to_followers else None

        return IssueComment.model_validate_json(
            await self._read(
                "POST",
                f"v3/issues/{issue_id}/comments",
                auth=auth,
                params=params,
                json=body,
                not_found=IssueNotFound(issue_id),
            )
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
        """Изменить комментарий в задаче."""
        body: dict[str, Any] = {"text": text}
        if summonees is not None:
            body["summonees"] = summonees
        if maillist_summonees is not None:
            body["maillistSummonees"] = maillist_summonees
        if markup_type is not None:
            body["markupType"] = markup_type

        return IssueComment.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/issues/{issue_id}/comments/{comment_id}",
                auth=auth,
                json=body,
                not_found=IssueNotFound(issue_id),
            )
        )

    async def issues_bulk_update(
        self,
        issues: list[str],
        *,
        values: dict[str, Any],
        notify: bool = False,
        auth: YandexAuth | None = None,
    ) -> BulkChange:
        return await self._bulk_change(
            "_update", {"issues": issues, "values": values}, notify, auth=auth
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
        body: dict[str, Any] = {"transition": transition, "issues": issues}
        if values:
            body["values"] = values
        return await self._bulk_change("_transition", body, notify, auth=auth)

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
        body: dict[str, Any] = {"queue": queue, "issues": issues}
        if values:
            body["values"] = values
        if move_all_fields:
            body["moveAllFields"] = True
        if initial_status:
            body["initialStatus"] = True
        return await self._bulk_change("_move", body, notify, auth=auth)

    async def _bulk_change(
        self,
        operation: str,
        body: dict[str, Any],
        notify: bool,
        *,
        auth: YandexAuth | None,
    ) -> BulkChange:
        """Queue a bulk change. `notify` is false on Tracker's side by default and
        is sent only when set."""
        return BulkChange.model_validate_json(
            await self._read(
                "POST",
                f"v3/bulkchange/{operation}",
                auth=auth,
                params={"notify": "true"} if notify else None,
                json=body,
            )
        )

    async def bulk_change_get(
        self, bulk_change_id: str, *, auth: YandexAuth | None = None
    ) -> BulkChange:
        return BulkChange.model_validate_json(
            await self._read(
                "GET",
                f"v3/bulkchange/{quote(bulk_change_id, safe='')}",
                auth=auth,
                not_found=BulkChangeNotFound(bulk_change_id),
            )
        )

    async def bulk_change_get_failures(
        self, bulk_change_id: str, *, auth: YandexAuth | None = None
    ) -> list[BulkChangeFailure]:
        return BulkChangeFailureList.model_validate_json(
            await self._read(
                "GET",
                f"v3/bulkchange/{quote(bulk_change_id, safe='')}/issues",
                auth=auth,
                not_found=BulkChangeNotFound(bulk_change_id),
            )
        ).root

    async def applications_list(
        self, *, auth: YandexAuth | None = None
    ) -> list[ExternalApplication]:
        return ExternalApplicationList.model_validate_json(
            await self._read("GET", "v3/applications", auth=auth)
        ).root

    async def issue_get_remote_links(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[RemoteLink]:
        return RemoteLinkList.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}/remotelinks",
                auth=auth,
                not_found=IssueNotFound(issue_id),
            )
        ).root

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
        """Link an issue to object `key` of application `origin`.

        `backlink` asks Tracker to create the mirror link in the other
        application too; it is sent only when set.
        """
        return RemoteLink.model_validate_json(
            await self._read(
                "POST",
                f"v3/issues/{issue_id}/remotelinks",
                auth=auth,
                params={"backlink": "true"} if backlink else None,
                json={
                    "relationship": relationship.upper(),
                    "key": key,
                    "origin": origin,
                },
                not_found=IssueNotFound(issue_id),
            )
        )

    async def issue_delete_remote_link(
        self, issue_id: str, link_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/issues/{issue_id}/remotelinks/{link_id}",
            auth=auth,
            not_found=IssueNotFound(issue_id),
        )

    async def issue_get_comment(
        self,
        issue_id: str,
        comment_id: int | str,
        *,
        auth: YandexAuth | None = None,
    ) -> IssueComment:
        """One comment, by its numeric `id` or its `longId`, with its files."""
        return IssueComment.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}/comments/{quote(str(comment_id), safe='')}",
                auth=auth,
                params={"expand": "attachments"},
                not_found=CommentNotFound(issue_id, comment_id),
            )
        )

    async def issue_delete_comment(
        self,
        issue_id: str,
        comment_id: int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        """Удалить комментарий из задачи."""
        await self._read(
            "DELETE",
            f"v3/issues/{issue_id}/comments/{comment_id}",
            auth=auth,
            not_found=IssueNotFound(issue_id),
        )

    async def issue_add_comment_reaction(
        self,
        issue_id: str,
        comment_id: int | str,
        reaction: CommentReaction,
        *,
        auth: YandexAuth | None = None,
    ) -> IssueComment:
        return await self._comment_reaction(
            "POST", issue_id, comment_id, reaction, auth=auth
        )

    async def issue_delete_comment_reaction(
        self,
        issue_id: str,
        comment_id: int | str,
        reaction: CommentReaction,
        *,
        auth: YandexAuth | None = None,
    ) -> IssueComment:
        # Undocumented, verified 2026-10-26: the same path as adding one.
        return await self._comment_reaction(
            "DELETE", issue_id, comment_id, reaction, auth=auth
        )

    async def _comment_reaction(
        self,
        method: Literal["POST", "DELETE"],
        issue_id: str,
        comment_id: int | str,
        reaction: CommentReaction,
        *,
        auth: YandexAuth | None,
    ) -> IssueComment:
        """Both answer with the comment and its reactions after the change; a
        reaction already there (or already gone) answers 422 with Tracker's text."""
        return IssueComment.model_validate_json(
            await self._read(
                method,
                f"v3/issues/{issue_id}/comments/"
                f"{quote(str(comment_id), safe='')}/reactions/{reaction}",
                auth=auth,
                not_found=CommentNotFound(issue_id, comment_id),
            )
        )

    @staticmethod
    def _search_body(query: str | None, filter_id: int | None) -> dict[str, Any]:
        """A search by a query, a saved filter or both - Tracker then returns the
        issues matching both."""
        body: dict[str, Any] = {}
        if query is not None:
            body["query"] = query
        if filter_id is not None:
            body["filterId"] = filter_id
        return body

    async def issues_suggest(
        self, text: str, *, auth: YandexAuth | None = None
    ) -> list[Issue]:
        """At most 20 issues whose summary contains `text`. The documented
        `queue` parameter is accepted but changes nothing (2026-10-26)."""
        return IssueList.model_validate_json(
            await self._read(
                "GET",
                "v3/issues/_suggest",
                auth=auth,
                params={
                    "input": text,
                    "full": "true",
                    "fields": "key,summary,status",
                },
            )
        ).root

    async def issues_find(
        self,
        query: str | None = None,
        *,
        filter_id: int | None = None,
        per_page: int = 15,
        page: int = 1,
        fields: Sequence[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> PaginatedResult[Issue]:
        params: dict[str, Any] = {
            "perPage": per_page,
            "page": page,
        }
        if fields:
            # The endpoint projects server-side, so an unwanted field costs
            # nothing on the wire instead of being fetched and dropped later.
            # Tracker always adds `self`, `id`, `key`, `version` and `favorite`
            # to whatever is asked for.
            params["fields"] = ",".join(fields)

        body = self._search_body(query, filter_id)

        async with self._request(
            "POST", "v3/issues/_search", auth=auth, params=params, json=body
        ) as response:
            return self._paginated(
                response, IssueList.model_validate_json(await response.read()).root
            )

    @classmethod
    def _paginated(
        cls, response: ClientResponse, values: list[ItemT]
    ) -> PaginatedResult[ItemT]:
        """Pair a decoded page with the totals Tracker reports for the whole query."""
        return PaginatedResult[ItemT](
            values=values,
            hits=cls._parse_int_header(response, "X-Total-Count"),
            pages=cls._parse_int_header(response, "X-Total-Pages"),
        )

    @staticmethod
    def _parse_int_header(response: ClientResponse, name: str) -> int | None:
        """Read an integer pagination total from a response header.

        The totals are advisory: a missing or malformed header just means the
        caller has to fall back to paging until a page comes back empty.
        """
        raw = response.headers.get(name)
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            logger.warning("non-integer %s response header: %r", name, raw)
            return None

    async def issue_get_worklogs(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[Worklog]:
        return WorklogList.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}/worklog",
                auth=auth,
                not_found=IssueNotFound(issue_id),
            )
        ).root

    async def worklogs_find(
        self,
        *,
        created_by: str | None = None,
        created_from: datetime.datetime | None = None,
        created_to: datetime.datetime | None = None,
        auth: YandexAuth | None = None,
    ) -> list[Worklog]:
        """Worklogs across issues, `POST v3/worklog/_search`.

        The API filters by the author and by when a record was *created*, not by
        the `start` of the work it records. The documentation says nothing about
        paging, so a `Link: rel="next"` header is followed if one comes back,
        with the same body, up to `_MAX_WORKLOG_SEARCH_PAGES`.
        """
        body: dict[str, Any] = {}
        if created_by is not None:
            body["createdBy"] = created_by
        created_at: dict[str, str] = {}
        if created_from is not None:
            created_at["from"] = _tracker_datetime(created_from)
        if created_to is not None:
            created_at["to"] = _tracker_datetime(created_to)
        if created_at:
            body["createdAt"] = created_at

        worklogs: list[Worklog] = []
        params: dict[str, str] | None = None
        for _ in range(_MAX_WORKLOG_SEARCH_PAGES):
            async with self._request(
                "POST", "v3/worklog/_search", auth=auth, params=params, json=body
            ) as response:
                worklogs.extend(
                    WorklogList.model_validate_json(await response.read()).root
                )
                next_link = response.links.get("next")
            next_url = next_link.get("url") if next_link is not None else None
            if not isinstance(next_url, URL):
                return worklogs
            params = dict(next_url.query)
        raise WorklogSearchTooLarge(_MAX_WORKLOG_SEARCH_PAGES)

    async def issue_add_worklog(
        self,
        issue_id: str,
        *,
        duration: str,
        comment: str | None = None,
        start: datetime.datetime | None = None,
        auth: YandexAuth | None = None,
    ) -> Worklog:
        """Добавить запись трудозатрат (worklog) к задаче.

        Args:
            issue_id: Ключ задачи (например, "QUEUE-123")
            duration: Длительность в формате ISO 8601 (например, "PT1H30M")
            comment: Комментарий к записи
            start: Время начала работ. Если не задано — используется текущее время на стороне Трекера.
            auth: Опциональная auth-структура (OAuth/Org) поверх конфигурации клиента
        """
        body: dict[str, Any] = {"duration": duration}
        if comment is not None:
            body["comment"] = comment
        if start is not None:
            # Если tz отсутствует — считаем, что время задано в UTC.
            body["start"] = _tracker_datetime(start)

        return Worklog.model_validate_json(
            await self._read(
                "POST",
                f"v3/issues/{issue_id}/worklog",
                auth=auth,
                json=body,
                not_found=IssueNotFound(issue_id),
            )
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
        """Обновить запись трудозатрат (worklog) в задаче."""
        body: dict[str, Any] = {}
        if duration is not None:
            body["duration"] = duration
        if comment is not None:
            body["comment"] = comment
        if start is not None:
            body["start"] = _tracker_datetime(start)

        return Worklog.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/issues/{issue_id}/worklog/{worklog_id}",
                auth=auth,
                json=body,
                not_found=IssueNotFound(issue_id),
            )
        )

    async def issue_delete_worklog(
        self,
        issue_id: str,
        worklog_id: int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        """Удалить запись трудозатрат (worklog) из задачи."""
        await self._read(
            "DELETE",
            f"v3/issues/{issue_id}/worklog/{worklog_id}",
            auth=auth,
            not_found=IssueNotFound(issue_id),
        )

    async def issue_get_attachments(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[IssueAttachment]:
        return IssueAttachmentList.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}/attachments",
                auth=auth,
                not_found=IssueNotFound(issue_id),
            )
        ).root

    async def issue_get_attachment(
        self, issue_id: str, attachment_id: str, *, auth: YandexAuth | None = None
    ) -> IssueAttachment:
        # Quoted whole: the id is the caller's text, and a `/` or `..` in it
        # would reach another endpoint.
        return IssueAttachment.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}/attachments/{quote(attachment_id, safe='')}",
                auth=auth,
                not_found=AttachmentNotFound(issue_id, attachment_id),
            )
        )

    async def issue_delete_attachment(
        self, issue_id: str, attachment_id: str, *, auth: YandexAuth | None = None
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/issues/{issue_id}/attachments/{quote(attachment_id, safe='')}",
            auth=auth,
            not_found=AttachmentNotFound(issue_id, attachment_id),
        )

    async def issue_add_attachment(
        self,
        issue_id: str,
        *,
        content: bytes,
        filename: str,
        auth: YandexAuth | None = None,
    ) -> IssueAttachment:
        async with self._request(
            "POST",
            f"v3/issues/{issue_id}/attachments/",
            auth=auth,
            params={"filename": filename},
            data=_attachment_form(content, filename),
            not_found=IssueNotFound(issue_id),
            timeout=self._attachment_timeout,
            timeout_setting="TRACKER_ATTACHMENT_TIMEOUT",
        ) as response:
            return IssueAttachment.model_validate_json(await response.read())

    async def attachment_create(
        self,
        *,
        content: bytes,
        filename: str,
        auth: YandexAuth | None = None,
    ) -> IssueAttachment:
        """Upload a temporary attachment - one bound to nothing yet.

        Its id is what `attachmentIds` of a new comment takes; the request is
        the issue upload's, sent to `v3/attachments/` instead.
        """
        async with self._request(
            "POST",
            "v3/attachments/",
            auth=auth,
            params={"filename": filename},
            data=_attachment_form(content, filename),
            timeout=self._attachment_timeout,
            timeout_setting="TRACKER_ATTACHMENT_TIMEOUT",
        ) as response:
            return IssueAttachment.model_validate_json(await response.read())

    async def issue_download_attachment(
        self,
        issue_id: str,
        attachment_id: str,
        file_name: str,
        destination: Path,
        *,
        auth: YandexAuth | None = None,
    ) -> int:
        """Stream an attachment into `destination`; returns the bytes written.

        The URL needs the attachment's name as its last segment; it and the id
        are quoted whole: a name is free text, and a `/` or `..` left in either
        would point the request at another endpoint under the server's
        credentials. The body goes to
        `<destination>.part` and is renamed only once complete, so a download
        that fails halfway never leaves a truncated file under the final name for
        a later call to take as finished. Both the declared length and the bytes
        actually received are held to `max_attachment_bytes`.
        """
        limit = self._max_attachment_bytes
        async with self._request(
            "GET",
            f"v3/issues/{issue_id}/attachments/{quote(attachment_id, safe='')}/"
            f"{quote(file_name, safe='')}",
            auth=auth,
            not_found=AttachmentNotFound(issue_id, attachment_id),
            timeout=self._attachment_timeout,
            timeout_setting="TRACKER_ATTACHMENT_TIMEOUT",
        ) as response:
            if response.content_length is not None and response.content_length > limit:
                raise AttachmentTooLarge(attachment_id, response.content_length, limit)

            destination.parent.mkdir(parents=True, exist_ok=True)
            partial = destination.with_name(f"{destination.name}.part")
            written = 0
            try:
                with partial.open("wb") as file:
                    # Each write is a hop to a worker thread; chunks of up to a
                    # megabyte rather than 64 KB cut the hops of a large file.
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        written += len(chunk)
                        if written > limit:
                            raise AttachmentTooLarge(attachment_id, written, limit)
                        await asyncio.to_thread(file.write, chunk)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
            partial.replace(destination)
            return written

    async def users_get_absences(
        self,
        users: list[str],
        *,
        date_from: datetime.datetime | None = None,
        date_to: datetime.datetime | None = None,
        auth: YandexAuth | None = None,
    ) -> list[UserAbsences]:
        """Absences overlapping a period, `POST v3/gaps/_search`.

        The API takes at most 100 users and pages by user, so one page of 100
        holds every answer; `hasMore` is followed anyway. A 403 means the token
        lacks the organization-administrator rights this method needs.
        """
        body: dict[str, Any] = {"users": users}
        if date_from is not None:
            body["from"] = _tracker_datetime(date_from)
        if date_to is not None:
            body["to"] = _tracker_datetime(date_to)

        result: list[UserAbsences] = []
        page = 1
        while True:
            try:
                raw = await self._read(
                    "POST",
                    "v3/gaps/_search",
                    auth=auth,
                    params={"page": page, "perPage": 100},
                    json=body,
                )
            except TrackerAPIError as exc:
                if exc.status == 403:
                    raise AbsencesForbidden() from exc
                raise
            found = AbsenceSearchPage.model_validate_json(raw)
            result.extend(found.user_gaps)
            if not found.has_more or not found.user_gaps:
                return result
            page += 1

    async def users_list(
        self, per_page: int = 50, page: int = 1, *, auth: YandexAuth | None = None
    ) -> PaginatedResult[User]:
        params: dict[str, str | int] = {
            "perPage": per_page,
            "page": page,
        }
        async with self._request(
            "GET", "v3/users", auth=auth, params=params
        ) as response:
            return self._paginated(
                response, UserList.model_validate_json(await response.read()).root
            )

    async def groups_list(
        self, per_page: int = 50, page: int = 1, *, auth: YandexAuth | None = None
    ) -> PaginatedResult[Group]:
        params: dict[str, str | int] = {"perPage": per_page, "page": page}
        async with self._request(
            "GET", "v3/groups", auth=auth, params=params
        ) as response:
            return self._paginated(
                response, GroupList.model_validate_json(await response.read()).root
            )

    async def user_get(
        self, user_id: str, *, auth: YandexAuth | None = None
    ) -> User | None:
        # An unknown user is an answer here, not an error, so the 404 is asked
        # for rather than raised.
        async with self._request(
            "GET", f"v3/users/{user_id}", auth=auth, allow_statuses=(404,)
        ) as response:
            if response.status == 404:
                return None
            return User.model_validate_json(await response.read())

    async def user_get_current(self, *, auth: YandexAuth | None = None) -> User:
        return User.model_validate_json(await self._read("GET", "v3/myself", auth=auth))

    async def issue_get_checklist(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[ChecklistItem]:
        return ChecklistItemList.model_validate_json(
            await self._read(
                "GET",
                f"v3/issues/{issue_id}/checklistItems",
                auth=auth,
                not_found=IssueNotFound(issue_id),
            )
        ).root

    @staticmethod
    def _checklist_item_deadline_body(
        deadline: ChecklistItemDeadlineInput | None,
    ) -> dict[str, Any] | None:
        if deadline is None:
            return None
        return {
            "date": _tracker_datetime(deadline.date),
            "deadlineType": deadline.deadline_type,
        }

    async def issue_add_checklist_items(
        self,
        issue_id: str,
        *,
        items: list[ChecklistItemInput],
        auth: YandexAuth | None = None,
    ) -> list[ChecklistItem]:
        """Добавить пункты в чеклист задачи (чеклист создаётся, если его нет).

        `POST .../checklistItems` принимает ровно один пункт за запрос, поэтому
        пункты отправляются последовательно, в переданном порядке; возвращается
        чеклист задачи после добавления последнего пункта.
        """
        if not items:
            return await self.issue_get_checklist(issue_id, auth=auth)

        checklist: list[ChecklistItem] = []

        for added, item in enumerate(items):
            body = self._build_checklist_item_body(
                text=item.text,
                checked=item.checked,
                assignee=item.assignee,
                deadline=self._checklist_item_deadline_body(item.deadline),
            )
            try:
                async with self._request(
                    "POST",
                    f"v3/issues/{issue_id}/checklistItems",
                    auth=auth,
                    json=body,
                    not_found=IssueNotFound(issue_id),
                ) as response:
                    raw = await response.read()
            except Exception as exc:
                # Nothing landed yet on the first item, so let that error speak
                # for itself; past it, say how much of the batch went through.
                if added == 0:
                    raise
                raise ChecklistBatchPartiallyAdded(
                    issue_id, added, len(items), exc
                ) from exc

            # The request succeeded - the item exists now regardless of what
            # follows, so a parse failure here must not be counted as "not
            # added" the way a request failure above is.
            checklist = _IssueChecklist.model_validate_json(raw).checklistItems

        return checklist

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
        """Изменить один пункт чеклиста задачи.

        Отправляются только переданные поля. Вопреки документации, `text` в теле
        не обязателен: проверено на живом API — `PATCH` с одним лишь `checked`
        (или `assignee`) отвечает 200 и сохраняет текущий текст пункта, так что
        дочитывать и переотправлять его не нужно.

        Исполнитель и дедлайн снимаются пустым объектом (`{}`) — тоже проверено
        на живом API: `null` Трекер молча игнорирует (200, значение остаётся),
        а `""` или `0` отвечают 422.
        """
        if clear_assignee and assignee is not None:
            raise FieldClearConflict("assignee")
        if clear_deadline and deadline is not None:
            raise FieldClearConflict("deadline")
        if (
            text is None
            and checked is None
            and assignee is None
            and deadline is None
            and not clear_assignee
            and not clear_deadline
        ):
            raise ChecklistItemEmptyUpdate()

        body = self._build_checklist_item_body(
            text=text,
            checked=checked,
            assignee={} if clear_assignee else assignee,
            deadline={}
            if clear_deadline
            else self._checklist_item_deadline_body(deadline),
        )
        # Item-scoped path: the 404 means an unknown issue *or* an unknown
        # item, and the caller is told to check both.
        async with self._request(
            "PATCH",
            f"v3/issues/{issue_id}/checklistItems/{checklist_item_id}",
            auth=auth,
            json=body,
            not_found=ChecklistItemNotFound(
                issue_id, checklist_item_id, ambiguous=True
            ),
        ) as response:
            return _IssueChecklist.model_validate_json(
                await response.read()
            ).checklistItems

    async def issue_delete_checklist_item(
        self,
        issue_id: str,
        checklist_item_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> list[ChecklistItem]:
        """Удалить один пункт из чеклиста задачи."""
        async with self._request(
            "DELETE",
            f"v3/issues/{issue_id}/checklistItems/{checklist_item_id}",
            auth=auth,
            not_found=ChecklistItemNotFound(
                issue_id, checklist_item_id, ambiguous=True
            ),
        ) as response:
            return _IssueChecklist.model_validate_json(
                await response.read()
            ).checklistItems

    async def issues_count(
        self,
        query: str | None = None,
        *,
        filter_id: int | None = None,
        auth: YandexAuth | None = None,
    ) -> int:
        body = self._search_body(query, filter_id)

        async with self._request(
            "POST", "v3/issues/_count", auth=auth, json=body
        ) as response:
            return int(await response.text())

    # Saved filters - see AGENTS.md, *Saved filters*.

    async def filter_get(
        self, filter_id: int, *, auth: YandexAuth | None = None
    ) -> IssueFilter:
        return IssueFilter.model_validate_json(
            await self._read(
                "GET",
                f"v3/filters/{filter_id}",
                auth=auth,
                not_found=FilterNotFound(filter_id),
            )
        )

    @staticmethod
    def _filter_body(
        *,
        name: str | None,
        query: str | None,
        filter: dict[str, Any] | None,
        sorts: list[FilterSort] | None,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """Tracker answers `query` and `filter` together with a 409."""
        if query is not None and filter is not None:
            raise FilterConditionsConflict()
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if query is not None:
            body["query"] = query
        if filter is not None:
            body["filter"] = filter
        if sorts is not None:
            body["sorts"] = [sort.model_dump() for sort in sorts]
        if fields is not None:
            body["fields"] = fields
        return body

    async def filter_create(
        self,
        *,
        name: str,
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        sorts: list[FilterSort] | None = None,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueFilter:
        body = self._filter_body(
            name=name, query=query, filter=filter, sorts=sorts, fields=fields
        )
        return IssueFilter.model_validate_json(
            await self._read("POST", "v3/filters", auth=auth, json=body)
        )

    async def filter_update(
        self,
        filter_id: int,
        *,
        name: str | None = None,
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        sorts: list[FilterSort] | None = None,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueFilter:
        """Change what is passed; no `version`. An empty body answers 200 and
        changes nothing, so it is refused here."""
        body = self._filter_body(
            name=name, query=query, filter=filter, sorts=sorts, fields=fields
        )
        if not body:
            raise FilterEmptyUpdate()
        return IssueFilter.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/filters/{filter_id}",
                auth=auth,
                json=body,
                not_found=FilterNotFound(filter_id),
            )
        )

    async def filter_delete(
        self, filter_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        # The reference gives the v2 path; v3 answers the same 204 (2026-10-26).
        await self._read(
            "DELETE",
            f"v3/filters/{filter_id}",
            auth=auth,
            not_found=FilterNotFound(filter_id),
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
        body: dict[str, Any] = {
            "queue": queue,
            "summary": summary,
        }

        if type is not None:
            body["type"] = _ref_body(type)
        if description is not None:
            body["description"] = description
        if markup_type is not None:
            body["markupType"] = markup_type
        if assignee is not None:
            body["assignee"] = assignee
        if priority is not None:
            body["priority"] = _ref_body(priority)
        if parent is not None:
            body["parent"] = _ref_body(parent)
        if sprint is not None:
            body["sprint"] = [_ref_body(s) for s in sprint]
        if followers is not None:
            body["followers"] = [_ref_body(f) for f in followers]
        if components is not None:
            body["components"] = [c.to_api_value() for c in components]
        if tags is not None:
            body["tags"] = tags
        if project is not None:
            body["project"] = _ref_body(project)

        # Applied last on purpose: an entry here overrides the dedicated
        # parameter of the same name, and an explicit null clears the field.
        if fields:
            body.update(fields)

        return Issue.model_validate_json(
            await self._read("POST", "v3/issues", auth=auth, json=body)
        )

    async def issue_get_transitions(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[IssueTransition]:
        return IssueTransitionList.model_validate_json(
            await self._read(
                "GET",
                f"v2/issues/{issue_id}/transitions",
                auth=auth,
                not_found=IssueNotFound(issue_id),
            )
        ).root

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
        params: dict[str, Any] = {"perPage": per_page}
        if cursor is not None:
            params["id"] = cursor
        if field is not None:
            params["field"] = field
        if type is not None:
            params["type"] = type

        async with self._request(
            "GET",
            f"v3/issues/{issue_id}/changelog",
            auth=auth,
            params=params,
            not_found=IssueNotFound(issue_id),
        ) as response:
            entries = ChangelogList.model_validate_json(await response.read()).root
            return ChangelogPage(
                entries=entries,
                next_cursor=self._parse_next_cursor(response),
            )

    @staticmethod
    def _parse_next_cursor(response: ClientResponse) -> str | None:
        """Extract the next-page cursor from the `Link: rel="next"` response header.

        Yandex Tracker paginates the changelog with an opaque cursor delivered as the
        `id` query parameter of the `next` link, not via the last entry's id.
        """
        next_link = response.links.get("next")
        if next_link is None:
            return None
        next_url = next_link.get("url")
        if not isinstance(next_url, URL):
            return None
        cursor = next_url.query.get("id")
        return str(cursor) if cursor is not None else None

    async def issue_execute_transition(
        self,
        issue_id: str,
        transition_id: str,
        *,
        comment: str | None = None,
        fields: dict[str, str | int | list[str]] | None = None,
        auth: YandexAuth | None = None,
    ) -> list[IssueTransition]:
        body: dict[str, Any] = {}
        if comment is not None:
            body["comment"] = comment
        if fields is not None:
            body.update(fields)

        return IssueTransitionList.model_validate_json(
            await self._read(
                "POST",
                f"v3/issues/{issue_id}/transitions/{transition_id}/_execute",
                auth=auth,
                json=body,
                not_found=IssueNotFound(issue_id),
            )
        ).root

    async def issue_close(
        self,
        issue_id: str,
        resolution_id: str,
        *,
        comment: str | None = None,
        fields: dict[str, str | int | list[str]] | None = None,
        auth: YandexAuth | None = None,
    ) -> list[IssueTransition]:
        # Fetch transitions and statuses in parallel
        async with asyncio.TaskGroup() as tg:
            transitions_task = tg.create_task(
                self.issue_get_transitions(issue_id, auth=auth)
            )
            statuses_task = tg.create_task(self.get_statuses(auth=auth))

        transitions = transitions_task.result()
        statuses = statuses_task.result()

        # Build a map of status key -> status type
        status_type_map: dict[str, str | None] = {
            status.key: status.type for status in statuses
        }

        # Find a transition to a status with type="done"
        done_transition: IssueTransition | None = None
        for transition in transitions:
            if transition.to and transition.to.key:
                status_type = status_type_map.get(transition.to.key)
                if status_type == "done":
                    done_transition = transition
                    break

        if done_transition is None:
            raise NoDoneTransition(issue_id, [t.id for t in transitions])

        if fields is None:
            fields = {}

        fields["resolution"] = resolution_id

        return await self.issue_execute_transition(
            issue_id,
            done_transition.id,
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
        body: dict[str, Any] = {}

        if summary is not None:
            body["summary"] = summary
        if description is not None:
            body["description"] = description
        if markup_type is not None:
            body["markupType"] = markup_type
        if parent is not None:
            body["parent"] = _ref_body(parent)
        if sprint is not None:
            body["sprint"] = [_ref_body(s) for s in sprint]
        if type is not None:
            body["type"] = _ref_body(type)
        if priority is not None:
            body["priority"] = _ref_body(priority)
        if assignee is not None:
            body["assignee"] = assignee
        if followers is not None:
            body["followers"] = [_ref_body(f) for f in followers]
        if components is not None:
            body["components"] = [c.to_api_value() for c in components]
        if project is not None:
            body["project"] = _ref_body(project)
        if attachment_ids is not None:
            body["attachmentIds"] = attachment_ids
        if description_attachment_ids is not None:
            body["descriptionAttachmentIds"] = description_attachment_ids
        if tags is not None:
            body["tags"] = tags

        # Applied last on purpose: an entry here overrides the dedicated
        # parameter of the same name, and an explicit null clears the field.
        if fields:
            body.update(fields)

        params: dict[str, int] = {}
        if version is not None:
            params["version"] = version

        return Issue.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/issues/{issue_id}",
                auth=auth,
                params=params,
                json=body,
                not_found=IssueNotFound(issue_id),
                conflict=IssueVersionConflict(issue_id, version),
            )
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
        params: dict[str, str] = {"queue": queue}
        if not notify:
            params["notify"] = "false"
        if notify_author:
            params["notifyAuthor"] = "true"
        if move_all_fields:
            params["moveAllFields"] = "true"
        if initial_status:
            params["initialStatus"] = "true"

        return Issue.model_validate_json(
            await self._read(
                "POST",
                f"v3/issues/{issue_id}/_move",
                auth=auth,
                params=params,
                not_found=IssueNotFound(issue_id),
            )
        )

    @staticmethod
    def _entity_fields_param(
        entity_type: Literal["project", "portfolio", "goal"],
        fields: list[str] | None,
    ) -> str:
        """Build the `fields` query value for an entity request.

        Yandex Tracker only populates the response's `fields` object with the
        fields explicitly named here, so a per-entity default is applied when
        the caller doesn't pass one. The default sets differ per entity type
        (e.g. `start` is not a valid goal field).
        """
        # An empty list means "nothing selected", which would send `fields=` and
        # come back with an empty `fields` object - fall back to the default.
        if fields:
            return ",".join(fields)
        return DEFAULT_ENTITY_FIELDS_PARAM[entity_type]

    async def _entity_get(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        entity_id: str,
        *,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        params = {"fields": self._entity_fields_param(entity_type, fields)}
        return await self._read(
            "GET", f"v3/entities/{entity_type}/{entity_id}", auth=auth, params=params
        )

    async def _entity_search(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        *,
        input: str | None,
        filter: dict[str, str | list[str]] | None,
        order_by: str | None,
        order_asc: bool | None,
        root_only: bool | None,
        per_page: int,
        page: int,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        params: dict[str, Any] = {
            "perPage": per_page,
            "page": page,
            "fields": self._entity_fields_param(entity_type, fields),
        }

        body: dict[str, Any] = {}
        if input is not None:
            body["input"] = input
        if filter is not None:
            body["filter"] = filter
        if order_by is not None:
            body["orderBy"] = order_by
        if order_asc is not None:
            body["orderAsc"] = order_asc
        if root_only is not None:
            body["rootOnly"] = root_only

        return await self._read(
            "POST",
            f"v3/entities/{entity_type}/_search",
            auth=auth,
            params=params,
            json=body,
        )

    async def project_get(
        self,
        entity_id: str,
        *,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> ProjectEntity:
        return ProjectEntity.model_validate_json(
            await self._entity_get("project", entity_id, fields=fields, auth=auth)
        )

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
        return ProjectSearchResult.model_validate_json(
            await self._entity_search(
                "project",
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
        )

    async def portfolio_get(
        self,
        entity_id: str,
        *,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> PortfolioEntity:
        return PortfolioEntity.model_validate_json(
            await self._entity_get("portfolio", entity_id, fields=fields, auth=auth)
        )

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
        return PortfolioSearchResult.model_validate_json(
            await self._entity_search(
                "portfolio",
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
        )

    async def goal_get(
        self,
        entity_id: str,
        *,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> GoalEntity:
        return GoalEntity.model_validate_json(
            await self._entity_get("goal", entity_id, fields=fields, auth=auth)
        )

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
        return GoalSearchResult.model_validate_json(
            await self._entity_search(
                "goal",
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
        )

    @staticmethod
    def _build_entity_fields_body(
        *,
        summary: str | None,
        description: str | None,
        lead: str | None,
        team_users: list[str] | None,
        clients: list[str] | None,
        followers: list[str] | None,
        start: datetime.date | datetime.datetime | None,
        end: datetime.date | datetime.datetime | None,
        tags: list[str] | None,
        entity_status: str | None,
        parent_entity: EntityParentEntityInput | None,
        team_access: bool | None = None,
    ) -> dict[str, Any]:
        fields_body: dict[str, Any] = {}
        if summary is not None:
            fields_body["summary"] = summary
        if description is not None:
            fields_body["description"] = description
        if lead is not None:
            fields_body["lead"] = lead
        if team_users is not None:
            fields_body["teamUsers"] = team_users
        if clients is not None:
            fields_body["clients"] = clients
        if followers is not None:
            fields_body["followers"] = followers
        if start is not None:
            fields_body["start"] = start.isoformat()
        if end is not None:
            fields_body["end"] = end.isoformat()
        if tags is not None:
            fields_body["tags"] = tags
        if entity_status is not None:
            fields_body["entityStatus"] = entity_status
        if parent_entity is not None:
            fields_body["parentEntity"] = parent_entity.model_dump(exclude_none=True)
        if team_access is not None:
            fields_body["teamAccess"] = team_access
        return fields_body

    async def _entity_create(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        *,
        fields_body: dict[str, Any],
        links: list[ProjectPortfolioLinkInput] | list[GoalLinkInput] | None,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        body: dict[str, Any] = {}
        if fields_body:
            body["fields"] = fields_body
        if links is not None:
            body["links"] = [link.model_dump(exclude_none=True) for link in links]

        return await self._read(
            "POST",
            f"v3/entities/{entity_type}",
            auth=auth,
            params={"fields": self._entity_fields_param(entity_type, fields)},
            json=body,
        )

    async def _entity_update(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        entity_id: str,
        *,
        fields_body: dict[str, Any],
        links: list[ProjectPortfolioLinkInput] | list[GoalLinkInput] | None,
        comment: str | None,
        version: int | None,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        # Tracker silently ignores `links` unless the request changes the entity
        # itself, so a links-only update would return 200 having done nothing.
        if links and not fields_body and comment is None:
            raise EntityLinksOnlyUpdate()

        # An update may touch only links and/or add a comment - don't send an empty `fields`.
        body: dict[str, Any] = {}
        if fields_body:
            body["fields"] = fields_body
        if links is not None:
            body["links"] = [link.model_dump(exclude_none=True) for link in links]
        if comment is not None:
            body["comment"] = comment

        params: dict[str, Any] = {
            "fields": self._entity_fields_param(entity_type, fields)
        }
        if version is not None:
            params["version"] = version

        return await self._read(
            "PATCH",
            f"v3/entities/{entity_type}/{entity_id}",
            auth=auth,
            params=params,
            json=body,
        )

    async def _entity_delete(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        entity_id: str,
        *,
        with_board: bool,
        auth: YandexAuth | None,
    ) -> None:
        params = {"withBoard": "true"} if with_board else None
        await self._read(
            "DELETE", f"v3/entities/{entity_type}/{entity_id}", auth=auth, params=params
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
        fields_body = self._build_entity_fields_body(
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
        )
        return ProjectEntity.model_validate_json(
            await self._entity_create(
                "project",
                fields_body=fields_body,
                links=links,
                fields=fields,
                auth=auth,
            )
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
        fields_body = self._build_entity_fields_body(
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
        )
        return ProjectEntity.model_validate_json(
            await self._entity_update(
                "project",
                entity_id,
                fields_body=fields_body,
                links=links,
                comment=comment,
                version=version,
                fields=fields,
                auth=auth,
            )
        )

    async def project_delete(
        self,
        entity_id: str,
        *,
        with_board: bool = False,
        auth: YandexAuth | None = None,
    ) -> None:
        await self._entity_delete(
            "project", entity_id, with_board=with_board, auth=auth
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
        fields_body = self._build_entity_fields_body(
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
        )
        return PortfolioEntity.model_validate_json(
            await self._entity_create(
                "portfolio",
                fields_body=fields_body,
                links=links,
                fields=fields,
                auth=auth,
            )
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
        fields_body = self._build_entity_fields_body(
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
        )
        return PortfolioEntity.model_validate_json(
            await self._entity_update(
                "portfolio",
                entity_id,
                fields_body=fields_body,
                links=links,
                comment=comment,
                version=version,
                fields=fields,
                auth=auth,
            )
        )

    async def portfolio_delete(
        self,
        entity_id: str,
        *,
        with_board: bool = False,
        auth: YandexAuth | None = None,
    ) -> None:
        await self._entity_delete(
            "portfolio", entity_id, with_board=with_board, auth=auth
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
        fields_body = self._build_entity_fields_body(
            summary=summary,
            description=description,
            lead=lead,
            team_users=team_users,
            clients=clients,
            followers=followers,
            start=None,
            end=end,
            tags=tags,
            entity_status=entity_status,
            parent_entity=parent_entity,
            team_access=team_access,
        )
        return GoalEntity.model_validate_json(
            await self._entity_create(
                "goal", fields_body=fields_body, links=links, fields=fields, auth=auth
            )
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
        fields_body = self._build_entity_fields_body(
            summary=summary,
            description=description,
            lead=lead,
            team_users=team_users,
            clients=clients,
            followers=followers,
            start=None,
            end=end,
            tags=tags,
            entity_status=entity_status,
            parent_entity=parent_entity,
            team_access=team_access,
        )
        return GoalEntity.model_validate_json(
            await self._entity_update(
                "goal",
                entity_id,
                fields_body=fields_body,
                links=links,
                comment=comment,
                version=version,
                fields=fields,
                auth=auth,
            )
        )

    async def goal_delete(
        self,
        entity_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        # Goals have no board, so `withBoard` is not applicable here.
        await self._entity_delete("goal", entity_id, with_board=False, auth=auth)

    async def _entity_get_comments(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        entity_id: str,
        *,
        per_page: int,
        cursor: str | None,
        auth: YandexAuth | None,
    ) -> CommentsPage:
        params: dict[str, Any] = {"perPage": per_page}
        if cursor is not None:
            # `from` is exclusive: the page starts after that comment.
            params["from"] = cursor

        async with self._request(
            "GET",
            f"v3/entities/{entity_type}/{entity_id}/comments/_relative",
            auth=auth,
            params=params,
        ) as response:
            page = EntityCommentsRelativePage.model_validate_json(await response.read())
            next_cursor: str | None = None
            if page.hasNext and page.comments:
                # `longId` is optional on the comment model; fall back to the
                # numeric id (the API accepts either) so a truncated page is
                # never reported as the complete list.
                last = page.comments[-1]
                next_cursor = last.long_id or str(last.id)
            return CommentsPage(comments=page.comments, next_cursor=next_cursor)

    async def _entity_add_comment(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        entity_id: str,
        *,
        text: str,
        summonees: list[str] | None,
        maillist_summonees: list[str] | None,
        auth: YandexAuth | None,
    ) -> IssueComment:
        body: dict[str, Any] = {"text": text}
        if summonees is not None:
            body["summonees"] = summonees
        if maillist_summonees is not None:
            body["maillistSummonees"] = maillist_summonees

        return IssueComment.model_validate_json(
            await self._read(
                "POST",
                f"v3/entities/{entity_type}/{entity_id}/comments",
                auth=auth,
                json=body,
            )
        )

    async def _entity_update_comment(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        entity_id: str,
        comment_id: int,
        *,
        text: str,
        summonees: list[str] | None,
        maillist_summonees: list[str] | None,
        auth: YandexAuth | None,
    ) -> IssueComment:
        body: dict[str, Any] = {"text": text}
        if summonees is not None:
            body["summonees"] = summonees
        if maillist_summonees is not None:
            body["maillistSummonees"] = maillist_summonees

        return IssueComment.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/entities/{entity_type}/{entity_id}/comments/{comment_id}",
                auth=auth,
                json=body,
            )
        )

    async def _entity_delete_comment(
        self,
        entity_type: Literal["project", "portfolio", "goal"],
        entity_id: str,
        comment_id: int,
        *,
        auth: YandexAuth | None,
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/entities/{entity_type}/{entity_id}/comments/{comment_id}",
            auth=auth,
        )

    async def project_get_comments(
        self,
        entity_id: str,
        *,
        per_page: int = 50,
        cursor: str | None = None,
        auth: YandexAuth | None = None,
    ) -> CommentsPage:
        return await self._entity_get_comments(
            "project", entity_id, per_page=per_page, cursor=cursor, auth=auth
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
        return await self._entity_add_comment(
            "project",
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
        return await self._entity_update_comment(
            "project",
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
        await self._entity_delete_comment("project", entity_id, comment_id, auth=auth)

    async def portfolio_get_comments(
        self,
        entity_id: str,
        *,
        per_page: int = 50,
        cursor: str | None = None,
        auth: YandexAuth | None = None,
    ) -> CommentsPage:
        return await self._entity_get_comments(
            "portfolio", entity_id, per_page=per_page, cursor=cursor, auth=auth
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
        return await self._entity_add_comment(
            "portfolio",
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
        return await self._entity_update_comment(
            "portfolio",
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
        await self._entity_delete_comment("portfolio", entity_id, comment_id, auth=auth)

    async def goal_get_comments(
        self,
        entity_id: str,
        *,
        per_page: int = 50,
        cursor: str | None = None,
        auth: YandexAuth | None = None,
    ) -> CommentsPage:
        return await self._entity_get_comments(
            "goal", entity_id, per_page=per_page, cursor=cursor, auth=auth
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
        return await self._entity_add_comment(
            "goal",
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
        return await self._entity_update_comment(
            "goal",
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
        await self._entity_delete_comment("goal", entity_id, comment_id, auth=auth)

    @staticmethod
    def _build_checklist_item_body(
        *,
        text: str | None,
        checked: bool | None,
        assignee: str | int | dict[str, Any] | None,
        deadline: dict[str, Any] | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if text is not None:
            body["text"] = text
        if checked is not None:
            body["checked"] = checked
        if assignee is not None:
            body["assignee"] = assignee
        if deadline is not None:
            body["deadline"] = deadline
        return body

    async def _entity_add_checklist_item(
        self,
        entity_type: Literal["project", "portfolio"],
        entity_id: str,
        *,
        text: str,
        checked: bool | None,
        assignee: str | None,
        deadline: dict[str, Any] | None,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        body = self._build_checklist_item_body(
            text=text, checked=checked, assignee=assignee, deadline=deadline
        )
        return await self._read(
            "POST",
            f"v3/entities/{entity_type}/{entity_id}/checklistItems",
            auth=auth,
            params={"fields": self._entity_fields_param(entity_type, fields)},
            json=body,
        )

    async def _entity_update_checklist_item(
        self,
        entity_type: Literal["project", "portfolio"],
        entity_id: str,
        checklist_item_id: str,
        *,
        text: str | None,
        checked: bool | None,
        assignee: str | None,
        deadline: dict[str, Any] | None,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        body = self._build_checklist_item_body(
            text=text, checked=checked, assignee=assignee, deadline=deadline
        )
        return await self._read(
            "PATCH",
            f"v3/entities/{entity_type}/{entity_id}/checklistItems/{checklist_item_id}",
            auth=auth,
            params={"fields": self._entity_fields_param(entity_type, fields)},
            json=body,
        )

    async def _entity_move_checklist_item(
        self,
        entity_type: Literal["project", "portfolio"],
        entity_id: str,
        checklist_item_id: str,
        *,
        before: str,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        return await self._read(
            "POST",
            f"v3/entities/{entity_type}/{entity_id}/checklistItems/{checklist_item_id}/_move",
            auth=auth,
            params={"fields": self._entity_fields_param(entity_type, fields)},
            json={"before": before},
        )

    async def _entity_delete_checklist_item(
        self,
        entity_type: Literal["project", "portfolio"],
        entity_id: str,
        checklist_item_id: str,
        *,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        return await self._read(
            "DELETE",
            f"v3/entities/{entity_type}/{entity_id}/checklistItems/{checklist_item_id}",
            auth=auth,
            params={"fields": self._entity_fields_param(entity_type, fields)},
        )

    async def _entity_update_checklist(
        self,
        entity_type: Literal["project", "portfolio"],
        entity_id: str,
        *,
        items: list[EntityChecklistItemUpdateInput],
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        body = [item.model_dump(exclude_none=True) for item in items]
        return await self._read(
            "PATCH",
            f"v3/entities/{entity_type}/{entity_id}/checklistItems",
            auth=auth,
            params={"fields": self._entity_fields_param(entity_type, fields)},
            json=body,
        )

    @staticmethod
    def _checklist_item_to_update_input(
        item: ChecklistItem,
    ) -> EntityChecklistItemUpdateInput:
        deadline: dict[str, Any] | None = None
        if item.deadline is not None:
            deadline = {
                "date": _tracker_datetime(item.deadline.date),
                "deadlineType": item.deadline.deadline_type,
            }
        return EntityChecklistItemUpdateInput(
            id=item.id,
            text=item.text,
            checked=item.checked,
            assignee=(item.assignee.id if item.assignee is not None else None),
            deadline=deadline,
        )

    async def _reconcile_checklist_update(
        self,
        entity_type: Literal["project", "portfolio"],
        entity_id: str,
        *,
        items: list[EntityChecklistItemUpdateInput],
        auth: YandexAuth | None,
    ) -> list[EntityChecklistItemUpdateInput]:
        """Fill in the rest of the checklist so a caller can send just the items it wants to change.

        `PATCH .../checklistItems` edits every item in the array it is given and
        rejects the request outright if the array's length does not match the
        entity's current item count - verified against the live API, sending a
        subset (to drop items) or an extra item (to add one) both answer with an
        opaque 500. Fetching the current checklist first and resending every item
        - untouched ones verbatim, requested ones with the caller's overrides
        applied - makes a true partial update possible without the caller having
        to know about this quirk.
        """
        current_raw = await self._entity_get(
            entity_type, entity_id, fields=["checklistItems"], auth=auth
        )
        current = _ChecklistSnapshot.model_validate_json(current_raw)
        current_by_id = {item.id: item for item in current.fields.checklistItems}

        overrides = {item.id: item for item in items}
        for item_id in overrides:
            if item_id not in current_by_id:
                raise ChecklistItemNotFound(entity_id, item_id)

        merged: list[EntityChecklistItemUpdateInput] = []
        for item_id, current_item in current_by_id.items():
            override = overrides.get(item_id)
            if override is None:
                merged.append(self._checklist_item_to_update_input(current_item))
                continue
            base = self._checklist_item_to_update_input(current_item)
            merged.append(
                EntityChecklistItemUpdateInput(
                    id=item_id,
                    text=override.text,
                    checked=(
                        override.checked
                        if override.checked is not None
                        else base.checked
                    ),
                    assignee=(
                        override.assignee
                        if override.assignee is not None
                        else base.assignee
                    ),
                    deadline=(
                        override.deadline
                        if override.deadline is not None
                        else base.deadline
                    ),
                )
            )
        return merged

    async def _entity_delete_checklist(
        self,
        entity_type: Literal["project", "portfolio"],
        entity_id: str,
        *,
        fields: list[str] | None,
        auth: YandexAuth | None,
    ) -> bytes:
        return await self._read(
            "DELETE",
            f"v3/entities/{entity_type}/{entity_id}/checklistItems",
            auth=auth,
            params={"fields": self._entity_fields_param(entity_type, fields)},
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
        return ProjectEntity.model_validate_json(
            await self._entity_add_checklist_item(
                "project",
                entity_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )
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
        return ProjectEntity.model_validate_json(
            await self._entity_update_checklist_item(
                "project",
                entity_id,
                checklist_item_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )
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
        return ProjectEntity.model_validate_json(
            await self._entity_move_checklist_item(
                "project",
                entity_id,
                checklist_item_id,
                before=before,
                fields=fields,
                auth=auth,
            )
        )

    async def project_delete_checklist_item(
        self,
        entity_id: str,
        checklist_item_id: str,
        *,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> ProjectEntity:
        return ProjectEntity.model_validate_json(
            await self._entity_delete_checklist_item(
                "project",
                entity_id,
                checklist_item_id,
                fields=fields,
                auth=auth,
            )
        )

    async def project_update_checklist(
        self,
        entity_id: str,
        *,
        items: list[EntityChecklistItemUpdateInput],
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> ProjectEntity:
        merged_items = await self._reconcile_checklist_update(
            "project", entity_id, items=items, auth=auth
        )
        return ProjectEntity.model_validate_json(
            await self._entity_update_checklist(
                "project",
                entity_id,
                items=merged_items,
                fields=fields,
                auth=auth,
            )
        )

    async def project_delete_checklist(
        self,
        entity_id: str,
        *,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> ProjectEntity:
        return ProjectEntity.model_validate_json(
            await self._entity_delete_checklist(
                "project", entity_id, fields=fields, auth=auth
            )
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
        return PortfolioEntity.model_validate_json(
            await self._entity_add_checklist_item(
                "portfolio",
                entity_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )
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
        return PortfolioEntity.model_validate_json(
            await self._entity_update_checklist_item(
                "portfolio",
                entity_id,
                checklist_item_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                fields=fields,
                auth=auth,
            )
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
        return PortfolioEntity.model_validate_json(
            await self._entity_move_checklist_item(
                "portfolio",
                entity_id,
                checklist_item_id,
                before=before,
                fields=fields,
                auth=auth,
            )
        )

    async def portfolio_delete_checklist_item(
        self,
        entity_id: str,
        checklist_item_id: str,
        *,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> PortfolioEntity:
        return PortfolioEntity.model_validate_json(
            await self._entity_delete_checklist_item(
                "portfolio",
                entity_id,
                checklist_item_id,
                fields=fields,
                auth=auth,
            )
        )

    async def portfolio_update_checklist(
        self,
        entity_id: str,
        *,
        items: list[EntityChecklistItemUpdateInput],
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> PortfolioEntity:
        merged_items = await self._reconcile_checklist_update(
            "portfolio", entity_id, items=items, auth=auth
        )
        return PortfolioEntity.model_validate_json(
            await self._entity_update_checklist(
                "portfolio",
                entity_id,
                items=merged_items,
                fields=fields,
                auth=auth,
            )
        )

    async def portfolio_delete_checklist(
        self,
        entity_id: str,
        *,
        fields: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> PortfolioEntity:
        return PortfolioEntity.model_validate_json(
            await self._entity_delete_checklist(
                "portfolio", entity_id, fields=fields, auth=auth
            )
        )

    async def boards_list(
        self,
        *,
        per_page: int = 100,
        cursor: int | None = None,
        auth: YandexAuth | None = None,
    ) -> list[Board]:
        """One page of boards, ascending by id.

        `cursor` is the id of the last board of the previous page and is
        exclusive; a page shorter than `per_page` is the last one.

        This is the only way boards are read. `/v3/boards` returns the whole
        organization in one response - 1.4 MB and 7-16s for 415 boards, in a
        different order every call - and no timeout fits that, because the
        request grows with the Tracker it is pointed at: generous for one
        organization is not enough for the next. A page is bounded by `per_page`
        instead, so what the budget has to cover stops depending on how large
        the organization is. It does not make the API's own variance go away,
        which is what `TRACKER_API_TIMEOUT` and `TrackerAPITimeout` are for.
        """
        params: dict[str, Any] = {"perPage": min(per_page, BOARDS_PAGE_MAX)}
        if cursor is not None:
            params["id"] = cursor

        return BoardList.model_validate_json(
            await self._read("GET", "v3/boards/_paginate", auth=auth, params=params)
        ).root

    async def board_get(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> Board:
        return Board.model_validate_json(
            await self._read(
                "GET",
                f"v3/boards/{board_id}",
                auth=auth,
                not_found=BoardNotFound(board_id),
            )
        )

    async def board_get_columns(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[BoardColumnDetail]:
        return BoardColumnList.model_validate_json(
            await self._read(
                "GET",
                f"v3/boards/{board_id}/columns",
                auth=auth,
                not_found=BoardNotFound(board_id),
            )
        ).root

    async def board_create(
        self,
        *,
        name: str,
        columns: list[BoardColumnInput] | None = None,
        owner: str | None = None,
        private: bool | None = None,
        sprints: bool | None = None,
        auto_filter: dict[str, list[str]] | None = None,
        auth: YandexAuth | None = None,
    ) -> Board:
        """Create a board through `POST v3/liveBoards`.

        The documented `POST v3/boards` is deprecated and ignores the body,
        creating a board with default settings. The auto-filter can only be set
        here: `PATCH v3/boards/{id}` answers 400 to `autoFilters` (live API,
        2026-10-26).
        """
        body: dict[str, Any] = {"name": name}
        if columns is not None:
            body["columns"] = [_column_body(c) for c in columns]
        if owner is not None:
            body["owner"] = owner
        if private is not None:
            body["boardPermissionsTemplate"] = "private" if private else "public"
        if sprints is not None:
            body.update(_sprints_body(sprints))
        if auto_filter is not None:
            body["autoFilters"] = {
                "addFilter": {
                    "liveFilter": {
                        "fieldValues": {
                            field: [{"fixed": value} for value in values]
                            for field, values in auto_filter.items()
                        }
                    },
                    "enabled": True,
                }
            }

        return Board.model_validate_json(
            await self._read("POST", "v3/liveBoards", auth=auth, json=body)
        )

    async def board_update(
        self,
        board_id: int,
        *,
        version: int | None = None,
        name: str | None = None,
        columns: list[BoardColumnInput] | None = None,
        sprints: bool | None = None,
        auth: YandexAuth | None = None,
    ) -> Board:
        """Change a board; `columns` replaces every column, under new ids."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if columns is not None:
            body["columns"] = [_column_body(c) for c in columns]
        if sprints is not None:
            body.update(_sprints_body(sprints))
        if not body:
            # An empty body answers 200 and changes nothing.
            raise BoardEmptyUpdate()

        return Board.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/boards/{board_id}",
                auth=auth,
                json=body,
                not_found=BoardNotFound(board_id),
                extra_headers=_if_match(version),
                conflict=_board_conflict(board_id, version),
            )
        )

    async def board_delete(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/boards/{board_id}",
            auth=auth,
            not_found=BoardNotFound(board_id),
        )

    # The column paths answer 404 with Tracker's own words for which of the two
    # is missing ("Колонка не существует." / "Доска не существует."), so no
    # `not_found` is passed: that text reaches the caller as it is.

    async def board_get_column(
        self, board_id: int, column_id: int, *, auth: YandexAuth | None = None
    ) -> BoardColumnDetail:
        return BoardColumnDetail.model_validate_json(
            await self._read(
                "GET", f"v3/boards/{board_id}/columns/{column_id}", auth=auth
            )
        )

    async def board_create_column(
        self,
        board_id: int,
        *,
        name: str,
        statuses: list[str],
        limit: int | None = None,
        version: int | None = None,
        auth: YandexAuth | None = None,
    ) -> BoardColumnDetail:
        body = _column_body(BoardColumnInput(name=name, statuses=statuses, limit=limit))
        return BoardColumnDetail.model_validate_json(
            await self._read(
                "POST",
                f"v3/boards/{board_id}/columns",
                auth=auth,
                json=body,
                extra_headers=_if_match(version),
                conflict=_board_conflict(board_id, version),
            )
        )

    async def board_update_column(
        self,
        board_id: int,
        column_id: int,
        *,
        version: int | None = None,
        name: str | None = None,
        statuses: list[str] | None = None,
        limit: int | None = None,
        auth: YandexAuth | None = None,
    ) -> BoardColumnDetail:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if statuses is not None:
            body["statuses"] = statuses
        if limit is not None:
            body["limit"] = limit
        if not body:
            # An empty body answers 200, changes nothing and still bumps the
            # board's version.
            raise BoardColumnEmptyUpdate()

        return BoardColumnDetail.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/boards/{board_id}/columns/{column_id}",
                auth=auth,
                json=body,
                extra_headers=_if_match(version),
                conflict=_board_conflict(board_id, version),
            )
        )

    async def board_delete_column(
        self,
        board_id: int,
        column_id: int,
        *,
        version: int | None = None,
        auth: YandexAuth | None = None,
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/boards/{board_id}/columns/{column_id}",
            auth=auth,
            extra_headers=_if_match(version),
            conflict=_board_conflict(board_id, version),
        )

    async def board_get_sprints(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[Sprint]:
        # A board that is not a scrum board answers 400 with "У доски этого типа
        # не может быть спринтов." - that explanation only reaches the caller
        # because `_request` puts every response through `_raise_for_status`.
        return SprintList.model_validate_json(
            await self._read(
                "GET",
                f"v3/boards/{board_id}/sprints",
                auth=auth,
                not_found=BoardNotFound(board_id),
            )
        ).root

    async def sprint_get(
        self, sprint_id: int, *, auth: YandexAuth | None = None
    ) -> Sprint:
        return Sprint.model_validate_json(
            await self._read(
                "GET",
                f"v3/sprints/{sprint_id}",
                auth=auth,
                not_found=SprintNotFound(sprint_id),
            )
        )

    async def sprint_create(
        self,
        board_id: int,
        *,
        name: str,
        start_date: datetime.date,
        end_date: datetime.date,
        auth: YandexAuth | None = None,
    ) -> Sprint:
        return Sprint.model_validate_json(
            await self._read(
                "POST",
                "v3/sprints",
                auth=auth,
                json={
                    "name": name,
                    "board": {"id": str(board_id)},
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                },
                not_found=BoardNotFound(board_id),
            )
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
        """Change a sprint under `If-Match: "<version>"`, as the API asks."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if start_date is not None:
            body["startDate"] = start_date.isoformat()
        if end_date is not None:
            body["endDate"] = end_date.isoformat()
        if status is not None:
            body["status"] = status
        if not body:
            raise SprintEmptyUpdate()

        return Sprint.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/sprints/{sprint_id}",
                auth=auth,
                json=body,
                extra_headers={"If-Match": f'"{version}"'},
                not_found=SprintNotFound(sprint_id),
                conflict=SprintVersionConflict(sprint_id, version),
            )
        )

    async def sprint_start(
        self, sprint_id: int, *, version: int, auth: YandexAuth | None = None
    ) -> Sprint:
        return await self._sprint_action(sprint_id, "_start", version, auth=auth)

    async def sprint_archive(
        self, sprint_id: int, *, version: int, auth: YandexAuth | None = None
    ) -> Sprint:
        return await self._sprint_action(sprint_id, "_archive", version, auth=auth)

    async def _sprint_action(
        self,
        sprint_id: int,
        action: str,
        version: int,
        *,
        auth: YandexAuth | None,
    ) -> Sprint:
        return Sprint.model_validate_json(
            await self._read(
                "POST",
                f"v3/sprints/{sprint_id}/{action}",
                auth=auth,
                extra_headers={"If-Match": f'"{version}"'},
                not_found=SprintNotFound(sprint_id),
                conflict=SprintVersionConflict(sprint_id, version),
            )
        )

    async def sprint_delete(
        self, sprint_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/sprints/{sprint_id}",
            auth=auth,
            not_found=SprintNotFound(sprint_id),
        )

    async def component_get_user_permissions(
        self, component_id: int, user: str, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions:
        return SubjectPermissions.model_validate_json(
            await self._read(
                "GET",
                f"v3/components/{component_id}/permissions/users/"
                f"{quote(user, safe='')}",
                auth=auth,
                not_found=ComponentNotFound(component_id),
            )
        )

    async def component_get_group_permissions(
        self, component_id: int, group_id: int, *, auth: YandexAuth | None = None
    ) -> SubjectPermissions:
        return SubjectPermissions.model_validate_json(
            await self._read(
                "GET",
                f"v3/components/{component_id}/permissions/groups/{group_id}",
                auth=auth,
                not_found=ComponentNotFound(component_id),
            )
        )

    async def component_get(
        self, component_id: int, *, auth: YandexAuth | None = None
    ) -> Component:
        """One component by id; undocumented - see AGENTS.md, *Queue components*."""
        return Component.model_validate_json(
            await self._read(
                "GET",
                f"v3/components/{component_id}",
                auth=auth,
                not_found=ComponentNotFound(component_id),
            )
        )

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
        """Create a component in a queue - see AGENTS.md, *Queue components*."""
        body: dict[str, Any] = {"queue": queue_id, "name": name}
        if description is not None:
            body["description"] = description
        if lead is not None:
            body["lead"] = lead
        if assign_auto is not None:
            body["assignAuto"] = assign_auto

        return Component.model_validate_json(
            await self._read("POST", "v3/components", auth=auth, json=body)
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
        """Change the fields of a component that are passed.

        `version` is required: the API answers 428 without it and 412 for a
        stale one. An empty body is a 200 no-op, so it is refused locally, and
        `{}` is what clears the lead - see AGENTS.md, *Queue components*.
        """
        if clear_lead and lead is not None:
            raise FieldClearConflict("lead")

        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if clear_lead:
            body["lead"] = {}
        elif lead is not None:
            body["lead"] = lead
        if assign_auto is not None:
            body["assignAuto"] = assign_auto
        if not body:
            raise ComponentEmptyUpdate()

        return Component.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/components/{component_id}",
                auth=auth,
                params={"version": version},
                json=body,
                not_found=ComponentNotFound(component_id),
                conflict=ComponentVersionConflict(component_id, version),
            )
        )

    async def component_delete(
        self, component_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        """Delete a component; undocumented, answers 204 and takes no `version` -
        see AGENTS.md, *Queue components*."""
        await self._read(
            "DELETE",
            f"v3/components/{component_id}",
            auth=auth,
            not_found=ComponentNotFound(component_id),
        )

    async def workflows_get_all(
        self, *, auth: YandexAuth | None = None
    ) -> list[Workflow]:
        return WorkflowList.model_validate_json(
            await self._read("GET", "v3/workflows", auth=auth)
        ).root

    async def workflow_get(
        self, workflow_id: str, *, auth: YandexAuth | None = None
    ) -> Workflow:
        return await self._workflow_read(workflow_id, auth=auth)

    async def _workflow_read(
        self, workflow_id: str, *, auth: YandexAuth | None, lang: str | None = None
    ) -> Workflow:
        return Workflow.model_validate_json(
            await self._read(
                "GET",
                f"v3/workflows/{quote(workflow_id, safe='')}",
                auth=auth,
                not_found=WorkflowNotFound(workflow_id),
                extra_headers={"Accept-Language": lang} if lang else None,
            )
        )

    async def queues_get_workflows(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> dict[str, list[IssueTypeReference]]:
        """Workflow id -> the issue types of the queue that run on it."""
        return QueueWorkflows.model_validate_json(
            await self._read(
                "GET",
                f"v3/queues/{queue_id}/workflows",
                auth=auth,
                not_found=QueueNotFound(queue_id),
            )
        ).root

    async def screen_get(
        self, screen_id: int, *, auth: YandexAuth | None = None
    ) -> Screen:
        """A transition screen; undocumented - see AGENTS.md, *Workflows*."""
        return await self._screen_read(screen_id, auth=auth)

    async def _screen_read(
        self, screen_id: int, *, auth: YandexAuth | None, lang: str | None = None
    ) -> Screen:
        return Screen.model_validate_json(
            await self._read(
                "GET",
                f"v3/screens/{screen_id}",
                auth=auth,
                not_found=ScreenNotFound(screen_id),
                extra_headers={"Accept-Language": lang} if lang else None,
            )
        )

    async def workflow_get_draft(
        self, workflow_id: str, *, auth: YandexAuth | None = None
    ) -> WorkflowDraft:
        """The workflow in the shape a write takes, for read-modify-write.

        A read names things in one language and a write wants both, so the
        workflow is read in Russian and in English, and every screen its
        transitions use is read too: a write cannot refer to a screen, only
        restate its fields. Writing the draft back unchanged leaves the
        workflow as it was (verified on the live API 2026-10-23), except that
        each screen comes back as a new copy with a new id.
        """
        for _ in range(_WORKFLOW_DRAFT_ATTEMPTS):
            ru, en = await asyncio.gather(
                self._workflow_read(workflow_id, auth=auth, lang="ru"),
                self._workflow_read(workflow_id, auth=auth, lang="en"),
            )
            # Changed between the two reads: read again rather than mix them.
            if ru.version == en.version:
                break
        else:
            raise WorkflowVersionConflict(workflow_id, ru.version)

        actions = [ru.initial_action] if ru.initial_action else []
        for step in ru.steps:
            actions.extend(step.actions or [])
            if step.meta_action:
                actions.append(step.meta_action)
        screen_ids = sorted(
            {int(a.screen.id) for a in actions if a.screen and a.screen.id is not None}
        )
        screens: dict[int, ScreenDraft | None] = {}
        for screen_id in screen_ids:
            screen_ru, screen_en = await asyncio.gather(
                self._screen_read(screen_id, auth=auth, lang="ru"),
                self._screen_read(screen_id, auth=auth, lang="en"),
            )
            screens[screen_id] = _screen_draft(screen_ru, screen_en)

        en_steps = {s.status.key: s for s in en.steps}

        def in_english(
            status: str, action: WorkflowAction, meta: bool = False
        ) -> WorkflowAction | None:
            step = en_steps.get(status)
            if step is None:
                return None
            if meta:
                return step.meta_action
            return next((a for a in step.actions or [] if a.id == action.id), None)

        steps = []
        for step in ru.steps:
            key = step.status.key or ""
            steps.append(
                WorkflowStepDraft(
                    status=key,
                    status_type=step.status_type,
                    step_coords=step.step_coords,
                    meta_action=_action_draft(
                        step.meta_action,
                        in_english(key, step.meta_action, meta=True),
                        screens,
                    )
                    if step.meta_action
                    else None,
                    actions=[
                        _action_draft(a, in_english(key, a), screens)
                        for a in step.actions or []
                    ],
                )
            )
        if ru.initial_action is None:  # pragma: no cover - every workflow has one
            raise TrackerAPIError(
                status=200,
                method="GET",
                url=f"v3/workflows/{workflow_id}",
                body="the workflow has no initialAction",
            )
        return WorkflowDraft(
            id=ru.id,
            version=ru.version,
            name=ru.name,
            queue=ru.queue.key if ru.queue else None,
            initial_action=_action_draft(ru.initial_action, en.initial_action, screens),
            steps=steps,
        )

    async def workflow_create(
        self,
        *,
        name: str,
        initial_action: WorkflowActionDraft,
        steps: list[WorkflowStepDraft],
        queue: str | None = None,
        auth: YandexAuth | None = None,
    ) -> Workflow:
        body: dict[str, Any] = {
            "name": name,
            "type": "VISUAL",
            "initialAction": initial_action.model_dump(by_alias=True),
            "steps": [s.model_dump(by_alias=True) for s in steps],
        }
        if queue is not None:
            body["queue"] = queue
        return Workflow.model_validate_json(
            await self._read("POST", "v3/workflows", auth=auth, json=body)
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
        """`steps` replaces every step and transition of the workflow."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if initial_action is not None:
            body["initialAction"] = initial_action.model_dump(by_alias=True)
        if steps is not None:
            body["steps"] = [s.model_dump(by_alias=True) for s in steps]
        if issue_type_resolutions is not None:
            body["issueTypeResolutions"] = [
                r.model_dump(by_alias=True) for r in issue_type_resolutions
            ]
        return Workflow.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/workflows/{quote(workflow_id, safe='')}",
                auth=auth,
                params={"version": version},
                json=body,
                not_found=WorkflowNotFound(workflow_id),
                conflict=WorkflowVersionConflict(workflow_id, version),
            )
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
        """Add one transition; undocumented (`POST .../steps/{status}/actions`).

        A 404 is passed through with Tracker's own text: it answers an unknown
        workflow and an unknown status ("Статус не существует") alike.
        """
        return Workflow.model_validate_json(
            await self._read(
                "POST",
                f"v3/workflows/{quote(workflow_id, safe='')}/steps/"
                f"{quote(status, safe='')}/actions",
                auth=auth,
                params={"version": version},
                json=action.model_dump(by_alias=True),
                conflict=WorkflowVersionConflict(workflow_id, version),
            )
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
        """Replace one transition with `action`. The API replaces it whole -
        what `action` leaves out is removed - and answers an unknown one with
        a 404 whose text is passed through ("Переход не существует")."""
        return Workflow.model_validate_json(
            await self._read(
                "PATCH",
                f"v3/workflows/{quote(workflow_id, safe='')}/steps/"
                f"{quote(status, safe='')}/actions/{quote(action_id, safe='')}",
                auth=auth,
                params={"version": version},
                json=action.model_dump(by_alias=True),
                conflict=WorkflowVersionConflict(workflow_id, version),
            )
        )

    async def workflow_delete(
        self, workflow_id: str, *, auth: YandexAuth | None = None
    ) -> None:
        await self._read(
            "DELETE",
            f"v3/workflows/{quote(workflow_id, safe='')}",
            auth=auth,
            not_found=WorkflowNotFound(workflow_id),
        )


_WORKFLOW_DRAFT_ATTEMPTS = 3

# Waits before deleting a queue again after Tracker's passing 412.
_QUEUE_DELETE_RETRY_WAITS = (2.0, 5.0, 10.0)


# Condition types a read names differently from what a write takes (verified on
# the live API 2026-10-23): the linked-queue condition reads back as
# `HasLinksConditionProto` and a write of that name answers 400.
_CONDITION_WRITE_TYPES = {"HasLinksConditionProto": "HasLinksCondition"}


def _condition_drafts(
    conditions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Read conditions in the shape a write takes, nested ones included."""
    if conditions is None:
        return None
    result = []
    for condition in _ref_value(conditions):
        condition = dict(condition)
        kind = condition.get("type")
        if kind in _CONDITION_WRITE_TYPES:
            condition["type"] = _CONDITION_WRITE_TYPES[kind]
        if isinstance(condition.get("conditions"), list):
            condition["conditions"] = _condition_drafts(condition["conditions"])
        result.append(condition)
    return result


def _ref_value(value: Any) -> Any:
    """A read's reference objects (`{"self": ..., "id": ..., "key": ...}`) as
    the key or id a write takes, recursively."""
    if isinstance(value, dict):
        if "self" in value:
            return value.get("key") or value.get("id")
        return {k: _ref_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_ref_value(v) for v in value]
    return value


def _localized(ru: str | None, en: str | None) -> LocalizedText | None:
    if ru is None and en is None:
        return None
    return LocalizedText(ru=ru or en or "", en=en or ru or "")


def _screen_draft(ru: Screen, en: Screen) -> ScreenDraft | None:
    # A screen with no fields (there are such, e.g. screen 3) asks for nothing:
    # writing it back as no screen keeps the transition as it behaves.
    if not ru.elements:
        return None
    return ScreenDraft(
        title=_localized(ru.title, en.title),
        elements=[
            ScreenElementDraft(field=str(e.field.id), required=e.required)
            for e in ru.elements
        ],
    )


def _action_draft(
    ru: WorkflowAction,
    en: WorkflowAction | None,
    screens: dict[int, ScreenDraft | None],
) -> WorkflowActionDraft:
    return WorkflowActionDraft(
        id=ru.id,
        name=_localized(ru.name, en.name if en else None)
        or LocalizedText(ru=ru.id, en=ru.id),
        target=(ru.target.key if ru.target else None) or "",
        description=_localized(ru.description, en.description if en else None),
        screen=screens[int(ru.screen.id)]
        if ru.screen and ru.screen.id is not None
        else None,
        post_functions=_ref_value(ru.post_functions),
        conditions=_condition_drafts(ru.conditions),
        action_coords=ru.action_coords,
    )
