from datetime import date, datetime, timezone
from uuid import uuid4

from contracts.types import Person, RoleKind, Team, TeamMembership


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_person_has_expected_fields():
    p = Person(
        id=uuid4(),
        display_name="Alex Chen",
        primary_email="alex@utmist.ca",
        active=True,
        created_at=_now(),
        updated_at=_now(),
        created_by="system",
        updated_by="system",
    )
    assert p.display_name == "Alex Chen"
    assert p.primary_email == "alex@utmist.ca"
    assert p.active is True


def test_person_primary_email_lowercased():
    p = Person(
        id=uuid4(),
        display_name="Alex",
        primary_email="Alex@UTMIST.CA",
        active=True,
        created_at=_now(),
        updated_at=_now(),
        created_by="system",
        updated_by="system",
    )
    assert p.primary_email == "alex@utmist.ca"


def test_team_hierarchy_field():
    parent_id = uuid4()
    t = Team(
        id=uuid4(),
        slug="events.agi_workshop_2025",
        label="AGI Workshop 2025 Team",
        description=None,
        parent_id=parent_id,
        active=True,
        created_at=_now(),
        updated_at=_now(),
        created_by="system",
        updated_by="system",
    )
    assert t.parent_id == parent_id


def test_role_kind_uses_slug_id():
    rk = RoleKind(
        id="lead",
        label="Lead",
        description=None,
        active=True,
        created_at=_now(),
        updated_at=_now(),
        created_by="system",
        updated_by="system",
    )
    assert rk.id == "lead"


def test_team_membership_defaults():
    m = TeamMembership(
        id=uuid4(),
        person_id=uuid4(),
        team_id=uuid4(),
        role_kind_id="member",
        is_team_admin=False,
        started_at=date.today(),
        ended_at=None,
        created_at=_now(),
        updated_at=_now(),
        created_by="system",
        updated_by="system",
    )
    assert m.role_kind_id == "member"
    assert m.is_team_admin is False
    assert m.ended_at is None


def test_extra_fields_are_forbidden():
    """extra='forbid' rejects unknown fields at construction time."""
    import pytest
    from pydantic import ValidationError

    from contracts.types import PersonCreate

    with pytest.raises(ValidationError):
        PersonCreate(
            display_name="Alex",
            primary_email="alex@utmist.ca",
            rogue_field="nope",
        )


def test_person_create_normalizes_email():
    """Regression test: PersonCreate applies the same normalization as Person."""
    from contracts.types import PersonCreate

    payload = PersonCreate(display_name="Alex", primary_email="  Alex@UTMIST.CA  ")
    assert payload.primary_email == "alex@utmist.ca"


def test_person_update_email_normalization_handles_none():
    """PersonUpdate with primary_email=None must not raise on the normalizer."""
    from contracts.types import PersonUpdate

    patch = PersonUpdate(primary_email=None)
    assert patch.primary_email is None


def test_team_membership_create_started_at_defaults_to_none():
    """The contract is 'defaults to today at storage layer' — the DTO holds None."""
    from uuid import uuid4

    from contracts.types import TeamMembershipCreate

    m = TeamMembershipCreate(person_id=uuid4(), team_id=uuid4())
    assert m.started_at is None


def test_team_create_rejects_bad_slug():
    """Slugs must match [a-z0-9_.]+ per DESIGN.md."""
    import pytest
    from pydantic import ValidationError

    from contracts.types import TeamCreate

    with pytest.raises(ValidationError):
        TeamCreate(slug="My Team!", label="x")


def test_team_create_accepts_good_slug():
    from contracts.types import TeamCreate

    ok = TeamCreate(slug="events.agi_workshop_2025", label="AGI")
    assert ok.slug == "events.agi_workshop_2025"


def _audit():
    now = datetime.now(timezone.utc)
    return dict(created_at=now, updated_at=now, created_by="t", updated_by="t")


def test_provider_model_roundtrips():
    from contracts.types import Provider

    p = Provider(id="discord", label="Discord", **_audit())
    assert p.id == "discord"
    assert p.active is True
    assert p.description is None


def test_person_identifier_model_roundtrips():
    from contracts.types import PersonIdentifier

    pi = PersonIdentifier(
        id=uuid4(),
        person_id=uuid4(),
        provider="discord",
        external_id="123456789",
        handle="alex#0001",
        **_audit(),
    )
    assert pi.provider == "discord"
    assert pi.external_id == "123456789"
    assert pi.handle == "alex#0001"


def test_identifier_create_defaults_handle_none():
    from contracts.types import PersonIdentifierCreate

    c = PersonIdentifierCreate(provider="github", external_id="42")
    assert c.handle is None


def test_identifier_update_is_partial():
    from contracts.types import PersonIdentifierUpdate

    u = PersonIdentifierUpdate(handle="newhandle")
    assert u.model_dump(exclude_unset=True) == {"handle": "newhandle"}


def test_identifier_create_rejects_extra_fields():
    import pytest
    from pydantic import ValidationError

    from contracts.types import PersonIdentifierCreate

    with pytest.raises(ValidationError):
        PersonIdentifierCreate(provider="discord", external_id="1", person_id=uuid4())
