"""Issue and comment template write MCP tools.

None of the endpoints is in the public API reference; they were verified on the
live API on 2026-10-27 (see AGENTS.md, *Templates*).
"""

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.mcp.params import (
    CommentTemplateID,
    CommentTemplateMaillistParam,
    CommentTemplateSummoneesParam,
    CommentTemplateTextParam,
    IssueTemplateChecklistParam,
    IssueTemplateFieldsParam,
    IssueTemplateID,
    TemplateNameParam,
    TemplateQueueParam,
    TemplateVersionParam,
)
from mcp_tracker.mcp.tools._access import check_queue_access
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import TemplateEmptyUpdate
from mcp_tracker.tracker.proto.types.templates import (
    BaseTemplate,
    CommentTemplate,
    IssueTemplate,
)


def _check_template_write(settings: Settings, template: BaseTemplate) -> None:
    """A template of a queue is a write to that queue; one bound to no queue is
    the user's own and touches none."""
    if template.queue is not None and template.queue.key is not None:
        check_queue_access(settings, template.queue.key, write=True)


def _current_version(template: BaseTemplate, version: int | None) -> int:
    if version is not None:
        return version
    if template.version is None:
        raise TrackerError(
            f"Template `{template.id}` came back without a `version`; pass it "
            f"explicitly."
        )
    return template.version


def register_template_write_tools(
    settings: Settings, mcp: MCPServer[AppContext]
) -> None:
    """Register the issue and comment template write tools."""

    @mcp.tool(
        title="Create Issue Template",
        description="Create an issue template ('шаблон задачи'): the field values and "
        "checklist an issue created from it starts with - issue_create takes its id "
        "as `template_id`.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_template_create(
        ctx: Context[AppContext],
        name: TemplateNameParam,
        queue: TemplateQueueParam = None,
        field_templates: IssueTemplateFieldsParam = None,
        checklist_items: IssueTemplateChecklistParam = None,
    ) -> IssueTemplate:
        if queue is not None:
            check_queue_access(settings, queue, write=True)
        return (
            await ctx.request_context.lifespan_context.templates.issue_template_create(
                name=name,
                queue=queue,
                field_templates=field_templates,
                checklist_items=checklist_items,
                auth=get_yandex_auth(ctx),
            )
        )

    @mcp.tool(
        title="Update Issue Template",
        description="Change an issue template ('шаблон задачи'). `field_templates` "
        "and `checklist_items` replace the template's whole set, so pass every value "
        "to keep - read it with issue_template_get first.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def issue_template_update(
        ctx: Context[AppContext],
        template_id: IssueTemplateID,
        name: TemplateNameParam | None = None,
        field_templates: IssueTemplateFieldsParam = None,
        checklist_items: IssueTemplateChecklistParam = None,
        version: TemplateVersionParam = None,
    ) -> IssueTemplate:
        if (name, field_templates, checklist_items) == (None,) * 3:
            raise TemplateEmptyUpdate("`name`, `field_templates` or `checklist_items`")
        templates = ctx.request_context.lifespan_context.templates
        auth = get_yandex_auth(ctx)
        current = await templates.get_issue_template(template_id, auth=auth)
        _check_template_write(settings, current)
        return await templates.issue_template_update(
            template_id,
            version=_current_version(current, version),
            name=name,
            field_templates=field_templates,
            checklist_items=checklist_items,
            auth=auth,
        )

    @mcp.tool(
        title="Delete Issue Template",
        description="Permanently delete an issue template ('шаблон задачи'); there is "
        "no undo. Issues created from it keep their values.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def issue_template_delete(
        ctx: Context[AppContext],
        template_id: IssueTemplateID,
        version: TemplateVersionParam = None,
    ) -> None:
        templates = ctx.request_context.lifespan_context.templates
        auth = get_yandex_auth(ctx)
        current = await templates.get_issue_template(template_id, auth=auth)
        _check_template_write(settings, current)
        await templates.issue_template_delete(
            template_id, version=_current_version(current, version), auth=auth
        )

    @mcp.tool(
        title="Create Comment Template",
        description="Create a comment template ('шаблон комментария'): reusable "
        "comment text with the users and mailing lists such a comment summons.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def comment_template_create(
        ctx: Context[AppContext],
        name: TemplateNameParam,
        queue: TemplateQueueParam = None,
        text: CommentTemplateTextParam = None,
        summonees: CommentTemplateSummoneesParam = None,
        maillist_summonees: CommentTemplateMaillistParam = None,
    ) -> CommentTemplate:
        if queue is not None:
            check_queue_access(settings, queue, write=True)
        return await ctx.request_context.lifespan_context.templates.comment_template_create(
            name=name,
            queue=queue,
            text=text,
            summonees=summonees,
            maillist_summonees=maillist_summonees,
            auth=get_yandex_auth(ctx),
        )

    @mcp.tool(
        title="Update Comment Template",
        description="Change a comment template ('шаблон комментария'); a list passed "
        "replaces the template's whole list.",
        annotations=ToolAnnotations(read_only_hint=False),
    )
    async def comment_template_update(
        ctx: Context[AppContext],
        template_id: CommentTemplateID,
        name: TemplateNameParam | None = None,
        text: CommentTemplateTextParam = None,
        summonees: CommentTemplateSummoneesParam = None,
        maillist_summonees: CommentTemplateMaillistParam = None,
        version: TemplateVersionParam = None,
    ) -> CommentTemplate:
        if (name, text, summonees, maillist_summonees) == (None,) * 4:
            raise TemplateEmptyUpdate(
                "`name`, `text`, `summonees` or `maillist_summonees`"
            )
        templates = ctx.request_context.lifespan_context.templates
        auth = get_yandex_auth(ctx)
        current = await templates.get_comment_template(template_id, auth=auth)
        _check_template_write(settings, current)
        return await templates.comment_template_update(
            template_id,
            version=_current_version(current, version),
            name=name,
            text=text,
            summonees=summonees,
            maillist_summonees=maillist_summonees,
            auth=auth,
        )

    @mcp.tool(
        title="Delete Comment Template",
        description="Permanently delete a comment template ('шаблон комментария'); "
        "there is no undo.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    async def comment_template_delete(
        ctx: Context[AppContext],
        template_id: CommentTemplateID,
        version: TemplateVersionParam = None,
    ) -> None:
        templates = ctx.request_context.lifespan_context.templates
        auth = get_yandex_auth(ctx)
        current = await templates.get_comment_template(template_id, auth=auth)
        _check_template_write(settings, current)
        await templates.comment_template_delete(
            template_id, version=_current_version(current, version), auth=auth
        )
