from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from contracts.types import (
    ApiKey,
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryStorageAdapter:
    """In-process storage adapter used in tests and for quick prototyping.

    Not thread-safe. Not persistent. Enforces the same semantic invariants as
    the Postgres adapter (email uniqueness, slug uniqueness, no schema surprises).
    """

    def __init__(self, seed_role_kinds: list[RoleKind] | None = None) -> None:
        self._people: dict[UUID, Person] = {}
        self._teams: dict[UUID, Team] = {}
        self._role_kinds: dict[str, RoleKind] = {
            rk.id: rk for rk in (seed_role_kinds or [])
        }
        self._memberships: dict[UUID, TeamMembership] = {}
        self._api_keys: dict[UUID, ApiKey] = {}
        self._api_key_hashes: dict[UUID, str] = {}

    # --- People ---

    def create_person(self, payload: PersonCreate, *, actor: str) -> Person:
        email = payload.primary_email.strip().lower()
        if any(p.primary_email == email for p in self._people.values()):
            raise ValueError(f"primary_email already exists: {email}")
        now = _now()
        p = Person(
            id=uuid4(),
            display_name=payload.display_name,
            primary_email=email,
            active=True,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
        self._people[p.id] = p
        return p

    def get_person(self, person_id: UUID) -> Person | None:
        return self._people.get(person_id)

    def get_person_by_email(self, primary_email: str) -> Person | None:
        target = primary_email.strip().lower()
        for p in self._people.values():
            if p.primary_email == target:
                return p
        return None

    def list_people(self, *, active_only: bool = False) -> list[Person]:
        people = list(self._people.values())
        if active_only:
            people = [p for p in people if p.active]
        return people

    def update_person(
        self, person_id: UUID, payload: PersonUpdate, *, actor: str
    ) -> Person | None:
        existing = self._people.get(person_id)
        if existing is None:
            return None
        data = existing.model_dump()
        patch = payload.model_dump(exclude_unset=True)
        if "primary_email" in patch and patch["primary_email"] != existing.primary_email:
            new_email = patch["primary_email"]
            if any(
                p.primary_email == new_email and p.id != person_id
                for p in self._people.values()
            ):
                raise ValueError(f"primary_email already exists: {new_email}")
        data.update(patch)
        data["updated_at"] = _now()
        data["updated_by"] = actor
        updated = Person(**data)
        self._people[person_id] = updated
        return updated

    # --- Teams ---

    def create_team(self, payload: TeamCreate, *, actor: str) -> Team:
        if any(t.slug == payload.slug for t in self._teams.values()):
            raise ValueError(f"slug already exists: {payload.slug}")
        now = _now()
        t = Team(
            id=uuid4(),
            slug=payload.slug,
            label=payload.label,
            description=payload.description,
            parent_id=payload.parent_id,
            active=True,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
        self._teams[t.id] = t
        return t

    def get_team(self, team_id: UUID) -> Team | None:
        return self._teams.get(team_id)

    def get_team_by_slug(self, slug: str) -> Team | None:
        for t in self._teams.values():
            if t.slug == slug:
                return t
        return None

    def list_teams(self, *, active_only: bool = False) -> list[Team]:
        teams = list(self._teams.values())
        if active_only:
            teams = [t for t in teams if t.active]
        return teams

    def update_team(
        self, team_id: UUID, payload: TeamUpdate, *, actor: str
    ) -> Team | None:
        existing = self._teams.get(team_id)
        if existing is None:
            return None
        data = existing.model_dump()
        patch = payload.model_dump(exclude_unset=True)
        if "slug" in patch and patch["slug"] != existing.slug:
            if any(
                t.slug == patch["slug"] and t.id != team_id
                for t in self._teams.values()
            ):
                raise ValueError(f"slug already exists: {patch['slug']}")
        data.update(patch)
        data["updated_at"] = _now()
        data["updated_by"] = actor
        updated = Team(**data)
        self._teams[team_id] = updated
        return updated

    # --- Role kinds ---

    def get_role_kind(self, role_kind_id: str) -> RoleKind | None:
        return self._role_kinds.get(role_kind_id)

    def list_role_kinds(self, *, active_only: bool = False) -> list[RoleKind]:
        kinds = list(self._role_kinds.values())
        if active_only:
            kinds = [k for k in kinds if k.active]
        return kinds

    # --- Team memberships ---

    def create_membership(
        self, payload: TeamMembershipCreate, *, actor: str
    ) -> TeamMembership:
        if payload.person_id not in self._people:
            raise ValueError(f"person_id not found: {payload.person_id}")
        if payload.team_id not in self._teams:
            raise ValueError(f"team_id not found: {payload.team_id}")
        if payload.role_kind_id not in self._role_kinds:
            raise ValueError(f"role_kind_id not found: {payload.role_kind_id}")
        now = _now()
        m = TeamMembership(
            id=uuid4(),
            person_id=payload.person_id,
            team_id=payload.team_id,
            role_kind_id=payload.role_kind_id,
            is_team_admin=payload.is_team_admin,
            started_at=payload.started_at or date.today(),
            ended_at=payload.ended_at,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
        self._memberships[m.id] = m
        return m

    def get_membership(self, membership_id: UUID) -> TeamMembership | None:
        return self._memberships.get(membership_id)

    def list_memberships(
        self,
        *,
        team_id: UUID | None = None,
        person_id: UUID | None = None,
        active_only: bool = False,
        as_of: date | None = None,
        is_team_admin: bool | None = None,
    ) -> list[TeamMembership]:
        results = list(self._memberships.values())
        if team_id is not None:
            results = [m for m in results if m.team_id == team_id]
        if person_id is not None:
            results = [m for m in results if m.person_id == person_id]
        if active_only:
            results = [m for m in results if m.ended_at is None]
        if as_of is not None:
            results = [
                m
                for m in results
                if m.started_at <= as_of
                and (m.ended_at is None or m.ended_at > as_of)
            ]
        if is_team_admin is not None:
            results = [m for m in results if m.is_team_admin == is_team_admin]
        return results

    def update_membership(
        self, membership_id: UUID, payload: TeamMembershipUpdate, *, actor: str
    ) -> TeamMembership | None:
        existing = self._memberships.get(membership_id)
        if existing is None:
            return None
        data = existing.model_dump()
        patch = payload.model_dump(exclude_unset=True)
        if "role_kind_id" in patch and patch["role_kind_id"] not in self._role_kinds:
            raise ValueError(f"role_kind_id not found: {patch['role_kind_id']}")
        data.update(patch)
        data["updated_at"] = _now()
        data["updated_by"] = actor
        updated = TeamMembership(**data)
        self._memberships[membership_id] = updated
        return updated

    def end_membership(
        self, membership_id: UUID, ended_at: date, *, actor: str
    ) -> TeamMembership | None:
        """Set ended_at only.

        Delegates to update_membership; correctness relies on
        TeamMembershipUpdate.model_dump(exclude_unset=True) skipping fields
        the caller didn't set. If TeamMembershipUpdate ever grows a field
        with a non-None default, revisit this method.
        """
        return self.update_membership(
            membership_id, TeamMembershipUpdate(ended_at=ended_at), actor=actor
        )

    # --- API keys ---

    def create_api_key(
        self,
        *,
        name: str,
        prefix: str,
        key_hash: str,
        scopes: list[str],
        actor: str,
    ) -> ApiKey:
        if any(k.name == name for k in self._api_keys.values()):
            raise ValueError(f"name already exists: {name}")
        if any(k.prefix == prefix for k in self._api_keys.values()):
            raise ValueError(f"prefix already exists: {prefix}")
        now = _now()
        key = ApiKey(
            id=uuid4(),
            name=name,
            prefix=prefix,
            scopes=scopes,
            active=True,
            revoked_at=None,
            last_used_at=None,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
        self._api_keys[key.id] = key
        self._api_key_hashes[key.id] = key_hash
        return key

    def get_api_key_by_prefix(self, prefix: str) -> ApiKey | None:
        for k in self._api_keys.values():
            if k.prefix == prefix:
                return k
        return None

    def get_api_key_hash(self, prefix: str) -> str | None:
        for k in self._api_keys.values():
            if k.prefix == prefix and k.active and k.revoked_at is None:
                return self._api_key_hashes.get(k.id)
        return None

    def list_api_keys(self, *, active_only: bool = False) -> list[ApiKey]:
        keys = list(self._api_keys.values())
        if active_only:
            keys = [k for k in keys if k.active and k.revoked_at is None]
        return keys

    def revoke_api_key(self, api_key_id: UUID, *, actor: str) -> ApiKey | None:
        existing = self._api_keys.get(api_key_id)
        if existing is None:
            return None
        now = _now()
        data = existing.model_dump()
        data["active"] = False
        data["revoked_at"] = now
        data["updated_at"] = now
        data["updated_by"] = actor
        revoked = ApiKey(**data)
        self._api_keys[api_key_id] = revoked
        return revoked

    def touch_api_key_last_used(self, api_key_id: UUID) -> None:
        existing = self._api_keys.get(api_key_id)
        if existing is None:
            return
        data = existing.model_dump()
        data["last_used_at"] = _now()
        self._api_keys[api_key_id] = ApiKey(**data)
