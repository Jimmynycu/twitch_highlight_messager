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


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def _gql(query: str, variables: dict, timeout: int = 10) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(_GQL, data=body,
                                 headers={"Client-Id": _WEB_CLIENT_ID,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


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


def normalize_scan_settings(raw: dict | None) -> dict:
    raw = raw or {}
    category_name = str(raw.get("category_name") or "Just Chatting").strip() or "Just Chatting"
    category_id = str(raw.get("category_id") or "509658").strip() or "509658"
    min_viewers = _clamp_int(raw.get("min_viewers"), 10, 0, 1_000_000)
    max_viewers = _clamp_int(raw.get("max_viewers"), 99, 0, 1_000_000)
    if min_viewers > max_viewers:
        min_viewers, max_viewers = max_viewers, min_viewers
    return {
        "category_name": category_name,
        "category_id": category_id,
        "min_viewers": min_viewers,
        "max_viewers": max_viewers,
        "max_channels": _clamp_int(raw.get("max_channels"), 20, 1, 50),
        "refresh_minutes": _clamp_int(raw.get("refresh_minutes"), 5, 1, 60),
    }


def get_scan_settings() -> dict:
    return normalize_scan_settings(_load().get("scan_settings"))


def set_scan_settings(settings: dict) -> dict:
    settings = normalize_scan_settings(settings)
    d = _load()
    d["scan_settings"] = settings
    _save(d)
    return settings


def search_categories(q: str, limit: int = 8) -> list[dict]:
    q = (q or "").strip()
    if len(q) < 2:
        return []
    query = """query($q:String!,$first:Int!){searchCategories(query:$q,first:$first){edges{node{id name displayName}}}}"""
    try:
        data = _gql(query, {"q": q, "first": _clamp_int(limit, 8, 1, 20)})
    except Exception:
        return []
    out = []
    for edge in (((data.get("data") or {}).get("searchCategories") or {}).get("edges") or []):
        node = edge.get("node") or {}
        if node.get("id") and (node.get("displayName") or node.get("name")):
            out.append({"id": str(node["id"]), "name": node.get("displayName") or node.get("name")})
    return out


def discover_scan_channels(settings: dict | None = None) -> dict:
    settings = normalize_scan_settings(settings)
    query = """query($id:ID!,$first:Int!,$after:Cursor){game(id:$id){id name streams(first:$first,after:$after,options:{sort:VIEWER_COUNT}){edges{cursor node{viewersCount broadcaster{login displayName}}} pageInfo{hasNextPage}}}}"""
    channels: list[dict] = []
    after = None
    fetched = 0
    first = 100
    for _ in range(12):
        try:
            data = _gql(query, {"id": settings["category_id"], "first": first, "after": after}, timeout=12)
        except Exception:
            break
        game = (data.get("data") or {}).get("game") or {}
        streams = game.get("streams") or {}
        edges = streams.get("edges") or []
        if game.get("name"):
            settings["category_name"] = game["name"]
        if not edges:
            break
        for edge in edges:
            fetched += 1
            node = edge.get("node") or {}
            broadcaster = node.get("broadcaster") or {}
            viewers = int(node.get("viewersCount") or 0)
            login = broadcaster.get("login")
            if login and settings["min_viewers"] <= viewers <= settings["max_viewers"]:
                channels.append({"login": login, "display_name": broadcaster.get("displayName") or login,
                                 "viewers": viewers})
                if len(channels) >= settings["max_channels"]:
                    return {"settings": settings, "channels": channels, "fetched": fetched}
        after = edges[-1].get("cursor")
        if not after or not (streams.get("pageInfo") or {}).get("hasNextPage"):
            break
        last_viewers = int(((edges[-1].get("node") or {}).get("viewersCount")) or 0)
        if last_viewers < settings["min_viewers"]:
            break
    return {"settings": settings, "channels": channels, "fetched": fetched}


def get_goal() -> str:
    """The user's own description of what to highlight (drives the 'Your gems' brain)."""
    return _load().get("gem_goal", "")


def set_goal(text: str) -> None:
    d = _load()
    d["gem_goal"] = (text or "").strip()
    _save(d)


def get_message_rules() -> dict:
    from .heuristic import normalize_message_rules
    return normalize_message_rules(_load().get("message_rules"))


def set_message_rules(rules: dict) -> dict:
    from .heuristic import normalize_message_rules
    rules = normalize_message_rules(rules)
    d = _load()
    d["message_rules"] = rules
    _save(d)
    return rules


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
