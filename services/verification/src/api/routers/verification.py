from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from contracts.storage import VerificationStore
from contracts.types import (
    ConfirmCodeIn,
    ConfirmCodeOut,
    RequestCodeIn,
    RequestCodeOut,
    VerificationCode,
)
from src.api.auth import AuthedKey, require_scope
from src.api.deps import get_email_sender, get_storage
from src.codes import generate_code, hash_code, verify_code
from src.config import get_settings
from src.email.base import EmailSender
from src.policy import CODE_TTL, MAX_ATTEMPTS, RATE_LIMIT_WINDOW

router = APIRouter(prefix="/verification", tags=["verification"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post(
    "/request-code",
    response_model=RequestCodeOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_code(
    payload: RequestCodeIn,
    storage: VerificationStore = Depends(get_storage),
    email_sender: EmailSender = Depends(get_email_sender),
    _: AuthedKey = Depends(require_scope("verification:write")),
) -> RequestCodeOut:
    now = _now()
    recent = storage.latest_unconsumed_for_email(payload.email)
    if recent is not None and (now - recent.created_at) < RATE_LIMIT_WINDOW:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")

    code = generate_code()
    storage.create_code(
        VerificationCode(
            subject=payload.subject,
            email=payload.email,
            code_hash=hash_code(code, get_settings().code_hmac_secret),
            expires_at=now + CODE_TTL,
            attempts=0,
            consumed_at=None,
            created_at=now,
        )
    )
    email_sender.send(
        to=payload.email,
        subject="Your UTMIST verification code",
        body=f"Your verification code is {code}. It expires in 10 minutes.",
    )
    return RequestCodeOut()


@router.post("/confirm-code", response_model=ConfirmCodeOut)
def confirm_code(
    payload: ConfirmCodeIn,
    storage: VerificationStore = Depends(get_storage),
    _: AuthedKey = Depends(require_scope("verification:write")),
) -> ConfirmCodeOut:
    now = _now()
    code = storage.get_code(payload.subject)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_pending_code")

    # Idempotent replay: already verified and still within the TTL window.
    if code.consumed_at is not None:
        if now < code.expires_at:
            return ConfirmCodeOut(verified=True, subject=code.subject, email=code.email)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_pending_code")

    if now >= code.expires_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="expired")
    if code.attempts >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts"
        )

    if not verify_code(payload.code, code.code_hash, get_settings().code_hmac_secret):
        storage.set_attempts(payload.subject, code.attempts + 1)
        if code.attempts + 1 >= MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts"
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_code")

    storage.mark_consumed(payload.subject, now)
    return ConfirmCodeOut(verified=True, subject=code.subject, email=code.email)
