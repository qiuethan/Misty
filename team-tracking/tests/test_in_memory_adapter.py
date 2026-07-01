from datetime import date, timedelta
from uuid import uuid4

import pytest

from conftest import build_seed_providers, build_seed_role_kinds
from contracts.types import (
    PersonCreate,
    PersonIdentifierCreate,
    PersonIdentifierUpdate,
    PersonUpdate,
    TeamCreate,
    TeamMembershipCreate,
    TeamMembershipUpdate,
)
from src.storage.in_memory import InMemoryStorageAdapter


@pytest.fixture
def adapter() -> InMemoryStorageAdapter:
    return InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())


def test_create_and_get_person(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"),
        actor="test",
    )
    fetched = adapter.get_person(p.id)
    assert fetched is not None
    assert fetched.display_name == "Alex"
    assert fetched.primary_email == "alex@utmist.ca"
    assert fetched.created_by == "test"


def test_email_uniqueness_case_insensitive(adapter):
    adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"),
        actor="test",
    )
    with pytest.raises(ValueError):
        adapter.create_person(
            PersonCreate(display_name="Other", primary_email="ALEX@UTMIST.CA"),
            actor="test",
        )


def test_update_person(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"),
        actor="test",
    )
    updated = adapter.update_person(
        p.id, PersonUpdate(display_name="Alexandra"), actor="editor"
    )
    assert updated is not None
    assert updated.display_name == "Alexandra"
    assert updated.updated_by == "editor"


def test_create_and_list_teams(adapter):
    parent = adapter.create_team(
        TeamCreate(slug="events", label="Events"), actor="test"
    )
    child = adapter.create_team(
        TeamCreate(
            slug="events.agi_workshop_2025",
            label="AGI Workshop 2025",
            parent_id=parent.id,
        ),
        actor="test",
    )
    teams = adapter.list_teams()
    assert {t.slug for t in teams} == {"events", "events.agi_workshop_2025"}
    assert child.parent_id == parent.id


def test_role_kinds_seeded(adapter):
    kinds = adapter.list_role_kinds()
    assert {k.id for k in kinds} == {"executive", "director", "lead", "member"}


def test_membership_create_defaults(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"),
        actor="test",
    )
    t = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="test")
    m = adapter.create_membership(
        TeamMembershipCreate(person_id=p.id, team_id=t.id),
        actor="test",
    )
    assert m.role_kind_id == "member"
    assert m.started_at == date.today()
    assert m.ended_at is None
    assert m.is_team_admin is False


