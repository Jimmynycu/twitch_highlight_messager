"""Wire source -> scorer -> sink, serve the panel, and gate on login.

Not authed -> serve the login screen, no chat. Authed -> serve the panel and pump
the logged-in user's real channel. The pump runs as a task that restarts on
login / channel change / logout. Brains switch live via /brain.

Dev shortcuts (skip login): RADAR_MOCK=1 (canned chat) or RADAR_CHANNEL=<name>
(anonymous real chat, no login).
"""
from __future__ import annotations
import asyncio
import os
import sys
import threading
import webbrowser
from collections import deque
from pathlib import Path

from aiohttp import web

from . import auth
from .config import Config
from .scorer import get_scorer, SCORERS
from .sink import WebPanelSink
from .source import MockSource, TwitchSource
from .presets import BRAINS


def _web_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)            # PyInstaller one-file unpack dir
    return Path(base) / "web" if base else Path(__file__).resolve().parent.parent / "web"


WEB = _web_dir()


async def pump(source, holder: dict, sink: WebPanelSink, window_size: int) -> None:
    window: deque = deque(maxlen=window_size)
    async for msg in source.stream():
        window.append(msg)
        hit = holder["scorer"].score(msg, window)
        if hit:
            sink.emit(hit.to_event())


def _bind_streamer(scorer, channel: str) -> None:
    if hasattr(scorer, "streamer") and channel and channel != "(mock)":
        scorer.streamer = channel.lstrip("#").lower()


def build_app(cfg: Config) -> web.Application:
    holder = {"scorer": get_scorer(cfg.scorer)}
    sink = WebPanelSink()
    state = {"task": None, "channel": None}

    forced_mock = bool(os.environ.get("RADAR_MOCK"))
    dev_channel = os.environ.get("RADAR_CHANNEL", "").strip()

    def authed() -> bool:
        return bool(forced_mock or dev_channel or auth.status()["twitch"])

    def resolve_channel() -> str:
        if forced_mock:
            return "(mock)"
        if dev_channel:
            return dev_channel
        st = auth.status()
        return st["channel"] if st["twitch"] else ""

    def start_pump() -> None:
        if state["task"]:
            state["task"].cancel()
            state["task"] = None
        ch = resolve_channel()
        state["channel"] = ch or None
        if not ch:
            return
        _bind_streamer(holder["scorer"], ch)
        src = MockSource(cfg.mock_rate) if ch == "(mock)" else TwitchSource(ch)
        state["task"] = asyncio.create_task(pump(src, holder, sink, cfg.window))

    async def index(_r):
        return web.FileResponse(WEB / ("panel.html" if authed() else "login.html"))

    async def health(_r):
        return web.json_response({"ok": True, "brain": holder["scorer"].name,
                                  "channel": state["channel"], "authed": authed()})

    async def auth_status(_r):
        return web.json_response(auth.status())

    async def twitch_login_ep(request):
        b = await request.json()
        cid, sec = b.get("client_id", "").strip(), b.get("client_secret", "").strip()
        if not (cid and sec):
            return web.json_response({"status": "error", "error": "client_id and client_secret required"}, status=400)
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, auth.twitch_login, cid, sec)   # blocking -> off the loop
        if res.get("status") == "ok":
            start_pump()
        return web.json_response(res)

    async def openai_login(_r):
        loop = asyncio.get_running_loop()
        # off the event loop: ai_sub_auth calls asyncio.run() internally, which
        # crashes if run inside the server's running loop (the bug you hit).
        res = await loop.run_in_executor(None, auth.openai_connect)
        return web.json_response(res)

    async def do_logout(_r):
        auth.logout()
        if state["task"]:
            state["task"].cancel()
            state["task"] = None
        state["channel"] = None
        return web.json_response({"ok": True})

    async def set_channel(request):
        ch = (await request.json()).get("channel", "").strip()
        if ch:
            auth.set_channel(ch)
            start_pump()
        return web.json_response({"ok": bool(ch), "channel": state["channel"]})

    async def brains(_r):
        active = holder["scorer"].name
        return web.json_response([{**b, "available": b["name"] in SCORERS,
                                   "active": b["name"] == active} for b in BRAINS])

    async def set_brain(request):
        name = (await request.json()).get("name", "")
        if name not in SCORERS:
            return web.json_response({"ok": False, "error": "unknown brain"}, status=400)
        sc = get_scorer(name)
        _bind_streamer(sc, state["channel"] or "")
        holder["scorer"] = sc
        return web.json_response({"ok": True, "active": name})

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/events", sink.sse)
    app.router.add_get("/health", health)
    app.router.add_get("/brains", brains)
    app.router.add_post("/brain", set_brain)
    app.router.add_get("/auth/status", auth_status)
    app.router.add_post("/auth/twitch/login", twitch_login_ep)
    app.router.add_post("/auth/openai", openai_login)
    app.router.add_post("/auth/logout", do_logout)
    app.router.add_post("/channel", set_channel)

    async def _start(_a):
        start_pump()

    async def _stop(_a):
        if state["task"]:
            state["task"].cancel()
            try:
                await state["task"]
            except asyncio.CancelledError:
                pass

    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)
    return app


def _open(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


def run() -> None:
    """Dev entry: server + browser. (The packaged app uses radar.desktop instead.)"""
    cfg = Config.load()
    url = f"http://localhost:{cfg.port}"
    print(f"Highlight Radar -> {url}   brain={cfg.scorer}")
    if os.environ.get("RADAR_NO_BROWSER", "").lower() not in ("1", "true", "yes", "on"):
        threading.Timer(1.2, lambda: _open(url)).start()
    web.run_app(build_app(cfg), host="127.0.0.1", port=cfg.port, print=None)
