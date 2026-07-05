import base64
import json
from email.mime.text import MIMEText


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
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(base64.b64decode(self._credentials_json_b64))
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=self._SCOPES, subject=self._sender
        )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def send(self, *, to: str, subject: str, body: str) -> None:
        service = self._service or self._build_service()
        message = MIMEText(body)
        message["To"] = to
        message["From"] = self._sender
        message["Subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
