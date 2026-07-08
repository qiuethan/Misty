from typing import Protocol


class EmailSendError(Exception):
    """Raised when an EmailSender fails to deliver a message.

    Lets callers distinguish a delivery failure (return a clean 502) from a
    programming error, instead of leaking a provider exception as a 500.
    """


class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...
