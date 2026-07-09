import pytest
from pydantic import ValidationError

from contracts.types import ConfirmCodeIn, RequestCodeIn


def test_email_normalized():
    assert RequestCodeIn(subject="s", email="  A@B.COM ").email == "a@b.com"


def test_email_requires_at():
    with pytest.raises(ValidationError):
        RequestCodeIn(subject="s", email="nope")


def test_subject_required_nonempty():
    with pytest.raises(ValidationError):
        RequestCodeIn(subject="   ", email="a@b.com")


def test_extra_forbidden():
    with pytest.raises(ValidationError):
        RequestCodeIn(subject="s", email="a@b.com", oops="x")


def test_confirm_in_fields():
    m = ConfirmCodeIn(subject="s", code="123456")
    assert m.subject == "s" and m.code == "123456"


def test_confirm_subject_trimmed():
    assert ConfirmCodeIn(subject="  discord:1  ", code="1").subject == "discord:1"


def test_confirm_subject_rejects_blank():
    with pytest.raises(ValidationError):
        ConfirmCodeIn(subject="   ", code="1")


def test_email_rejects_incomplete_address():
    for bad in ("a@", "@b.com", "a@b"):  # no domain / no local / no dot
        with pytest.raises(ValidationError):
            RequestCodeIn(subject="s", email=bad)
