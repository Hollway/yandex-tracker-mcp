import json
from collections.abc import Sequence
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

MAX_ERROR_BODY_LENGTH = 1000


class YandexTrackerError(ToolError):
    """Base class for errors raised by the Yandex Tracker client.

    Subclasses `ToolError` so the message reaches the model: the SDK forwards a
    `ToolError`'s text in the tool result and hides the text of any other
    exception behind a bare `Error executing tool <name>`.
    """

    pass


class IssueNotFound(YandexTrackerError):
    def __init__(self, issue_id: str):
        super().__init__(f"Issue with ID '{issue_id}' not found.")
        self.issue_id = issue_id


class QueueNotFound(YandexTrackerError):
    def __init__(self, queue_id: str):
        super().__init__(f"Queue with ID '{queue_id}' not found.")
        self.queue_id = queue_id


class BoardNotFound(YandexTrackerError):
    def __init__(self, board_id: int):
        super().__init__(f"Board with ID '{board_id}' not found.")
        self.board_id = board_id


class ComponentNotFound(YandexTrackerError):
    def __init__(self, component_id: int):
        super().__init__(f"Component with ID '{component_id}' not found.")
        self.component_id = component_id


class IssueTemplateNotFound(YandexTrackerError):
    def __init__(self, template_id: str):
        super().__init__(f"Issue template with ID '{template_id}' not found.")
        self.template_id = template_id


class CommentTemplateNotFound(YandexTrackerError):
    def __init__(self, template_id: str):
        super().__init__(f"Comment template with ID '{template_id}' not found.")
        self.template_id = template_id


class TemplateVersionConflict(YandexTrackerError):
    """Raised when a template update or delete is rejected (409/412) over its
    `version`."""

    def __init__(self, kind: str, template_id: str, version: int):
        super().__init__(
            f"Editing conflict for {kind} template '{template_id}' with version "
            f"{version}: the template was changed since that version was read. "
            f"Re-read it with {kind}_template_get and retry, or omit `version` to "
            f"act on the current one."
        )
        self.template_id = template_id
        self.version = version


class TemplateEmptyUpdate(YandexTrackerError):
    """Raised for a template update that would change nothing - Tracker answers
    an empty PATCH body with 200 and leaves the template untouched."""

    def __init__(self, fields: str):
        super().__init__(
            f"A template update must change something: pass at least one of {fields}."
        )


class IssueVersionConflict(YandexTrackerError):
    """Raised when an update is rejected because `version` is not current.

    Tracker bumps an issue's version on every change, including changes made by
    queue triggers and automation right after the issue is created, so a version
    read moments ago can already be stale.
    """

    def __init__(self, issue_id: str, version: int | None = None):
        expected = f" with version {version}" if version is not None else ""
        super().__init__(
            f"Editing conflict for issue '{issue_id}'{expected}: the issue was changed "
            f"in the meantime (queue triggers and automation change it too, so the "
            f"version returned by issue_create is often already outdated). "
            f"Re-read the issue with issue_get to get its current version and retry, "
            f"or omit the version parameter to update the latest version unconditionally."
        )
        self.issue_id = issue_id
        self.version = version


class ComponentVersionConflict(YandexTrackerError):
    """Raised when a component update is rejected (412) because `version` is stale."""

    def __init__(self, component_id: int, version: int):
        super().__init__(
            f"Editing conflict for component '{component_id}' with version "
            f"{version}: the component was changed since that version was read. "
            f"Re-read it with component_get (or queue_get_components) and retry, "
            f"or omit the version parameter of component_update to update the "
            f"current one."
        )
        self.component_id = component_id
        self.version = version


class TrackerAPITimeout(YandexTrackerError):
    """A request to the Yandex Tracker API ran out of its time budget.

    Worth a class of its own only because the alternative is unreadable:
    `str(TimeoutError())` is the empty string, so a timeout reaches the caller
    as `Error executing tool <name>:` with nothing after the colon and no hint
    that time, rather than the request, was the problem.
    """

    def __init__(
        self,
        *,
        method: str,
        url: str,
        timeout: float,
        setting: str = "TRACKER_API_TIMEOUT",
    ):
        self.method = method
        self.url = url
        self.timeout = timeout
        # The environment variable that sets this request's budget - a file upload
        # has its own, and naming the wrong one sends the caller to a knob that
        # changes nothing.
        self.setting = setting
        super().__init__(
            f"Yandex Tracker API request {method} {url} timed out after "
            f"{timeout:g}s. Raise {setting} if this endpoint is "
            f"slow for this organization."
        )


