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
| `RADAR_LLM_MODEL` | `gpt-4o-mini` | model the LLM brains use |
| `RADAR_LLM` | `sub` | LLM backend: `sub` (ChatGPT subscription, default) · `openai` (API key) · `auto` |

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

## Status

- [x] Pipeline end to end — mock + anonymous Twitch read, live panel
- [x] Four rule brains, switchable **live** from the panel dropdown: `heuristic` (Balanced), `crowd_pulse`, `community`, `question`
- [x] Brain presets from the research pass; LLM presets (`answer_chat`, `everything_smart`, `safe_and_quiet`) implemented (`LLMBrain`, provider-agnostic) — auto-enable when `OPENAI_API_KEY` is set, otherwise shown as "needs key"
- [x] End-to-end QA — `selfcheck.py` green (incl. LLM brain + registration seam) + live panel / SSE / brain-switch verified on Windows
- [x] One-click Windows build: `build.ps1` → `dist\radar.exe`, double-click to run (verified serving the live panel)
- [x] ChatGPT **subscription is the default** LLM backend (`RADAR_LLM=sub`, lazy login) with `OPENAI_API_KEY` as fallback — **adapter unverified live**: `ai-sub-auth` isn't on PyPI (install from source), API assumed from its README, needs your one-time `ai.connect()` login. Wiring proven against a mock.
- [ ] TwitchIO OAuth for sub / cheer / raid events (full Community First)
