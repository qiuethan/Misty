"""person access_level

Revision ID: 005
Revises: 004
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "people",
        sa.Column(
            "access_level",
            sa.Text,
            nullable=False,
            server_default=sa.text("'member'"),
        ),
    )
    op.create_check_constraint(
        "ck_people_access_level",
        "people",
        "access_level IN ('member', 'admin', 'superuser')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_people_access_level", "people", type_="check")
    op.drop_column("people", "access_level")
