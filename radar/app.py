"""Wire source -> scorer -> sink, serve the panel. Pick a channel, watch real chat.

No login: reading Twitch chat is anonymous. First run (no channel) serves the channel
picker; once a channel is set, the panel streams its real chat. Dev shortcuts:
RADAR_MOCK=1 (canned chat) or RADAR_CHANNEL=<name> (skip the picker).
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

    def channel() -> str:
        if forced_mock:
            return "(mock)"
        return dev_channel or auth.watch_channel()

    def start_pump() -> None:
        if state["task"]:
            state["task"].cancel()
            state["task"] = None
        ch = channel()
        state["channel"] = ch or None
        if not ch:
            return
        _bind_streamer(holder["scorer"], ch)
        src = MockSource(cfg.mock_rate) if ch == "(mock)" else TwitchSource(ch)
        state["task"] = asyncio.create_task(pump(src, holder, sink, cfg.window))

    async def index(_r):
        return web.FileResponse(WEB / ("panel.html" if channel() else "login.html"))

    async def health(_r):
        from .llm import is_subscription_connected
        return web.json_response({"ok": True, "brain": holder["scorer"].name, "channel": state["channel"],
                                  "openai": is_subscription_connected() or bool(os.environ.get("OPENAI_API_KEY"))})

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

    async def settings_page(_r):
        return web.FileResponse(WEB / "settings.html")

    async def openai_login(_r):
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, auth.openai_connect)   # blocking OAuth, off the loop
        if res.get("status") == "ok":
            from .llm import subscription_client
            from .scorer import register_llm
            c = subscription_client()
            if c:
                register_llm(c)                  # smart brains light up immediately
        return web.json_response(res)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/events", sink.sse)
    app.router.add_get("/health", health)
    app.router.add_get("/brains", brains)
    app.router.add_post("/brain", set_brain)
    app.router.add_post("/channel", set_channel)
    app.router.add_get("/settings", settings_page)
    app.router.add_post("/auth/openai", openai_login)

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
    """Dev entry: server + browser. (The packaged app uses radar.desktop.)"""
    cfg = Config.load()
    url = f"http://localhost:{cfg.port}"
    print(f"Highlight Radar -> {url}   brain={cfg.scorer}")
    if os.environ.get("RADAR_NO_BROWSER", "").lower() not in ("1", "true", "yes", "on"):
        threading.Timer(1.2, lambda: _open(url)).start()
    web.run_app(build_app(cfg), host="127.0.0.1", port=cfg.port, print=None)
