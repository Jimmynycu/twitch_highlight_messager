"""Real auth + token persistence. Login is asked once; tokens live in %APPDATA%.

Twitch uses the Device Code Flow (needs only a client id from YOUR Twitch dev app —
no secret, no redirect server). ChatGPT uses ai-sub-auth's connect().

UNTESTED end to end: I can't register your dev app or perform the sign-in. The flow
is built to the docs; we debug it against your runtime.
"""
from __future__ import annotations
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home()) / "HighlightRadar"
TOKENS = APP_DIR / "tokens.json"
TWITCH_SCOPES = "user:read:chat chat:read"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
USERS_URL = "https://api.twitch.tv/helix/users"


def _load() -> dict:
    try:
        return json.loads(TOKENS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS.write_text(json.dumps(d, indent=2), encoding="utf-8")


def logout() -> None:
    """Forget everything — next launch asks for login again."""
    try:
        TOKENS.unlink()
    except FileNotFoundError:
        pass


def status() -> dict:
    d = _load()
    tw = d.get("twitch", {})
    return {
        "twitch": bool(tw.get("access_token")),
        "login": tw.get("login", ""),
        "channel": d.get("watch_channel") or tw.get("login", ""),
        "openai": bool(d.get("openai_connected")),
    }


def watch_channel() -> str:
    s = status()
    return s["channel"]


def set_channel(name: str) -> None:
    d = _load()
    d["watch_channel"] = name.lstrip("#").lower()
    _save(d)


def _post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def twitch_start(client_id: str) -> dict:
    """Begin Device Code Flow. Returns user_code, verification_uri, device_code, interval."""
    d = _load()
    d["twitch_client_id"] = client_id
    _save(d)
    return _post(DEVICE_URL, {"client_id": client_id, "scopes": TWITCH_SCOPES})


def twitch_poll(device_code: str) -> dict:
    """Poll once. -> {status: 'pending'} | {status: 'ok', login: ...} | {status: 'error', error}."""
    client_id = _load().get("twitch_client_id", "")
    try:
        tok = _post(TOKEN_URL, {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
    except urllib.error.HTTPError as e:
        msg = e.read().decode()
        if "authorization_pending" in msg:
            return {"status": "pending"}
        return {"status": "error", "error": msg[:200]}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    login = _twitch_login_name(client_id, tok.get("access_token", ""))
    d = _load()
    d["twitch"] = {**tok, "client_id": client_id, "login": login}
    d.setdefault("watch_channel", login)
    _save(d)
    return {"status": "ok", "login": login}


def _twitch_login_name(client_id: str, access_token: str) -> str:
    req = urllib.request.Request(USERS_URL, headers={
        "Authorization": f"Bearer {access_token}", "Client-Id": client_id})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())["data"][0]["login"]
    except Exception:
        return ""


def openai_connect() -> dict:
    """Reuse a ChatGPT subscription via ai-sub-auth (opens its login). UNTESTED."""
    try:
        from ai_sub_auth import AI
        AI(provider="openai_codex").connect()          # ChatGPT subscription (OAuth)
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"[:200]}
    d = _load()
    d["openai_connected"] = True
    _save(d)
    return {"status": "ok"}
