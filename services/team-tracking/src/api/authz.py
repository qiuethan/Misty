"""Service-level authorization helpers layered on top of platform_auth.

`people:write` gates ordinary directory edits, but changing a person's
`access_level` is a privilege grant (the Discord bot trusts
`person.access_level` for authorization). Escalating it therefore requires a
dedicated, elevated scope so that a plain `people:write` key cannot promote any
record — including its own linked one — to admin/superuser.

The `admin` wildcard scope satisfies `has_scope`, so the legitimate
seed/promote flow (env-bootstrap key or an admin-scoped DB key) keeps working;
`people:elevate` can also be granted explicitly to a promote-only key.
"""

from fastapi import HTTPException, status

from src.api.auth import AuthedKey

# Elevated scope required to set/change a person's access_level.
PEOPLE_ELEVATE_SCOPE = "people:elevate"


def require_access_level_change(key: AuthedKey) -> None:
    """Reject (403) callers that lack the elevated scope needed to change
    access_level. Never silently drops the field — the request fails loudly."""
    if not key.has_scope(PEOPLE_ELEVATE_SCOPE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"changing access_level requires scope: {PEOPLE_ELEVATE_SCOPE}",
        )
