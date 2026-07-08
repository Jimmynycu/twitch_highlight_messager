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
from .llm import custom_brain, subscription_client, get_client, is_subscription_connected
from .heuristic import message_allowed


def _web_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)            # PyInstaller one-file unpack dir
    return Path(base) / "web" if base else Path(__file__).resolve().parent.parent / "web"


WEB = _web_dir()


async def pump(source, holder: dict, sink: WebPanelSink, window_size: int) -> None:
    """Rule brains score per message (sub-ms). LLM brains score in BATCHES off the
    event loop — one ~2s model call can never run per message on live chat, so
    candidates buffer and a flusher classifies the newest batch every few seconds."""
    window: deque = deque(maxlen=window_size)
    pending: deque = deque(maxlen=32)                     # bounded: busy chat drops oldest
    loop = asyncio.get_running_loop()

    async def flusher() -> None:
        while True:
            await asyncio.sleep(2.5)
            sc = holder["scorer"]
            if not pending or not hasattr(sc, "score_batch"):
                continue
            batch = list(pending)
            pending.clear()
            hits = await loop.run_in_executor(None, sc.score_batch, batch, list(window))
            for h in hits:
                sink.emit(h.to_event())

    flush_task = asyncio.create_task(flusher())
    try:
        async for msg in source.stream():
            if not message_allowed(msg, holder.get("message_rules")):
                continue
            window.append(msg)
            scorer = holder["scorer"]
            if hasattr(scorer, "score_batch"):
                pending.append(msg)                       # scored by the flusher
                continue
            hit = scorer.score(msg, window)
            if hit:
                sink.emit(hit.to_event())
    finally:
        flush_task.cancel()


def _bind_streamer(scorer, channel: str) -> None:
    if hasattr(scorer, "streamer") and channel and channel != "(mock)":
        scorer.streamer = channel.lstrip("#").lower()


def build_app(cfg: Config) -> web.Application:
    holder = {"scorer": get_scorer(cfg.scorer), "message_rules": auth.get_message_rules()}
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

    def _refresh_custom() -> None:
        """Register the user's 'Your gems' brain when a goal is set and an LLM is available."""
        goal = auth.get_goal()
        client = (subscription_client() if is_subscription_connected() else None) or get_client()
        if goal and client:
            SCORERS["custom"] = custom_brain(goal, client)
        else:
            SCORERS.pop("custom", None)

    async def index(_r):
        return web.FileResponse(WEB / ("panel.html" if channel() else "login.html"))

    async def health(_r):
        from .llm import is_subscription_connected
        return web.json_response({"ok": True, "brain": holder["scorer"].name, "channel": state["channel"],
                                  "openai": is_subscription_connected() or bool(os.environ.get("OPENAI_API_KEY"))})

    async def set_channel(request):
        ch = auth.normalize_channel((await request.json()).get("channel", ""))
        if not ch:
            return web.json_response({"ok": False, "error": "Not a valid Twitch channel name."}, status=400)
        loop = asyncio.get_running_loop()
        exists = await loop.run_in_executor(None, auth.channel_exists, ch)   # real Twitch check
        if exists is False:
            return web.json_response({"ok": False, "error": f"Channel '{ch}' doesn't exist on Twitch."}, status=404)
        auth.set_channel(ch)
        start_pump()
        return web.json_response({"ok": True, "channel": state["channel"]})

    async def brains(_r):
        active = holder["scorer"].name
        # only brains that actually work right now: rule brains always; LLM ones after connect
        return web.json_response([{**b, "available": True, "active": b["name"] == active}
                                  for b in BRAINS if b["name"] in SCORERS])

    async def set_brain(request):
        name = (await request.json()).get("name", "")
        if name not in SCORERS:
            return web.json_response({"ok": False, "error": "unknown brain"}, status=400)
        sc = get_scorer(name)
        _bind_streamer(sc, state["channel"] or "")
        holder["scorer"] = sc
        return web.json_response({"ok": True, "active": name})

    async def get_gems(_r):
        return web.json_response({"goal": auth.get_goal()})

    async def set_gems(request):
        goal = (await request.json()).get("goal", "").strip()
        auth.set_goal(goal)
        _refresh_custom()
        if goal and "custom" in SCORERS:
            sc = SCORERS["custom"]
            _bind_streamer(sc, state["channel"] or "")
            holder["scorer"] = sc
            return web.json_response({"ok": True, "active": "custom"})
        note = "" if not goal else "Connect ChatGPT (or set OPENAI_API_KEY) to use your gems."
        return web.json_response({"ok": bool(goal), "active": holder["scorer"].name, "note": note})

    async def get_message_rules(_r):
        holder["message_rules"] = auth.get_message_rules()
        return web.json_response(holder["message_rules"])

    async def set_message_rules(request):
        holder["message_rules"] = auth.set_message_rules(await request.json())
        return web.json_response({"ok": True, "message_rules": holder["message_rules"]})

    async def categories(request):
        q = request.query.get("q", "")
        loop = asyncio.get_running_loop()
        found = await loop.run_in_executor(None, auth.search_categories, q)
        return web.json_response(found)

    async def get_scan_settings(_r):
        return web.json_response(auth.get_scan_settings())

    async def set_scan_settings(request):
        return web.json_response({"ok": True, "scan_settings": auth.set_scan_settings(await request.json())})

    async def scan_preview(request):
        body = await request.json()
        loop = asyncio.get_running_loop()
        preview = await loop.run_in_executor(None, auth.discover_scan_channels, body)
        return web.json_response(preview)

    async def settings_page(_r):
        return web.FileResponse(WEB / "settings.html")

    async def change_page(_r):                                   # "Change channel" -> the real picker
        return web.FileResponse(WEB / "login.html")

    async def openai_login(_r):
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, auth.openai_connect)   # blocking OAuth, off the loop
        if res.get("status") == "ok":
            from .scorer import register_llm
            c = subscription_client()
            if c:
                register_llm(c)                  # smart brains light up immediately
            _refresh_custom()                    # and the user's custom gems brain
        return web.json_response(res)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/events", sink.sse)
    app.router.add_get("/health", health)
    app.router.add_get("/brains", brains)
    app.router.add_post("/brain", set_brain)
    app.router.add_post("/channel", set_channel)
    app.router.add_get("/settings", settings_page)
    app.router.add_get("/change", change_page)
    app.router.add_post("/auth/openai", openai_login)
    app.router.add_get("/gems", get_gems)
    app.router.add_post("/gems", set_gems)
    app.router.add_get("/message-rules", get_message_rules)
    app.router.add_post("/message-rules", set_message_rules)
    app.router.add_get("/categories", categories)
    app.router.add_get("/scan-settings", get_scan_settings)
    app.router.add_post("/scan-settings", set_scan_settings)
    app.router.add_post("/scan-preview", scan_preview)

    async def _start(_a):
        _refresh_custom()
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
