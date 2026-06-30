"""Where chat comes from.

MockSource  — replays canned chat, zero deps/network, for offline dev + E2E QA.
TwitchSource — anonymous IRC read. No auth, no API key, no dependency: reading
               chat needs none. (OAuth/TwitchIO arrives only when the brain wants
               sub/cheer/raid events.)  ponytail: raw asyncio IRC until then.
"""
from __future__ import annotations
import asyncio
from typing import AsyncIterator

from .models import Message


class MockSource:
    """Scripted chat with deliberate bursts — emote wave, copypasta, shout,
    first-timers, questions — so every brain and the crowd signals are visibly
    exercised offline. `rate` scales the scripted gaps (1.0 = as written)."""
    SCRIPT = [
        (0.0, "vodzilla", "what game is this? just got here", "#57C2FF"),
        (1.4, "ggwp_andy", "are you gonna play ranked after this?", "#5BD6A0"),
        (1.2, "frostbyte", "lol nice", "#57C2FF"),
        (0.18, "rektlord", "KEKW", "#FFD866"),
        (0.14, "bonk_tv", "KEKW", "#C792EA"),
        (0.12, "saltmine", "OMEGALUL", "#FF7070"),
        (0.12, "pogtato", "KEKW", "#FFB454"),
        (0.12, "lilybyte", "LULW", "#FF7BC2"),
        (0.12, "grimjaw", "KEKW he really did that", "#7AA2FF"),
        (1.6, "m1ndgames", "go left through the caves, trust", "#C792EA"),
        (1.3, "newbie_kev", "first time on the channel, love the vibe", "#5BD6A0"),
        (0.25, "p1", "Have you ever heard the tragedy of Darth Plagueis the Wise?", "#9C95AE"),
        (0.22, "p2", "Have you ever heard the tragedy of Darth Plagueis the Wise?", "#9C95AE"),
        (0.22, "p3", "Have you ever heard the tragedy of Darth Plagueis the Wise?", "#9C95AE"),
        (1.5, "clutchordie", "LETS GOOOOO", "#FFB454"),
        (0.9, "nora_b", "clip that", "#57C2FF"),
        (2.2, "lurkmaster", "why did you build armor instead of crit there?", "#FF7BC2"),
    ]

    def __init__(self, rate: float = 1.0):
        self.rate = rate

    async def stream(self) -> AsyncIterator[Message]:
        i = 0
        while True:
            gap, user, text, color = self.SCRIPT[i % len(self.SCRIPT)]
            i += 1
            await asyncio.sleep(gap * self.rate)
            yield Message(user=user, text=text, color=color)


class TwitchSource:
    HOST, PORT = "irc.chat.twitch.tv", 6667

    def __init__(self, channel: str):
        self.channel = channel.lstrip("#").lower()

    async def stream(self) -> AsyncIterator[Message]:
        while True:                                   # reconnect loop
            try:
                async for m in self._read():
                    yield m
            except (OSError, asyncio.IncompleteReadError):
                await asyncio.sleep(2)

    async def _read(self) -> AsyncIterator[Message]:
        reader, writer = await asyncio.open_connection(self.HOST, self.PORT)
        nick = "justinfan" + str(10000 + sum(map(ord, self.channel)) % 80000)
        writer.write(b"CAP REQ :twitch.tv/tags\r\n")
        writer.write(f"NICK {nick}\r\n".encode())
        writer.write(f"JOIN #{self.channel}\r\n".encode())
        await writer.drain()
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("PING"):
                    writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await writer.drain()
                    continue
                msg = self._parse(line)
                if msg:
                    yield msg
        finally:
            writer.close()

    @staticmethod
    def _parse(line: str) -> "Message | None":
        tags: dict = {}
        if line.startswith("@"):
            tagstr, _, line = line.partition(" ")
            for kv in tagstr[1:].split(";"):
                k, _, v = kv.partition("=")
                tags[k] = v
        if "PRIVMSG" not in line:
            return None
        prefix, _, rest = line.partition(" ")        # ":nick!user@host PRIVMSG #chan :text"
        parts = rest.split(" ", 2)
        if len(parts) < 3:
            return None
        text = parts[2][1:] if parts[2].startswith(":") else parts[2]
        nick = prefix[1:].split("!", 1)[0]
        return Message(
            user=tags.get("display-name") or nick,
            text=text,
            color=tags.get("color") or "#9C95AE",
            tags=tags,
        )
