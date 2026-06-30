"""Native desktop window — the packaged app. No browser, no localhost bar.

Runs the local aiohttp server in a background thread, then opens a pywebview window
pointed at it. (For dev without pywebview, use `python -m radar`.)
"""
from __future__ import annotations
import asyncio
import threading
import time

from aiohttp import web

from .app import build_app
from .config import Config


def _serve(cfg: Config) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(build_app(cfg))
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", cfg.port).start())
    loop.run_forever()


def main() -> None:
    cfg = Config.load()
    url = f"http://127.0.0.1:{cfg.port}"
    threading.Thread(target=_serve, args=(cfg,), daemon=True).start()
    time.sleep(0.8)                                  # let the server bind
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