def test_membership_list_filters(adapter):
    p1 = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    p2 = adapter.create_person(
        PersonCreate(display_name="B", primary_email="b@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    other = adapter.create_team(TeamCreate(slug="ev", label="Events"), actor="t")
    adapter.create_membership(
        TeamMembershipCreate(person_id=p1.id, team_id=team.id), actor="t"
    )
    adapter.create_membership(
        TeamMembershipCreate(person_id=p2.id, team_id=team.id), actor="t"
    )
    adapter.create_membership(
        TeamMembershipCreate(person_id=p1.id, team_id=other.id), actor="t"
    )
    assert len(adapter.list_memberships(team_id=team.id)) == 2
    assert len(adapter.list_memberships(person_id=p1.id)) == 2


def test_end_membership_sets_ended_at(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    m = adapter.create_membership(
        TeamMembershipCreate(person_id=p.id, team_id=team.id), actor="t"
    )
    end_date = date.today() + timedelta(days=30)
    ended = adapter.end_membership(m.id, end_date, actor="t")
    assert ended is not None
    assert ended.ended_at == end_date
    active = adapter.list_memberships(team_id=team.id, active_only=True)
    assert len(active) == 0


def test_as_of_date_filter(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    m = adapter.create_membership(
        TeamMembershipCreate(
            person_id=p.id,
            team_id=team.id,
            started_at=date(2024, 9, 1),
            ended_at=date(2025, 4, 30),
        ),
        actor="t",
    )
    assert m.started_at == date(2024, 9, 1)
    as_of_active = adapter.list_memberships(as_of=date(2025, 1, 15))
    assert len(as_of_active) == 1
    as_of_before = adapter.list_memberships(as_of=date(2024, 8, 1))
    assert len(as_of_before) == 0
    as_of_after = adapter.list_memberships(as_of=date(2025, 6, 1))
    assert len(as_of_after) == 0


def test_is_team_admin_filter(adapter):
    """Regression test for the DESIGN.md 'current team admins' query."""
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


def test_fk_checks_on_membership_create(adapter):
    """Membership create fails cleanly when FKs don't exist."""
    from uuid import uuid4

    with pytest.raises(ValueError):
        adapter.create_membership(
            TeamMembershipCreate(person_id=uuid4(), team_id=uuid4()),
            actor="t",
        )


def test_update_membership_role_kind_validation(adapter):
    """Updating with a nonexistent role_kind fails."""
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    m = adapter.create_membership(
        TeamMembershipCreate(person_id=p.id, team_id=team.id), actor="t"
    )
    with pytest.raises(ValueError):
        adapter.update_membership(
            m.id,
            TeamMembershipUpdate(role_kind_id="nonexistent"),
            actor="t",
        )


def test_get_person_by_email_case_insensitive(adapter):
    adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    found = adapter.get_person_by_email("A@UTMIST.CA")
    assert found is not None
    assert found.primary_email == "a@utmist.ca"


def test_get_team_by_slug(adapter):
    adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    found = adapter.get_team_by_slug("ops")
    assert found is not None
    assert found.label == "Ops"
    assert adapter.get_team_by_slug("nonexistent") is None


def test_get_role_kind(adapter):
    lead = adapter.get_role_kind("lead")
    assert lead is not None
    assert lead.label == "Lead"
    assert adapter.get_role_kind("nonexistent") is None


def test_update_person_email_conflict(adapter):
    """update_person with an email that conflicts with another person raises."""
    adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    p2 = adapter.create_person(
        PersonCreate(display_name="B", primary_email="b@utmist.ca"), actor="t"
    )
    with pytest.raises(ValueError):
        adapter.update_person(
            p2.id, PersonUpdate(primary_email="A@UTMIST.CA"), actor="t"
        )


def test_update_team_slug_conflict(adapter):
    """update_team with a slug that conflicts with another team raises."""
    adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    t2 = adapter.create_team(TeamCreate(slug="events", label="Events"), actor="t")
    from contracts.types import TeamUpdate

    with pytest.raises(ValueError):
        adapter.update_team(t2.id, TeamUpdate(slug="ops"), actor="t")


def test_end_membership_on_nonexistent_returns_none(adapter):
    """end_membership on a nonexistent id returns None, does not raise."""
    from uuid import uuid4

    result = adapter.end_membership(uuid4(), date.today(), actor="t")
    assert result is None


def test_list_memberships_active_only_direct(adapter):
    """active_only filter returns only rows where ended_at is None."""
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    team = adapter.create_team(TeamCreate(slug="ops", label="Ops"), actor="t")
    m_active = adapter.create_membership(
        TeamMembershipCreate(person_id=p.id, team_id=team.id), actor="t"
    )
    adapter.create_membership(
        TeamMembershipCreate(
            person_id=p.id, team_id=team.id, ended_at=date(2020, 1, 1)
        ),
        actor="t",
    )
    all_rows = adapter.list_memberships()
    active_rows = adapter.list_memberships(active_only=True)
    assert len(all_rows) == 2
    assert len(active_rows) == 1
    assert active_rows[0].id == m_active.id


def test_api_key_create_and_lookup(adapter):
    key = adapter.create_api_key(
        name="discord-bot",
        prefix="tt_abc123",
        key_hash="$argon2id$v=19$fake_hash",
        scopes=["people:read", "memberships:write"],
        actor="admin",
    )
    assert key.name == "discord-bot"
    assert key.prefix == "tt_abc123"
    assert key.scopes == ["people:read", "memberships:write"]
    assert key.active is True

    fetched = adapter.get_api_key_by_prefix("tt_abc123")
    assert fetched is not None
    assert fetched.id == key.id

    h = adapter.get_api_key_hash("tt_abc123")
    assert h == "$argon2id$v=19$fake_hash"


def test_api_key_name_unique(adapter):
    adapter.create_api_key(
        name="bot", prefix="tt_a", key_hash="h1", scopes=[], actor="admin"
    )
    with pytest.raises(ValueError):
        adapter.create_api_key(
            name="bot", prefix="tt_b", key_hash="h2", scopes=[], actor="admin"
        )


def test_api_key_prefix_unique(adapter):
    adapter.create_api_key(
        name="a", prefix="tt_x", key_hash="h1", scopes=[], actor="admin"
    )
    with pytest.raises(ValueError):
        adapter.create_api_key(
            name="b", prefix="tt_x", key_hash="h2", scopes=[], actor="admin"
        )


def test_revoke_api_key(adapter):
    key = adapter.create_api_key(
        name="bot", prefix="tt_p", key_hash="h", scopes=[], actor="admin"
    )
    revoked = adapter.revoke_api_key(key.id, actor="admin")
    assert revoked is not None
    assert revoked.active is False
    assert revoked.revoked_at is not None
    # get_api_key_hash returns None for revoked keys (auth path)
    assert adapter.get_api_key_hash("tt_p") is None
    # get_api_key_by_prefix still returns it (admin visibility)
    assert adapter.get_api_key_by_prefix("tt_p") is not None


def test_touch_api_key_last_used(adapter):
    key = adapter.create_api_key(
        name="bot", prefix="tt_l", key_hash="h", scopes=[], actor="admin"
    )
    assert key.last_used_at is None
    adapter.touch_api_key_last_used(key.id)
    assert adapter.get_api_key_by_prefix("tt_l").last_used_at is not None


def test_touch_api_key_nonexistent_is_noop(adapter):
    from uuid import uuid4
    # Must not raise
    adapter.touch_api_key_last_used(uuid4())


def test_list_api_keys_active_only(adapter):
    k1 = adapter.create_api_key(name="a", prefix="tt_a", key_hash="h", scopes=[], actor="admin")
    adapter.create_api_key(name="b", prefix="tt_b", key_hash="h", scopes=[], actor="admin")
    adapter.revoke_api_key(k1.id, actor="admin")
    assert len(adapter.list_api_keys()) == 2
    assert len(adapter.list_api_keys(active_only=True)) == 1


def _adapter():
    return InMemoryStorageAdapter(
        seed_role_kinds=build_seed_role_kinds(),
        seed_providers=build_seed_providers(),
    )


def _person(a):
    return a.create_person(PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"), actor="t")


def test_list_and_get_providers():
    a = _adapter()
    assert {p.id for p in a.list_providers()} == {"discord", "github", "notion", "uoft_email"}
    assert a.get_provider("discord").label == "Discord"
    assert a.get_provider("nope") is None


def test_create_and_list_identifier():
    a = _adapter()
    p = _person(a)
    pi = a.create_person_identifier(
        p.id, PersonIdentifierCreate(provider="discord", external_id="123", handle="alex"), actor="bot"
    )
    assert pi.provider == "discord" and pi.external_id == "123"
    assert pi.created_by == "bot"
    assert [i.id for i in a.list_person_identifiers(p.id)] == [pi.id]


def test_duplicate_provider_for_person_raises():
    a = _adapter()
    p = _person(a)
    a.create_person_identifier(p.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t")
    with pytest.raises(ValueError):
        a.create_person_identifier(p.id, PersonIdentifierCreate(provider="discord", external_id="2"), actor="t")


def test_external_id_owned_by_another_person_raises():
    a = _adapter()
    p1 = _person(a)
    p2 = a.create_person(PersonCreate(display_name="Bo", primary_email="bo@utmist.ca"), actor="t")
    a.create_person_identifier(p1.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t")
    with pytest.raises(ValueError):
        a.create_person_identifier(p2.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t")


def test_reverse_lookup_returns_person():
    a = _adapter()
    p = _person(a)
    a.create_person_identifier(p.id, PersonIdentifierCreate(provider="discord", external_id="999"), actor="t")
    found = a.get_person_by_identifier("discord", "999")
    assert found is not None and found.id == p.id
    assert a.get_person_by_identifier("discord", "absent") is None


def test_update_and_delete_identifier():
    a = _adapter()
    p = _person(a)
    a.create_person_identifier(p.id, PersonIdentifierCreate(provider="discord", external_id="1", handle="old"), actor="t")
    updated = a.update_person_identifier(p.id, "discord", PersonIdentifierUpdate(handle="new"), actor="t")
    assert updated.handle == "new" and updated.external_id == "1"
    assert a.update_person_identifier(p.id, "github", PersonIdentifierUpdate(handle="x"), actor="t") is None
    assert a.delete_person_identifier(p.id, "discord") is True
    assert a.delete_person_identifier(p.id, "discord") is False


def test_update_person_identifier_external_id_collision_raises():
    """Updating external_id to a value owned by another person raises ValueError."""
    a = _adapter()
    p1 = _person(a)
    p2 = a.create_person(PersonCreate(display_name="Bo", primary_email="bo@utmist.ca"), actor="t")
    a.create_person_identifier(p1.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t")
    a.create_person_identifier(p2.id, PersonIdentifierCreate(provider="discord", external_id="2"), actor="t")
    with pytest.raises(ValueError):
        a.update_person_identifier(p2.id, "discord", PersonIdentifierUpdate(external_id="1"), actor="t")


def test_update_person_identifier_external_id_change_succeeds():
    """Updating external_id to a new unclaimed value succeeds and updates reverse lookup."""
    a = _adapter()
    p = _person(a)
    a.create_person_identifier(p.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t")
    updated = a.update_person_identifier(p.id, "discord", PersonIdentifierUpdate(external_id="2"), actor="t")
    assert updated is not None
    assert updated.external_id == "2"
    found_by_new = a.get_person_by_identifier("discord", "2")
    assert found_by_new is not None and found_by_new.id == p.id
    found_by_old = a.get_person_by_identifier("discord", "1")
    assert found_by_old is None
