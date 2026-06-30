"""Native desktop window — the packaged app. No browser, no localhost bar.

Runs the local aiohttp server in a background thread on a PRIVATE free port, then
opens a pywebview window pointed at exactly that port. Binding our own ephemeral
port (not a fixed 8080) means nothing else — another app, a stale dev server, a
second copy of us — can ever shadow the window. (For dev with a known URL, use
`python -m radar`.)
"""
from __future__ import annotations
import asyncio
import socket
import threading
import time

from aiohttp import web

from .app import build_app
from .config import Config


def _bind_free() -> socket.socket:
    """Bind 127.0.0.1 on an OS-chosen free port and hand back the listening socket.
    Binding the socket here (not a fixed port) makes the desktop app collision-proof."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    return sock


def _serve(cfg: Config, sock: socket.socket, ready: threading.Event) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(build_app(cfg))
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.SockSite(runner, sock).start())   # serve on OUR bound socket
    ready.set()
    loop.run_forever()


def main() -> None:
    cfg = Config.load()
    sock = _bind_free()
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    ready = threading.Event()
    threading.Thread(target=_serve, args=(cfg, sock, ready), daemon=True).start()
    if not ready.wait(timeout=10):                   # wait for the real bind, no sleep-race
        print("[radar] server failed to start in time")
    try:
        import webview                               # pywebview — native window
        webview.create_window("Highlight Radar", url, width=520, height=820, min_size=(420, 600))
        webview.start()
    except Exception as exc:                         # no native backend -> never just die
        print(f"[radar] native window unavailable ({exc}); opening in browser: {url}")
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
