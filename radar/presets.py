"""The default brains the user picks from — grounded in the brain-research pass.

The first four are rule-only: zero setup, no API key, work the moment you run.
The last three came out of the research as LLM-graded presets; they register only
when an LLM key/login is wired, so the picker shows them but marks them "needs key".

`label`/`tagline` drive the panel's brain picker. `name` matches the scorer registry.
"""

BRAINS = [
    {"name": "custom", "label": "Your gems",
     "tagline": "Highlights what YOU describe — set it up in Settings.", "needs_llm": True},
    {"name": "heuristic", "label": "Balanced",
     "tagline": "Crowd energy + questions + newcomers. The all-rounder.", "needs_llm": False},
    {"name": "crowd_pulse", "label": "Crowd Pulse",
     "tagline": "Pure hype — emote waves, copypasta, clip-the-moment. For gameplay.", "needs_llm": False},
    {"name": "community", "label": "Community",
     "tagline": "Questions, @mentions & first-timers. Reaction noise off. For just-chatting.", "needs_llm": False},
    {"name": "question", "label": "Just Questions",
     "tagline": "Minimal — only genuine questions worth answering on air.", "needs_llm": False},

    # research presets that need an LLM key/login — selectable once one is connected
    {"name": "answer_chat", "label": "Answer the Chat",
     "tagline": "LLM-graded genuine questions, rhetorical/backseat filtered out.", "needs_llm": True},
    {"name": "everything_smart", "label": "Everything Interesting",
     "tagline": "Full rule + LLM stack: events, crowd, questions, hidden gems.", "needs_llm": True},
    {"name": "safe_and_quiet", "label": "Safe & Quiet",
     "tagline": "Rare, high-confidence nudges. Heavy toxicity/noise filtering.", "needs_llm": True},
]
