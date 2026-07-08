"""LLM brains — the research presets that grade chat with a model.

The decision path is provider-agnostic and unit-tested with a fake client:
    cheap noise filter -> candidate gate (only spend a call on plausible lines)
    -> client.classify -> accept-label check -> map to a panel category.

The ONLY part that needs a key/login is the real client's `classify` (it builds the
prompt and calls the model). With no key, `get_client()` returns None and these
brains never register — the panel shows them as "needs key". `ai-sub-auth` (reuse a
ChatGPT subscription) plugs in at `get_client()` later; OPENAI_API_KEY works today.
"""
from __future__ import annotations
import os
import re
from typing import Optional, Protocol

from .models import Message, Highlight

# LLM label -> the panel's category key
LABEL_CAT = {"question": "q", "hype": "hype", "funny": "fun", "new": "nw"}

# preset id -> (goal handed to the model, labels this preset is allowed to surface)
PRESET_GOALS = {
    "answer_chat": (
        "Surface only genuine, answerable questions or direct callouts to the streamer. "
        "Ignore rhetorical, sarcastic, backseat-as-question, and copypasta.",
        {"question"}),
    "everything_smart": (
        "Surface anything genuinely interesting: real questions, crowd energy, funny or "
        "novel lines, first-timers. Filter toxicity, spam, and sarcasm-misread-as-praise.",
        {"question", "hype", "funny", "new"}),
    "safe_and_quiet": (
        "Surface ONLY must-react moments: clearly genuine high-relevance questions and the "
        "biggest positive crowd peaks. Filter everything else aggressively.",
        {"question", "hype"}),
}

_CMD = re.compile(r"^\s*!")
_SPAM = ("http://", "https://", "discord.gg/", "follow my", "check out my", "cheap view", "buy follow")
_EMOTES = ("KEKW", "OMEGALUL", "LULW", "LUL", "Pog", "POGGERS", "monkaS")


def _noise(t: str) -> bool:
    if len(t) < 6 or _CMD.match(t):
        return True
    low = t.lower()
    return any(s in low for s in _SPAM)


class LLMClient(Protocol):
    def classify(self, message: str, goal: str, recent: list[str]) -> str: ...


class LLMBrain:
    def __init__(self, name: str, goal: str, accept, client: LLMClient, streamer: str = ""):
        self.name = name
        self.goal = goal
        self.accept = set(accept)
        self.client = client
        self.streamer = streamer.lstrip("#").lower()

    def _candidate(self, t: str) -> bool:
        """Cheap gate: only spend a model call on plausibly-interesting lines."""
        if "?" in t or len(t.split()) >= 4 or any(e in t for e in _EMOTES):
            return True
        return bool(self.streamer) and ("@" + self.streamer) in t.lower()

    def score(self, msg: Message, window) -> Optional[Highlight]:
        t = msg.text.strip()
        if _noise(t) or not self._candidate(t):
            return None
        try:
            recent = [m.text for m in list(window)[-12:]]
            label = (self.client.classify(t, self.goal, recent) or "none").strip().lower()
        except Exception:
            return None                      # a flaky model never breaks the pump
        if label not in self.accept:
            return None
        cat = LABEL_CAT.get(label)
        if not cat:
            return None
        return Highlight(msg, why=cat, score=1.5, reason=f"LLM · {label}")

    def score_batch(self, msgs: list[Message], window) -> list[Highlight]:
        """Realtime path: ONE model call for a batch of messages (~2s latency each —
        per-message calls can never keep up with live chat). Also picks the single
        best message to spend time replying to on stream."""
        cand = [m for m in msgs if not _noise(m.text.strip()) and self._candidate(m.text.strip())]
        cand = cand[-16:]                    # bound the call; newest matter most
        if not cand:
            return []
        try:
            recent = [m.text for m in list(window)[-12:]]
            labels, best = self.client.classify_batch([m.text for m in cand], self.goal, recent)
        except Exception:
            return []
        hits: list[Highlight] = []
        for i, (m, label) in enumerate(zip(cand, labels)):
            if label not in self.accept:
                continue
            cat = LABEL_CAT.get(label)
            if not cat:
                continue
            is_best = (best == i)
            hits.append(Highlight(m, why=cat, score=2.5 if is_best else 1.5,
                                  reason=f"LLM · {label}" + (" · best to reply" if is_best else "")))
        return hits