class TrackerAPIConnectionError(YandexTrackerError):
    """A request to the Yandex Tracker API never got an answer.

    DNS, a refused connection, a TLS failure or a connection dropped mid-body
    all surface from aiohttp as a `ClientError`, which is not a `ToolError`:
    left untranslated, the model would see a bare `Error executing tool <name>`
    with no hint of which host was unreachable or why.
    """

    def __init__(self, *, method: str, url: str, cause: Exception):
        self.method = method
        self.url = url
        self.cause = cause
        # Some aiohttp errors stringify to nothing; the class name is then the
        # only clue left.
        reason = str(cause) or type(cause).__name__
        super().__init__(f"Yandex Tracker API request {method} {url} failed: {reason}")


class TrackerAuthConfigError(YandexTrackerError):
    """The request cannot be authenticated or attributed to one organization.

    Raised per request rather than at startup because the token and the
    organization can come from the HTTP request itself (OAuth passthrough,
    `?orgId=` / `?cloudOrgId=`), so a bad combination is the caller's to fix.
    """


class NoDoneTransition(YandexTrackerError):
    """`issue_close` found no transition into a status of type `done`.

    The ids of the transitions that *are* available are what the caller needs
    to fall back on `issue_execute_transition`, so they are part of the message.
    """

    def __init__(self, issue_id: str, transition_ids: list[str]):
        super().__init__(
            f"No transition to a 'done' status found for issue {issue_id}. "
            f"Available transitions: {transition_ids}."
        )
        self.issue_id = issue_id
        self.transition_ids = transition_ids


class TrackerAPIError(YandexTrackerError):
    """A non-2xx response from the Yandex Tracker API.

    Tracker explains *why* a request was rejected in the response body
    (`errorMessages` / `errors`), which is the only way to tell, for example,
    which field of an issue_create call was invalid. The body is therefore part
    of the raised error instead of being dropped by `raise_for_status()`.
    """

    def __init__(self, *, status: int, method: str, url: str, body: str):
        self.status = status
        self.method = method
        self.url = url
        self.body = body
        self.error_messages, self.errors = _parse_error_body(body)

        details: list[str] = list(self.error_messages)
        details.extend(f"{field}: {message}" for field, message in self.errors.items())
        if not details and body:
            details.append(body[:MAX_ERROR_BODY_LENGTH])

        message = f"Yandex Tracker API error {status} on {method} {url}"
        if details:
            message += ": " + "; ".join(details)
        super().__init__(message)


class TrackerRateLimited(TrackerAPIError):
    """Tracker kept answering 429 Too Many Requests after the retries ran out.

    A subclass so that whoever catches `TrackerAPIError` by status still does,
    with a message that says what to do: the request was refused before it ran,
    so it is safe to send again once the limit clears, and calls made in parallel
    count against the same limit.
    """

    def __init__(
        self,
        *,
        method: str,
        url: str,
        body: str,
        retries: int,
        retry_after: float | None,
    ):
        super().__init__(status=429, method=method, url=url, body=body)
        self.retries = retries
        self.retry_after = retry_after
        wait = (
            f"wait {retry_after:g}s, as Tracker asks,"
            if retry_after is not None
            else "wait a few seconds"
        )
        refused = f", still refused after {retries} retries" if retries else ""
        # Replaces the generic message `TrackerAPIError` built from the body.
        self.args = (
            f"Yandex Tracker API rate limit (429) on {method} {url}{refused}. "
            f"Nothing was changed: {wait} and send it again, one call at a time - "
            f"parallel calls share the same limit.",
        )


