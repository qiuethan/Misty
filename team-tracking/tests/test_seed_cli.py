import argparse

from conftest import build_seed_role_kinds
from src.seed_cli import cmd_seed_person
from src.storage.in_memory import InMemoryStorageAdapter


def _args(name, email, level="member"):
    return argparse.Namespace(name=name, email=email, level=level, actor="seed-cli")


def test_seed_person_creates_new():
    adapter = InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())
    rc = cmd_seed_person(_args("Ethan Qiu", "ethanqiu@gmail.com", "superuser"), adapter=adapter)
    assert rc == 0
    p = adapter.get_person_by_email("ethanqiu@gmail.com")
    assert p is not None
    assert p.display_name == "Ethan Qiu"
    assert p.access_level == "superuser"


def test_seed_person_is_idempotent_and_updates():
    adapter = InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())
    cmd_seed_person(_args("Ethan", "ethanqiu@gmail.com", "member"), adapter=adapter)
    cmd_seed_person(_args("Ethan Qiu", "ethanqiu@gmail.com", "superuser"), adapter=adapter)
    people = adapter.list_people()
    assert len(people) == 1
    assert people[0].display_name == "Ethan Qiu"
    assert people[0].access_level == "superuser"
