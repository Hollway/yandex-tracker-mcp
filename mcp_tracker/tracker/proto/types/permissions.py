"""Access permissions of queues, components, projects, portfolios and goals,
and the user groups they are granted to."""

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from mcp_tracker.tracker.proto.types.base import (
    BaseTrackerEntity,
    NoneExcludedField,
    none_excluder,
)
from mcp_tracker.tracker.proto.types.refs import BaseReference

# What a permission allows: create issues, read them, change them, change the
# queue's settings - and the explicit denial, which wins over the others.
PermissionAction = Literal["create", "read", "write", "grant", "deny"]


class PermissionUser(BaseReference):
    display: str | None = None
    cloudUid: str | None = None
    passportUid: int | None = None


class PermissionRef(BaseReference):
    """A group or a role a permission is granted to (`id` is a group id or a
    role key such as 'author')."""

    display: str | None = None


class PermissionComponent(BaseReference):
    name: str | None = None


class PermissionGrantees(BaseTrackerEntity):
    """Who holds one permission."""

    users: list[PermissionUser] | None = None
    groups: list[PermissionRef] | None = None
    roles: list[PermissionRef] | None = None


class QueuePermissions(BaseTrackerEntity):
    """Every permission of a queue (or a component) with whom it is granted to."""

    version: int | None = None
    create: PermissionGrantees | None = None
    read: PermissionGrantees | None = None
    write: PermissionGrantees | None = None
    grant: PermissionGrantees | None = None
    deny: PermissionGrantees | None = None


class SubjectPermissions(BaseTrackerEntity):
    """The permissions one user or group holds in a queue or a component, each
    with the grantees it comes through (the group, the role or the user
    itself). Keys are upper case: CREATE, READ, WRITE, GRANT."""

    user: PermissionUser | None = None
    group: PermissionRef | None = None
    component: PermissionComponent | None = None
    permissions: dict[str, PermissionGrantees] = Field(default_factory=dict)


class Group(BaseTrackerEntity):
    """A user group of the organization."""

    id: int
    name: str | None = None
    description: str | None = None
    type: int | None = None
    visibility: str | None = None


class GranteeChange(BaseModel):
    """A change to the users, groups or roles one permission is granted to."""

    model_config = ConfigDict(extra="forbid")

    add: list[str | int] | None = Field(
        default=None, description="Grant the permission to these, keeping the rest."
    )
    remove: list[str | int] | None = Field(
        default=None, description="Revoke the permission from these."
    )
    set: list[str | int] | None = Field(
        default=None,
        description="Replace the whole list with these; [] revokes it from all. "
        "Not combined with `add` / `remove`.",
    )

    @model_validator(mode="after")
    def _one_way(self) -> "GranteeChange":
        if self.set is not None and (self.add is not None or self.remove is not None):
            raise ValueError(
                "`set` replaces the list; do not combine it with add/remove"
            )
        if self.set is None and self.add is None and self.remove is None:
            raise ValueError("pass `add`, `remove` or `set`")
        return self

    def to_api(self) -> list[str | int] | dict[str, list[str | int]]:
        if self.set is not None:
            return self.set
        return {
            k: v
            for k, v in (("add", self.add), ("remove", self.remove))
            if v is not None
        }


class PermissionChange(BaseModel):
    """Changes to who holds one permission."""

    model_config = ConfigDict(extra="forbid")

    users: GranteeChange | None = Field(
        default=None, description="Users, by login or uid."
    )
    groups: GranteeChange | None = Field(
        default=None, description="Groups, by numeric id (groups_get_all)."
    )
    roles: GranteeChange | None = Field(
        default=None,
        description="Roles: 'author', 'assignee', 'follower', 'access' (anyone the "
        "issue was shared with) or 'queue-lead'.",
    )

    @model_validator(mode="after")
    def _not_empty(self) -> "PermissionChange":
        if self.users is None and self.groups is None and self.roles is None:
            raise ValueError("pass `users`, `groups` or `roles`")
        return self

    def to_api(self) -> dict[str, object]:
        return {
            kind: change.to_api()
            for kind, change in (
                ("users", self.users),
                ("groups", self.groups),
                ("roles", self.roles),
            )
            if change is not None
        }


