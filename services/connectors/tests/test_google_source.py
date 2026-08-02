import pytest

from src.sources.base import (
    SourceForbidden,
    SourceNotConfigured,
    SourceNotFound,
    SourceUnavailable,
    SourceUnsupported,
)
from src.sources.google import GoogleSource

DOC_URL = "https://docs.google.com/document/d/abc123/edit"
SHEET_URL = "https://docs.google.com/spreadsheets/d/abc123/edit"
SLIDES_URL = "https://docs.google.com/presentation/d/abc123/edit"
DRIVE_URL = "https://drive.google.com/file/d/abc123/view"


class _FakeRequest:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error

    def execute(self):
        if self._error is not None:
            raise self._error
        return self._result


class _FakeFiles:
    def __init__(self, meta, payload=None, get_error=None, export_error=None):
        self._meta, self._payload = meta, payload
        self._get_error, self._export_error = get_error, export_error
        self.export_mime = None

    def get(self, *, fileId, fields=None, alt=None):
        if alt == "media":
            return _FakeRequest(result=self._payload, error=self._export_error)
        return _FakeRequest(result=self._meta, error=self._get_error)

    def export(self, *, fileId, mimeType):
        self.export_mime = mimeType
        return _FakeRequest(result=self._payload, error=self._export_error)


class _FakeService:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


def _source(files, **kwargs):
    return GoogleSource(
        credentials_json_b64="fake",
        max_content_chars=1000,
        services={"drive": _FakeService(files)},
        **kwargs,
    )


def test_google_doc_falls_back_to_plain_text_export_until_task_6():
    # Task 6 replaces this with the native Docs API; until then Docs uses the
    # same Drive-export fallback as Slides.
    files = _FakeFiles(
        meta={"name": "Sponsorship Deck", "mimeType": "application/vnd.google-apps.document"},
        payload=b"the document body",
    )
    result = _source(files).fetch(DOC_URL)
    assert result.title == "Sponsorship Deck"
    assert result.content == "the document body"
    assert result.warnings == []
    assert files.export_mime == "text/plain"


def test_slides_export_as_plain_text():
    files = _FakeFiles(
        meta={"name": "Kickoff", "mimeType": "application/vnd.google-apps.presentation"},
        payload=b"slide one",
    )
    result = _source(files).fetch(SLIDES_URL)
    assert result.content == "slide one"
    assert files.export_mime == "text/plain"


def test_spreadsheet_exports_as_csv_and_always_warns():
    files = _FakeFiles(
        meta={"name": "Budget", "mimeType": "application/vnd.google-apps.spreadsheet"},
        payload=b"a,b\n1,2\n",
    )
    result = _source(files).fetch(SHEET_URL)
    assert result.content == "a,b\n1,2\n"
    assert files.export_mime == "text/csv"
    # Unconditional: Drive metadata does not expose tab count, so "has more than
    # one tab" is undetectable without the Sheets API.
    assert len(result.warnings) == 1
    assert "first sheet" in result.warnings[0]


def test_plain_text_upload_downloads_via_media():
    files = _FakeFiles(meta={"name": "notes.txt", "mimeType": "text/plain"}, payload=b"raw notes")
    result = _source(files).fetch(DRIVE_URL)
    assert result.content == "raw notes"


def test_binary_file_is_unsupported():
    files = _FakeFiles(meta={"name": "logo.png", "mimeType": "image/png"})
    with pytest.raises(SourceUnsupported):
        _source(files).fetch(DRIVE_URL)


def test_unrecognized_url_is_not_found():
    files = _FakeFiles(meta={})
    with pytest.raises(SourceNotFound):
        _source(files).fetch("https://example.com/whatever")


def test_missing_credentials_raise_not_configured():
    source = GoogleSource(credentials_json_b64="", max_content_chars=1000)
    with pytest.raises(SourceNotConfigured):
        source.fetch(DOC_URL)


def test_content_is_bounded_by_max_content_chars():
    files = _FakeFiles(
        meta={"name": "Huge", "mimeType": "application/vnd.google-apps.document"},
        payload=b"x" * 5000,
    )
    source = GoogleSource(
        credentials_json_b64="fake",
        max_content_chars=100,
        services={"drive": _FakeService(files)},
    )
    result = source.fetch(DOC_URL)
    assert len(result.content) == 100


def test_registry_exposes_an_extractor_per_google_editor_type():
    from src.sources.google import EXTRACTORS

    assert set(EXTRACTORS) >= {
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.presentation",
        "application/vnd.google-apps.spreadsheet",
    }


def test_required_scopes_include_drive_readonly():
    from src.sources.google import required_scopes

    assert "https://www.googleapis.com/auth/drive.readonly" in required_scopes()


def test_required_services_is_just_drive_with_current_registry():
    from src.sources.google import required_services

    assert required_services() == ("drive",)


def test_required_services_unions_in_a_new_extractor_declared_service():
    from src.sources import google

    class _FakeSlidesExtractor:
        scopes = ()
        services = ("slides",)

        def extract(self, services, file_id, mime):
            raise NotImplementedError

    original = dict(google.EXTRACTORS)
    google.EXTRACTORS["application/vnd.google-apps.presentation"] = _FakeSlidesExtractor()
    try:
        assert "slides" in google.required_services()
    finally:
        google.EXTRACTORS.clear()
        google.EXTRACTORS.update(original)


def _http_error(status):
    from googleapiclient.errors import HttpError

    class _Resp:
        def __init__(self, status):
            self.status = status
            self.reason = "fake"

    return HttpError(_Resp(status), b"{}")


@pytest.mark.parametrize(
    "status,expected",
    [(403, SourceForbidden), (404, SourceNotFound), (500, SourceUnavailable)],
)
def test_drive_http_errors_map_to_source_errors(status, expected):
    files = _FakeFiles(meta=None, get_error=_http_error(status))
    with pytest.raises(expected):
        _source(files).fetch(DOC_URL)
