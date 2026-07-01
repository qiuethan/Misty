"""seed role_kinds

Revision ID: 002
Revises: 001
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

ROLE_KINDS = [
    ("executive", "Executive"),
    ("director", "Director"),
    ("lead", "Lead"),
    ("member", "Member"),
]


def upgrade() -> None:
    role_kinds = sa.table(
        "role_kinds",
        sa.column("id", sa.Text),
        sa.column("label", sa.Text),
        sa.column("created_by", sa.Text),
        sa.column("updated_by", sa.Text),
    )
    op.bulk_insert(
        role_kinds,
        [
            {"id": rid, "label": rlabel, "created_by": "system", "updated_by": "system"}
            for rid, rlabel in ROLE_KINDS
        ],
    )


def downgrade() -> None:
    ids = [rid for rid, _ in ROLE_KINDS]
    op.execute(
        sa.text("DELETE FROM role_kinds WHERE id = ANY(:ids)").bindparams(ids=ids)
    )
