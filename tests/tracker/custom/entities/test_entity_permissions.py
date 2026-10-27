import re

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.custom.errors import (
    EntityHasNoParent,
    EntityPermissionsChangeWhileInheriting,
    EntityPermissionsEmptyUpdate,
    EntityPermissionsInherited,
)
from mcp_tracker.tracker.proto.types.entities import EntityType
from mcp_tracker.tracker.proto.types.permissions import (
    EntityGranteeChange,
    EntityPermissionAction,
    EntityPermissionChange,
    EntityRoleChange,
)
from tests.aioresponses_utils import RequestCapture

ENTITY_TYPES: list[EntityType] = ["project", "portfolio", "goal"]

PORTFOLIO = {
    "self": "https://api.tracker.yandex.net/v3/entities/portfolio/pf1",
    "id": "pf1",
    "display": "Portfolio",
}
OWN = {
    "acl": {
        "WRITE": {
            "users": [{"id": "1", "display": "Robot"}],
            "groups": [{"id": "1", "display": "Все сотрудники"}],
            "roles": ["AUTHOR", "OWNER", "MEMBER"],
        },
        "GRANT": {"users": [], "groups": [], "roles": ["AUTHOR", "OWNER"]},
    },
    "accessType": "public",
}
INHERITED = {
    **OWN,
    "permissionSources": [PORTFOLIO],
    "parentEntities": {"primary": PORTFOLIO, "secondary": []},
}
WITH_PARENT = {**OWN, "parentEntities": {"primary": PORTFOLIO, "secondary": []}}


def url(entity_type: str) -> re.Pattern[str]:
    return re.compile(
        rf"^https://api\.tracker\.yandex\.net/v3/entities/{entity_type}/e1/"
        r"extendedPermissions$"
    )


REVOKE_FOLLOWER: dict[EntityPermissionAction, EntityPermissionChange] = {
    "WRITE": EntityPermissionChange(roles=EntityRoleChange(remove=["FOLLOWER"]))
}


class TestEntityGetPermissions:
    @pytest.mark.parametrize("entity_type", ENTITY_TYPES)
    async def test_parses_extended_permissions(
        self, tracker_client: TrackerClient, entity_type: EntityType
    ) -> None:
        with aioresponses() as m:
            m.get(url(entity_type), payload=INHERITED)
            permissions = await tracker_client.entity_get_permissions(entity_type, "e1")

        assert permissions.acl is not None
        assert permissions.acl.write is not None
        assert permissions.acl.write.roles == ["AUTHOR", "OWNER", "MEMBER"]
        assert permissions.acl.read is None
        assert permissions.permissionSources is not None
        assert permissions.permissionSources[0].id == "pf1"
        assert permissions.accessType == "public"
        dumped = permissions.model_dump(by_alias=True, exclude_none=True)
        assert set(dumped["acl"]) == {"WRITE", "GRANT"}


class TestEntityUpdatePermissions:
    async def test_grants_and_revokes(self, tracker_client: TrackerClient) -> None:
        capture = RequestCapture(payload=OWN)

        with aioresponses() as m:
            m.get(url("project"), payload=OWN)
            m.patch(url("project"), callback=capture.callback)
            await tracker_client.entity_update_permissions(
                "project",
                "e1",
                {
                    "READ": EntityPermissionChange(
                        groups=EntityGranteeChange(add=[1]),
                        users=EntityGranteeChange(
                            add=["i.ivanov"], remove=["p.petrov"]
                        ),
                    ),
                    "WRITE": EntityPermissionChange(
                        groups=EntityGranteeChange(remove=[1])
                    ),
                },
            )

        capture.last_request.assert_json_body(
            {
                "acl": {
                    "grant": {"READ": {"groups": [1], "users": ["i.ivanov"]}},
                    "revoke": {
                        "READ": {"users": ["p.petrov"]},
                        "WRITE": {"groups": [1]},
                    },
                }
            }
        )

    async def test_change_to_inherited_permissions_is_refused(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(url("project"), payload=INHERITED)
            with pytest.raises(EntityPermissionsInherited, match="from 'Portfolio'"):
                await tracker_client.entity_update_permissions(
                    "project", "e1", REVOKE_FOLLOWER
                )

    async def test_stop_inheriting_goes_with_the_change(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=OWN)

        with aioresponses() as m:
            m.patch(url("portfolio"), callback=capture.callback)
            await tracker_client.entity_update_permissions(
                "portfolio", "e1", REVOKE_FOLLOWER, inherit=False
            )

        capture.assert_called_once()
        capture.last_request.assert_json_body(
            {
                "permissionSources": [],
                "acl": {"revoke": {"WRITE": {"roles": ["FOLLOWER"]}}},
            }
        )

    async def test_inherit_sends_the_primary_parent(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload=INHERITED)

        with aioresponses() as m:
            m.get(url("goal"), payload=WITH_PARENT)
            m.patch(url("goal"), callback=capture.callback)
            await tracker_client.entity_update_permissions(
                "goal", "e1", {}, inherit=True
            )

        capture.last_request.assert_json_body({"permissionSources": ["pf1"]})

    async def test_inherit_with_a_change_is_refused(
        self, tracker_client: TrackerClient
    ) -> None:
        with pytest.raises(EntityPermissionsChangeWhileInheriting):
            await tracker_client.entity_update_permissions(
                "project", "e1", REVOKE_FOLLOWER, inherit=True
            )

    async def test_inherit_without_a_parent_is_refused(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(url("project"), payload=OWN)
            with pytest.raises(EntityHasNoParent):
                await tracker_client.entity_update_permissions(
                    "project", "e1", {}, inherit=True
                )

    async def test_empty_change_is_refused(self, tracker_client: TrackerClient) -> None:
        with pytest.raises(EntityPermissionsEmptyUpdate):
            await tracker_client.entity_update_permissions("project", "e1", {})
