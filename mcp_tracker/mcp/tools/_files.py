"""Reading a local file for the tools that upload one (`TRACKER_FILE_UPLOAD_ENABLED`)."""

import asyncio
from pathlib import Path
from typing import Annotated

from pydantic import Field

from mcp_tracker.mcp.errors import TrackerError

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
