from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_email(v: str) -> str:
    return v.strip().lower()


class RequestCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str
    email: str

    @field_validator("subject")
    @classmethod
    def _subject_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("subject must not be empty")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = _normalize_email(v)
        if "@" not in v:
            raise ValueError("invalid email")
        return v


class RequestCodeOut(BaseModel):
    status: str = "sent"


class ConfirmCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str
    code: str


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
