import json

import pytest

from src.email.base import EmailSendError
from src.email.resend import ResendSender


class _RecordingPost:
    """Captures the request and returns a configurable status."""

    def __init__(self, status=202, raises=None):
        self.status = status
        self.raises = raises
        self.calls = []

    def __call__(self, url, *, headers, data, timeout):
        self.calls.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        return self.status


def test_resend_send_builds_request_and_succeeds():
    post = _RecordingPost(status=202)
    sender = ResendSender(api_key="re_test_key", sender="UTMIST <noreply@utmist.ca>", post=post)
    sender.send(to="a@b.com", subject="Your code", body="Your verification code is 123456.")

    assert len(post.calls) == 1
    call = post.calls[0]
    assert call["url"] == "https://api.resend.com/emails"
    assert call["headers"]["Authorization"] == "Bearer re_test_key"
    # Cloudflare (fronting Resend) blocks the default urllib UA — must send one.
    assert call["headers"].get("User-Agent")
    payload = json.loads(call["data"])
    assert payload["from"] == "UTMIST <noreply@utmist.ca>"
    assert payload["to"] == ["a@b.com"]
    assert payload["subject"] == "Your code"
    assert "123456" in payload["text"]


def test_resend_send_raises_on_non_2xx():
    sender = ResendSender(api_key="k", sender="s@x.com", post=_RecordingPost(status=422))
    with pytest.raises(EmailSendError):
        sender.send(to="a@b.com", subject="Hi", body="code 123456")


def test_resend_send_wraps_transport_error():
    import urllib.error

    post = _RecordingPost(raises=urllib.error.URLError("boom"))
    sender = ResendSender(api_key="k", sender="s@x.com", post=post)
    with pytest.raises(EmailSendError):
        sender.send(to="a@b.com", subject="Hi", body="code 123456")