class LLMLabelClient:
    """Turns any text-completion backend into a one-label classifier.

    The prompt + parse here is the tested part; the backend (`complete`) is the seam —
    OpenAI today, an ai-sub-auth ChatGPT subscription when enabled. Defensive by design.
    """
    _LABELS = "question, hype, funny, new, none"

    def __init__(self, complete):
        self._complete = complete            # callable(system, user) -> str

    def classify(self, message: str, goal: str, recent: list[str]) -> str:
        system = (f"You grade Twitch chat for a streamer. Goal: {goal} "
                  f"Reply with exactly ONE label from: {self._LABELS}. "
                  f"Use 'none' if the message should not be surfaced.")
        user = "Recent chat:\n" + "\n".join(recent[-8:]) + f"\n\nMessage to classify:\n{message}"
        try:
            out = (self._complete(system, user) or "none").lower()
        except Exception:
            return "none"
        for lab in ("question", "hype", "funny", "new"):
            if lab in out:
                return lab
        return "none"

    def classify_batch(self, messages: list[str], goal: str, recent: list[str]):
        """One call, many messages. Returns (labels_per_message, best_index|None)."""
        system = (f"You grade Twitch chat for a streamer. Goal: {goal} "
                  f"For EACH numbered message output one line 'N: label' with a label "
                  f"from: {self._LABELS}. Use 'none' for anything not worth surfacing. "
                  f"Then one final line 'best: N' for the single message most worth the "
                  f"streamer's time to reply to on air (or 'best: none').")
        numbered = "\n".join(f"{i+1}. {m}" for i, m in enumerate(messages))
        user = "Recent chat:\n" + "\n".join(recent[-8:]) + f"\n\nMessages to grade:\n{numbered}"
        labels = ["none"] * len(messages)
        best = None
        try:
            out = (self._complete(system, user) or "").lower()
        except Exception:
            return labels, best
        for line in out.splitlines():
            m = re.match(r"\s*best\s*[:\-]\s*(\d+)", line)
            if m:
                i = int(m.group(1)) - 1
                if 0 <= i < len(messages):
                    best = i
                continue
            m = re.match(r"\s*(\d+)\s*[.:\-]\s*(\w+)", line)
            if m:
                i, lab = int(m.group(1)) - 1, m.group(2)
                if 0 <= i < len(messages) and lab in ("question", "hype", "funny", "new", "none"):
                    labels[i] = lab
        return labels, best


def _openai_complete():
    """Build an OPENAI_API_KEY-backed completion fn, or None if unavailable."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    client = OpenAI()
    model = os.environ.get("RADAR_LLM_MODEL", "gpt-4o-mini")

    def complete(system: str, user: str) -> str:
        r = client.chat.completions.create(
            model=model, max_tokens=200, temperature=0,   # room for batch 'N: label' lines
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        return r.choices[0].message.content or "none"

    return complete


def _aisub_complete():
    """Reuse a ChatGPT subscription via ai-sub-auth — the DEFAULT LLM backend.

    Available whenever the lib imports; the one-time `ai.connect()` browser login is
    LAZY (first classify call, token cached after) so startup never blocks. Fully
    defensive: any failure -> 'none'; an absent lib -> None (rule brains unaffected).
    Not on PyPI — install from source:
        pip install git+https://github.com/AlexAnys/ai-sub-auth
    """
    try:
        import ai_sub_auth  # noqa: F401   availability check only — no login here
    except Exception:
        return None

    state = {"ai": None}
    # gpt-4o (the lib default) is REJECTED on ChatGPT/Codex accounts, and a tiny max_tokens
    # starves a reasoning model before it emits the labels — both verified live.
    model = os.environ.get("RADAR_LLM_MODEL", "gpt-5.5")

    def complete(system: str, user: str) -> str:
        try:
            if state["ai"] is None:
                from ai_sub_auth import AI
                ai = AI(provider="openai_codex")          # ChatGPT subscription
                ai.connect()                              # reuses cached token; logs in on first use
                state["ai"] = ai
            r = state["ai"].chat_sync(user, system=system, model=model, max_tokens=4000)
            return getattr(r, "content", None) or "none"
        except Exception:
            return "none"

    return complete


def get_client() -> Optional[LLMClient]:
    """Return a usable LLM client, or None when nothing is configured.

    Default backend is the ChatGPT **subscription** (ai-sub-auth); an OPENAI_API_KEY is
    the fallback. Override with RADAR_LLM = sub | openai | auto. None -> the LLM brains
    stay "needs setup" in the picker (rule brains still work with zero setup).
    """
    pref = os.environ.get("RADAR_LLM", "openai").lower()   # default: API key, no login UI
    if pref in ("sub", "subscription"):
        order = (_aisub_complete, _openai_complete)
    elif pref == "auto":
        order = (_openai_complete, _aisub_complete)
    else:                                     # "openai" (default) — key only, no OAuth surprise
        order = (_openai_complete,)
    for build in order:
        comp = build()
        if comp is not None:
            return LLMLabelClient(comp)
    return None


def subscription_client():
    """An LLM client backed by the ChatGPT subscription (after openai_connect)."""
    comp = _aisub_complete()
    return LLMLabelClient(comp) if comp else None


def custom_brain(goal: str, client):
    """LLM brain that surfaces whatever matches the user's OWN words/examples."""
    if not (goal and client):
        return None
    return LLMBrain("custom", goal, {"question", "hype", "funny", "new"}, client)


def is_subscription_connected() -> bool:
    """True only if the user actually connected (flag) or a real token is persisted.

    NOT true for a merely-importable Codex CLI — that false positive made the smart
    brains look available while their LLM calls silently failed (dead feed).
    """
    from . import auth
    if auth.openai_connected():
        return True
    try:
        from ai_sub_auth.providers import PROVIDERS
        from ai_sub_auth.token_store import TokenStore
        store = TokenStore(filename=PROVIDERS["openai_codex"].token_filename)
        return bool(store.load())
    except Exception:
        return False
