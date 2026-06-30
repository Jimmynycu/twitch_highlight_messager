"""The two types that cross the pipeline seams."""
from __future__ import annotations
from dataclasses import dataclass, field
import time


@dataclass
class Message:
    user: str
    text: str
    ts: float = field(default_factory=time.time)
    color: str = "#9C95AE"          # Twitch name color if known
    tags: dict = field(default_factory=dict)


@dataclass
class Highlight:
    msg: Message
    why: str                         # category key the panel colors on: q | hype | fun | nw
    score: float = 1.0
    reason: str = ""                 # human-readable trigger shown on the card ("KEKW x5")

    def to_event(self) -> dict:
        """Wire shape consumed by the panel over SSE."""
        return {
            "cat": self.why,
            "user": self.msg.user,
            "color": self.msg.color,
            "text": self.msg.text,
            "score": self.score,
            "reason": self.reason,
            "ts": self.msg.ts,
        }
