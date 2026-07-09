"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_codes",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("subject", name="uq_verification_codes_subject"),
    )
    op.create_index("ix_verification_codes_email", "verification_codes", ["email"])


def downgrade() -> None:
    op.drop_index("ix_verification_codes_email", table_name="verification_codes")
    op.drop_table("verification_codes")
