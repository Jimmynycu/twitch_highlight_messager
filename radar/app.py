"""Wire source -> scorer -> sink and serve the panel.

The pipeline is the `pump` coroutine; the brain it uses lives in a mutable slot so
the panel can switch brains live (POST /brain) without a restart.
"""
from __future__ import annotations
import asyncio
from collections import deque
from pathlib import Path

from aiohttp import web

from .config import Config
from .scorer import get_scorer, SCORERS
from .sink import WebPanelSink
from .source import MockSource, TwitchSource
from .presets import BRAINS

WEB = Path(__file__).resolve().parent.parent / "web"


async def pump(source, holder: dict, sink: WebPanelSink, window_size: int) -> None:
    window: deque = deque(maxlen=window_size)
    async for msg in source.stream():
        window.append(msg)
        hit = holder["scorer"].score(msg, window)
        if hit:
            sink.emit(hit.to_event())


def _bind_streamer(scorer, cfg: Config) -> None:
    if hasattr(scorer, "streamer") and cfg.channel not in ("", "(mock)"):
        scorer.streamer = cfg.channel.lstrip("#").lower()


def build_app(cfg: Config) -> web.Application:
    scorer = get_scorer(cfg.scorer)                       # fails loud on bad name
    _bind_streamer(scorer, cfg)
    holder = {"scorer": scorer}
    source = MockSource(cfg.mock_rate) if cfg.mock else TwitchSource(cfg.channel)
    sink = WebPanelSink()

    async def index(_r):
        return web.FileResponse(WEB / "panel.html")

    async def health(_r):
        return web.json_response({"ok": True, "brain": holder["scorer"].name,
                                  "source": "mock" if cfg.mock else cfg.channel})

    async def brains(_r):
        active = holder["scorer"].name
        return web.json_response([
            {**b, "available": b["name"] in SCORERS, "active": b["name"] == active}
            for b in BRAINS
        ])

    async def set_brain(request):
        try:
            name = (await request.json()).get("name", "")
        except Exception:
            name = ""
        if name not in SCORERS:
            return web.json_response({"ok": False, "error": "unknown or unavailable brain"}, status=400)
        sc = get_scorer(name)
        _bind_streamer(sc, cfg)
        holder["scorer"] = sc
        return web.json_response({"ok": True, "active": name})

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/events", sink.sse)
    app.router.add_get("/health", health)
    app.router.add_get("/brains", brains)
    app.router.add_post("/brain", set_brain)

    async def _start(a: web.Application):
        a["pump"] = asyncio.create_task(pump(source, holder, sink, cfg.window))

    async def _stop(a: web.Application):
        a["pump"].cancel()
        try:
            await a["pump"]
        except asyncio.CancelledError:
            pass

    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)
    return app


def run() -> None:
    cfg = Config.load()
    src = "mock" if cfg.mock else f"#{cfg.channel}"
    print(f"Highlight Radar -> http://localhost:{cfg.port}   source={src}   brain={cfg.scorer}")
    if cfg.mock:
        print("  (mock mode — set RADAR_CHANNEL=<channel> for live Twitch chat)")
    web.run_app(build_app(cfg), host="127.0.0.1", port=cfg.port, print=None)
