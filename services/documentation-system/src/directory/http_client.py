from uuid import UUID

import httpx

from contracts.directory import DirectoryUnavailable

_TIMEOUT = httpx.Timeout(5.0)


class HttpDirectoryClient:
    """Validates directory ids and fetches display labels over team-tracking's
    HTTP API. A 404 means 'no such record' (returns None); connection failure
    or 5xx means 'directory unavailable' (raises DirectoryUnavailable)."""

    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    def _get_label(self, path: str, label_field: str) -> str | None:
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.get(
                f"{self._base_url}{path}", headers={"X-API-Key": self._api_key}
            )
        except httpx.HTTPError as e:
            raise DirectoryUnavailable(f"directory unreachable: {e}") from e
        finally:
            if self._client is None:
                client.close()
        if resp.status_code == 404:
            return None
        if not (200 <= resp.status_code < 300):
            raise DirectoryUnavailable(f"directory returned {resp.status_code}")
        return resp.json().get(label_field)

    def get_team_label(self, team_id: UUID) -> str | None:
        return self._get_label(f"/teams/{team_id}", "label")

    def get_person_label(self, person_id: UUID) -> str | None:
        return self._get_label(f"/people/{person_id}", "display_name")

    def get_active_team_ids(self, person_id: UUID) -> frozenset[UUID]:
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.get(
                f"{self._base_url}/memberships",
                params={"person_id": str(person_id), "active_only": "true"},
                headers={"X-API-Key": self._api_key},
            )
        except httpx.HTTPError as e:
            raise DirectoryUnavailable(f"directory unreachable: {e}") from e
        finally:
            if self._client is None:
                client.close()
        if not (200 <= resp.status_code < 300):
            raise DirectoryUnavailable(f"directory returned {resp.status_code}")
        return frozenset(UUID(m["team_id"]) for m in resp.json())
