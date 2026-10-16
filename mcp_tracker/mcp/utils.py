import datetime
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypeVar, get_args

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import Context
from pydantic import BaseModel
from starlette.requests import Request

from mcp_tracker.tracker.proto.common import YandexAuth

T = TypeVar("T", bound=BaseModel)


def get_yandex_auth(ctx: Context[Any, Request]) -> YandexAuth:
    access_token = get_access_token()
    token = access_token.token if access_token else None

    # Passthrough mode: when MCP OAuth is disabled (no access_token from MCP auth
    # middleware), read the Yandex OAuth token directly from the Authorization
    # header. This enables use behind a reverse proxy that injects per-user
    # tokens (e.g. a gateway that resolves user identity and fetches their
    # stored OAuth token from a secret store).
    if token is None and ctx.request_context.request is not None:
        auth_header = ctx.request_context.request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip() or None

    auth = YandexAuth(token=token)

    if ctx.request_context.request is not None:
        cloud_org_id = ctx.request_context.request.query_params.get("cloudOrgId")
        org_id = ctx.request_context.request.query_params.get("orgId")

        if cloud_org_id:
            cloud_org_id = cloud_org_id.strip()
            auth.cloud_org_id = cloud_org_id or None

        if org_id:
            org_id = org_id.strip()
            auth.org_id = org_id or None

    return auth


def set_non_needed_fields_null(data: Iterable[T], needed_fields: set[str]) -> None:
    for item in data:
        model_fields = type(item).model_fields
        extra = item.__pydantic_extra__
        # `model_fields_set` is mutated below, so iterate over a snapshot.
        for field in tuple(item.model_fields_set):
            if field in needed_fields:
                continue

            if extra is not None and field in extra:
                # Fields the API returned that the model does not declare
                # (`self`, `id`, `queue`, `boards`, the queue's own
                # `<queue-id>--<key>` fields) live in `__pydantic_extra__`,
                # which carries no `exclude_if=none_excluder`. Nulling one
                # leaves it in the response as an explicit `null`, so dropping
                # it is the only way to honour the field selection.
                del extra[field]
                item.__pydantic_fields_set__.discard(field)
                continue

            field_info = model_fields.get(field)
            # Skip fields whose declared type doesn't allow None (e.g. required
            # `id: int`) - nulling them would produce a response that violates
            # the tool's own output schema.
            if field_info is not None and type(None) not in get_args(
                field_info.annotation
            ):
                continue
            setattr(item, field, None)


# Characters no file name may contain on Windows, which also covers the POSIX
# separator, plus the control characters.
_UNSAFE_FILE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_FILE_NAME_LENGTH = 150
_MAX_KEPT_SUFFIX_LENGTH = 16


def safe_file_name(name: str) -> str:
    """`name` as one file name that is valid on Windows and POSIX alike.

    Attachment names are free text typed by whoever attached the file, so they
    can hold separators, `..`, characters Windows refuses and any length. Each
    unsafe character becomes `_`; a long name keeps its extension, so the file
    still opens with the right program.
    """
    cleaned = _UNSAFE_FILE_NAME_CHARS.sub("_", name).strip().rstrip(". ")
    if not cleaned:
        return "_"
    if len(cleaned) > _MAX_FILE_NAME_LENGTH:
        suffix = Path(cleaned).suffix
        if len(suffix) > _MAX_KEPT_SUFFIX_LENGTH:
            suffix = ""
        stem = cleaned[: _MAX_FILE_NAME_LENGTH - len(suffix)].rstrip(". ")
        cleaned = f"{stem}{suffix}"
    return cleaned


def local_day_start(day: datetime.date) -> datetime.datetime:
    """Midnight at the start of `day` in the server's local time zone.

    The server runs on the user's own machine (the tools that take dates are
    stdio-local in practice), so "a day" is the user's day, not a UTC one.
    """
    return datetime.datetime.combine(day, datetime.time()).astimezone()


def local_day_end(day: datetime.date) -> datetime.datetime:
    """Midnight at the end of `day`, local time - an inclusive day as a bound."""
    return local_day_start(day + datetime.timedelta(days=1))
