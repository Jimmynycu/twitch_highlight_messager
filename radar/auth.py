"""Real auth + token persistence, OBS-style.

Twitch: Authorization-Code + **loopback** flow like OBS — open the browser to Twitch,
user clicks Authorize, Twitch redirects to a tiny local server that catches the code,
we exchange it for tokens. No code-typing. Needs a Client ID + Secret from your Twitch
dev app, with redirect `http://localhost:27420` registered.

ChatGPT: ai_sub_auth's own loopback OAuth (vendored).

These calls BLOCK (they wait on the browser), so app.py runs them off the event loop.
The login itself can't be tested without your accounts; the flow is built to the docs.
"""
from __future__ import annotations
import http.server
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home()) / "HighlightRadar"
TOKENS = APP_DIR / "tokens.json"
TWITCH_SCOPES = "user:read:chat chat:read"
AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
USERS_URL = "https://api.twitch.tv/helix/users"
REDIRECT_PORT = 27420
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"


def _load() -> dict:
    try:
        return json.loads(TOKENS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS.write_text(json.dumps(d, indent=2), encoding="utf-8")


def logout() -> None:
    """Forget everything — next launch asks for login again (also: switch accounts)."""
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
    return status()["channel"]


def set_channel(name: str) -> None:
    d = _load()
    d["watch_channel"] = name.lstrip("#").lower()
    _save(d)


def _post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _twitch_login_name(client_id: str, access_token: str) -> str:
    req = urllib.request.Request(USERS_URL, headers={
        "Authorization": f"Bearer {access_token}", "Client-Id": client_id})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())["data"][0]["login"]
    except Exception:
        return ""


_SUCCESS = (b"<!doctype html><meta charset=utf-8>"
            b"<body style='font-family:system-ui;background:#13111A;color:#ECE9F2;text-align:center;padding-top:3rem'>"
            b"<h2>&#10003; Connected</h2><p>You can close this tab and return to Highlight Radar.</p></body>")


def twitch_login(client_id: str, client_secret: str, log=lambda *_: None) -> dict:
    """OBS-style: open browser to Twitch, catch the redirect on localhost, exchange.

    Blocks up to ~3 min waiting for you to authorize. Returns {status, login|error}.
    """
    import webbrowser
    state = os.urandom(16).hex()
    box: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            box["code"] = q.get("code", [None])[0]
            box["state"] = q.get("state", [None])[0]
            box["error"] = q.get("error_description", q.get("error", [None]))[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_SUCCESS)

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    except OSError as e:
        return {"status": "error", "error": f"local port {REDIRECT_PORT} busy: {e}"}
    srv.timeout = 180

    params = urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "scope": TWITCH_SCOPES, "state": state, "force_verify": "true",
    })
    try:
        webbrowser.open(f"{AUTHORIZE_URL}?{params}")
    except Exception:
        pass
    log("Waiting for Twitch authorization in your browser...")
    srv.handle_request()                       # blocks for the one redirect (or 180s timeout)
    srv.server_close()

    if box.get("error"):
        return {"status": "error", "error": box["error"]}
    if not box.get("code") or box.get("state") != state:
        return {"status": "error", "error": "login cancelled or timed out"}
    try:
        tok = _post(TOKEN_URL, {
            "client_id": client_id, "client_secret": client_secret, "code": box["code"],
            "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI,
        })
    except urllib.error.HTTPError as e:
        return {"status": "error", "error": f"token exchange {e.code}: {e.read().decode()[:160]}"}
    except Exception as e:
        return {"status": "error", "error": f"token exchange failed: {str(e)[:160]}"}

    login = _twitch_login_name(client_id, tok.get("access_token", ""))
    d = _load()
    d["twitch"] = {**tok, "client_id": client_id, "client_secret": client_secret, "login": login}
    d.setdefault("watch_channel", login)
    _save(d)
    return {"status": "ok", "login": login}


def openai_connect() -> dict:
    """Reuse a ChatGPT subscription via ai_sub_auth (its own loopback OAuth)."""
    try:
        from ai_sub_auth import AI
        AI(provider="openai_codex").connect()
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"[:200]}
    d = _load()
    d["openai_connected"] = True
    _save(d)
    return {"status": "ok"}
