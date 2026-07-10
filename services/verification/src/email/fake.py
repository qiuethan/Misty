import re
from dataclasses import dataclass, field


@dataclass
class SentMessage:
    to: str
    subject: str
    body: str


@dataclass
class FakeSender:
    """Captures emails in memory instead of sending. Used in tests + playground."""

    sent: list[SentMessage] = field(default_factory=list)

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append(SentMessage(to=to, subject=subject, body=body))

    def last_code(self) -> str | None:
        """Test/playground convenience: pull the 6-digit code from the last body."""
        if not self.sent:
            return None
        m = re.search(r"\b(\d{6})\b", self.sent[-1].body)
        return m.group(1) if m else None
