from datetime import date

import pytest
from sqlalchemy.engine import Engine

from contracts.types import (
    PersonCreate,
    PersonUpdate,
    TeamCreate,
    TeamMembershipCreate,
    TeamMembershipUpdate,
)
from src.storage.postgres import PostgresStorageAdapter


@pytest.fixture
def adapter(clean_db: Engine) -> PostgresStorageAdapter:
    return PostgresStorageAdapter(clean_db)


def test_create_and_get_person(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"),
        actor="test",
    )
    fetched = adapter.get_person(p.id)
    assert fetched is not None
    assert fetched.display_name == "Alex"
    assert fetched.primary_email == "alex@utmist.ca"


def test_email_uniqueness_case_insensitive(adapter):
    adapter.create_person(
        PersonCreate(display_name="A", primary_email="alex@utmist.ca"),
        actor="t",
    )
    with pytest.raises(Exception):  # IntegrityError from citext unique
        adapter.create_person(
            PersonCreate(display_name="B", primary_email="ALEX@UTMIST.CA"),
            actor="t",
        )


def test_update_person(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    updated = adapter.update_person(
        p.id, PersonUpdate(display_name="Alexandra"), actor="editor"
    )
    assert updated is not None
    assert updated.display_name == "Alexandra"
    assert updated.updated_by == "editor"


def test_team_hierarchy(adapter):
    parent = adapter.create_team(TeamCreate(slug="events", label="Events"), actor="t")
    child = adapter.create_team(
        TeamCreate(slug="events.agi", label="AGI", parent_id=parent.id),
        actor="t",
    )
    assert child.parent_id == parent.id


def test_role_kinds_seeded(adapter):
    kinds = adapter.list_role_kinds()
    assert {k.id for k in kinds} == {"executive", "director", "lead", "member"}


def test_membership_full_cycle(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    m = adapter.create_membership(
        TeamMembershipCreate(person_id=p.id, team_id=team.id), actor="t"
    )
    assert m.role_kind_id == "member"
    assert m.is_team_admin is False

    made_admin = adapter.update_membership(
        m.id, TeamMembershipUpdate(is_team_admin=True), actor="t"
    )
    assert made_admin is not None
    assert made_admin.is_team_admin is True

    end = date(2026, 12, 31)
    ended = adapter.end_membership(m.id, end, actor="t")
    assert ended is not None
    assert ended.ended_at == end

    active = adapter.list_memberships(team_id=team.id, active_only=True)
    assert len(active) == 0


def test_as_of_query(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    adapter.create_membership(
        TeamMembershipCreate(
            person_id=p.id,
            team_id=team.id,
            started_at=date(2024, 9, 1),
            ended_at=date(2025, 4, 30),
        ),
        actor="t",
    )
    assert len(adapter.list_memberships(as_of=date(2024, 12, 1))) == 1
    assert len(adapter.list_memberships(as_of=date(2025, 6, 1))) == 0


def test_is_team_admin_filter(adapter):
    p1 = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    p2 = adapter.create_person(
        PersonCreate(display_name="B", primary_email="b@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    adapter.create_membership(
        TeamMembershipCreate(person_id=p1.id, team_id=team.id, is_team_admin=True),
        actor="t",
    )
    adapter.create_membership(
        TeamMembershipCreate(person_id=p2.id, team_id=team.id),
        actor="t",
    )
    admins = adapter.list_memberships(team_id=team.id, is_team_admin=True)
    non_admins = adapter.list_memberships(team_id=team.id, is_team_admin=False)
    assert len(admins) == 1
    assert len(non_admins) == 1
