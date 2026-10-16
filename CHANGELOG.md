# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Features

- **`issue_add_attachment`** - attach a file from the machine the server runs on to an issue; attachments could only be listed ([aikts#34](https://github.com/aikts/yandex-tracker-mcp/pull/34))
  - Opt-in via `TRACKER_FILE_UPLOAD_ENABLED` (default `false`); the server refuses to start with it on a network transport or with `OAUTH_ENABLED`
  - File transfers have their own time budget, `TRACKER_ATTACHMENT_TIMEOUT` (default 300 seconds), instead of `TRACKER_API_TIMEOUT`
- **Files in comments** - `attachment_create` uploads a local file as a temporary attachment, and `issue_add_comment` attaches it with the new `attachment_ids`; comments now list their `attachments`. Gated by `TRACKER_FILE_UPLOAD_ENABLED` like `issue_add_attachment`
- **`issue_download_attachment`** - save an issue attachment to the machine the server runs on and get its local path, so an agent can open screenshots and documents attached to an issue ([aikts#33](https://github.com/aikts/yandex-tracker-mcp/pull/33))
  - Opt-in via `TRACKER_ATTACHMENT_DOWNLOAD_ENABLED` (default `false`), local servers only like the upload flag; available in read-only mode
  - Saved under `TRACKER_ATTACHMENTS_DIR` (default: a folder in the system temp directory); attachments over `TRACKER_MAX_ATTACHMENT_BYTES` (default 50 MiB) are refused
- **`worklogs_find`** - the time one user logged across all issues over a period, by the day of the work or the day it was entered; time logged in advance can be missed, since Tracker filters by the entry date ([aikts#14](https://github.com/aikts/yandex-tracker-mcp/pull/14))
- **`users_get_absences`** - vacations, sick leave and other absences of up to 100 users over a period; needs organization administrator rights
- **`issue_get_comment`** - one comment by its id, with its attached files
- **`issue_delete_attachment`** - delete a file attached to an issue
- **`queue_get_triggers`** - the automation triggers of a queue with their conditions and actions; webhook credentials are left out
- **`queue_update_version`, `queue_delete_version`** - change or delete a queue version; versions could only be listed and created
- **Links to other applications** - `issue_get_remote_links`, `issue_add_remote_link` and `issue_delete_remote_link`, with `applications_get_all` for the applications an issue can be linked to
- **Sprint management** - `board_create_sprint`, `board_update_sprint`, `board_start_sprint`, `board_archive_sprint` and `board_delete_sprint`; not covered by the queue restrictions, since a board belongs to no queue
- **Bulk changes** - `issues_bulk_update`, `issues_bulk_transition` and `issues_bulk_move` for up to 10 000 issues, with `issues_get_bulk_change` for the outcome
  - Opt-in via `TRACKER_BULK_ENABLED` (default `false`); every issue is checked against the queue restrictions, and the user confirms the change where the client supports elicitation
- **The queue setting 'AI tools access' is honoured** - issues of a queue that forbids AI tools come back as their key and `restricted`, as from Tracker's own MCP server; writes still work, and `TRACKER_AI_ACCESS_IGNORED_QUEUES` lists the queues to read regardless

### Bug Fixes

- **Issues with a text `version`** - an issue whose `version` came back as a string such as `MVP-0` failed validation, and with it every listing that contained it ([aikts#49](https://github.com/aikts/yandex-tracker-mcp/pull/49))
- **Rate limiting** - a call Tracker refused with 429 Too Many Requests failed outright, which a few parallel tool calls were enough to trigger; it is now sent again after the wait Tracker asks for, file uploads excepted

## [0.10.0] - 2026-10-15

### Features

- **Yandex Tracker MCP server** - queues, issues, comments, worklogs, links, checklists, attachments, change history, transitions, fields, templates, boards and sprints, queue components, users, and opt-in projects, portfolios and goals
- **Access controls** - read-only mode, a queue allow-list and per-queue read-only queues

### Documentation

- **Installation from this repository** - `uvx --from git+...`, a Docker image built from the repository, or a locally packed `.mcpb`

### Internal

- **Releases are not published** to PyPI, ghcr.io or the MCP registry; CI runs the tests only