def _parse_error_body(body: str) -> tuple[list[str], dict[str, str]]:
    """Extract Tracker's `errorMessages` / `errors` from an error response body."""
    try:
        parsed: Any = json.loads(body)
    except ValueError:
        return [], {}

    if not isinstance(parsed, dict):
        return [], {}

    raw_messages = parsed.get("errorMessages")
    messages = [str(m) for m in raw_messages] if isinstance(raw_messages, list) else []

    raw_errors = parsed.get("errors")
    errors = (
        {str(k): str(v) for k, v in raw_errors.items()}
        if isinstance(raw_errors, dict)
        else {}
    )

    return messages, errors


class ChecklistItemNotFound(YandexTrackerError):
    """Raised when a checklist edit names an id that isn't in the current
    checklist of the issue or entity.

    The edit endpoints can only change items that already exist - they have no
    way to add one - so an unknown id here means the caller wanted an
    *_add_checklist_item(s) tool instead.

    `ambiguous` is set where the id came back as a 404 from an item-scoped path
    (`.../checklistItems/{itemId}`), which Tracker answers the same way for an
    unknown issue as for an unknown item: the message then names both causes
    instead of asserting the one it cannot tell apart. Where the checklist was
    read first, the entity is known to exist and the message stays specific.
    """

    def __init__(
        self, entity_id: str, checklist_item_id: str, *, ambiguous: bool = False
    ):
        if ambiguous:
            message = (
                f"Checklist item '{checklist_item_id}' was not found on "
                f"'{entity_id}'. Tracker answers the same 404 when the issue "
                f"itself does not exist, so check both the id of the issue and "
                f"the id of the item - issue_get_checklist lists the current ones."
            )
        else:
            message = (
                f"Checklist item '{checklist_item_id}' was not found on "
                f"'{entity_id}'. Only items that already exist can be edited - "
                f"use an *_add_checklist_item(s) tool to add a new one."
            )
        super().__init__(message)
        self.entity_id = entity_id
        self.checklist_item_id = checklist_item_id
        self.ambiguous = ambiguous


class ChecklistBatchPartiallyAdded(YandexTrackerError):
    """Raised when a batch of checklist items fails partway through.

    Tracker takes one item per request, so a batch is several requests and the
    ones that already succeeded are not rolled back. A bare error would leave
    the caller unable to tell how much of the batch landed, and a naive retry
    would duplicate those items.
    """

    def __init__(self, issue_id: str, added: int, total: int, cause: Exception):
        super().__init__(
            f"Added {added} of {total} checklist items to '{issue_id}' before the "
            f"request failed: {cause}. The items already added were kept - read the "
            f"checklist with issue_get_checklist and retry only what is missing, "
            f"or the successful ones will be duplicated."
        )
        self.issue_id = issue_id
        self.added = added
        self.total = total
        self.cause = cause


class ChecklistItemEmptyUpdate(YandexTrackerError):
    """Raised for a checklist item update that would change nothing.

    Verified against the live API: Tracker answers an empty PATCH body with 200
    and leaves the item untouched, so such a call is a silent no-op round-trip.
    It is refused here rather than reported back as a success.
    """

    def __init__(self) -> None:
        super().__init__(
            "A checklist item update must change something: pass at least one of "
            "`text`, `checked`, `assignee`, `deadline`, `clear_assignee` or "
            "`clear_deadline`. An omitted field keeps its current value; use the "
            "`clear_*` flags to remove one."
        )


class ComponentEmptyUpdate(YandexTrackerError):
    """Raised for a component update that would change nothing - Tracker answers
    an empty PATCH body with 200 and leaves the component untouched."""

    def __init__(self) -> None:
        super().__init__(
            "A component update must change something: pass at least one of "
            "`name`, `description`, `lead`, `assign_auto` or `clear_lead`. An "
            "omitted field keeps its current value; `clear_lead` removes the lead."
        )


class FieldClearConflict(YandexTrackerError):
    """Raised when an update both sets and clears the same field."""

    def __init__(self, field: str) -> None:
        super().__init__(
            f"`{field}` and `clear_{field}` cannot be passed together: pass "
            f"`{field}` to set a new value, or `clear_{field}` to remove the "
            f"current one."
        )


