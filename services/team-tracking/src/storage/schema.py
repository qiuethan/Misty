"""SQLAlchemy Core Table definitions for the team-tracking base schema.

This module defines TABLES, not ORM classes. All queries in
PostgresStorageAdapter use core-style expressions against these tables.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, UUID

metadata = MetaData()

people = Table(
    "people",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("display_name", Text, nullable=False),
    Column("primary_email", CITEXT, nullable=False, unique=True),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("access_level", Text, nullable=False, server_default=text("'member'")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
)

teams = Table(
    "teams",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("slug", Text, nullable=False, unique=True),
    Column("label", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("parent_id", UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
)

role_kinds = Table(
    "role_kinds",
    metadata,
    Column("id", Text, primary_key=True),  # slug PK
    Column("label", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
)

team_memberships = Table(
    "team_memberships",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("person_id", UUID(as_uuid=True), ForeignKey("people.id"), nullable=False),
    Column("team_id", UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False),
    Column(
        "role_kind_id",
        Text,
        ForeignKey("role_kinds.id"),
        nullable=False,
        server_default=text("'member'"),
    ),
    Column("is_team_admin", Boolean, nullable=False, server_default=text("false")),
    Column("started_at", Date, nullable=False, server_default=text("CURRENT_DATE")),
    Column("ended_at", Date, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
    Index("ix_team_memberships_team_ended", "team_id", "ended_at"),
    Index("ix_team_memberships_person_ended", "person_id", "ended_at"),
    Index("ix_team_memberships_dates", "started_at", "ended_at"),
)

api_keys = Table(
    "api_keys",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("name", Text, nullable=False, unique=True),
    Column("prefix", Text, nullable=False, unique=True),
    Column("key_hash", Text, nullable=False),
    Column("scopes", ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("last_used_at", DateTime(timezone=True), nullable=True),
)

providers = Table(
    "providers",
    metadata,
    Column("id", Text, primary_key=True),  # slug PK
    Column("label", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
)

person_identifiers = Table(
    "person_identifiers",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("person_id", UUID(as_uuid=True), ForeignKey("people.id"), nullable=False),
    Column("provider", Text, ForeignKey("providers.id"), nullable=False),
    Column("external_id", Text, nullable=False),
    Column("handle", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
    # One account per provider per person (except email, which is multi-valued);
    # and one account maps to one person. The (provider, external_id) unique
    # index also powers the reverse lookup, so no separate Index is needed.
    UniqueConstraint("provider", "external_id", name="uq_person_identifiers_provider_external"),
)

Index(
    "uq_person_identifiers_person_provider",
    person_identifiers.c.person_id,
    person_identifiers.c.provider,
    unique=True,
    postgresql_where=text("provider <> 'email'"),
)
