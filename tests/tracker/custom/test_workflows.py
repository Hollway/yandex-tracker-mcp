"""TrackerClient workflow methods: reads, the write-shape draft and the writes.

Payload shapes follow the live API (2026-10-23, see AGENTS.md, *Workflows*): a
read names things in the language of `Accept-Language` and gives statuses,
screens and resolutions as reference objects; a write wants names as
`{"ru", "en"}`, statuses by key, screens inline and `version` as a query
parameter.
"""

import copy
from typing import Any

import pytest
from aioresponses import CallbackResult, aioresponses
from yarl import URL

from mcp_tracker.tracker.custom.client import TrackerClient, _condition_drafts
from mcp_tracker.tracker.custom.errors import (
    QueueNotFound,
    ScreenNotFound,
    TrackerAPIError,
    WorkflowNotFound,
    WorkflowVersionConflict,
)
from mcp_tracker.tracker.proto.types.workflows import (
    IssueTypeResolutionsDraft,
    LocalizedText,
    Screen,
    ScreenDraft,
    ScreenElementDraft,
    Workflow,
    WorkflowActionDraft,
    WorkflowDraft,
    WorkflowStepDraft,
)
from tests.aioresponses_utils import RequestCapture

BASE = "https://api.tracker.yandex.net"
WORKFLOWS_URL = f"{BASE}/v3/workflows"
W9_URL = f"{BASE}/v3/workflows/W9"
SCREEN_URL = f"{BASE}/v3/screens/704"


def ref(kind: str, ref_id: str, key: str | None, display: str) -> dict[str, Any]:
    result = {"self": f"{BASE}/v3/{kind}/{ref_id}", "id": ref_id, "display": display}
    if key is not None:
        result["key"] = key
    return result


def workflow_payload(lang: str, *, version: int = 5) -> dict[str, Any]:
    """`GET v3/workflows/W9` in one language: names follow `Accept-Language`,
    keys, ids and coordinates do not."""
    ru = lang == "ru"

    def text(ru_text: str, en_text: str) -> str:
        return ru_text if ru else en_text

    open_ = ref("statuses", "1", "open", text("Открыт", "Open"))
    in_progress = ref("statuses", "3", "inProgress", text("В работе", "In progress"))
    closed = ref("statuses", "8", "closed", text("Закрыт", "Closed"))
    return {
        "self": W9_URL,
        "id": "W9",
        "name": "Тестовый процесс",
        "version": version,
        "type": "visual",
        "queue": ref("queues", "7", "ORG", "Организация"),
        "initialAction": {
            "id": "create",
            "name": text("Создать", "Create"),
            "target": open_,
        },
        "steps": [
            {
                "status": open_,
                "statusType": "new",
                "stepCoords": {"x": 0, "y": 0},
                "actions": [
                    {
                        "id": "start",
                        "name": text("В работу", "Start"),
                        "target": in_progress,
                        "description": text("Начать работу", "Start working"),
                        "postFunctions": [
                            {
                                "type": "SetCurrentTimeFunction",
                                "field": ref(
                                    "fields", "start", None, text("Начало", "Start")
                                ),
                                "skipFilled": True,
                            }
                        ],
                        "actionCoords": {"start": 2, "finish": 0},
                        "shortId": 1,
                    }
                ],
            },
            {
                "status": in_progress,
                "statusType": "inProgress",
                "stepCoords": {"x": 300, "y": 0},
                "metaAction": {
                    "id": "reopen",
                    "name": text("Переоткрыть", "Reopen"),
                    "target": in_progress,
                    "postFunctions": [{"type": "UnsetResolutionFunction"}],
                    "actionCoords": {"start": 0, "finish": 100},
                },
                "actions": [
                    {
                        "id": "close",
                        "name": text("Закрыть", "Close"),
                        "target": closed,
                        "screen": {"self": SCREEN_URL, "id": "704", "display": "704"},
                        "postFunctions": [
                            {
                                "type": "SetResolutionFunction",
                                "resolution": ref(
                                    "resolutions", "1", "fixed", text("Решён", "Fixed")
                                ),
                            }
                        ],
                        "conditions": [
                            {
                                "type": "FieldCondition",
                                "field": ref(
                                    "fields",
                                    "assignee",
                                    None,
                                    text("Исполнитель", "Assignee"),
                                ),
                                "values": [ref("users", "42", None, "Иван")],
                            }
                        ],
                        "actionCoords": {"start": 1, "finish": 3},
                        "shortId": 2,
                    }
                ],
            },
            {
                "status": closed,
                "statusType": "done",
                "stepCoords": {"x": 600, "y": 0},
                "actions": [],
            },
        ],
        "created": "2026-10-23T09:00:00.000+0000",
        "updated": "2026-10-23T10:00:00.000+0000",
        "deleted": False,
    }


