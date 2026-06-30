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
    assert c.mock is True and c.scorer == "heuristic" and c.port == 8080


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


def check_llm_brain():
    from collections import deque as _dq
    from radar.llm import LLMBrain, get_client, PRESET_GOALS

    seen = []

    class Fake:
        def classify(self, message, goal, recent):
            seen.append(message)
            t = message.lower()
            if t.endswith("?"):
                return "question"
            if "kekw" in t:
                return "funny"
            return "none"

    w = _dq(maxlen=10)
    ask = LLMBrain("answer_chat", "ask-only", {"question"}, Fake())
    # noise/short never reaches the model (cheap filter first)
    assert ask.score(Message("u", "hi"), w) is None and not seen
    # a genuine question surfaces as q
    h = ask.score(Message("u", "what sensitivity do you use?"), w)
    assert h is not None and h.why == "q", h
    # funny is classified but answer_chat doesn't accept it -> filtered
    assert ask.score(Message("u", "KEKW KEKW that was a great moment"), w) is None
    # everything_smart DOES accept funny
    allb = LLMBrain("everything_smart", "all", {"question", "hype", "funny", "new"}, Fake())
    assert allb.score(Message("u", "KEKW KEKW that was a great moment"), w) is not None
    # preset goals are defined for the three LLM presets
    assert set(PRESET_GOALS) == {"answer_chat", "everything_smart", "safe_and_quiet"}
    # the LLM presets register only when an LLM is actually available:
    # an API key (get_client) OR an already-connected ChatGPT subscription.
    from radar.llm import is_subscription_connected
    if get_client() is None and not is_subscription_connected():
        assert "answer_chat" not in SCORERS


def check_llm_registration():
    """With a client present, the 3 LLM presets register and are selectable."""
    from radar.scorer import register_llm, SCORERS as REG, get_scorer

    class Fake:
        def classify(self, message, goal, recent):
            return "none"

    added = register_llm(Fake())
    try:
        for n in ("answer_chat", "everything_smart", "safe_and_quiet"):
            assert n in REG, n
            assert get_scorer(n).name == n        # selectable by name -> picker enables it
    finally:
        for n in added:                           # restore the no-key state
            REG.pop(n, None)


def check_llm_client_parse():
    """The shared prompt/parse used by both the OpenAI and ai-sub-auth backends."""
    from radar.llm import LLMLabelClient
    assert LLMLabelClient(lambda system, user: "QUESTION").classify("x", "g", []) == "question"
    assert LLMLabelClient(lambda system, user: "banana").classify("x", "g", []) == "none"
    # a backend that throws must degrade to "none", never raise
    def boom(system, user):
        raise RuntimeError("model down")
    assert LLMLabelClient(boom).classify("x", "g", []) == "none"


def check_subscription_default():
    """Subscription is the default backend; prove the path with a FAKE ai_sub_auth
    module (no real lib, no login). Verifies lazy connect + chat_sync -> label -> brain."""
    import os
    import sys
    import types
    from collections import deque as _dq

    connects = []
    fake = types.ModuleType("ai_sub_auth")

    class AI:                                        # matches the real ai_sub_auth.AI signature
        def __init__(self, **kw):
            pass

        def connect(self, **kw):
            connects.append(1)                       # lazy: only on first classify

        def chat_sync(self, message="", *, system="", **kw):
            return types.SimpleNamespace(content="question" if "?" in (message + system) else "none")

    fake.AI = AI
    sys.modules["ai_sub_auth"] = fake
    os.environ["RADAR_LLM"] = "sub"                  # force the subscription backend
    os.environ.pop("OPENAI_API_KEY", None)
    try:
        import radar.llm as llm
        c = llm.get_client()
        assert c is not None, "sub-default should yield a client when the lib is present"
        assert not connects, "connect() must be lazy, not at get_client() time"
        assert c.classify("what sens?", "goal", []) == "question"
        assert connects, "first classify should trigger the one-time connect()"
        b = llm.LLMBrain("answer_chat", "ask", {"question"}, c)
        h = b.score(Message("u", "what sens do you use?"), _dq(maxlen=8))
        assert h is not None and h.why == "q"
    finally:
        sys.modules.pop("ai_sub_auth", None)
        os.environ.pop("RADAR_LLM", None)


def check_channel_input():
    """Channel input accepts bare name, #name, @name, a twitch URL, or a markdown link."""
    from radar.auth import normalize_channel as n
    assert n("moriarty_vt") == "moriarty_vt"
    assert n("#Moriarty_VT") == "moriarty_vt"
    assert n("@moriarty_vt") == "moriarty_vt"
    assert n("https://www.twitch.tv/moriarty_vt") == "moriarty_vt"
    assert n("https://twitch.tv/moriarty_vt/videos?x=1") == "moriarty_vt"
    assert n("  twitch.tv/Moriarty_VT  ") == "moriarty_vt"
    assert n("[moriarty_vt](https://www.twitch.tv/moriarty_vt)") == "moriarty_vt"
    assert n("") == ""


def check_gems():
    """Custom 'Your gems' goal store + brain factory (no network)."""
    import pathlib
    import tempfile
    import radar.auth as a
    from radar.llm import custom_brain, LLMLabelClient
    tmp = pathlib.Path(tempfile.mkdtemp())
    a.APP_DIR, a.STORE = tmp, tmp / "settings.json"
    assert a.get_goal() == ""
    a.set_goal("  funny copypasta and big plays  ")
    assert a.get_goal() == "funny copypasta and big plays"
    assert custom_brain("", None) is None and custom_brain("x", None) is None
    b = custom_brain("surface funny", LLMLabelClient(lambda s, u: "funny"))
    assert b and b.name == "custom"


def check_channel_store():
    """Channel persistence (temp dir, no network)."""
    import pathlib
    import tempfile
    import radar.auth as a
    tmp = pathlib.Path(tempfile.mkdtemp())
    a.APP_DIR, a.STORE = tmp, tmp / "settings.json"
    assert a.watch_channel() == ""
    a.set_channel("#SomeChannel")
    assert a.watch_channel() == "somechannel"


if __name__ == "__main__":
    check_scorer()
    check_source()
    check_config()
    check_heuristic()
    check_profiles()
    check_llm_brain()
    check_llm_registration()
    check_llm_client_parse()
    check_subscription_default()
    check_channel_input()
    check_channel_store()
    check_gems()
    print("selfcheck OK")
