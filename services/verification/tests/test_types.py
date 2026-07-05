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
