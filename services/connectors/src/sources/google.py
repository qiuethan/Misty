"""Google Drive source: URL to file id, then Drive export/download to text.

Google client libraries are imported lazily inside _build_service so the
dependency never loads unless a Google URL is actually fetched — the same
pattern as services/verification/src/email/gmail.py.
"""

import base64
import json
import re
import threading

from src.sources.base import (
    SourceNotConfigured,
    SourceNotFound,
    SourceResult,
    SourceUnsupported,
)
from src.sources.google_extractors.base import Extractor, execute
from src.sources.google_extractors.docs import DocsExtractor
from src.sources.google_extractors.drive_export import DRIVE_READONLY, DriveExportExtractor

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


GOOGLE_SOURCE_IDS = ("gdocs", "gsheets", "gslides", "gdrive")

GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES = "application/vnd.google-apps.presentation"

SHEET_WARNING = "spreadsheet export captures the first sheet only; other tabs were not read"

# MIME type -> extractor. GOOGLE_DOC uses the native Docs API extractor; the
# GOOGLE_SLIDES and GOOGLE_SHEET entries are the slots a SlidesExtractor /
# SheetsExtractor would take.
EXTRACTORS: dict[str, Extractor] = {
    GOOGLE_DOC: DocsExtractor(),
    GOOGLE_SLIDES: DriveExportExtractor(export_mime="text/plain"),
    GOOGLE_SHEET: DriveExportExtractor(export_mime="text/csv", warning=SHEET_WARNING),
}

# Uploaded (non-Google-native) text files have real bytes to download.
_MEDIA_EXTRACTOR = DriveExportExtractor(export_mime=None)


def required_scopes() -> tuple[str, ...]:
    """Every scope the registered extractors need, plus Drive for metadata."""
    scopes = {DRIVE_READONLY}
    for extractor in EXTRACTORS.values():
        scopes.update(extractor.scopes)
    scopes.update(_MEDIA_EXTRACTOR.scopes)
    return tuple(sorted(scopes))


# Google API name -> discovery API version, for the clients required_services()
# can name. Extend this alongside a new extractor that declares a new service.
_API_VERSIONS = {"drive": "v3", "docs": "v1", "slides": "v1", "sheets": "v4"}


def required_services() -> tuple[str, ...]:
    """Every Google API client name the registered extractors need, plus Drive
    for metadata. Mirrors required_scopes(): a new extractor declares its own
    service names rather than having them hard-coded at the build site.
    """
    services = {"drive"}
    for extractor in EXTRACTORS.values():
        services.update(extractor.services)
    services.update(_MEDIA_EXTRACTOR.services)
    return tuple(sorted(services))


class GoogleSource:
    """Reads Google Drive documents as text via a read-only service account.

    The account sees exactly what has been shared with its address — Drive's
    sharing settings are the access control, so there is no folder allowlist
    here by design.
    """

    def __init__(
        self,
        *,
        credentials_json_b64: str,
        max_content_chars: int,
        services: dict | None = None,
        request_timeout_s: float = 30.0,
    ) -> None:
        self._credentials_json_b64 = credentials_json_b64
        self._max_content_chars = max_content_chars
        self._request_timeout_s = request_timeout_s
        # API name -> client. A dict rather than one client because extractors
        # need different APIs (drive, docs, ...). Tests inject fakes here; in
        # production this starts None and is memoized by _get_services() on
        # first use, guarded by _build_lock.
        self._services = services
        # FastAPI runs sync route handlers in a threadpool, so concurrent
        # /fetch calls can race the first build. Guards ONLY the build below,
        # never the rest of fetch().
        self._build_lock = threading.Lock()

    def _build_services(self) -> dict:
        # Imported lazily so the Google dependency tree never loads unless a
        # Google URL is actually fetched.
        import google_auth_httplib2
        import httplib2
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        try:
            info = json.loads(base64.b64decode(self._credentials_json_b64))
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=list(required_scopes())
            )
        except Exception as e:  # malformed key material is a config failure
            raise SourceNotConfigured(f"invalid google credentials: {type(e).__name__}") from e

        def _client(name: str, version: str):
            authed = google_auth_httplib2.AuthorizedHttp(
                creds, http=httplib2.Http(timeout=self._request_timeout_s)
            )
            return build(name, version, http=authed, cache_discovery=False)

        clients = {}
        for name in required_services():
            version = _API_VERSIONS.get(name)
            if version is None:
                raise SourceNotConfigured(f"no discovery API version mapped for {name!r}")
            clients[name] = _client(name, version)
        return clients

    def _get_services(self) -> dict:
        """Build the Google API clients once and memoize them. Credential
        decode + JWT token exchange happen at most once per process (per
        instance), not on every /fetch. Double-checked locking: the lock is
        only held while actually building, not on the fast (already-built)
        path."""
        if self._services is not None:
            return self._services
        with self._build_lock:
            if self._services is None:
                self._services = self._build_services()
            return self._services

    def fetch(self, url: str) -> SourceResult:
        file_id = parse_file_id(url)
        if file_id is None:
            raise SourceNotFound(f"no google file id in url: {url!r}")
        if self._services is None and not self._credentials_json_b64:
            raise SourceNotConfigured("google credentials not configured")
        services = self._get_services()

        meta = execute(services["drive"].files().get(fileId=file_id, fields="name,mimeType"))
        name = (meta or {}).get("name")
        mime = (meta or {}).get("mimeType") or ""

        extractor = EXTRACTORS.get(mime)
        if extractor is None:
            if not mime.startswith("text/"):
                raise SourceUnsupported(f"no text form for mime type: {mime}")
            extractor = _MEDIA_EXTRACTOR

        extracted = extractor.extract(services, file_id, mime)
        return SourceResult(
            title=name,
            content=extracted.text[: self._max_content_chars],
            warnings=list(extracted.warnings),
        )
