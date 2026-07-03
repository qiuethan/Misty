from typing import Protocol
from uuid import UUID


class DirectoryUnavailable(Exception):
    """Raised when team-tracking cannot be reached (connection/timeout/5xx).
    The ingest layer degrades: stores the id with a null label + a warning."""


class DirectoryClient(Protocol):
    def get_team_label(self, team_id: UUID) -> str | None:
        """Return the team's display label, or None if no such team.
        Raises DirectoryUnavailable if the directory cannot be reached."""
        ...

    def get_person_label(self, person_id: UUID) -> str | None:
        """Return the person's display name, or None if no such person.
        Raises DirectoryUnavailable if the directory cannot be reached."""
        ...
