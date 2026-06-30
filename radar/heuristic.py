"""Rule brains — no model, no network, sub-millisecond.

One engine, three switchable *profiles* (grounded in the research presets), so the
user picks the philosophy that fits their stream:

  heuristic    (balanced)  — crowd energy + questions + newcomers. The all-rounder.
  crowd_pulse  (crowd)     — only crowd reactions: spikes, emote waves, copypasta,
                             clip requests, shouting. Clip-the-moment for gameplay.
  community    (community) — questions, @mentions, directing, first-timers. Reaction
                             noise off. For just-chatting / IRL.

Crowd/window signals fire ONCE per moment (cooldown) so a wall of KEKW becomes one
highlight with a count, not 50. Thresholds are static — per-channel auto-tuning is
the upgrade (ponytail: good enough until a real channel says otherwise).
"""
from __future__ import annotations
import re
from collections import deque, Counter
from typing import Optional

from .models import Message, Highlight

# emote -> panel category (community lexicon; third-party emotes arrive as plain text)
FUNNY = {"KEKW", "LULW", "OMEGALUL", "LUL", "KEKL", "ICANT", "PepeLaugh", "LMAOO"}
HYPE = {"PogChamp", "Pog", "POGGERS", "PogU", "Poggers", "LETSGO", "GIGACHAD", "EZ",
        "HYPERS", "monkaS", "monkaW", "PauseChamp"}

CLIP_RE = re.compile(r"\b(clip (that|it)|!clip)\b", re.I)
CONFUSE_RE = re.compile(r"(wait what|what just happened|how did|how is|\?\?\?)", re.I)
HOTTAKE_RE = re.compile(r"\b(hot take|overrated|underrated|better than|fight me)\b", re.I)
DIRECTION_RE = re.compile(r"\b(go (left|right|back)|pick the|take the|rush [ab]|do .+ first)\b", re.I)

# which signal groups each profile surfaces
PROFILES = {
    "balanced":  {"crowd", "ask", "community"},
    "crowd":     {"crowd"},
    "community": {"ask", "community"},
}
PROFILE_NAME = {"balanced": "heuristic", "crowd": "crowd_pulse", "community": "community"}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def _caps_ratio(t: str) -> float:
    letters = [c for c in t if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


class HeuristicBrain:
    # tunables
    SPIKE_WINDOW = 3.0   # seconds counted as "now"
    SPIKE_MIN = 6        # min msgs in window before a spike can fire
    SPIKE_FACTOR = 2.5   # current rate must beat this * rolling baseline
    EMOTE_BURST = 4      # same emote this many times in window = a burst
    DUP_BURST = 3        # identical message this many times = copypasta wave
    COOLDOWN = 6.0       # seconds between fires of the same window-level signal
    FLOOR = 1.2          # minimum score to surface

    def __init__(self, streamer: str = "", profile: str = "balanced"):
        self.profile = profile if profile in PROFILES else "balanced"
        self.groups = PROFILES[self.profile]
        self.name = PROFILE_NAME[self.profile]
        self.streamer = streamer.lstrip("#").lower()
        self.times: deque[float] = deque()
        self.ema = 0.0
        self.seen: set[str] = set()
        self._fired: dict[str, float] = {}

    def _rate(self, now: float) -> int:
        while self.times and now - self.times[0] > self.SPIKE_WINDOW:
            self.times.popleft()
        return len(self.times)

    def _cool(self, key: str, now: float) -> bool:
        if now - self._fired.get(key, -1e9) < self.COOLDOWN:
            return False
        self._fired[key] = now
        return True

    def score(self, msg: Message, window: "deque[Message]") -> Optional[Highlight]:
        now = msg.ts
        self.times.append(now)
        cur = self._rate(now)
        self.ema = (0.9 * self.ema + 0.1 * cur) if self.ema else float(cur)

        g = self.groups
        text = msg.text
        norm = _norm(text)
        tokens = text.split()

        tagged_first = msg.tags.get("first-msg") == "1"
        inferred_first = bool(msg.user) and msg.user.lower() not in self.seen
        if msg.user:
            self.seen.add(msg.user.lower())

        best: Optional[tuple[float, str, str]] = None

        def consider(s: float, cat: str, reason: str) -> None:
            nonlocal best
            if best is None or s > best[0]:
                best = (s, cat, reason)

        if "crowd" in g:
            # crowd: velocity spike (window-level, fires once per spike)
            if cur >= self.SPIKE_MIN and cur >= self.SPIKE_FACTOR * max(self.ema, 1.0) and self._cool("spike", now):
                consider(3.0, "hype", f"chat popping off ({cur}/3s)")

            # crowd: synchronized emote burst
            present = [w for w in tokens if w in FUNNY or w in HYPE]
            if present:
                counts: Counter = Counter()
                for m in window:
                    for w in m.text.split():
                        if w in FUNNY or w in HYPE:
                            counts[w] += 1
                for e in set(present):
                    if counts[e] >= self.EMOTE_BURST and self._cool("emote:" + e, now):
                        consider(2.6, "fun" if e in FUNNY else "hype", f"{e} x{counts[e]}")

            # crowd: copypasta wave
            if len(norm) >= 12:
                dup = sum(1 for m in window if _norm(m.text) == norm)
                if dup >= self.DUP_BURST and self._cool("dup:" + norm[:24], now):
                    consider(2.4, "fun", f"copypasta x{dup}")

            # crowd: clip requests, shouting, confusion (clip-the-moment cues)
            if CLIP_RE.search(text):
                consider(1.8, "hype", "clip request")
            if len(tokens) >= 2 and len(text) > 4 and _caps_ratio(text) > 0.7:
                consider(1.4, "hype", "shouting")
            if CONFUSE_RE.search(text):
                consider(1.4, "q", "confusion — clip the last few seconds")

        if "ask" in g:
            if norm.endswith("?") and len(norm) > 5:
                consider(1.6, "q", "question")
            if DIRECTION_RE.search(text):
                consider(1.7, "q", "directing the run")
            if HOTTAKE_RE.search(text):
                consider(1.3, "q", "hot take")
            if self.streamer and ("@" + self.streamer in text.lower() or self.streamer in norm.split()):
                consider(1.5, "q", "mentions you")

        if "community" in g:
            # tagged first-msg is authoritative; inferred (no tag) needs substance
            if tagged_first or (inferred_first and len(norm) >= 12 and len(tokens) >= 3):
                consider(1.2, "nw", "first message")

        if best is None or best[0] < self.FLOOR:
            return None

        s, cat, reason = best
        badges = msg.tags.get("badges", "")
        if any(b in badges for b in ("broadcaster", "moderator", "vip")):
            s *= 1.15
        return Highlight(msg, why=cat, score=round(s, 2), reason=reason)
