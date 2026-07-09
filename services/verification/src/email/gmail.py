import base64
import json
from email.mime.text import MIMEText

from src.email.base import EmailSendError

# Bound the blocking Gmail HTTP call so a slow/unreachable Gmail can't hang a
# request worker indefinitely.
_HTTP_TIMEOUT_SECONDS = 10


class GmailSender:
    """Sends email via the Gmail API using a service account with domain-wide
    delegation (impersonating ``sender``). ``service`` is injectable for tests.
    """

    _SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    def __init__(self, *, sender: str, credentials_json_b64: str, service=None) -> None:
        self._sender = sender
        self._credentials_json_b64 = credentials_json_b64
        self._service = service

    def _build_service(self):
        import google_auth_httplib2
        import httplib2
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(base64.b64decode(self._credentials_json_b64))
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=self._SCOPES, subject=self._sender
        )
        authed_http = google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(timeout=_HTTP_TIMEOUT_SECONDS)
        )
        return build("gmail", "v1", http=authed_http, cache_discovery=False)

    def send(self, *, to: str, subject: str, body: str) -> None:
        service = self._service if self._service is not None else self._build_service()
        message = MIMEText(body)
        message["To"] = to
        message["From"] = self._sender
        message["Subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        try:
            service.users().messages().send(userId="me", body={"raw": raw}).execute(num_retries=2)
        except Exception as exc:
            # Normalize any provider/transport error into our domain exception.
            raise EmailSendError("failed to send verification email") from exc
