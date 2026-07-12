from datetime import date

import pytest
from sqlalchemy.engine import Engine

from contracts.types import (
    PersonCreate,
    PersonIdentifierCreate,
    PersonIdentifierUpdate,
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
    with pytest.raises(ValueError):
        adapter.create_person(
            PersonCreate(display_name="B", primary_email="ALEX@UTMIST.CA"),
            actor="t",
        )


def test_update_person(adapter):
    p = adapter.create_person(
        PersonCreate(display_name="A", primary_email="a@utmist.ca"), actor="t"
    )
    updated = adapter.update_person(p.id, PersonUpdate(display_name="Alexandra"), actor="editor")
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
    m = adapter.create_membership(TeamMembershipCreate(person_id=p.id, team_id=team.id), actor="t")
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


def test_api_key_create_and_lookup_pg(adapter):
    key = adapter.create_api_key(
        name="discord-bot",
        prefix="tt_pg_1",
        key_hash="$argon2id$v=19$fake",
        scopes=["people:read"],
        actor="admin",
    )
    fetched = adapter.get_api_key_by_prefix("tt_pg_1")
    assert fetched is not None
    assert fetched.id == key.id
    assert adapter.get_api_key_hash("tt_pg_1") == "$argon2id$v=19$fake"


def test_api_key_name_conflict_pg(adapter):
    adapter.create_api_key(name="dup", prefix="tt_pg_x", key_hash="h", scopes=[], actor="admin")
    with pytest.raises(ValueError):
        adapter.create_api_key(name="dup", prefix="tt_pg_y", key_hash="h", scopes=[], actor="admin")


def test_revoke_and_touch_pg(adapter):
    key = adapter.create_api_key(
        name="bot-pg", prefix="tt_pg_r", key_hash="h", scopes=[], actor="admin"
    )
    adapter.touch_api_key_last_used(key.id)
    assert adapter.get_api_key_by_prefix("tt_pg_r").last_used_at is not None
    adapter.revoke_api_key(key.id, actor="admin")
    assert adapter.get_api_key_hash("tt_pg_r") is None


def test_pg_provider_seed_present(adapter):
    assert {p.id for p in adapter.list_providers()} >= {"discord", "github", "notion", "uoft_email"}
    assert adapter.get_provider("discord").label == "Discord"


def test_pg_identifier_crud_and_reverse_lookup(adapter):
    person = adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"), actor="t"
    )
    pi = adapter.create_person_identifier(
        person.id,
        PersonIdentifierCreate(provider="discord", external_id="123", handle="alex"),
        actor="bot",
    )
    assert pi.external_id == "123"
    assert [i.id for i in adapter.list_person_identifiers(person.id)] == [pi.id]

    found = adapter.get_person_by_identifier("discord", "123")
    assert found is not None and found.id == person.id

    updated = adapter.update_person_identifier(
        person.id, "discord", PersonIdentifierUpdate(handle="new"), actor="t"
    )
    assert updated.handle == "new"

    assert adapter.delete_person_identifier(person.id, "discord") is True
    assert adapter.delete_person_identifier(person.id, "discord") is False
    assert adapter.get_person_by_identifier("discord", "123") is None


def test_pg_duplicate_provider_raises(adapter):
    person = adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"), actor="t"
    )
    adapter.create_person_identifier(
        person.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t"
    )
    with pytest.raises(ValueError, match="already has an identifier for provider"):
        adapter.create_person_identifier(
            person.id, PersonIdentifierCreate(provider="discord", external_id="2"), actor="t"
        )


def test_pg_external_id_owned_by_another_person_raises(adapter):
    person_a = adapter.create_person(
        PersonCreate(display_name="Alex", primary_email="alex@utmist.ca"), actor="t"
    )
    person_b = adapter.create_person(
        PersonCreate(display_name="Blair", primary_email="blair@utmist.ca"), actor="t"
    )
    adapter.create_person_identifier(
        person_a.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t"
    )
    with pytest.raises(ValueError, match="linked to another person"):
        adapter.create_person_identifier(
            person_b.id, PersonIdentifierCreate(provider="discord", external_id="1"), actor="t"
        )


