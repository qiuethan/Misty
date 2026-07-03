from datetime import datetime, timezone

from contracts.types import Source

# (id, label, url_patterns, requires_auth, has_api, content_fetch_enabled) — matches migration 002.
_SEED = [
    ("web", "Web page", [], False, False, True),
    ("github", "GitHub", ["github.com"], False, True, True),
    ("gdrive", "Google Drive", ["drive.google.com"], True, True, False),
    ("gdocs", "Google Docs", ["docs.google.com/document"], True, True, False),
    ("gsheets", "Google Sheets", ["docs.google.com/spreadsheets"], True, True, False),
    ("gslides", "Google Slides", ["docs.google.com/presentation"], True, True, False),
    ("notion", "Notion", ["notion.so", "notion.site"], True, True, False),
    ("youtube", "YouTube", ["youtube.com", "youtu.be"], False, True, False),
]


def build_seed_sources() -> list[Source]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Source(id=s[0], label=s[1], url_patterns=s[2], requires_auth=s[3], has_api=s[4],
               content_fetch_enabled=s[5], active=True,
               created_at=now, updated_at=now, created_by="system", updated_by="system")
        for s in _SEED
    ]
