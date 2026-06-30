"""Settings from env / .env. No dependency — a 6-line .env reader does it."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Config:
    mock: bool
    channel: str
    scorer: str
    port: int
    window: int
    mock_rate: float

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv()
        channel = os.environ.get("RADAR_CHANNEL", "").strip()
        forced_mock = os.environ.get("RADAR_MOCK", "").lower() in ("1", "true", "yes", "on")
        return cls(
            mock=forced_mock or not channel,         # no channel set -> mock
            channel=channel or "(mock)",
            scorer=os.environ.get("RADAR_SCORER", "heuristic"),   # Balanced — surfaces signal out of the box
            port=int(os.environ.get("RADAR_PORT", "8080")),
            window=int(os.environ.get("RADAR_WINDOW", "200")),
            mock_rate=float(os.environ.get("RADAR_MOCK_RATE", "2.0")),
        )
