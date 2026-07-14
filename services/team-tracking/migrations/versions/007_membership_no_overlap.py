"""membership temporal non-overlap constraint

Revision ID: 007
Revises: 006
Create Date: 2026-07-13

Enforce that a person cannot hold two memberships in the same team whose active
date ranges overlap. A partial unique index `WHERE ended_at IS NULL` would miss
future-dated memberships, and a partial index cannot use CURRENT_DATE (not
IMMUTABLE), so we use a gist EXCLUDE constraint over
daterange(started_at, COALESCE(ended_at, 'infinity')) backed by btree_gist.

The daterange upper bound is exclusive, so ending a membership and re-adding the
person on the same day does not overlap and is allowed.

Before adding the constraint we MUST backfill: existing data may already contain
overlapping active memberships (the old application layer had only a bypassable
pre-check). In each overlapping group we keep one survivor (earliest started_at,
then created_at, then id) and neutralize the rest.

NOTE ON THE CLOSING VALUE: closing a losing row to CURRENT_DATE (as one might
first reach for) does NOT remove the overlap when the duplicate started in the
past and the survivor spans that period -- e.g. survivor [2024-09-01, inf) and
loser closed to [2025-01-15, CURRENT_DATE) still overlap. The only value that
provably removes the overlap for an arbitrarily historical row is the row's own
started_at, which collapses it to an EMPTY range (daterange(x, x) = 'empty',
which && nothing). These duplicate rows are erroneous double-adds, so tomb-
stoning them as zero-length records (updated_by='migration_007_dedup') is the
safe, overlap-free resolution. For the common "duplicate created today" case
started_at == CURRENT_DATE, so this is equivalent to closing at CURRENT_DATE.
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # --- Backfill: dedup overlapping active memberships FIRST ---
    # Two memberships for the same (person_id, team_id) conflict when their
    # daterange(started_at, COALESCE(ended_at, 'infinity')) ranges overlap.
    # A row is a "loser" iff a strictly-better row (earlier started_at, then
    # created_at, then id) exists for the same (person_id, team_id) and overlaps
    # it. We collapse every loser to an empty range by setting
    # ended_at = started_at (see the module docstring for why CURRENT_DATE is not
    # sufficient). An empty range overlaps nothing, so the survivor -- the unique
    # best row in each overlap-connected group -- keeps its full range and all
    # overlaps are removed. Disjoint historical memberships are never flagged, so
    # legitimate re-joins are preserved.
    #
    # Iterate to a fixed point for defence-in-depth (one pass is sufficient given
    # the ranking, but re-running until no rows change is cheap and robust).
    op.execute(
        """
        DO $$
        DECLARE
            affected integer;
        BEGIN
            LOOP
                WITH conflicts AS (
                    SELECT DISTINCT a.id AS loser_id
                    FROM team_memberships a
                    JOIN team_memberships b
                      ON a.person_id = b.person_id
                     AND a.team_id = b.team_id
                     AND a.id <> b.id
                     AND daterange(a.started_at, COALESCE(a.ended_at, 'infinity'::date))
                         && daterange(b.started_at, COALESCE(b.ended_at, 'infinity'::date))
                    WHERE (b.started_at, b.created_at, b.id) < (a.started_at, a.created_at, a.id)
                )
                UPDATE team_memberships t
                SET ended_at = t.started_at,
                    updated_at = now(),
                    updated_by = 'migration_007_dedup'
                FROM conflicts c
                WHERE t.id = c.loser_id
                  AND (t.ended_at IS NULL OR t.ended_at <> t.started_at);

                GET DIAGNOSTICS affected = ROW_COUNT;
                EXIT WHEN affected = 0;
            END LOOP;
        END $$;
        """
    )

    op.execute(
        """
        ALTER TABLE team_memberships
        ADD CONSTRAINT team_memberships_no_overlap
        EXCLUDE USING gist (
            person_id WITH =,
            team_id WITH =,
            daterange(started_at, COALESCE(ended_at, 'infinity'::date)) WITH &&
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE team_memberships DROP CONSTRAINT team_memberships_no_overlap")
    # Intentionally leave the btree_gist extension in place; other objects may
    # come to rely on it and dropping an extension is a heavier, riskier op.
