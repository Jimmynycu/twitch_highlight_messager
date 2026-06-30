"""The brain seam.

Every brain implements `score(msg, window) -> Highlight | None`. The window (recent
chat) is handed in even when a brain ignores it, so cross-message brains (crowd
signals, copypasta, hype spikes) drop in later without changing the interface.

Swap brains by name via RADAR_SCORER. Register new ones with @register.
"""
from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable
from collections import deque

from .models import Message, Highlight


@runtime_checkable
class Scorer(Protocol):
    name: str
    def score(self, msg: Message, window: "deque[Message]") -> Optional[Highlight]: ...


SCORERS: dict[str, Scorer] = {}


def register(scorer: Scorer) -> Scorer:
    SCORERS[scorer.name] = scorer
    return scorer


def get_scorer(name: str) -> Scorer:
    if name not in SCORERS:
        raise KeyError(f"unknown brain {name!r}; available: {sorted(SCORERS)}")
    return SCORERS[name]


# ----- v0 brain: questions worth answering on-air -----
class _Question:
    """One line of real logic. The window is unused here — but it's there.

    Research-driven brains (crowd-signal, embedding, llm-judge, hybrid) register
    alongside this and are selected by name; this stays as the zero-cost default.
    """
    name = "question"

    def score(self, msg: Message, window: "deque[Message]") -> Optional[Highlight]:
        t = msg.text.strip()
        if len(t) > 5 and t.endswith("?"):
            return Highlight(msg, why="q", reason="question")
        return None


# instances, not classes, live in the registry
SCORERS["question"] = _Question()

# research-driven brains register here too — switch with RADAR_SCORER=<name> or the panel picker
from .heuristic import HeuristicBrain  # noqa: E402

SCORERS["heuristic"] = HeuristicBrain()                      # balanced — the all-rounder
SCORERS["crowd_pulse"] = HeuristicBrain(profile="crowd")     # crowd energy only
SCORERS["community"] = HeuristicBrain(profile="community")   # questions + newcomers

# LLM presets — register only when a model key/login is configured; otherwise the
# panel shows them as "needs key". Provider-agnostic (OPENAI_API_KEY today).
from .llm import LLMBrain, get_client, PRESET_GOALS  # noqa: E402


def register_llm(client) -> list[str]:
    """Register the LLM presets against `client`; return the names added.

    Called at import with whatever get_client() finds. The seam tests call it with a
    fake client to prove the presets become selectable once a key/login exists.
    """
    for name, (goal, accept) in PRESET_GOALS.items():
        SCORERS[name] = LLMBrain(name, goal, accept, client)
    return list(PRESET_GOALS)


_llm_client = get_client()
if _llm_client is not None:
    register_llm(_llm_client)