# Roles a project, portfolio or goal grants access to: its author, its lead
# (OWNER), customers, followers and team members.
EntityRole = Literal["AUTHOR", "OWNER", "CLIENT", "FOLLOWER", "MEMBER"]

# What an entity permission allows: see it, change it, change who may.
EntityPermissionAction = Literal["READ", "WRITE", "GRANT"]


class EntityGrantees(BaseTrackerEntity):
    """Who holds one permission on a project, portfolio or goal."""

    users: list[PermissionUser] | None = NoneExcludedField
    groups: list[PermissionRef] | None = NoneExcludedField
    roles: list[EntityRole] | None = NoneExcludedField


class EntityAcl(BaseTrackerEntity):
    """The permissions of an entity. A right includes the ones below it, so a
    subject holding WRITE is not listed under READ; with no READ at all the
    entity is readable by everyone."""

    read: EntityGrantees | None = Field(
        None,
        validation_alias=AliasChoices("READ", "read"),
        serialization_alias="READ",
        exclude_if=none_excluder,
    )
    write: EntityGrantees | None = Field(
        None,
        validation_alias=AliasChoices("WRITE", "write"),
        serialization_alias="WRITE",
        exclude_if=none_excluder,
    )
    grant: EntityGrantees | None = Field(
        None,
        validation_alias=AliasChoices("GRANT", "grant"),
        serialization_alias="GRANT",
        exclude_if=none_excluder,
    )


class EntityPermissionSource(BaseReference):
    display: str | None = None


class EntityParentEntities(BaseTrackerEntity):
    primary: EntityPermissionSource | None = None
    secondary: list[EntityPermissionSource] | None = None


class EntityPermissions(BaseTrackerEntity):
    """Who may read, change and manage access to a project, portfolio or
    goal, and where those rights come from."""

    acl: EntityAcl | None = NoneExcludedField
    # The parent the entity inherits its access from; empty when it has its own.
    permissionSources: list[EntityPermissionSource] | None = NoneExcludedField
    parentEntities: EntityParentEntities | None = NoneExcludedField
    # "public" or "custom".
    accessType: str | None = NoneExcludedField


class EntityGranteeChange(BaseModel):
    """Users or groups to give a permission to or take it from."""

    model_config = ConfigDict(extra="forbid")

    add: list[str | int] | None = Field(default=None, description="Grant to these.")
    remove: list[str | int] | None = Field(
        default=None, description="Revoke from these."
    )

    @model_validator(mode="after")
    def _not_empty(self) -> "EntityGranteeChange":
        if not self.add and not self.remove:
            raise ValueError("pass `add` or `remove`")
        return self


class EntityRoleChange(BaseModel):
    """Roles to give a permission to or take it from."""

    model_config = ConfigDict(extra="forbid")

    add: list[EntityRole] | None = Field(default=None, description="Grant to these.")
    remove: list[EntityRole] | None = Field(
        default=None, description="Revoke from these."
    )

    @model_validator(mode="after")
    def _not_empty(self) -> "EntityRoleChange":
        if not self.add and not self.remove:
            raise ValueError("pass `add` or `remove`")
        return self


class EntityPermissionChange(BaseModel):
    """Changes to who holds one permission of an entity."""

    model_config = ConfigDict(extra="forbid")

    users: EntityGranteeChange | None = Field(
        default=None, description="Users, by login or uid."
    )
    groups: EntityGranteeChange | None = Field(
        default=None, description="Groups, by numeric id (groups_get_all)."
    )
    roles: EntityRoleChange | None = Field(
        default=None,
        description="Roles: AUTHOR, OWNER (the lead), CLIENT, FOLLOWER, MEMBER "
        "(the team).",
    )

    @model_validator(mode="after")
    def _not_empty(self) -> "EntityPermissionChange":
        if self.users is None and self.groups is None and self.roles is None:
            raise ValueError("pass `users`, `groups` or `roles`")
        return self

    def part(self, side: Literal["add", "remove"]) -> dict[str, list[Any]]:
        """The grants (`add`) or the revocations (`remove`) of this change."""
        return {
            kind: values
            for kind, change in (
                ("users", self.users),
                ("groups", self.groups),
                ("roles", self.roles),
            )
            if change is not None and (values := getattr(change, side))
        }
