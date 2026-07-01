from src.cli import cmd_issue, cmd_list, cmd_revoke, build_parser
from src.storage.in_memory import InMemoryStorageAdapter


def test_issue_prints_plaintext_and_stores_key(capsys):
    adapter = InMemoryStorageAdapter()
    args = build_parser().parse_args(["issue", "--name", "bot", "--scopes", "docs:write"])
    rc = cmd_issue(args, adapter)
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("doc_")
    assert adapter.list_api_keys()[0].name == "bot"


def test_revoke_marks_inactive(capsys):
    adapter = InMemoryStorageAdapter()
    issue_args = build_parser().parse_args(["issue", "--name", "bot", "--scopes", "docs:read"])
    cmd_issue(issue_args, adapter)
    key_id = adapter.list_api_keys()[0].id
    rc = cmd_revoke(build_parser().parse_args(["revoke", str(key_id)]), adapter)
    assert rc == 0
    assert adapter.list_api_keys(active_only=True) == []
