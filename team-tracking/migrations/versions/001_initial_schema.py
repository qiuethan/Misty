"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT, UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "people",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("primary_email", CITEXT, nullable=False, unique=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
    )

    op.create_table(
        "teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
    )

    op.create_table(
        "role_kinds",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
    )

    op.create_table(
        "team_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("role_kind_id", sa.Text, sa.ForeignKey("role_kinds.id"), nullable=False, server_default=sa.text("'member'")),
        sa.Column("is_team_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.Date, nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("ended_at", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
    )
    op.create_index("ix_team_memberships_team_ended", "team_memberships", ["team_id", "ended_at"])
    op.create_index("ix_team_memberships_person_ended", "team_memberships", ["person_id", "ended_at"])
    op.create_index("ix_team_memberships_dates", "team_memberships", ["started_at", "ended_at"])


def downgrade() -> None:
    op.drop_index("ix_team_memberships_dates", table_name="team_memberships")
    op.drop_index("ix_team_memberships_person_ended", table_name="team_memberships")
    op.drop_index("ix_team_memberships_team_ended", table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_table("role_kinds")
    op.drop_table("teams")
    op.drop_table("people")
