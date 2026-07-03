"""SQLAlchemy Core Table definitions for the documentation-system schema."""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, MetaData, Table, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

metadata = MetaData()

sources = Table(
    "sources", metadata,
    Column("id", Text, primary_key=True),  # slug PK
    Column("label", Text, nullable=False),
    Column("url_patterns", ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")),
    Column("requires_auth", Boolean, nullable=False, server_default=text("false")),
    Column("has_api", Boolean, nullable=False, server_default=text("false")),
    Column("content_fetch_enabled", Boolean, nullable=False, server_default=text("false")),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
)

docs = Table(
    "docs", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("url", Text, nullable=False),
    Column("url_normalized", Text, nullable=False),
    Column("title", Text, nullable=True),
    Column("source_id", Text, ForeignKey("sources.id"), nullable=False, server_default=text("'web'")),
    Column("description", Text, nullable=True),
    Column("owning_team_id", UUID(as_uuid=True), nullable=True),
    Column("owning_team_label", Text, nullable=True),
    Column("owning_person_id", UUID(as_uuid=True), nullable=True),
    Column("owning_person_label", Text, nullable=True),
    Column("content_snapshot", Text, nullable=True),
    Column("fetched_at", DateTime(timezone=True), nullable=True),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("created_by", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
    Index("ix_docs_url_normalized", "url_normalized"),
    Index("ix_docs_owning_team", "owning_team_id"),
    Index("ix_docs_owning_person", "owning_person_id"),
    Index("ix_docs_source", "source_id"),
)

doc_tags = Table(
    "doc_tags", metadata,
    Column("doc_id", UUID(as_uuid=True), ForeignKey("docs.id", ondelete="CASCADE"), nullable=False),
    Column("tag", Text, nullable=False),
    UniqueConstraint("doc_id", "tag", name="uq_doc_tags_doc_tag"),
    Index("ix_doc_tags_tag", "tag"),
)

api_keys = Table(
    "api_keys", metadata,
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
