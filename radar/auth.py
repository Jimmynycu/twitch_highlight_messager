"""Local settings: which channel to watch. Stored in %APPDATA%.

No accounts, no OAuth — reading Twitch chat is anonymous, so the app needs no login.
ponytail: the Twitch/ChatGPT login was deleted; it was the failure loop and the core
app never needed it. Re-add OAuth here only if you ever want sub/cheer/raid events.
"""
from __future__ import annotations
import json
import os
import pathlib
import re
import urllib.request

APP_DIR = pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home()) / "HighlightRadar"
STORE = APP_DIR / "settings.json"


def _load() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8-sig"))   # -sig: tolerate a BOM
    except Exception:
        return {}


def _save(d: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=2), encoding="utf-8")


def watch_channel() -> str:
    return _load().get("channel", "")


def normalize_channel(s: str) -> str:
    """Accept a bare name, #name, @name, a twitch.tv URL, or a [md](url) link -> login name."""
    s = (s or "").strip()
    m = re.search(r"\(([^)]+)\)", s)                    # markdown [text](url) -> use the url
    if m and m.group(1).strip():
        s = m.group(1).strip()
    m = re.search(r"twitch\.tv/([^/?#\s]+)", s, re.I)   # strip a twitch URL to its first path part
    if m:
        s = m.group(1)
    s = s.lstrip("#@").strip()
    m = re.match(r"[A-Za-z0-9_]+", s)                   # the channel token
    return m.group(0).lower() if m else ""


def set_channel(name: str) -> None:
    d = _load()
    d["channel"] = normalize_channel(name)
    _save(d)


# Twitch's own public web Client-Id — lets us query GQL anonymously (no user login).
_GQL = "https://gql.twitch.tv/gql"
_WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"


def channel_exists(name: str):
    """True/False if the Twitch login exists. None if the check itself failed (then allow).

    ponytail: uses Twitch's public web client-id over GQL — no OAuth. If it ever breaks,
    None means we fall back to letting the channel through rather than blocking the user.
    """
    name = normalize_channel(name)
    if not name:
        return False
    body = json.dumps({"query": "query($l:String!){user(login:$l){id}}",
                       "variables": {"l": name}}).encode()
    req = urllib.request.Request(_GQL, data=body,
                                 headers={"Client-Id": _WEB_CLIENT_ID,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        return bool((data.get("data") or {}).get("user"))
    except Exception:
        return None


def get_goal() -> str:
    """The user's own description of what to highlight (drives the 'Your gems' brain)."""
    return _load().get("gem_goal", "")


def set_goal(text: str) -> None:
    d = _load()
    d["gem_goal"] = (text or "").strip()
    _save(d)


def openai_connected() -> bool:
    """True once the user has actually completed the in-app ChatGPT connect."""
    return bool(_load().get("openai_connected"))


def openai_connect() -> dict:
    """Optional: reuse a ChatGPT subscription via ai_sub_auth (opens its OAuth login).

    Not required — the rule brains work with no AI. This only unlocks the smart brains.
    The token is cached by ai_sub_auth, so it's a one-time login.
    """
    try:
        from ai_sub_auth import AI
        AI(provider="openai_codex").connect()
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"[:200]}
    d = _load()
    d["openai_connected"] = True
    _save(d)
    return {"status": "ok"}