def screen_payload(lang: str) -> dict[str, Any]:
    ru = lang == "ru"
    return {
        "self": SCREEN_URL,
        "id": 704,
        "version": 1,
        "type": "workflow",
        "title": "Укажите резолюцию" if ru else "Set the resolution",
        "elements": [
            {
                "self": f"{SCREEN_URL}/elements/resolution",
                "field": ref("fields", "resolution", None, "Резолюция"),
                "required": True,
            },
            {
                "self": f"{SCREEN_URL}/elements/6582fa303d406816db7e1dd4--systemId",
                "field": {
                    "self": f"{BASE}/v3/queues/ORG/localFields/systemId",
                    "id": "6582fa303d406816db7e1dd4--systemId",
                    "display": "ID системы",
                },
                "required": False,
            },
        ],
    }


class ByLanguage:
    """Answers each request with the payload for its `Accept-Language`,
    recording the languages asked for."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.languages: list[str | None] = []

    def callback(self, url: URL, **kwargs: Any) -> CallbackResult:
        language = (kwargs.get("headers") or {}).get("Accept-Language")
        self.languages.append(language)
        return CallbackResult(status=200, payload=self._payload(language))


def action_draft(**overrides: Any) -> WorkflowActionDraft:
    values: dict[str, Any] = {
        "id": "close",
        "name": LocalizedText(ru="Закрыть", en="Close"),
        "target": "closed",
    }
    values.update(overrides)
    return WorkflowActionDraft(**values)


class TestWorkflowReads:
    async def test_workflows_get_all(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(
            payload=[workflow_payload("ru"), {"id": "W2", "name": "Веб", "version": 2}]
        )

        with aioresponses() as m:
            m.get(WORKFLOWS_URL, callback=capture.callback)

            workflows = await tracker_client.workflows_get_all()

        capture.assert_called_once()
        assert [w.id for w in workflows] == ["W9", "W2"]
        assert all(isinstance(w, Workflow) for w in workflows)
        assert workflows[0].queue is not None
        assert workflows[0].queue.key == "ORG"
        assert workflows[1].steps == []

    async def test_workflow_get(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=workflow_payload("ru"))

        with aioresponses() as m:
            m.get(W9_URL, callback=capture.callback)

            workflow = await tracker_client.workflow_get("W9")

        capture.assert_called_once()
        # A plain read leaves the language to the token's defaults.
        assert "Accept-Language" not in capture.last_request.headers
        assert workflow.version == 5
        assert workflow.initial_action is not None
        assert workflow.initial_action.target is not None
        assert workflow.initial_action.target.key == "open"
        step = workflow.steps[1]
        assert step.status_type == "inProgress"
        assert step.meta_action is not None
        assert step.meta_action.id == "reopen"
        assert step.actions is not None
        close = step.actions[0]
        assert close.screen is not None
        assert close.screen.id == "704"
        assert close.post_functions is not None
        assert close.post_functions[0]["resolution"]["key"] == "fixed"
        assert close.action_coords == {"start": 1, "finish": 3}

    async def test_queues_get_workflows(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(
            payload={
                "quickStartV2PresetWorkflow": [
                    ref("issuetypes", "21", "milestone", "Веха"),
                    ref("issuetypes", "2", "task", "Задача"),
                ]
            }
        )

        with aioresponses() as m:
            m.get(f"{BASE}/v3/queues/ORG/workflows", callback=capture.callback)

            result = await tracker_client.queues_get_workflows("ORG")

        capture.assert_called_once()
        assert list(result) == ["quickStartV2PresetWorkflow"]
        assert [t.key for t in result["quickStartV2PresetWorkflow"]] == [
            "milestone",
            "task",
        ]

    async def test_screen_get(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=screen_payload("ru"))

        with aioresponses() as m:
            m.get(SCREEN_URL, callback=capture.callback)

            screen = await tracker_client.screen_get(704)

        capture.assert_called_once()
        assert isinstance(screen, Screen)
        assert screen.id == 704
        assert screen.title == "Укажите резолюцию"
        assert [(e.field.id, e.required) for e in screen.elements] == [
            ("resolution", True),
            ("6582fa303d406816db7e1dd4--systemId", False),
        ]

    @pytest.mark.parametrize(
        ("method_name", "url", "args", "error", "attribute", "value"),
        [
            ("workflow_get", W9_URL, ("W9",), WorkflowNotFound, "workflow_id", "W9"),
            ("screen_get", SCREEN_URL, (704,), ScreenNotFound, "screen_id", 704),
            (
                "queues_get_workflows",
                f"{BASE}/v3/queues/ORG/workflows",
                ("ORG",),
                QueueNotFound,
                "queue_id",
                "ORG",
            ),
        ],
        ids=["workflow", "screen", "queue"],
    )
    async def test_not_found(
        self,
        tracker_client: TrackerClient,
        method_name: str,
        url: str,
        args: tuple[Any, ...],
        error: type[Exception],
        attribute: str,
        value: Any,
    ) -> None:
        with aioresponses() as m:
            m.get(url, status=404, payload={"errorMessages": ["Не найдено."]})

            with pytest.raises(error) as exc_info:
                await getattr(tracker_client, method_name)(*args)

        assert getattr(exc_info.value, attribute) == value


class TestWorkflowGetDraft:
    async def test_merges_both_languages_and_inlines_screens(
        self, tracker_client: TrackerClient
    ) -> None:
        workflow_reads = ByLanguage(workflow_payload)
        screen_reads = ByLanguage(screen_payload)

        with aioresponses() as m:
            m.get(W9_URL, callback=workflow_reads.callback, repeat=True)
            m.get(SCREEN_URL, callback=screen_reads.callback, repeat=True)

            draft = await tracker_client.workflow_get_draft("W9")

        assert sorted(map(str, workflow_reads.languages)) == ["en", "ru"]
        assert sorted(map(str, screen_reads.languages)) == ["en", "ru"]
        assert isinstance(draft, WorkflowDraft)
        assert (draft.id, draft.version, draft.name, draft.queue) == (
            "W9",
            5,
            "Тестовый процесс",
            "ORG",
        )
        assert draft.initial_action.model_dump(by_alias=True) == {
            "id": "create",
            "name": {"ru": "Создать", "en": "Create"},
            "target": "open",
        }
        assert [s.model_dump(by_alias=True) for s in draft.steps] == [
            {
                "status": "open",
                "statusType": "new",
                "stepCoords": {"x": 0, "y": 0},
                "actions": [
                    {
                        "id": "start",
                        "name": {"ru": "В работу", "en": "Start"},
                        "target": "inProgress",
                        "description": {"ru": "Начать работу", "en": "Start working"},
                        # A reference without a key goes by its id.
                        "postFunctions": [
                            {
                                "type": "SetCurrentTimeFunction",
                                "field": "start",
                                "skipFilled": True,
                            }
                        ],
                        "actionCoords": {"start": 2, "finish": 0},
                    }
                ],
            },
            {
                "status": "inProgress",
                "statusType": "inProgress",
                "metaAction": {
                    "id": "reopen",
                    "name": {"ru": "Переоткрыть", "en": "Reopen"},
                    "target": "inProgress",
                    "postFunctions": [{"type": "UnsetResolutionFunction"}],
                    "actionCoords": {"start": 0, "finish": 100},
                },
                "stepCoords": {"x": 300, "y": 0},
                "actions": [
                    {
                        "id": "close",
                        "name": {"ru": "Закрыть", "en": "Close"},
                        "target": "closed",
                        # Inline: a write cannot refer to a screen by id.
                        "screen": {
                            "title": {
                                "ru": "Укажите резолюцию",
                                "en": "Set the resolution",
                            },
                            "elements": [
                                {"field": "resolution", "required": True},
                                {
                                    "field": "6582fa303d406816db7e1dd4--systemId",
                                    "required": False,
                                },
                            ],
                        },
                        # A reference with a key goes by its key.
                        "postFunctions": [
                            {"type": "SetResolutionFunction", "resolution": "fixed"}
                        ],
                        "conditions": [
                            {
                                "type": "FieldCondition",
                                "field": "assignee",
                                "values": ["42"],
                            }
                        ],
                        "actionCoords": {"start": 1, "finish": 3},
                    }
                ],
            },
            {
                "status": "closed",
                "statusType": "done",
                "stepCoords": {"x": 600, "y": 0},
                "actions": [],
            },
        ]

    async def test_reads_each_screen_once_per_language(
        self, tracker_client: TrackerClient
    ) -> None:
        """Two transitions on the same screen still cost one pair of reads."""

        def payload(lang: str) -> dict[str, Any]:
            result = workflow_payload(lang)
            shared = copy.deepcopy(result["steps"][1]["actions"][0])
            shared["id"] = "close_again"
            result["steps"][0]["actions"].append(shared)
            return result

        workflow_reads = ByLanguage(payload)
        screen_reads = ByLanguage(screen_payload)

        with aioresponses() as m:
            m.get(W9_URL, callback=workflow_reads.callback, repeat=True)
            m.get(SCREEN_URL, callback=screen_reads.callback, repeat=True)

            draft = await tracker_client.workflow_get_draft("W9")

        assert len(screen_reads.languages) == 2
        open_step = draft.step("open")
        assert open_step is not None
        assert open_step.actions[1].screen == draft.steps[1].actions[0].screen

    async def test_a_name_missing_in_english_falls_back_to_russian(
        self, tracker_client: TrackerClient
    ) -> None:
        """Tracker refuses a write that gives one language only (422), so a
        text the English read lacks is sent in Russian under both."""

        def payload(lang: str) -> dict[str, Any]:
            result = workflow_payload(lang)
            if lang == "en":
                del result["steps"][0]
                result["steps"][0]["actions"][0]["description"] = "Close it"
            return result

        with aioresponses() as m:
            m.get(W9_URL, callback=ByLanguage(payload).callback, repeat=True)
            m.get(SCREEN_URL, callback=ByLanguage(screen_payload).callback, repeat=True)

            draft = await tracker_client.workflow_get_draft("W9")

        assert [s.status for s in draft.steps] == ["open", "inProgress", "closed"]
        # The step the English read lacks: Russian under both languages.
        start = draft.steps[0].actions[0]
        assert start.name == LocalizedText(ru="В работу", en="В работу")
        assert start.description == LocalizedText(
            ru="Начать работу", en="Начать работу"
        )
        # A text only the English read has: English under both.
        close = draft.steps[1].actions[0]
        assert close.name == LocalizedText(ru="Закрыть", en="Close")
        assert close.description == LocalizedText(ru="Close it", en="Close it")

    async def test_rereads_when_the_version_moved_between_the_two_reads(
        self, tracker_client: TrackerClient
    ) -> None:
        versions = iter([5, 6, 6, 6])

        def payload(lang: str) -> dict[str, Any]:
            return workflow_payload(lang, version=next(versions))

        workflow_reads = ByLanguage(payload)

        with aioresponses() as m:
            m.get(W9_URL, callback=workflow_reads.callback, repeat=True)
            m.get(SCREEN_URL, callback=ByLanguage(screen_payload).callback, repeat=True)

            draft = await tracker_client.workflow_get_draft("W9")

        assert len(workflow_reads.languages) == 4
        assert draft.version == 6

    async def test_gives_up_when_the_version_keeps_moving(
        self, tracker_client: TrackerClient
    ) -> None:
        versions = iter(range(1, 100))

        def payload(lang: str) -> dict[str, Any]:
            return workflow_payload(lang, version=next(versions))

        workflow_reads = ByLanguage(payload)

        with aioresponses() as m:
            m.get(W9_URL, callback=workflow_reads.callback, repeat=True)

            with pytest.raises(WorkflowVersionConflict):
                await tracker_client.workflow_get_draft("W9")

        assert len(workflow_reads.languages) == 6

    async def test_unknown_workflow(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(W9_URL, status=404, repeat=True)

            with pytest.raises(WorkflowNotFound):
                await tracker_client.workflow_get_draft("W9")


class TestWorkflowWrites:
    async def test_workflow_create(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=workflow_payload("ru", version=1))
        initial = action_draft(
            id="create", name=LocalizedText(ru="Создать", en="Create"), target="open"
        )
        steps = [
            WorkflowStepDraft(
                status="open",
                status_type="new",
                actions=[
                    action_draft(
                        screen=ScreenDraft(
                            title=LocalizedText(ru="Резолюция", en="Resolution"),
                            elements=[
                                ScreenElementDraft(field="resolution", required=True)
                            ],
                        )
                    )
                ],
            ),
            WorkflowStepDraft(status="closed", status_type="done"),
        ]

        with aioresponses() as m:
            m.post(WORKFLOWS_URL, callback=capture.callback)

            workflow = await tracker_client.workflow_create(
                name="Тестовый процесс",
                initial_action=initial,
                steps=steps,
                queue="ORG",
            )

        capture.assert_called_once()
        assert workflow.id == "W9"
        capture.last_request.assert_json_body(
            {
                "name": "Тестовый процесс",
                "type": "VISUAL",
                "queue": "ORG",
                "initialAction": {
                    "id": "create",
                    "name": {"ru": "Создать", "en": "Create"},
                    "target": "open",
                },
                "steps": [
                    {
                        "status": "open",
                        "statusType": "new",
                        "actions": [
                            {
                                "id": "close",
                                "name": {"ru": "Закрыть", "en": "Close"},
                                "target": "closed",
                                "screen": {
                                    "title": {"ru": "Резолюция", "en": "Resolution"},
                                    "elements": [
                                        {"field": "resolution", "required": True}
                                    ],
                                },
                            }
                        ],
                    },
                    {"status": "closed", "statusType": "done", "actions": []},
                ],
            }
        )

    async def test_workflow_create_without_queue_sends_none(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=workflow_payload("ru", version=1))

        with aioresponses() as m:
            m.post(WORKFLOWS_URL, callback=capture.callback)

            await tracker_client.workflow_create(
                name="Общий",
                initial_action=action_draft(id="create", target="open"),
                steps=[WorkflowStepDraft(status="open")],
            )

        assert "queue" not in capture.last_request.get_json_body()

    @pytest.mark.parametrize(
        ("kwargs", "expected_body"),
        [
            ({"name": "Новое имя"}, {"name": "Новое имя"}),
            (
                {"steps": [WorkflowStepDraft(status="open", actions=[action_draft()])]},
                {
                    "steps": [
                        {
                            "status": "open",
                            "actions": [
                                {
                                    "id": "close",
                                    "name": {"ru": "Закрыть", "en": "Close"},
                                    "target": "closed",
                                }
                            ],
                        }
                    ]
                },
            ),
            (
                {"initial_action": action_draft(id="create", target="open")},
                {
                    "initialAction": {
                        "id": "create",
                        "name": {"ru": "Закрыть", "en": "Close"},
                        "target": "open",
                    }
                },
            ),
            (
                {
                    "issue_type_resolutions": [
                        IssueTypeResolutionsDraft(
                            issue_type="task", resolutions=["fixed", "wontFix"]
                        )
                    ]
                },
                {
                    "issueTypeResolutions": [
                        {"issueType": "task", "resolutions": ["fixed", "wontFix"]}
                    ]
                },
            ),
        ],
        ids=["name", "steps", "initial-action", "issue-type-resolutions"],
    )
    async def test_workflow_update_sends_only_what_is_given(
        self,
        tracker_client: TrackerClient,
        kwargs: dict[str, Any],
        expected_body: dict[str, Any],
    ) -> None:
        capture = RequestCapture(payload=workflow_payload("ru", version=6))

        with aioresponses() as m:
            m.patch(f"{W9_URL}?version=5", callback=capture.callback)

            workflow = await tracker_client.workflow_update("W9", version=5, **kwargs)

        capture.assert_called_once()
        # Every write needs the version as a query parameter (400 without it).
        capture.last_request.assert_param("version", 5)
        capture.last_request.assert_json_body(expected_body)
        assert workflow.version == 6

    async def test_workflow_add_action(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=workflow_payload("ru", version=6))
        action = action_draft(
            id="cancel",
            name=LocalizedText(ru="Отменить", en="Cancel"),
            description=LocalizedText(ru="Отмена", en="Cancellation"),
            post_functions=[{"type": "SetResolutionFunction", "resolution": "wontFix"}],
        )

        with aioresponses() as m:
            m.post(
                f"{W9_URL}/steps/inProgress/actions?version=5",
                callback=capture.callback,
            )

            await tracker_client.workflow_add_action(
                "W9", "inProgress", version=5, action=action
            )

        capture.assert_called_once()
        capture.last_request.assert_param("version", 5)
        capture.last_request.assert_json_body(
            {
                "id": "cancel",
                "name": {"ru": "Отменить", "en": "Cancel"},
                "target": "closed",
                "description": {"ru": "Отмена", "en": "Cancellation"},
                "postFunctions": [
                    {"type": "SetResolutionFunction", "resolution": "wontFix"}
                ],
            }
        )

    async def test_workflow_update_action(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=workflow_payload("ru", version=6))
        action = action_draft(action_coords={"start": 1, "finish": 3})

        with aioresponses() as m:
            m.patch(
                f"{W9_URL}/steps/inProgress/actions/close?version=5",
                callback=capture.callback,
            )

            await tracker_client.workflow_update_action(
                "W9", "inProgress", "close", version=5, action=action
            )

        capture.assert_called_once()
        capture.last_request.assert_param("version", 5)
        # The whole transition: the API removes whatever the body leaves out.
        capture.last_request.assert_json_body(
            {
                "id": "close",
                "name": {"ru": "Закрыть", "en": "Close"},
                "target": "closed",
                "actionCoords": {"start": 1, "finish": 3},
            }
        )

    @pytest.mark.parametrize(
        ("method_name", "verb", "url", "args"),
        [
            ("workflow_update", "PATCH", f"{W9_URL}?version=5", ("W9",)),
            (
                "workflow_add_action",
                "POST",
                f"{W9_URL}/steps/inProgress/actions?version=5",
                ("W9", "inProgress"),
            ),
            (
                "workflow_update_action",
                "PATCH",
                f"{W9_URL}/steps/inProgress/actions/close?version=5",
                ("W9", "inProgress", "close"),
            ),
        ],
        ids=["update", "add-action", "update-action"],
    )
    async def test_stale_version_raises_conflict(
        self,
        tracker_client: TrackerClient,
        method_name: str,
        verb: str,
        url: str,
        args: tuple[str, ...],
    ) -> None:
        kwargs: dict[str, Any] = {"version": 5}
        if method_name == "workflow_update":
            kwargs["name"] = "Новое имя"
        else:
            kwargs["action"] = action_draft()

        with aioresponses() as m:
            m.add(
                url,
                method=verb,
                status=412,
                payload={
                    "errorMessages": [
                        "Воркфлоу: не удалось сохранить изменения, попробуйте ещё раз."
                    ]
                },
            )

            with pytest.raises(WorkflowVersionConflict) as exc_info:
                await getattr(tracker_client, method_name)(*args, **kwargs)

        assert "W9" in str(exc_info.value)
        assert "5" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("method_name", "verb", "url", "args", "message"),
        [
            (
                "workflow_add_action",
                "POST",
                f"{W9_URL}/steps/nope/actions?version=5",
                ("W9", "nope"),
                "Статус не существует.",
            ),
            (
                "workflow_update_action",
                "PATCH",
                f"{W9_URL}/steps/inProgress/actions/nope?version=5",
                ("W9", "inProgress", "nope"),
                "Переход не существует.",
            ),
        ],
        ids=["add-action", "update-action"],
    )
    async def test_action_scoped_404_keeps_trackers_text(
        self,
        tracker_client: TrackerClient,
        method_name: str,
        verb: str,
        url: str,
        args: tuple[str, ...],
        message: str,
    ) -> None:
        """An unknown status or transition answers 404 too, so it is not
        reported as an unknown workflow."""
        with aioresponses() as m:
            m.add(url, method=verb, status=404, payload={"errorMessages": [message]})

            with pytest.raises(TrackerAPIError) as exc_info:
                await getattr(tracker_client, method_name)(
                    *args, version=5, action=action_draft()
                )

        assert not isinstance(exc_info.value, WorkflowNotFound)
        assert exc_info.value.status == 404
        assert message in str(exc_info.value)

    async def test_workflow_update_unknown_workflow(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.patch(f"{W9_URL}?version=5", status=404)

            with pytest.raises(WorkflowNotFound):
                await tracker_client.workflow_update("W9", version=5, name="X")

    async def test_workflow_delete(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(status=204)

        with aioresponses() as m:
            m.delete(W9_URL, callback=capture.callback)

            await tracker_client.workflow_delete("W9")

        capture.assert_called_once()
        assert capture.last_request.url.path == "/v3/workflows/W9"

    async def test_workflow_delete_unknown_workflow(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.delete(W9_URL, status=404)

            with pytest.raises(WorkflowNotFound) as exc_info:
                await tracker_client.workflow_delete("W9")

        assert exc_info.value.workflow_id == "W9"


class TestWorkflowStepDraft:
    def test_refuses_duplicate_transition_ids(self) -> None:
        with pytest.raises(ValueError, match="duplicate transition ids"):
            WorkflowStepDraft(status="open", actions=[action_draft(), action_draft()])


QUEUE_ORG = {"self": f"{BASE}/v3/queues/ORG", "id": "1", "key": "ORG", "display": "ORG"}
GROUP_3 = {"self": f"{BASE}/v3/groups/3", "id": "3", "display": "Admins"}


@pytest.mark.parametrize(
    ("read", "written"),
    [
        pytest.param(None, None, id="none"),
        pytest.param(
            [{"type": "HasLinksConditionProto", "queues": [QUEUE_ORG]}],
            [{"type": "HasLinksCondition", "queues": ["ORG"]}],
            id="linked-queue-renamed",
        ),
        pytest.param(
            [
                {
                    "type": "OrCondition",
                    "conditions": [
                        {"type": "UserInGroupCondition", "group": GROUP_3},
                        {
                            "type": "AndCondition",
                            "conditions": [
                                {
                                    "type": "HasLinksConditionProto",
                                    "queues": [QUEUE_ORG],
                                },
                                {"type": "UserIsQueueLeadCondition"},
                            ],
                        },
                    ],
                }
            ],
            [
                {
                    "type": "OrCondition",
                    "conditions": [
                        {"type": "UserInGroupCondition", "group": "3"},
                        {
                            "type": "AndCondition",
                            "conditions": [
                                {"type": "HasLinksCondition", "queues": ["ORG"]},
                                {"type": "UserIsQueueLeadCondition"},
                            ],
                        },
                    ],
                }
            ],
            id="nested",
        ),
    ],
)
def test_condition_drafts(
    read: list[dict[str, Any]] | None, written: list[dict[str, Any]] | None
) -> None:
    """A read's conditions in the shape a write takes - verified live: the
    linked-queue condition reads as `HasLinksConditionProto` and is written as
    `HasLinksCondition`."""
    assert _condition_drafts(read) == written
