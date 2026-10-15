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

## [0.10.0] - 2026-10-15

### Features

- **Yandex Tracker MCP server** - queues, issues, comments, worklogs, links, checklists, attachments, change history, transitions, fields, templates, boards and sprints, queue components, users, and opt-in projects, portfolios and goals
- **Access controls** - read-only mode, a queue allow-list and per-queue read-only queues

### Documentation

- **Installation from this repository** - `uvx --from git+...`, a Docker image built from the repository, or a locally packed `.mcpb`

### Internal

- **Releases are not published** to PyPI, ghcr.io or the MCP registry; CI runs the tests only
