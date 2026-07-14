"""Storage-layer domain errors shared across adapters.

These are raised by storage adapters (Postgres and in-memory) so that both
backends signal the same failure the same way, and routers can map them to
distinct HTTP responses.
"""

from uuid import UUID


class UnknownParentTeamError(ValueError):
    """A ``create_team`` call referenced a ``parent_id`` that does not exist.

    Subclasses ``ValueError`` so existing generic ``except ValueError`` handlers
    still catch it, but routers can catch it first to return a 400 (bad request)
    instead of a 409 (slug conflict).
    """

    def __init__(self, parent_id: UUID) -> None:
        self.parent_id = parent_id
        super().__init__(f"unknown parent team: {parent_id}")
