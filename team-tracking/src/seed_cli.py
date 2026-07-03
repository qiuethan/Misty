"""team-tracking-seed — direct-to-DB member seeding + access-level bootstrap.

Runs the same PostgresStorageAdapter the HTTP service uses, bypassing the
network layer. Intended for operators with DB credentials to create the first
superuser (before any admin exists to use the bot's gated /seed command).

USAGE:
  team-tracking-seed seed-person --name "<name>" --email <email> [--level member|admin|superuser]

Idempotent by email: creates the person, or updates name/level if the email
already exists.
"""

import argparse
import sys

from sqlalchemy import create_engine

from contracts.types import PersonCreate, PersonUpdate
from src.config import get_settings
from src.storage.postgres import PostgresStorageAdapter


def _adapter() -> PostgresStorageAdapter:
    engine = create_engine(get_settings().database_url, future=True)
    return PostgresStorageAdapter(engine)


def cmd_seed_person(args: argparse.Namespace, adapter=None) -> int:
    adapter = adapter or _adapter()
    email = args.email.strip().lower()
    existing = adapter.get_person_by_email(email)
    if existing is None:
        level = args.level or "member"
        p = adapter.create_person(
            PersonCreate(display_name=args.name, primary_email=email, access_level=level),
            actor=args.actor,
        )
        verb = "created"
    else:
        update_kwargs = {"display_name": args.name}
        if args.level is not None:
            update_kwargs["access_level"] = args.level
        p = adapter.update_person(existing.id, PersonUpdate(**update_kwargs), actor=args.actor)
        verb = "updated"
    print(
        f"{verb}: {p.display_name} <{p.primary_email}> level={p.access_level} id={p.id}",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="team-tracking-seed",
        description="Seed people and access levels directly into the DB.",
    )
    p.add_argument("--actor", default="seed-cli", help="Actor stamped on created_by/updated_by")
    subs = p.add_subparsers(dest="cmd", required=True)

    sp = subs.add_parser("seed-person", help="Create or update a person by email")
    sp.add_argument("--name", required=True, help="Display name")
    sp.add_argument("--email", required=True, help="Primary email (case-insensitive)")
    sp.add_argument(
        "--level",
        choices=["member", "admin", "superuser"],
        default=None,
        help="Access level to grant (default: member on create; unchanged on update)",
    )
    sp.set_defaults(func=cmd_seed_person)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
