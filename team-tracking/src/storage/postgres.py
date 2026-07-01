from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.engine import Engine

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
from src.storage.schema import people, role_kinds, team_memberships, teams


def _person_row_to_model(row) -> Person:
    return Person(
        id=row.id,
        display_name=row.display_name,
        primary_email=row.primary_email,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _team_row_to_model(row) -> Team:
    return Team(
        id=row.id,
        slug=row.slug,
        label=row.label,
        description=row.description,
        parent_id=row.parent_id,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _role_kind_row_to_model(row) -> RoleKind:
    return RoleKind(
        id=row.id,
        label=row.label,
        description=row.description,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _membership_row_to_model(row) -> TeamMembership:
    return TeamMembership(
        id=row.id,
        person_id=row.person_id,
        team_id=row.team_id,
        role_kind_id=row.role_kind_id,
        is_team_admin=row.is_team_admin,
        started_at=row.started_at,
        ended_at=row.ended_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


class PostgresStorageAdapter:
    """Postgres-backed StorageAdapter using SQLAlchemy Core.

    Every method returns Pydantic domain models (never raw rows). Callers should
    not need to know this backend exists — they see StorageAdapter (Protocol).
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # --- People ---

    def create_person(self, payload: PersonCreate, *, actor: str) -> Person:
        with self._engine.begin() as conn:
            row = conn.execute(
                insert(people)
                .values(
                    display_name=payload.display_name,
                    primary_email=payload.primary_email,
                    created_by=actor,
                    updated_by=actor,
                )
                .returning(people)
            ).one()
        return _person_row_to_model(row)

    def get_person(self, person_id: UUID) -> Person | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(people).where(people.c.id == person_id)
            ).one_or_none()
        return _person_row_to_model(row) if row else None

    def get_person_by_email(self, primary_email: str) -> Person | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(people).where(people.c.primary_email == primary_email)
            ).one_or_none()
        return _person_row_to_model(row) if row else None

    def list_people(self, *, active_only: bool = False) -> list[Person]:
        stmt = select(people)
        if active_only:
            stmt = stmt.where(people.c.active.is_(True))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [_person_row_to_model(r) for r in rows]

    def update_person(
        self, person_id: UUID, payload: PersonUpdate, *, actor: str
    ) -> Person | None:
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            return self.get_person(person_id)
        patch["updated_at"] = datetime.utcnow()
        patch["updated_by"] = actor
        with self._engine.begin() as conn:
            row = conn.execute(
                update(people)
                .where(people.c.id == person_id)
                .values(**patch)
                .returning(people)
            ).one_or_none()
        return _person_row_to_model(row) if row else None

    # --- Teams ---

    def create_team(self, payload: TeamCreate, *, actor: str) -> Team:
        with self._engine.begin() as conn:
            row = conn.execute(
                insert(teams)
                .values(
                    slug=payload.slug,
                    label=payload.label,
                    description=payload.description,
                    parent_id=payload.parent_id,
                    created_by=actor,
                    updated_by=actor,
                )
                .returning(teams)
            ).one()
        return _team_row_to_model(row)

    def get_team(self, team_id: UUID) -> Team | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(teams).where(teams.c.id == team_id)
            ).one_or_none()
        return _team_row_to_model(row) if row else None

    def get_team_by_slug(self, slug: str) -> Team | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(teams).where(teams.c.slug == slug)
            ).one_or_none()
        return _team_row_to_model(row) if row else None

    def list_teams(self, *, active_only: bool = False) -> list[Team]:
        stmt = select(teams)
        if active_only:
            stmt = stmt.where(teams.c.active.is_(True))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [_team_row_to_model(r) for r in rows]

    def update_team(
        self, team_id: UUID, payload: TeamUpdate, *, actor: str
    ) -> Team | None:
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            return self.get_team(team_id)
        patch["updated_at"] = datetime.utcnow()
        patch["updated_by"] = actor
        with self._engine.begin() as conn:
            row = conn.execute(
                update(teams)
                .where(teams.c.id == team_id)
                .values(**patch)
                .returning(teams)
            ).one_or_none()
        return _team_row_to_model(row) if row else None

    # --- Role kinds ---

    def get_role_kind(self, role_kind_id: str) -> RoleKind | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(role_kinds).where(role_kinds.c.id == role_kind_id)
            ).one_or_none()
        return _role_kind_row_to_model(row) if row else None

    def list_role_kinds(self, *, active_only: bool = False) -> list[RoleKind]:
        stmt = select(role_kinds)
        if active_only:
            stmt = stmt.where(role_kinds.c.active.is_(True))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [_role_kind_row_to_model(r) for r in rows]

    # --- Team memberships ---

    def create_membership(
        self, payload: TeamMembershipCreate, *, actor: str
    ) -> TeamMembership:
        values = {
            "person_id": payload.person_id,
            "team_id": payload.team_id,
            "role_kind_id": payload.role_kind_id,
            "is_team_admin": payload.is_team_admin,
            "ended_at": payload.ended_at,
            "created_by": actor,
            "updated_by": actor,
        }
        if payload.started_at is not None:
            values["started_at"] = payload.started_at
        with self._engine.begin() as conn:
            row = conn.execute(
                insert(team_memberships).values(**values).returning(team_memberships)
            ).one()
        return _membership_row_to_model(row)

    def get_membership(self, membership_id: UUID) -> TeamMembership | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(team_memberships).where(team_memberships.c.id == membership_id)
            ).one_or_none()
        return _membership_row_to_model(row) if row else None

    def list_memberships(
        self,
        *,
        team_id: UUID | None = None,
        person_id: UUID | None = None,
        active_only: bool = False,
        as_of: date | None = None,
        is_team_admin: bool | None = None,
    ) -> list[TeamMembership]:
        stmt = select(team_memberships)
        conditions = []
        if team_id is not None:
            conditions.append(team_memberships.c.team_id == team_id)
        if person_id is not None:
            conditions.append(team_memberships.c.person_id == person_id)
        if active_only:
            conditions.append(team_memberships.c.ended_at.is_(None))
        if as_of is not None:
            conditions.append(team_memberships.c.started_at <= as_of)
            conditions.append(
                or_(
                    team_memberships.c.ended_at.is_(None),
                    team_memberships.c.ended_at > as_of,
                )
            )
        if is_team_admin is not None:
            conditions.append(team_memberships.c.is_team_admin.is_(is_team_admin))
        if conditions:
            stmt = stmt.where(and_(*conditions))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [_membership_row_to_model(r) for r in rows]

    def update_membership(
        self, membership_id: UUID, payload: TeamMembershipUpdate, *, actor: str
    ) -> TeamMembership | None:
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            return self.get_membership(membership_id)
        patch["updated_at"] = datetime.utcnow()
        patch["updated_by"] = actor
        with self._engine.begin() as conn:
            row = conn.execute(
                update(team_memberships)
                .where(team_memberships.c.id == membership_id)
                .values(**patch)
                .returning(team_memberships)
            ).one_or_none()
        return _membership_row_to_model(row) if row else None

    def end_membership(
        self, membership_id: UUID, ended_at: date, *, actor: str
    ) -> TeamMembership | None:
        return self.update_membership(
            membership_id, TeamMembershipUpdate(ended_at=ended_at), actor=actor
        )
