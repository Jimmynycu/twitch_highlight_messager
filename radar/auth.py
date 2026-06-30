"""Local settings: which channel to watch. Stored in %APPDATA%.

No accounts, no OAuth — reading Twitch chat is anonymous, so the app needs no login.
ponytail: the Twitch/ChatGPT login was deleted; it was the failure loop and the core
app never needed it. Re-add OAuth here only if you ever want sub/cheer/raid events.
"""
from __future__ import annotations
import json
import os
import pathlib

APP_DIR = pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home()) / "HighlightRadar"
STORE = APP_DIR / "settings.json"


def _load() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=2), encoding="utf-8")


def watch_channel() -> str:
    return _load().get("channel", "")


def set_channel(name: str) -> None:
    d = _load()
    d["channel"] = name.lstrip("#").strip().lower()
    _save(d)
