import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

# Deliberately lightweight: reject the obviously-malformed (no "@", no domain
# dot) without pulling in a full RFC email-validation dependency. Real
# deliverability is proven by the one-time code, not by this check.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(v: str) -> str:
    return v.strip().lower()


def _normalize_subject(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("subject must not be empty")
    return v


class RequestCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str
    email: str

    @field_validator("subject")
    @classmethod
    def _subject(cls, v: str) -> str:
        return _normalize_subject(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = _normalize_email(v)
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v


class RequestCodeOut(BaseModel):
    status: str = "sent"


class ConfirmCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str
    code: str

    @field_validator("subject")
    @classmethod
    def _subject(cls, v: str) -> str:
        return _normalize_subject(v)


class ConfirmCodeOut(BaseModel):
    verified: bool
    subject: str
    email: str


class VerificationCode(BaseModel):
    """Internal record persisted by the storage adapter (not a public DTO)."""

    model_config = ConfigDict(extra="forbid")
    subject: str
    email: str
    code_hash: str
    expires_at: datetime
    attempts: int
    consumed_at: datetime | None
    created_at: datetime