class EntityLinksOnlyUpdate(YandexTrackerError):
    """Raised for an entity update that would only change links.

    Verified against the live API: Tracker answers 200 but ignores `links`
    unless the same request also changes the entity (a field value or a
    comment), so such a call would silently do nothing.
    """

    def __init__(self) -> None:
        super().__init__(
            "Yandex Tracker ignores `links` when the update changes nothing else: "
            "pass at least one field to change, or a `comment`, in the same call. "
            "Note that links are added, not replaced - sending a link that already "
            "exists fails; *_get_links lists them and *_delete_link removes one."
        )


class AttachmentNotFound(YandexTrackerError):
    """Raised for a 404 from an attachment-scoped path.

    Not `IssueNotFound`: Tracker answers an unknown issue and an unknown
    attachment alike there, and the usual cause is the attachment - an id from
    an older `issue_get_attachments` call or from another issue - so the message
    names both.
    """

    def __init__(self, issue_id: str, attachment_id: str):
        super().__init__(
            f"Attachment '{attachment_id}' was not found on issue '{issue_id}', or "
            f"the issue itself does not exist - issue_get_attachments lists the "
            f"current attachments of an issue."
        )
        self.issue_id = issue_id
        self.attachment_id = attachment_id


class AttachmentThumbnailNotFound(YandexTrackerError):
    """Raised for a 404 from `v3/issues/{id}/thumbnails/{attachmentId}`.

    The download tool reads the attachment first, so by then the attachment
    exists and the 404 means Tracker made no thumbnail - it makes them for images
    only ("Миниатюра не существует.", verified 2026-10-26).
    """

    def __init__(self, issue_id: str, attachment_id: str):
        super().__init__(
            f"Attachment '{attachment_id}' of issue '{issue_id}' has no thumbnail: "
            f"Yandex Tracker makes them for images only. Download the file itself."
        )
        self.issue_id = issue_id
        self.attachment_id = attachment_id


class DashboardNotFound(YandexTrackerError):
    """Raised for a 404 from a dashboard-scoped path, `v3/dashboards/{id}...`."""

    def __init__(self, dashboard_id: int):
        super().__init__(
            f"Dashboard {dashboard_id} was not found - dashboards_get_all lists the "
            f"organization's dashboards."
        )
        self.dashboard_id = dashboard_id


class AttachmentTooLarge(YandexTrackerError):
    """Raised for a download over `TRACKER_MAX_ATTACHMENT_BYTES`."""

    def __init__(self, attachment_id: str, size: int, limit: int):
        super().__init__(
            f"Attachment '{attachment_id}' is {size} bytes, over the limit of "
            f"{limit} bytes for one download. Raise TRACKER_MAX_ATTACHMENT_BYTES to "
            f"download it."
        )
        self.attachment_id = attachment_id
        self.size = size
        self.limit = limit


class WorklogSearchTooLarge(YandexTrackerError):
    """Raised when a worklog search keeps paging past the safety limit."""

    def __init__(self, pages: int):
        super().__init__(
            f"The worklog search returned more than {pages} pages. Narrow the period "
            f"or search for one author at a time."
        )
        self.pages = pages


class AbsencesForbidden(YandexTrackerError):
    """Raised for a 403 from the absence endpoints, which only admins may call."""

    def __init__(self, action: str = "search") -> None:
        super().__init__(
            f"Yandex Tracker refused to {action} absences: it needs the rights of "
            "an organization administrator, which the token's owner does not have."
        )
        self.action = action


class CommentNotFound(YandexTrackerError):
    """Raised for a 404 from a comment-scoped path, which Tracker answers alike
    for an unknown issue and an unknown comment."""

    def __init__(self, issue_id: str, comment_id: int | str):
        super().__init__(
            f"Comment '{comment_id}' was not found on issue '{issue_id}', or the "
            f"issue itself does not exist - issue_get_comments lists the current "
            f"comments of an issue."
        )
        self.issue_id = issue_id
        self.comment_id = comment_id


class VersionNotFound(YandexTrackerError):
    def __init__(self, version_id: int):
        super().__init__(
            f"Queue version with ID '{version_id}' not found - queue_get_versions "
            f"lists the versions of a queue."
        )
        self.version_id = version_id


