# Highlight Radar

Surfaces the chat messages worth reacting to on stream. Reads Twitch chat in real
time, scores each message with a swappable "brain," and pushes the keepers to a
live streamer panel in the browser.

Pipeline: **source → scorer (the brain) → web panel (SSE)**.

## Run it — one click, no Python

```powershell
./build.ps1            # builds dist\radar.exe (one file, ~35 MB)
```

Then **double-click `dist\radar.exe`** — it starts the local server and opens the panel
in your browser. No Python, no install, no folder to poke at. Mock chat by default; set
`RADAR_CHANNEL` for a real channel. (To share it, attach `dist\radar.exe` to a GitHub
Release — it's too big to live in the repo; or the other person runs `build.ps1`.)

## Quickstart for development (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m radar           # mock mode — open http://localhost:8080
```

Mock mode replays canned chat so you can see the panel work with zero setup.
To read a real channel:

```powershell
$env:RADAR_CHANNEL = "somechannel"   # anonymous read — no login needed
python -m radar
```

Or run `./run.ps1` (creates the venv, installs, launches).

## The brain is swappable

Every brain implements one method — `score(msg, window) -> Highlight | None` — and
is selected by name. The window (recent chat) is always passed in, so cross-message
brains (crowd-signal, copypasta, hype spikes) drop in without changing anything else.

```powershell
$env:RADAR_SCORER = "heuristic"   # "Balanced" — crowd energy + questions + newcomers (the all-rounder)
# others: crowd_pulse (pure hype / clip-the-moment), community (questions + first-timers), question (minimal)
# or just switch live from the brain dropdown in the panel — no restart
```

Add a brain: implement the method in `radar/scorer.py`, register it, select by name.
More brains land after the research pass (see Status).

## Settings (env or a local `.env`)

| Var | Default | Meaning |
|-----|---------|---------|
| `RADAR_CHANNEL` | _(unset → mock)_ | Twitch channel to read |
| `RADAR_SCORER` | `question` | which brain |
| `RADAR_PORT` | `8080` | panel port |
| `RADAR_MOCK` | _(off)_ | force mock even with a channel set |
| `OPENAI_API_KEY` | _(unset)_ | set it (and `pip install openai`) to unlock the LLM brains |
| `RADAR_LLM_MODEL` | `gpt-4o-mini` (key) / `gpt-5.5` (subscription) | model the LLM brains use |
| `RADAR_LLM` | `openai` | LLM backend: `openai` (API key) · `sub` (ChatGPT subscription) · `auto`. The app auto-uses the subscription when it's connected in-app. |

## Layout

```
radar/
  models.py   Message, Highlight  (cross the seams)
  source.py   MockSource (replay) + TwitchSource (anonymous IRC)
  scorer.py   Scorer protocol + brains + registry   <- the swappable part
  sink.py     WebPanelSink — SSE to the browser
  app.py      wires source -> scorer -> sink, serves the panel
  config.py   env / .env settings
web/panel.html   the live streamer panel
selfcheck.py     `python selfcheck.py` — runnable, no network
```

## QA — mandatory, against the #1 live channel

Gem quality is verified against the **busiest live channel on Twitch**, not a quiet or mock one
(a quiet channel hides brain problems). This runs the real pipeline:

```powershell
python qa_live.py            # finds the current #1 by viewers, prints surfaced gems + % surfaced
```

A **pre-commit hook enforces it on every commit** (and therefore before every release):

```powershell
git config core.hooksPath .githooks   # once per clone
```

The hook blocks the commit if the pipeline can't read the live channel (catches mock / wrong-source /
crash regressions). Override only in emergencies with `git commit --no-verify`. A healthy busy channel
surfaces ~3–5% of chat (real questions, @mentions/callouts, crowd moments, genuine first-timers).

## Status

- [x] Pipeline end to end — mock + anonymous Twitch read, live panel
- [x] Four rule brains, switchable **live** from the panel dropdown: `heuristic` (Balanced), `crowd_pulse`, `community`, `question`
- [x] Brain presets from the research pass; LLM presets (`answer_chat`, `everything_smart`, `safe_and_quiet`) implemented (`LLMBrain`, provider-agnostic) — auto-enable when `OPENAI_API_KEY` is set, otherwise shown as "needs key"
- [x] End-to-end QA — `selfcheck.py` green (incl. LLM brain + registration seam) + live panel / SSE / brain-switch verified on Windows
- [x] One-click Windows build: `build.ps1` → `dist\radar.exe`, double-click to run (verified serving the live panel)
- [x] ChatGPT **subscription LLM path verified live** (ai-sub-auth, model `gpt-5.5` — `gpt-4o` is rejected on ChatGPT/Codex accounts): realtime **batch scoring** (one model call per ~2.5s window, off the event loop, bounded backlog) surfaced correct labeled gems + a **"best to reply" pick per batch** on the #1 live channel (82k viewers). Per-message LLM calls can never keep up with live chat — the batch path is the realtime design.
- [ ] TwitchIO OAuth for sub / cheer / raid events (full Community First)
