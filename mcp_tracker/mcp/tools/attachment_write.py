"""Temporary attachment tools (registered with TRACKER_FILE_UPLOAD_ENABLED on a
writable server)."""

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.tools._files import (
    UploadFilenameParam,
    UploadFilePathParam,
    read_upload_file,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.issues import IssueAttachment


def register_attachment_file_upload_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register the tools that upload a local file as a temporary attachment.

    A temporary attachment belongs to no issue and so to no queue: the queue
    checks apply where it is attached, in `issue_add_comment`.
    """

    @mcp.tool(
        title="Upload Temporary Attachment",
        description="Upload a file from the machine the server runs on as a "
        "temporary attachment and return its `id`, to attach the file to a comment "
        "via `attachment_ids` of issue_add_comment (requires "
        "TRACKER_FILE_UPLOAD_ENABLED).",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def attachment_create(
        ctx: Context[AppContext],
        file_path: UploadFilePathParam,
        filename: UploadFilenameParam = None,
    ) -> IssueAttachment:
        content, path = await read_upload_file(file_path)

        return await ctx.request_context.lifespan_context.issues.attachment_create(
            content=content,
            filename=filename or path.name,
            auth=get_yandex_auth(ctx),
        )