class VersionEmptyUpdate(YandexTrackerError):
    """Raised for a version update that would change nothing."""

    def __init__(self) -> None:
        super().__init__(
            "A version update must change something: pass at least one of `name`, "
            "`description`, `start_date` or `due_date`."
        )


class BoardVersionConflict(YandexTrackerError):
    """Raised when Tracker refuses a board or column write over the board's `version`.

    A column has no version of its own: every change to a column bumps the
    board's, so a version read before a column change is stale after it.
    """

    def __init__(self, board_id: int, version: int):
        super().__init__(
            f"Editing conflict for board '{board_id}' with version {version}: the "
            f"board or one of its columns was changed since that version was read. "
            f"Re-read it with board_get, or omit `version` to write to the current "
            f"board."
        )
        self.board_id = board_id
        self.version = version


class BoardEmptyUpdate(YandexTrackerError):
    def __init__(self) -> None:
        super().__init__(
            "A board update must change something: pass at least one of `name`, "
            "`columns` or `sprints`."
        )


class BoardColumnEmptyUpdate(YandexTrackerError):
    def __init__(self) -> None:
        super().__init__(
            "A column update must change something: pass at least one of `name`, "
            "`statuses` or `limit`."
        )


class SprintNotFound(YandexTrackerError):
    def __init__(self, sprint_id: int):
        super().__init__(
            f"Sprint with ID '{sprint_id}' not found - board_get_sprints lists the "
            f"sprints of a board."
        )
        self.sprint_id = sprint_id


class SprintVersionConflict(YandexTrackerError):
    """Raised when Tracker refuses a sprint write over its `version`.

    Tracker answers a stale version and a passing failure right after a change
    with the same 412 and the same text, so the message names both.
    """

    def __init__(self, sprint_id: int, version: int):
        super().__init__(
            f"Editing conflict for sprint '{sprint_id}' with version {version}: "
            f"either the sprint was changed since that version was read, or "
            f"Tracker refused the write for a moment, as it does right after a "
            f"sprint changes. Retry without `version` to act on the current one, "
            f"which is retried for you, or re-read it with board_get_sprints."
        )
        self.sprint_id = sprint_id
        self.version = version


class SprintEmptyUpdate(YandexTrackerError):
    def __init__(self) -> None:
        super().__init__(
            "A sprint update must change something: pass at least one of `name`, "
            "`start_date`, `end_date` or `status`."
        )


class BulkChangeNotFound(YandexTrackerError):
    def __init__(self, bulk_change_id: str):
        super().__init__(
            f"Bulk change '{bulk_change_id}' not found - use the `id` an issues_bulk_* "
            f"tool returned."
        )
        self.bulk_change_id = bulk_change_id


class WorkflowNotFound(YandexTrackerError):
    def __init__(self, workflow_id: str):
        super().__init__(
            f"Workflow with ID '{workflow_id}' not found - workflows_get_all lists "
            f"the workflows, queue_get_workflows those of one queue."
        )
        self.workflow_id = workflow_id


class WorkflowVersionConflict(YandexTrackerError):
    """Raised when Tracker refuses a workflow write over its `version` (412).

    Tracker words it as a passing failure ("не удалось сохранить изменения,
    попробуйте ещё раз"), the same text it gives a stale sprint version.
    """

    def __init__(self, workflow_id: str, version: int):
        super().__init__(
            f"Editing conflict for workflow '{workflow_id}' with version {version}: "
            f"the workflow was changed since that version was read. Re-read it with "
            f"workflow_get and retry, or omit `version` to act on the current one."
        )
        self.workflow_id = workflow_id
        self.version = version


class ScreenNotFound(YandexTrackerError):
    def __init__(self, screen_id: int):
        super().__init__(
            f"Screen with ID '{screen_id}' not found - a transition's `screen.id` "
            f"in workflow_get names its screen."
        )
        self.screen_id = screen_id


class CatalogObjectNotFound(YandexTrackerError):
    """An organization-wide status, resolution, issue type or priority that
    does not exist."""

    def __init__(self, kind: str, object_id: str, listing: str):
        super().__init__(
            f"No {kind} with key or ID '{object_id}' - {listing} lists them."
        )
        self.kind = kind
        self.object_id = object_id


