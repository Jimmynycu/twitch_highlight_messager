"""The streamer panel sink: pushes highlights to every open browser over SSE.

No new dependency beyond aiohttp, no frontend framework — the browser opens
EventSource('/events') and each highlight arrives as one `data:` line.
"""
from __future__ import annotations
import asyncio
import json

from aiohttp import web


class WebPanelSink:
    def __init__(self) -> None:
        self.clients: set[asyncio.Queue] = set()

    def emit(self, event: dict) -> None:
        for q in list(self.clients):
            q.put_nowait(event)

    async def sse(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        })
        await resp.prepare(request)
        q: asyncio.Queue = asyncio.Queue()
        self.clients.add(q)
        try:
            await resp.write(b": connected\n\n")
            while True:
                event = await q.get()
                await resp.write(f"data: {json.dumps(event)}\n\n".encode())
        except (asyncio.CancelledError, ConnectionResetError, ConnectionError):
            pass
        finally:
            self.clients.discard(q)
        return resp
