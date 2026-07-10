"""The single definition of document visibility. The in-memory adapter calls
`doc_visible` directly; the Postgres adapter compiles the same rule to SQL.
Both must stay in lockstep — see tests/test_visibility.py and the adapter
parity tests."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    person_id: UUID
    team_ids: frozenset[UUID]


class _Sentinel(Enum):
    SEE_ALL = "see_all"
    DENY = "deny"


SEE_ALL = _Sentinel.SEE_ALL
DENY = _Sentinel.DENY

ActorContext = Actor | _Sentinel


def doc_visible(
    ctx: ActorContext,
    *,
    owning_person_id: UUID | None,
    owning_team_id: UUID | None,
    grants: Iterable[tuple[str, UUID | None]],
) -> bool:
    if ctx is SEE_ALL:
        return True
    if ctx is DENY:
        return False
    # ctx is an Actor
    if owning_person_id is not None and owning_person_id == ctx.person_id:
        return True
    if owning_team_id is not None and owning_team_id in ctx.team_ids:
        return True
    for grantee_type, grantee_id in grants:
        if grantee_type == "org":
            return True
        if grantee_type == "person" and grantee_id == ctx.person_id:
            return True
        if grantee_type == "team" and grantee_id in ctx.team_ids:
            return True
    return False