class CatalogVersionConflict(YandexTrackerError):
    """Raised when Tracker refuses a status, resolution, issue type or priority
    update over its `version` - documented as 409 for some and 412 for others."""

    def __init__(self, kind: str, object_id: str, version: int, listing: str):
        super().__init__(
            f"Editing conflict for {kind} '{object_id}' with version {version}: it "
            f"was changed since that version was read. Re-read it with {listing} "
            f"and retry, or omit `version` to update the current one."
        )
        self.kind = kind
        self.object_id = object_id
        self.version = version


class CatalogEmptyUpdate(YandexTrackerError):
    """Raised for a status, resolution, issue type or priority update that
    would change nothing."""

    def __init__(self, kind: str, fields: Sequence[str]):
        names = ", ".join(f"`{f}`" for f in fields)
        super().__init__(
            f"A {kind} update must change something: pass at least one of {names}."
        )


class CatalogNameEnWithoutName(YandexTrackerError):
    """Raised for an update that passes the English name alone - Tracker takes
    a name as both languages at once."""

    def __init__(self) -> None:
        super().__init__(
            "`name_en` cannot be changed alone: pass `name` (the Russian name) "
            "with it - the name is written in both languages at once."
        )


class TriggerNotFound(YandexTrackerError):
    """Raised for a 404 from a trigger-scoped path, which Tracker answers alike
    for an unknown queue and an unknown trigger."""

    def __init__(self, queue_id: str, trigger_id: int):
        super().__init__(
            f"Trigger '{trigger_id}' was not found in queue '{queue_id}', or the "
            f"queue itself does not exist - queue_get_triggers lists the triggers "
            f"of a queue."
        )
        self.queue_id = queue_id
        self.trigger_id = trigger_id


class TriggerVersionConflict(YandexTrackerError):
    """Raised when a trigger update is rejected (409/412) over its `version`."""

    def __init__(self, queue_id: str, trigger_id: int, version: int):
        super().__init__(
            f"Editing conflict for trigger '{trigger_id}' of queue '{queue_id}' with "
            f"version {version}: the trigger was changed since that version was "
            f"read. Re-read it with queue_get_trigger and retry, or omit `version` "
            f"to update the current one."
        )
        self.queue_id = queue_id
        self.trigger_id = trigger_id
        self.version = version


class TriggerEmptyUpdate(YandexTrackerError):
    def __init__(self) -> None:
        super().__init__(
            "A trigger update must change something: pass at least one of `name`, "
            "`actions`, `conditions`, `active` or `before`."
        )


class AutoactionNotFound(YandexTrackerError):
    """Raised for a 404 from an autoaction-scoped path, which Tracker answers
    alike for an unknown queue and an unknown autoaction."""

    def __init__(self, queue_id: str, autoaction_id: int):
        super().__init__(
            f"Autoaction '{autoaction_id}' was not found in queue '{queue_id}', or "
            f"the queue itself does not exist - queue_get_autoactions lists the "
            f"autoactions of a queue."
        )
        self.queue_id = queue_id
        self.autoaction_id = autoaction_id


class LocalFieldNotFound(YandexTrackerError):
    """Raised for a 404 from a local-field path, which Tracker answers alike
    for an unknown queue and an unknown field."""

    def __init__(self, queue_id: str, field_key: str):
        super().__init__(
            f"Local field '{field_key}' was not found in queue '{queue_id}', or the "
            f"queue itself does not exist - queue_get_fields lists the fields of a "
            f"queue; a local field is addressed by its `key`, not its `id`."
        )
        self.queue_id = queue_id
        self.field_key = field_key


class PermissionsEmptyUpdate(YandexTrackerError):
    """Raised for a permissions change that changes nothing - Tracker answers
    an empty one 200 and does nothing."""

    def __init__(self) -> None:
        super().__init__(
            "A permissions change must change something: pass at least one of "
            "`create`, `read`, `write`, `grant` or `deny`."
        )


