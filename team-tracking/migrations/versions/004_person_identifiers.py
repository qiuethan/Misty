"""person_identifiers + providers

Revision ID: 004
Revises: 003
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

PROVIDERS = [
    ("discord", "Discord"),
    ("github", "GitHub"),
    ("notion", "Notion"),
    ("uoft_email", "UofT Email"),
]


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
    )
    op.create_table(
        "person_identifiers",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("provider", sa.Text, sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("handle", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
        sa.UniqueConstraint("person_id", "provider", name="uq_person_identifiers_person_provider"),
        sa.UniqueConstraint(
            "provider", "external_id", name="uq_person_identifiers_provider_external"
        ),
    )
    providers = sa.table(
        "providers",
        sa.column("id", sa.Text),
        sa.column("label", sa.Text),
        sa.column("created_by", sa.Text),
        sa.column("updated_by", sa.Text),
    )
    op.bulk_insert(
        providers,
        [
            {"id": pid, "label": plabel, "created_by": "system", "updated_by": "system"}
            for pid, plabel in PROVIDERS
        ],
    )


def downgrade() -> None:
    op.drop_table("person_identifiers")
    op.drop_table("providers")
