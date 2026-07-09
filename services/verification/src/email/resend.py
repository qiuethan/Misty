import json
import urllib.error
import urllib.request

from src.email.base import EmailSendError

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10


def _urlopen_post(url: str, *, headers: dict[str, str], data: bytes, timeout: int) -> int:
    """Default transport: POST via stdlib and return the HTTP status code.

    urllib raises HTTPError (a URLError) for non-2xx, so any failure surfaces as
    an exception the caller normalizes to EmailSendError.
    """
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


class ResendSender:
    """Sends email via the Resend HTTP API (https://resend.com).

    Works on any Railway plan (HTTPS, not SMTP). ``post`` is injectable so tests
    exercise the request building + status handling without hitting the network.
    """

    def __init__(self, *, api_key: str, sender: str, post=_urlopen_post) -> None:
        self._api_key = api_key
        self._sender = sender
        self._post = post

    def send(self, *, to: str, subject: str, body: str) -> None:
        payload = json.dumps(
            {"from": self._sender, "to": [to], "subject": subject, "text": body}
        ).encode()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            # Resend's API is behind Cloudflare, which blocks the default
            # `Python-urllib/*` User-Agent with error 1010. Send a real UA.
            "User-Agent": "utmist-verification/0.1",
        }
        try:
            status = self._post(
                _RESEND_URL, headers=headers, data=payload, timeout=_TIMEOUT_SECONDS
            )
        except urllib.error.URLError as exc:
            raise EmailSendError("failed to send verification email via Resend") from exc
        if status not in (200, 201, 202):
            raise EmailSendError(f"Resend returned unexpected status {status}")
