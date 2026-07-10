"""email provider + multi-valued email identifiers

Revision ID: 006
Revises: 005
Create Date: 2026-07-09

Downgrade is LOSSY: it deletes all provider='email' identifiers before it can
re-add the strict UNIQUE(person_id, provider) (that constraint cannot hold while
any person has more than one email row).
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    providers = sa.table(
        "providers",
        sa.column("id", sa.Text),
        sa.column("label", sa.Text),
        sa.column("created_by", sa.Text),
        sa.column("updated_by", sa.Text),
    )
    op.bulk_insert(
        providers,
        [{"id": "email", "label": "Email", "created_by": "system", "updated_by": "system"}],
    )
    # Swap the table-wide one-per-provider uniqueness for a partial index of the
    # SAME NAME that exempts the (multi-valued) email provider.
    op.drop_constraint(
        "uq_person_identifiers_person_provider", "person_identifiers", type_="unique"
    )
    op.create_index(
        "uq_person_identifiers_person_provider",
        "person_identifiers",
        ["person_id", "provider"],
        unique=True,
        postgresql_where=sa.text("provider <> 'email'"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM person_identifiers WHERE provider = 'email'")
    op.drop_index("uq_person_identifiers_person_provider", table_name="person_identifiers")
    op.create_unique_constraint(
        "uq_person_identifiers_person_provider",
        "person_identifiers",
        ["person_id", "provider"],
    )
    op.execute("DELETE FROM providers WHERE id = 'email'")
