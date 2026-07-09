from src.email.fake import FakeSender


def test_fake_sender_captures_and_extracts_code():
    s = FakeSender()
    s.send(to="a@b.com", subject="Hi", body="Your verification code is 654321. ...")
    assert len(s.sent) == 1
    assert s.sent[0].to == "a@b.com"
    assert s.last_code() == "654321"
