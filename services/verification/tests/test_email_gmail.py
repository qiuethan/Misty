import base64

from src.email.gmail import GmailSender


class _FakeMessages:
    def __init__(self):
        self.sent = []

    def send(self, *, userId, body):  # noqa: N803 (Gmail API arg name)
        self.sent.append((userId, body))
        return self

    def execute(self):
        return {"id": "x"}


class _FakeUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class _FakeService:
    def __init__(self):
        self.messages_obj = _FakeMessages()

    def users(self):
        return _FakeUsers(self.messages_obj)


def test_gmail_sender_builds_and_sends_message():
    svc = _FakeService()
    sender = GmailSender(sender="noreply@utmist.ca", credentials_json_b64="", service=svc)
    sender.send(to="a@b.com", subject="Hi", body="Your verification code is 123456.")
    assert len(svc.messages_obj.sent) == 1
    user_id, payload = svc.messages_obj.sent[0]
    assert user_id == "me"
    raw = base64.urlsafe_b64decode(payload["raw"]).decode()
    assert "a@b.com" in raw
    assert "123456" in raw
    assert "noreply@utmist.ca" in raw
