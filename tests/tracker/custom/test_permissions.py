"""TrackerClient methods for queue and component permissions and user groups.

Payloads as the live API answered them on 2026-10-26 (temporary queue MCPTMS).
"""

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    ComponentNotFound,
    PermissionsEmptyUpdate,
    QueueNotFound,
    TrackerAPIError,
)
from mcp_tracker.tracker.proto.types.permissions import GranteeChange, PermissionChange
from tests.aioresponses_utils import RequestCapture

BASE = "https://api.tracker.yandex.net"
ROBOT = {
    "self": f"{BASE}/v3/users/780889736",
    "id": "780889736",
    "display": "Робот сервиса Tracker Робот",
    "cloudUid": "ajemm8a2d8lr8n3no467",
    "passportUid": 780889736,
}
ALL_STAFF = {"self": f"{BASE}/v3/groups/1", "id": "1", "display": "Все сотрудники"}
PERMISSIONS = {
    "self": f"{BASE}/v3/queues/MCPTMS/permissions",
    "version": 2,
    "create": {
        "self": f"{BASE}/v3/queues/MCPTMS/permissions/create",
        "users": [ROBOT],
        "groups": [ALL_STAFF],
        "roles": [
            {
                "self": f"{BASE}/v3/roles/queue-lead",
                "id": "queue-lead",
                "display": "Владелец очереди",
            }
        ],
    },
    "read": {
        "self": f"{BASE}/v3/queues/MCPTMS/permissions/read",
        "roles": [{"self": f"{BASE}/v3/roles/access", "id": "access"}],
    },
    "deny": {"roles": [{"id": "author", "display": "Автор"}]},
}
USER_PERMISSIONS = {
    "user": {**ROBOT, "id": "1767417737", "display": "Валерий Криворот"},
    "permissions": {
        "CREATE": {"groups": [ALL_STAFF]},
        "WRITE": {"groups": [ALL_STAFF]},
    },
}


class TestQueuePermissions:
    async def test_get(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/queues/MCPTMS/permissions", payload=PERMISSIONS)
            permissions = await tracker_client.queue_get_permissions("MCPTMS")

        assert permissions.version == 2
        assert permissions.create is not None
        assert permissions.create.users is not None
        assert permissions.create.users[0].passportUid == 780889736
        assert permissions.deny is not None
        assert permissions.deny.roles is not None
        assert permissions.deny.roles[0].id == "author"
        assert permissions.grant is None

    async def test_get_unknown_queue(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/queues/NOPE/permissions", status=404)
            with pytest.raises(QueueNotFound):
                await tracker_client.queue_get_permissions("NOPE")

    async def test_user_permissions(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{BASE}/v3/queues/MCPTMS/permissions/users/i.ivanov",
                payload=USER_PERMISSIONS,
            )
            subject = await tracker_client.queue_get_user_permissions(
                "MCPTMS", "i.ivanov"
            )

        assert subject.user is not None
        assert subject.user.display == "Валерий Криворот"
        assert set(subject.permissions) == {"CREATE", "WRITE"}

    async def test_unknown_user_is_passed_through(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(
                f"{BASE}/v3/queues/MCPTMS/permissions/users/no.such",
                status=422,
                payload={"errorMessages": ["пользователь no.such не существует."]},
            )
            with pytest.raises(TrackerAPIError) as exc_info:
                await tracker_client.queue_get_user_permissions("MCPTMS", "no.such")

        assert "не существует" in str(exc_info.value)

    async def test_group_permissions(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{BASE}/v3/queues/MCPTMS/permissions/groups/1",
                payload={"group": ALL_STAFF, "permissions": {}},
            )
            subject = await tracker_client.queue_get_group_permissions("MCPTMS", 1)

        assert subject.group is not None
        assert subject.group.id == "1"
        assert subject.permissions == {}

    async def test_update_sends_each_change_in_the_api_shape(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=PERMISSIONS)

        with aioresponses() as m:
            m.patch(f"{BASE}/v3/queues/MCPTMS/permissions", callback=capture.callback)
            await tracker_client.queue_update_permissions(
                "MCPTMS",
                {
                    "read": PermissionChange(
                        groups=GranteeChange(add=[3]),
                        users=GranteeChange(add=["a"], remove=["b"]),
                    ),
                    "write": PermissionChange(roles=GranteeChange(set=["author"])),
                    "deny": PermissionChange(users=GranteeChange(set=[])),
                },
            )

        capture.last_request.assert_json_body(
            {
                "read": {
                    "users": {"add": ["a"], "remove": ["b"]},
                    "groups": {"add": [3]},
                },
                "write": {"roles": ["author"]},
                "deny": {"users": []},
            }
        )

    async def test_empty_update_is_refused_without_a_request(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses():
            with pytest.raises(PermissionsEmptyUpdate):
                await tracker_client.queue_update_permissions("MCPTMS", {})


class TestComponentPermissions:
    async def test_user_permissions(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{BASE}/v3/components/1/permissions/users/i.ivanov",
                payload={
                    "user": ROBOT,
                    "component": {"id": 1, "name": "MCP comp"},
                    "permissions": {},
                },
            )
            subject = await tracker_client.component_get_user_permissions(1, "i.ivanov")

        assert subject.component is not None
        assert subject.component.name == "MCP comp"

    async def test_unknown_component(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(f"{BASE}/v3/components/999/permissions/groups/1", status=404)
            with pytest.raises(ComponentNotFound):
                await tracker_client.component_get_group_permissions(999, 1)


class TestGroups:
    async def test_groups_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                f"{BASE}/v3/groups?page=1&perPage=50",
                payload=[
                    {
                        "self": f"{BASE}/v3/groups/1",
                        "id": 1,
                        "type": 7,
                        "name": "Все сотрудники",
                        "visibility": "public",
                        "allowChangeVisibility": False,
                    }
                ],
                headers={"X-Total-Count": "7", "X-Total-Pages": "1"},
            )
            result = await tracker_client.groups_list()

        assert result.values[0].id == 1
        assert result.values[0].name == "Все сотрудники"
