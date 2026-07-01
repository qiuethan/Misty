"""team-tracking CLI — direct-to-DB ops for API key management.

Runs the same PostgresStorageAdapter the HTTP service uses, but bypasses
the network layer. Intended for operators with DB credentials.

USAGE:
  team-tracking-keys issue --name <name> --scopes <space-separated>
  team-tracking-keys list [--active-only]
  team-tracking-keys revoke <api_key_id>

The `issue` command PRINTS THE PLAINTEXT KEY ONCE to stdout. Capture it
immediately; it cannot be recovered later (only the argon2 hash is stored).
"""

import argparse
import sys
from uuid import UUID

from sqlalchemy import create_engine

from src.api.hashing import generate_key
from src.config import get_settings
from src.storage.postgres import PostgresStorageAdapter


def _adapter() -> PostgresStorageAdapter:
    engine = create_engine(get_settings().database_url, future=True)
    return PostgresStorageAdapter(engine)


def cmd_issue(args: argparse.Namespace) -> int:
    """Issue a new API key. Prints the plaintext key ONCE to stdout."""
    adapter = _adapter()
    plaintext, prefix, key_hash = generate_key()
    key = adapter.create_api_key(
        name=args.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=list(args.scopes or []),
        actor=args.actor,
    )
    print("=" * 70, file=sys.stderr)
    print("API KEY ISSUED (this is the only time it will be shown)", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Name:    {key.name}", file=sys.stderr)
    print(f"  Prefix:  {key.prefix}", file=sys.stderr)
    print(f"  Scopes:  {', '.join(key.scopes) if key.scopes else '(none)'}", file=sys.stderr)
    print(f"  Key id:  {key.id}", file=sys.stderr)
    print("", file=sys.stderr)
    # Plaintext to stdout so it can be piped: `team-tracking-keys issue ... > key.txt`
    print(plaintext)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List API keys. Never prints the hash or plaintext — only metadata."""
    adapter = _adapter()
    keys = adapter.list_api_keys(active_only=args.active_only)
    if not keys:
        print("(no keys)", file=sys.stderr)
        return 0
    print(f"{'name':<25} {'prefix':<10} {'active':<7} {'scopes'}")
    print("-" * 80)
    for k in keys:
        active = "yes" if (k.active and k.revoked_at is None) else "no"
        scopes = ", ".join(k.scopes) if k.scopes else "(none)"
        print(f"{k.name:<25} {k.prefix:<10} {active:<7} {scopes}")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    """Revoke a key by id (soft-delete: sets revoked_at, active=false)."""
    adapter = _adapter()
    try:
        key_id = UUID(args.api_key_id)
    except ValueError:
        print(f"error: not a valid UUID: {args.api_key_id}", file=sys.stderr)
        return 2
    revoked = adapter.revoke_api_key(key_id, actor=args.actor)
    if revoked is None:
        print(f"error: no such api key: {key_id}", file=sys.stderr)
        return 1
    print(f"revoked {revoked.name} ({revoked.prefix})", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="team-tracking-keys",
        description="Direct-to-DB management of team-tracking API keys.",
    )
    p.add_argument(
        "--actor",
        default="cli",
        help="Actor identifier stamped on created_by/updated_by (default: 'cli')",
    )
    subs = p.add_subparsers(dest="cmd", required=True)

    p_issue = subs.add_parser("issue", help="Issue a new API key")
    p_issue.add_argument("--name", required=True, help="Consumer name, e.g. 'discord-bot'")
    p_issue.add_argument(
        "--scopes",
        nargs="*",
        default=[],
        help="Scopes to grant, e.g. people:read memberships:write. Use 'admin' for wildcard.",
    )
    p_issue.set_defaults(func=cmd_issue)

    p_list = subs.add_parser("list", help="List existing API keys (metadata only)")
    p_list.add_argument("--active-only", action="store_true", help="Only show non-revoked keys")
    p_list.set_defaults(func=cmd_list)

    p_revoke = subs.add_parser("revoke", help="Revoke an API key by id")
    p_revoke.add_argument("api_key_id", help="UUID of the key to revoke")
    p_revoke.set_defaults(func=cmd_revoke)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
