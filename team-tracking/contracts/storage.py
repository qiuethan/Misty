from datetime import date
from typing import Protocol
from uuid import UUID

from contracts.types import (
    Person,
    PersonCreate,
    PersonUpdate,
    RoleKind,
    Team,
    TeamCreate,
    TeamMembership,
    TeamMembershipCreate,
    TeamMembershipUpdate,
    TeamUpdate,
)


class StorageAdapter(Protocol):
    """Stable internal contract between the API and the persistence layer.

    Any concrete adapter (Postgres, SQLite, in-memory, ...) implements these
    methods with identical semantics. Consumers of the API never see this
    interface — only the API layer does.

    Conventions:
    - All methods that write also stamp created_by/updated_by using the actor arg.
    - `list_*` methods that take filters return every matching record; pagination
      is not implemented in v1 (add later if the roster grows past ~500 people).
    - `end_membership` is a semantic helper: sets ended_at without deleting the row.
    - Records are never hard-deleted; use `active=False` on Person/Team, or
      `end_membership` for soft-removal.
    """

    # People
    def create_person(self, payload: PersonCreate, *, actor: str) -> Person: ...
    def get_person(self, person_id: UUID) -> Person | None: ...
    def get_person_by_email(self, primary_email: str) -> Person | None: ...
    def list_people(self, *, active_only: bool = False) -> list[Person]:
        """List every person. To fetch people for a specific team, use
        `list_memberships(team_id=...)` and resolve `person_id` values."""
        ...
    def update_person(
        self, person_id: UUID, payload: PersonUpdate, *, actor: str
    ) -> Person | None: ...

    # Teams
    def create_team(self, payload: TeamCreate, *, actor: str) -> Team: ...
    def get_team(self, team_id: UUID) -> Team | None: ...
    def get_team_by_slug(self, slug: str) -> Team | None: ...
    def list_teams(self, *, active_only: bool = False) -> list[Team]: ...
    def update_team(
        self, team_id: UUID, payload: TeamUpdate, *, actor: str
    ) -> Team | None: ...

    # Role kinds
    def get_role_kind(self, role_kind_id: str) -> RoleKind | None: ...
    def list_role_kinds(self, *, active_only: bool = False) -> list[RoleKind]: ...

    # Team memberships
    def create_membership(
        self, payload: TeamMembershipCreate, *, actor: str
    ) -> TeamMembership: ...
    def get_membership(self, membership_id: UUID) -> TeamMembership | None: ...
    def list_memberships(
        self,
        *,
        team_id: UUID | None = None,
        person_id: UUID | None = None,
        active_only: bool = False,
        as_of: date | None = None,
        is_team_admin: bool | None = None,
    ) -> list[TeamMembership]:
        """List memberships matching every provided filter.

        `as_of`: return only memberships active on that date — i.e. rows where
        `started_at <= as_of` AND (`ended_at IS NULL` OR `ended_at > as_of`).
        """
        ...
    def update_membership(
        self, membership_id: UUID, payload: TeamMembershipUpdate, *, actor: str
    ) -> TeamMembership | None: ...
    def end_membership(
        self, membership_id: UUID, ended_at: date, *, actor: str
    ) -> TeamMembership | None:
        """Set `ended_at` without touching role_kind or admin flag.

        Prefer this over `update_membership` for soft-closes so intent is clear
        at the call site. `update_membership` accepts `ended_at` too, but is
        semantically the general edit path.
        """
        ...
