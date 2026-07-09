"""SQLAlchemy Core table definitions for the verification service."""

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

verification_codes = Table(
    "verification_codes",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("subject", Text, nullable=False),
    Column("email", Text, nullable=False, index=True),
    Column("code_hash", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("consumed_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("subject", name="uq_verification_codes_subject"),
)