class MacroNotFound(YandexTrackerError):
    """Raised for a 404 from a macro-scoped path, which Tracker answers alike
    for an unknown queue and an unknown macro."""

    def __init__(self, queue_id: str, macro_id: int):
        super().__init__(
            f"Macro '{macro_id}' was not found in queue '{queue_id}', or the queue "
            f"itself does not exist - queue_get_macros lists the macros of a queue."
        )
        self.queue_id = queue_id
        self.macro_id = macro_id


class MacroEmptyUpdate(YandexTrackerError):
    def __init__(self) -> None:
        super().__init__(
            "A macro update must change something: pass at least one of `name`, "
            "`body`, `issue_update` or `clear_body`."
        )


class FilterNotFound(YandexTrackerError):
    def __init__(self, filter_id: int):
        super().__init__(
            f"Saved filter '{filter_id}' was not found. The API has no listing of "
            f"filters: take the id from the filter's link in Tracker or from "
            f"filter_create."
        )
        self.filter_id = filter_id


class FilterConditionsConflict(YandexTrackerError):
    """Raised for a filter given both `query` and `filter` - Tracker answers 409."""

    def __init__(self) -> None:
        super().__init__(
            "A saved filter takes its conditions as either `query` or `filter`, "
            "not both."
        )


class FilterEmptyUpdate(YandexTrackerError):
    """Raised for a filter update that changes nothing - Tracker answers an
    empty one 200 and does nothing."""

    def __init__(self) -> None:
        super().__init__(
            "A filter update must change something: pass at least one of `name`, "
            "`query`, `filter`, `sorts` or `fields`."
        )


class EntityItemNotFound(YandexTrackerError):
    """Raised when a key result or metric id is not in the entity's list.

    Tracker answers a `remove` of an unknown id with 200 and changes nothing,
    and rewriting a list gives every item a new id - so the list is read first
    and an id it lacks is refused here.
    """

    def __init__(self, entity_id: str, item_id: str, *, item: str, field: str):
        super().__init__(
            f"No {item} '{item_id}' on '{entity_id}'. Ids change whenever the "
            f"list is rewritten (any update or move); read the current ones with "
            f"fields=['{field}']."
        )
        self.entity_id = entity_id
        self.item_id = item_id


class EntityItemEmptyUpdate(YandexTrackerError):
    """Raised for a key result or metric update that would change nothing."""

    def __init__(self, item: str) -> None:
        super().__init__(
            f"A {item} update must change something: pass at least one field. "
            f"An omitted field keeps its current value."
        )


class EntityPermissionsEmptyUpdate(YandexTrackerError):
    """Raised for an entity permissions change that changes nothing."""

    def __init__(self) -> None:
        super().__init__(
            "A permissions change must change something: pass at least one of "
            "`read`, `write`, `grant` or `inherit`."
        )


class EntityPermissionsInherited(YandexTrackerError):
    """Raised for a change to the permissions of an entity that inherits them.

    Verified against the live API: while an entity inherits its permissions
    from its parent, Tracker answers a change to them 200 and drops it.
    """

    def __init__(self, entity_id: str, source: str) -> None:
        super().__init__(
            f"'{entity_id}' inherits its permissions from '{source}', and Tracker ignores "
            "changes to them until it stops: pass `inherit=false` in the same call "
            "to give it permissions of its own, starting from the inherited ones."
        )
        self.entity_id = entity_id


class EntityHasNoParent(YandexTrackerError):
    """Raised for `inherit=true` on an entity that has no parent to inherit from."""

    def __init__(self, entity_id: str) -> None:
        super().__init__(
            f"'{entity_id}' has no parent to inherit permissions from: set "
            "`parent_entity` with the entity's update tool first."
        )
        self.entity_id = entity_id


class EntityPermissionsChangeWhileInheriting(YandexTrackerError):
    """Raised for `inherit=true` together with permission changes, which
    Tracker would drop: an inheriting entity takes its parent's permissions."""

    def __init__(self) -> None:
        super().__init__(
            "`inherit=true` takes the parent's permissions and Tracker ignores "
            "`read` / `write` / `grant` alongside it: pass one or the other."
        )
