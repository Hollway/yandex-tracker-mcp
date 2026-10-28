"""Getting the file for the tools that upload one: a local file
(`TRACKER_FILE_UPLOAD_ENABLED`) or one fetched by URL
(`TRACKER_ATTACHMENT_URL_PREFIXES`)."""

import asyncio
from pathlib import Path, PurePosixPath
from typing import Annotated
from urllib.parse import unquote, urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout
from pydantic import Field

from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.settings import Settings

# Tracker's documented limit for one attachment.
MAX_ATTACHMENT_SIZE = 1024 * 1024 * 1024

UploadFilePathParam = Annotated[
    str,
    Field(
        description="Absolute path to the file on the machine the server runs on; a "
        "relative one resolves against the server's working directory."
    ),
]

UploadFilenameParam = Annotated[
    str | None,
    Field(
        description="Name to store the attachment under. Defaults to the file's own "
        "name."
    ),
]


async def read_upload_file(file_path: str) -> tuple[bytes, Path]:
    """The content of the file to upload and its resolved path.

    The size is checked before the read, so a file over Tracker's limit is
    refused without being loaded into memory; the read itself runs in a thread.
    """
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise TrackerError(f"File `{path}` does not exist.")
    if not path.is_file():
        raise TrackerError(f"`{path}` is not a file; pass the path to a file.")

    size = path.stat().st_size
    if size > MAX_ATTACHMENT_SIZE:
        raise TrackerError(
            f"File `{path}` is {size / 1024 / 1024:.0f} MB, over Yandex Tracker's "
            f"{MAX_ATTACHMENT_SIZE // 1024 // 1024} MB limit for one attachment. "
            "Compress or split it, or upload it somewhere else and link to it."
        )

    try:
        content = await asyncio.to_thread(path.read_bytes)
    except OSError as exc:
        raise TrackerError(f"Could not read file `{path}`: {exc}") from exc

    return content, path


UploadFileUrlParam = Annotated[
    str,
    Field(
        description="https URL of the file, starting with one of the prefixes the "
        "server allows (TRACKER_ATTACHMENT_URL_PREFIXES); redirects are not followed."
    ),
]

UploadUrlFilenameParam = Annotated[
    str | None,
    Field(
        description="Name to store the attachment under. Defaults to the last "
        "segment of the URL's path."
    ),
]

_CHUNK = 64 * 1024


async def fetch_upload_url(settings: Settings, url: str) -> tuple[bytes, str]:
    """The content of the file at `url` and the name its path ends in.

    Only a URL under one of `TRACKER_ATTACHMENT_URL_PREFIXES` is fetched, by a
    session of its own that sends none of the Tracker credentials, without
    following redirects - a 302 would lead past the prefixes - and with
    `TRACKER_MAX_ATTACHMENT_BYTES` held against both the announced and the
    received size.
    """
    prefixes = settings.tracker_attachment_url_prefixes or []
    if not any(url.startswith(prefix) for prefix in prefixes):
        raise TrackerError(
            f"`{url}` is not under a URL prefix this server allows "
            f"({', '.join(prefixes) or 'none'}); see TRACKER_ATTACHMENT_URL_PREFIXES."
        )

    limit = settings.tracker_max_attachment_bytes
    too_big = (
        f"The file at `{url}` is over the {limit // 1024 // 1024} MB this server "
        "takes (TRACKER_MAX_ATTACHMENT_BYTES)."
    )
    timeout = ClientTimeout(total=settings.tracker_attachment_timeout)
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=False) as response:
                if 300 <= response.status < 400:
                    raise TrackerError(
                        f"`{url}` answered {response.status}, a redirect to "
                        f"`{response.headers.get('Location', '?')}`; redirects are "
                        "not followed - pass the final URL."
                    )
                if response.status != 200:
                    raise TrackerError(
                        f"`{url}` answered {response.status} {response.reason or ''}".rstrip()
                        + "."
                    )
                if (
                    response.content_length is not None
                    and response.content_length > limit
                ):
                    raise TrackerError(too_big)
                content = bytearray()
                async for chunk in response.content.iter_chunked(_CHUNK):
                    content.extend(chunk)
                    if len(content) > limit:
                        raise TrackerError(too_big)
    except TimeoutError as exc:
        raise TrackerError(
            f"Fetching `{url}` took over {settings.tracker_attachment_timeout:g} "
            "seconds (TRACKER_ATTACHMENT_TIMEOUT)."
        ) from exc
    except ClientError as exc:
        raise TrackerError(f"Could not fetch `{url}`: {exc}") from exc

    name = unquote(PurePosixPath(urlsplit(url).path).name)
    return bytes(content), name or "attachment"
