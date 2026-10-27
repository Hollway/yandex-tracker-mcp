# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Features

- **`issue_add_attachment`** - attach a file from the machine the server runs on to an issue; attachments could only be listed ([aikts#34](https://github.com/aikts/yandex-tracker-mcp/pull/34))
  - Opt-in via `TRACKER_FILE_UPLOAD_ENABLED` (default `false`); the server refuses to start with it on a network transport or with `OAUTH_ENABLED`
  - File transfers have their own time budget, `TRACKER_ATTACHMENT_TIMEOUT` (default 300 seconds), instead of `TRACKER_API_TIMEOUT`
- **Files in comments** - `attachment_create` uploads a local file as a temporary attachment, and `issue_add_comment` attaches it with the new `attachment_ids`; comments now list their `attachments`. Gated by `TRACKER_FILE_UPLOAD_ENABLED` like `issue_add_attachment`
- **`issue_download_attachment`** - save an issue attachment to the machine the server runs on and get its local path, so an agent can open screenshots and documents attached to an issue, or only the thumbnail of an image ([aikts#33](https://github.com/aikts/yandex-tracker-mcp/pull/33))
  - Opt-in via `TRACKER_ATTACHMENT_DOWNLOAD_ENABLED` (default `false`), local servers only like the upload flag; available in read-only mode
  - Saved under `TRACKER_ATTACHMENTS_DIR` (default: a folder in the system temp directory); attachments over `TRACKER_MAX_ATTACHMENT_BYTES` (default 50 MiB) are refused
- **`worklogs_find`** - the time one user logged across all issues over a period, by the day of the work or the day it was entered; time logged in advance can be missed, since Tracker filters by the entry date ([aikts#14](https://github.com/aikts/yandex-tracker-mcp/pull/14))
- **Absences** - `users_get_absences` reads the vacations, sick leave and other absences of up to 100 users over a period, `users_create_absences` and `users_delete_absences` record and remove them; all three need organization administrator rights
- **`issue_get_comment`** - one comment by its id, with its attached files
- **`issue_delete_checklist`** - delete the whole checklist of an issue at once
- **Reports** - `report_create` exports the issues a query matches to an xlsx, csv or xml file in Tracker, `report_get`, `reports_find` and `report_delete` read and remove reports; the file itself is downloaded in Tracker's web interface
- **Dashboards** - `dashboards_get_all` and `dashboard_get` read dashboards, `dashboard_create` and `dashboard_delete` create and remove them, and `dashboard_add_cycle_time_widget` adds a cycle time chart, the one widget the API can create
- **`issue_delete_attachment`** - delete a file attached to an issue
- **`queue_get_triggers`** - the automation triggers of a queue with their conditions and actions; webhook credentials are left out
- **`queue_update_version`, `queue_delete_version`** - change or delete a queue version; versions could only be listed and created
- **Links to other applications** - `issue_get_remote_links`, `issue_add_remote_link` and `issue_delete_remote_link`, with `applications_get_all` for the applications an issue can be linked to
- **Sprint management** - `board_create_sprint`, `board_update_sprint`, `board_start_sprint`, `board_archive_sprint` and `board_delete_sprint`; not covered by the queue restrictions, since a board belongs to no queue
- **Bulk changes** - `issues_bulk_update`, `issues_bulk_transition` and `issues_bulk_move` for up to 10 000 issues, with `issues_get_bulk_change` for the outcome
  - Opt-in via `TRACKER_BULK_ENABLED` (default `false`); every issue is checked against the queue restrictions, and the user confirms the change where the client supports elicitation
- **Workflows** - `workflows_get_all`, `workflow_get`, `queue_get_workflows` and `screen_get` read workflows with their statuses, transitions (with their conditions and post-functions) and transition screens; `workflow_create`, `workflow_delete`, `workflow_add_action`, `workflow_update_action`, `workflow_delete_action`, `workflow_add_status`, `workflow_delete_status`, `workflow_update_status` and `workflow_update` change them; `status_create`, `resolution_create`, `issue_type_create` and `priority_create` add to the organization's statuses, resolutions, issue types and priorities, and their `*_update` counterparts change them
  - The write tools are opt-in via `TRACKER_WORKFLOWS_WRITE_ENABLED` (default `false`): a change applies to every queue sharing the workflow, and each write re-creates the transition screens it touches, leaving the old ones behind
- **Queue automation and administration** - read, create and change queue triggers (`queue_get_trigger`, `queue_create_trigger`, `queue_update_trigger`, `queue_get_trigger_logs`), autoactions (`queue_get_autoactions`, `queue_get_autoaction`, `queue_create_autoaction`, `queue_get_autoaction_logs`) and macros (`queue_get_macros`, `queue_get_macro`, `queue_create_macro`, `queue_update_macro`, `queue_delete_macro`); create, delete and restore queues (`queue_create`, `queue_delete`, `queue_restore`) and set the workflow of an issue type or remove the type (`queue_set_issue_type_workflow`, `queue_remove_issue_type`)
- **Issue fields** - `field_get` and `fields_get_categories` read a field of the organization and the field categories; `field_create`, `field_update`, `field_create_category` and `field_update_category` change them, gated by `TRACKER_WORKFLOWS_WRITE_ENABLED` like the status catalogue
- **Local fields and tags of a queue** - `queue_get_local_field`, `queue_create_local_field` and `queue_update_local_field` read and change the fields only one queue's issues have; `queue_delete_tag` removes a tag from a queue
- **Queue access** - `queue_get_permissions`, `queue_get_user_permissions` and `queue_get_group_permissions` show who may do what in a queue, `component_get_user_permissions` and `component_get_group_permissions` the same for a component, and `groups_get_all` lists the user groups; `queue_update_permissions` grants and revokes permissions, confirmed by the user where the client can ask
- **The queue setting 'AI tools access' is honoured** - issues of a queue that forbids AI tools come back as their key and `restricted`, as from Tracker's own MCP server; writes still work, and `TRACKER_AI_ACCESS_IGNORED_QUEUES` lists the queues to read regardless
- **`issue_move` confirms its options through the SDK's multi-round-trip elicitation** — works on clients speaking the 2026-07-28 protocol revision and on 2025-era clients alike; a client that cannot be asked (no form elicitation, or a 2025-era client over streamable-http, which has no channel for the question) gets the values passed to the tool

### Bug Fixes

- **Issues with a text `version`** - an issue whose `version` came back as a string such as `MVP-0` failed validation, and with it every listing that contained it ([aikts#49](https://github.com/aikts/yandex-tracker-mcp/pull/49))
- Over streamable-http the Tracker client and its HTTP session are created once per process; they were created once per request
- **Rate limiting** - a call Tracker refused with 429 Too Many Requests failed outright, which a few parallel tool calls were enough to trigger; it is now sent again after the wait Tracker asks for, file uploads excepted
- **Queue restrictions and 'AI tools access' by the issue's real queue** - an internal issue id or the old key of a moved issue could read a queue that forbids AI tools, or, under `TRACKER_LIMIT_QUEUES` / `TRACKER_READ_ONLY_QUEUES`, one outside the restrictions; a failure reading the queue setting no longer counts as permission, and issue links follow the setting too
  - Under a queue restriction, pass issue keys: an internal id is refused, since it names no queue to check
- **Bulk change report** - `issues_get_bulk_change` no longer lists issues from queues outside `TRACKER_LIMIT_QUEUES`
- **Sprint writes right after a change** - Tracker sometimes refuses a sprint update, start or archive for a moment even with the current version, which reached the agent as an editing conflict; without an explicit `version` the write is now retried on a fresh read

### Internal

- **`mcp` 2.1** — the server speaks the 2026-07-28 protocol revision and still serves 2025-era clients; tool errors subclass `ToolError` so their text keeps reaching the model
  - `tracker-mcp://configuration` is a resource template (`tracker-mcp://configuration{?cloudOrgId,orgId}`) and is listed under `resources/templates/list` rather than `resources/list`; the plain URI still reads

## [0.10.0] - 2026-10-15

### Features

- **Yandex Tracker MCP server** - queues, issues, comments, worklogs, links, checklists, attachments, change history, transitions, fields, templates, boards and sprints, queue components, users, and opt-in projects, portfolios and goals
- **Access controls** - read-only mode, a queue allow-list and per-queue read-only queues

### Documentation

- **Installation from this repository** - `uvx --from git+...`, a Docker image built from the repository, or a locally packed `.mcpb`

### Internal

- **Releases are not published** to PyPI, ghcr.io or the MCP registry; CI runs the tests only