def _seed_person(adapter, email="a@x.com", name="A"):
    return adapter.create_person(PersonCreate(display_name=name, primary_email=email), actor="t")


def test_pg_add_multiple_emails_to_one_person(adapter):
    p = _seed_person(adapter, "p@x.com")
    adapter.add_person_email(p.id, "one@x.com", actor="t")
    adapter.add_person_email(p.id, "two@x.com", actor="t")
    emails = [i.external_id for i in adapter.list_person_identifiers(p.id) if i.provider == "email"]
    assert sorted(emails) == ["one@x.com", "two@x.com"]


def test_pg_add_email_normalizes(adapter):
    p = _seed_person(adapter, "p@x.com")
    adapter.add_person_email(p.id, "  MixEd@Case.COM ", actor="t")
    assert adapter.get_person_by_identifier("email", "mixed@case.com").id == p.id


def test_pg_add_email_idempotent(adapter):
    p = _seed_person(adapter, "p@x.com")
    first = adapter.add_person_email(p.id, "e@x.com", actor="t")
    again = adapter.add_person_email(p.id, "E@X.com", actor="t")
    assert again.id == first.id
    assert sum(i.provider == "email" for i in adapter.list_person_identifiers(p.id)) == 1


def test_pg_add_email_rejects_another_persons_identifier(adapter):
    a = _seed_person(adapter, "a@x.com", "A")
    b = _seed_person(adapter, "b@x.com", "B")
    adapter.add_person_email(a.id, "shared@x.com", actor="t")
    with pytest.raises(ValueError, match="email_registered_to_another"):
        adapter.add_person_email(b.id, "shared@x.com", actor="t")


def test_pg_add_email_rejects_another_persons_primary(adapter):
    _seed_person(adapter, "a@x.com", "A")
    b = _seed_person(adapter, "b@x.com", "B")
    with pytest.raises(ValueError, match="email_registered_to_another"):
        adapter.add_person_email(b.id, "A@X.com", actor="t")  # a's primary


def test_pg_add_email_own_primary_creates_identifier(adapter):
    p = _seed_person(adapter, "me@x.com")
    ident = adapter.add_person_email(p.id, "Me@X.com", actor="t")
    assert ident.provider == "email"
    assert ident.external_id == "me@x.com"
    email_idents = [i for i in adapter.list_person_identifiers(p.id) if i.provider == "email"]
    assert len(email_idents) == 1

    again = adapter.add_person_email(p.id, "Me@X.com", actor="t")
    assert again.id == ident.id
    email_idents = [i for i in adapter.list_person_identifiers(p.id) if i.provider == "email"]
    assert len(email_idents) == 1


def test_pg_add_person_email_uses_on_conflict_do_nothing_path(adapter):
    """Exercises the new on_conflict_do_nothing + re-read code path directly
    (item 1). A true concurrent same-person race isn't deterministically
    reproducible in a unit test, but repeat calls through the same insert
    statement must still return the same row idempotently."""
    p = _seed_person(adapter, "race@x.com")
    first = adapter.add_person_email(p.id, "shared-addr@x.com", actor="t")
    again = adapter.add_person_email(p.id, "shared-addr@x.com", actor="t")
    assert again.id == first.id
    email_idents = [i for i in adapter.list_person_identifiers(p.id) if i.provider == "email"]
    assert len(email_idents) == 1


def test_pg_add_person_email_rejects_blank(adapter):
    p = _seed_person(adapter, "p2@x.com")
    with pytest.raises(ValueError, match="email_must_not_be_empty"):
        adapter.add_person_email(p.id, "   ", actor="t")


def test_pg_generic_identifier_ops_reject_email_provider(adapter):
    p = _seed_person(adapter, "p@x.com")
    with pytest.raises(ValueError, match="email_not_addressable_by_provider"):
        adapter.create_person_identifier(
            p.id, PersonIdentifierCreate(provider="email", external_id="e@x.com"), actor="t"
        )
    with pytest.raises(ValueError, match="email_not_addressable_by_provider"):
        adapter.update_person_identifier(
            p.id, "email", PersonIdentifierUpdate(external_id="e@x.com"), actor="t"
        )
    with pytest.raises(ValueError, match="email_not_addressable_by_provider"):
        adapter.delete_person_identifier(p.id, "email")
