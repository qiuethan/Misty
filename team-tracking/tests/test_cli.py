"""Tests for the team-tracking-keys CLI.

Uses InMemoryStorageAdapter via monkeypatch; does not require Postgres.
"""

import pytest

from conftest import build_seed_role_kinds
from src.cli import build_parser, main
from src.storage.in_memory import InMemoryStorageAdapter


@pytest.fixture
def adapter(monkeypatch):
    a = InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())
    monkeypatch.setattr("src.cli._adapter", lambda: a)
    return a


def test_issue_prints_plaintext_and_stores_hash(adapter, capsys):
    rc = main(["issue", "--name", "test-bot", "--scopes", "people:read"])
    assert rc == 0
    out = capsys.readouterr()
    plaintext = out.out.strip()
    assert plaintext.startswith("tt_")
    keys = adapter.list_api_keys()
    assert len(keys) == 1
    assert keys[0].name == "test-bot"
    assert keys[0].scopes == ["people:read"]
    # Human-readable info goes to stderr
    assert "API KEY ISSUED" in out.err


def test_issue_multiple_scopes(adapter, capsys):
    rc = main([
        "issue", "--name", "many", "--scopes", "people:read", "memberships:write", "admin"
    ])
    assert rc == 0
    keys = adapter.list_api_keys()
    assert keys[0].scopes == ["people:read", "memberships:write", "admin"]


def test_issue_no_scopes(adapter, capsys):
    rc = main(["issue", "--name", "empty"])
    assert rc == 0
    keys = adapter.list_api_keys()
    assert keys[0].scopes == []


def test_list_empty(adapter, capsys):
    rc = main(["list"])
    assert rc == 0
    out = capsys.readouterr()
    assert "(no keys)" in out.err


def test_list_with_keys(adapter, capsys):
    main(["issue", "--name", "a", "--scopes", "people:read"])
    main(["issue", "--name", "b", "--scopes", "admin"])
    capsys.readouterr()  # clear
    rc = main(["list"])
    assert rc == 0
    out = capsys.readouterr()
    assert "a" in out.out
    assert "b" in out.out


def test_list_active_only_filters_revoked(adapter, capsys):
    main(["issue", "--name", "keep"])
    main(["issue", "--name", "gone"])
    keys = adapter.list_api_keys()
    gone = next(k for k in keys if k.name == "gone")
    main(["revoke", str(gone.id)])
    capsys.readouterr()

    rc = main(["list", "--active-only"])
    assert rc == 0
    out = capsys.readouterr()
    assert "keep" in out.out
    assert "gone" not in out.out


def test_revoke_bad_uuid_returns_2(adapter, capsys):
    rc = main(["revoke", "not-a-uuid"])
    assert rc == 2
    out = capsys.readouterr()
    assert "not a valid UUID" in out.err


def test_revoke_missing_returns_1(adapter, capsys):
    from uuid import uuid4
    rc = main(["revoke", str(uuid4())])
    assert rc == 1
    out = capsys.readouterr()
    assert "no such api key" in out.err


def test_revoke_success(adapter, capsys):
    main(["issue", "--name", "victim"])
    keys = adapter.list_api_keys()
    capsys.readouterr()
    rc = main(["revoke", str(keys[0].id)])
    assert rc == 0
    out = capsys.readouterr()
    assert "revoked victim" in out.err
    assert adapter.list_api_keys(active_only=True) == []


def test_parser_requires_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
