"""Google Drive source: URL to file id, then Drive export/download to text.

Google client libraries are imported lazily inside _build_service so the
dependency never loads unless a Google URL is actually fetched — the same
pattern as services/verification/src/email/gmail.py.
"""

import re

# Drive file ids are URL-safe base64-ish: letters, digits, hyphen, underscore.
_ID = r"([a-zA-Z0-9_-]+)"

_FILE_ID_PATTERNS = (
    re.compile(rf"docs\.google\.com/document/d/{_ID}"),
    re.compile(rf"docs\.google\.com/spreadsheets/d/{_ID}"),
    re.compile(rf"docs\.google\.com/presentation/d/{_ID}"),
    re.compile(rf"drive\.google\.com/file/d/{_ID}"),
    re.compile(rf"drive\.google\.com/open\?(?:[^#]*&)?id={_ID}"),
)


def parse_file_id(url: str) -> str | None:
    """The Drive file id in `url`, or None if it is not a recognized form."""
    for pattern in _FILE_ID_PATTERNS:
        match = pattern.search(url or "")
        if match:
            return match.group(1)
    return None
