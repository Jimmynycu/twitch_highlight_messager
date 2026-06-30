"""Runnable self-check for the pipeline core. No network, stdlib only.

    python selfcheck.py
"""
import asyncio
from collections import deque

from radar.models import Message
from radar.scorer import get_scorer, SCORERS
from radar.source import MockSource, TwitchSource
from radar.config import Config


def check_scorer():
    s = get_scorer("question")
    w = deque(maxlen=10)
    assert s.score(Message("u", "what sensitivity do you use?"), w) is not None
    assert s.score(Message("u", "hello chat"), w) is None
    assert s.score(Message("u", "?"), w) is None                      # too short
    h = s.score(Message("bob", "ranked after this?"), w)
    ev = h.to_event()
    assert ev["cat"] == "q" and ev["user"] == "bob" and ev["text"].endswith("?")
    assert "question" in SCORERS
    try:
        get_scorer("nope")
        raise AssertionError("bad brain name should raise")
    except KeyError:
        pass


def check_source():
    async def first():
        async for m in MockSource(rate=0).stream():
            return m
    m = asyncio.run(first())
    assert isinstance(m, Message) and m.text

    p = TwitchSource._parse(
        "@color=#FF7070;display-name=VodZilla :vodzilla!v@v.tmi.twitch.tv PRIVMSG #chan :is this ranked?"
    )
    assert p and p.user == "VodZilla" and p.color == "#FF7070" and p.text == "is this ranked?"


def check_config():
    import os
    os.environ.pop("RADAR_CHANNEL", None)
    os.environ.pop("RADAR_MOCK", None)
    c = Config.load()
    assert c.mock is True and c.scorer == "question" and c.port == 8080


def check_heuristic():
    from collections import deque as _dq
    from radar.heuristic import HeuristicBrain
    b = HeuristicBrain(streamer="captainclutch")
    w = _dq(maxlen=50)
    clock = [1000.0]

    def feed(user, text, dt=1.0):
        m = Message(user, text, ts=clock[0]); clock[0] += dt
        w.append(m); return b.score(m, w)

    assert feed("u1", "what sens do you use?").why == "q"
    burst = [feed(f"e{i}", "KEKW") for i in range(6)]          # spaced -> emote burst, not velocity
    assert any(r and r.why == "fun" for r in burst), burst
    assert feed("newbie_kev", "hi there everyone").why == "nw"
    assert feed("u2", "clip that").why == "hype"
    assert feed("u3", "LETS GOOOO").why == "hype"
    assert feed("u4", "@captainclutch you have to try this").why == "q"


def check_profiles():
    from collections import deque as _dq
    from radar.heuristic import HeuristicBrain
    assert HeuristicBrain(profile="crowd").name == "crowd_pulse"
    assert HeuristicBrain(profile="community").name == "community"
    # crowd profile ignores plain questions; community surfaces them
    cp = HeuristicBrain(profile="crowd")
    assert cp.score(Message("u", "what sens do you use?"), _dq(maxlen=8)) is None
    cm = HeuristicBrain(profile="community")
    assert cm.score(Message("u", "what sens do you use?"), _dq(maxlen=8)) is not None
    for n in ("question", "heuristic", "crowd_pulse", "community"):
        assert n in SCORERS, n


if __name__ == "__main__":
    check_scorer()
    check_source()
    check_config()
    check_heuristic()
    check_profiles()
    print("selfcheck OK")
