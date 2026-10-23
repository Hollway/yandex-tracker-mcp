from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_tracker.tracker.caching.client import make_cached_protocols
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.types.workflows import (
    LocalizedText,
    WorkflowActionDraft,
    WorkflowStepDraft,
)
from mcp_tracker.tracker.proto.workflows import WorkflowsProtocol

ACTION = WorkflowActionDraft(
    id="close", name=LocalizedText(ru="Закрыть", en="Close"), target="closed"
)
STEPS = [WorkflowStepDraft(status="open", actions=[ACTION])]

# (method, call args, call kwargs, expected args, expected kwargs without `auth`):
# every method is a passthrough, defaults included.
CALLS: list[
    tuple[str, tuple[Any, ...], dict[str, Any], tuple[Any, ...], dict[str, Any]]
] = [
    ("workflows_get_all", (), {}, (), {}),
    ("workflow_get", ("W9",), {}, ("W9",), {}),
    ("queues_get_workflows", ("ORG",), {}, ("ORG",), {}),
    ("screen_get", (704,), {}, (704,), {}),
    ("workflow_get_draft", ("W9",), {}, ("W9",), {}),
    (
        "workflow_create",
        (),
        {"name": "Процесс", "initial_action": ACTION, "steps": STEPS},
        (),
        {"name": "Процесс", "initial_action": ACTION, "steps": STEPS, "queue": None},
    ),
    (
        "workflow_update",
        ("W9",),
        {"version": 5, "steps": STEPS},
        ("W9",),
        {
            "version": 5,
            "name": None,
            "initial_action": None,
            "steps": STEPS,
            "issue_type_resolutions": None,
        },
    ),
    (
        "workflow_add_action",
        ("W9", "open"),
        {"version": 5, "action": ACTION},
        ("W9", "open"),
        {"version": 5, "action": ACTION},
    ),
    (
        "workflow_update_action",
        ("W9", "open", "close"),
        {"version": 5, "action": ACTION},
        ("W9", "open", "close"),
        {"version": 5, "action": ACTION},
    ),
    ("workflow_delete", ("W9",), {}, ("W9",), {}),
]


class TestCachingWorkflowsProtocol:
    @pytest.fixture
    def mock_original(self) -> AsyncMock:
        return AsyncMock(spec=WorkflowsProtocol)

    @pytest.fixture
    def caching_workflows_protocol(self, mock_original: AsyncMock) -> Any:
        return make_cached_protocols({"ttl": 300}).workflows(mock_original)

    def test_implements_protocol(self, caching_workflows_protocol: Any) -> None:
        assert isinstance(caching_workflows_protocol, WorkflowsProtocol)

    @pytest.mark.parametrize(
        ("method_name", "args", "kwargs", "expected_args", "expected_kwargs"),
        CALLS,
        ids=[call[0] for call in CALLS],
    )
    @pytest.mark.parametrize("with_auth", [True, False], ids=["auth", "no-auth"])
    async def test_calls_original(
        self,
        caching_workflows_protocol: Any,
        mock_original: AsyncMock,
        yandex_auth: YandexAuth,
        method_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        expected_args: tuple[Any, ...],
        expected_kwargs: dict[str, Any],
        with_auth: bool,
    ) -> None:
        auth = yandex_auth if with_auth else None
        original = getattr(mock_original, method_name)

        result = await getattr(caching_workflows_protocol, method_name)(
            *args, **kwargs, **({"auth": auth} if with_auth else {})
        )

        original.assert_called_once_with(*expected_args, **expected_kwargs, auth=auth)
        assert result == original.return_value

    @pytest.mark.parametrize(
        ("method_name", "args"),
        [
            ("workflows_get_all", ()),
            ("workflow_get", ("W9",)),
            ("queues_get_workflows", ("ORG",)),
            ("screen_get", (704,)),
            ("workflow_get_draft", ("W9",)),
        ],
    )
    async def test_reads_are_not_cached(
        self,
        caching_workflows_protocol: Any,
        mock_original: AsyncMock,
        method_name: str,
        args: tuple[Any, ...],
    ) -> None:
        """The write tools read the current version and transitions to rewrite
        them; a cached read would hand them a stale workflow."""
        await getattr(caching_workflows_protocol, method_name)(*args)
        await getattr(caching_workflows_protocol, method_name)(*args)

        assert getattr(mock_original, method_name).call_count == 2
