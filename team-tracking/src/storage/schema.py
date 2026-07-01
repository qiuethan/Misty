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
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID

metadata = MetaData()

people = Table(
    "people",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("display_name", Text, nullable=False),
    Column("primary_email", CITEXT, nullable=False, unique=True),
    Column("active", Boolean, nullable=False, server_default=text("true")),
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
    Column("role_kind_id", Text, ForeignKey("role_kinds.id"), nullable=False, server_default=text("'member'")),
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
