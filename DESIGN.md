---
version: alpha
name: Highlight Radar
description: >
  A streamer's second-monitor companion. A small dark native window (~520x820)
  that watches a Twitch channel's live chat and surfaces only the messages worth
  reacting to ("gems"), color-coded, newest on top. The design language is a quiet
  precision instrument — a radar scope left running on a second monitor — not a chat
  client. Near-black neutral chrome at near-zero chroma, one owned signal accent
  (radar aqua), a disciplined semantic gem spectrum, and a tabular-mono readout voice.

# ----------------------------------------------------------------------------
# COLORS  — cool-neutral near-black chrome (NOT purple-tinted), saturation spent only on signal
# ----------------------------------------------------------------------------
colors:
  # --- surface ladder (chrome). Depth = these steps + hairlines, never shadow. ---
  frame:                "#07080A"   # outermost window field / footer — deepest, faint cool tint
  surface:              "#0C0D10"   # app body / page background
  surface-container:    "#121317"   # gem card resting surface
  surface-container-hi: "#181A1F"   # gem card hover / priority / active chip fill
  surface-glass:        "rgba(10,11,14,0.72)"  # header only — paired with backdrop blur

  # --- hairlines (stepped; lighten on hover, do NOT use opacity overlays) ---
  outline:              "#202329"   # default 1px borders (cards, chips, inputs)
  outline-strong:       "#2C3037"   # hover / focus-adjacent borders, dividers
  outline-glass:        "rgba(255,255,255,0.07)"  # 1px line on glass header

  # --- text (never pure white; avoids halation on near-black) ---
  on-surface:           "#ECEDEF"   # primary text, gem message body
  on-surface-variant:   "#9BA0AA"   # secondary — usernames, secondary labels
  on-surface-muted:     "#666C76"   # tertiary — timestamps, mono micro-labels, captions

  # --- THE OWNED ACCENT (radar aqua). Brand mark, focus, active state, primary CTA. ---
  accent:               "#3FE0BE"   # high-voltage signal aqua — "radar lock / live sweep"
  accent-hover:         "#5AE9CB"
  accent-dim:           "#2BB89B"
  on-accent:            "#04140F"   # ink on accent fills
  accent-soft:          "rgba(63,224,190,0.13)"

  # --- live / status ---
  live:                 "#5BD6A0"   # connected pulse dot
  error:                "#FF6B6B"

  # --- gem category spectrum (the ONLY saturated thing on screen) ---
  # Used as: foreground hue (chip + username accent) + left signal stripe. NEVER a full background.
  gem-question:         "#6AA0FF"
  gem-hype:             "#FFB454"
  gem-fun:              "#FF7BC2"
  gem-new:              "#3FE0BE"   # New / Notable — intentionally the brand hue
  gem-mention:          "#C77DFF"   # priority
  gem-sub:              "#FF6B6B"    # priority

# ----------------------------------------------------------------------------
# TYPOGRAPHY  — two voices, system stacks only (no CDN webfonts)
#   VOICE 1 (sans):  tight negative-tracking UI sans  — chrome, brand, message body
#   VOICE 2 (mono):  tabular instrument readout       — every number, label, status, time
#   --sans: "Segoe UI Variable Display","Segoe UI",system-ui,-apple-system,"SF Pro Display",Arial,sans-serif
#   --mono: ui-monospace,"Cascadia Code","SF Mono","Consolas",Menlo,monospace
# ----------------------------------------------------------------------------
typography:
  brand:       { fontFamily: sans, fontSize: 15px, fontWeight: "600", letterSpacing: -0.02em }
  title-lg:    { fontFamily: sans, fontSize: 20px, fontWeight: "600", letterSpacing: -0.025em }
  title-md:    { fontFamily: sans, fontSize: 15px, fontWeight: "600", letterSpacing: -0.015em }
  body-msg:    { fontFamily: sans, fontSize: 16px, fontWeight: "450", lineHeight: 1.45, letterSpacing: -0.005em }
  body:        { fontFamily: sans, fontSize: 14px, fontWeight: "400", lineHeight: 1.5 }
  username:    { fontFamily: sans, fontSize: 13px, fontWeight: "650", letterSpacing: -0.01em }
  readout:     { fontFamily: mono, fontSize: 15px, fontWeight: "600", fontFeature: "tnum" }   # stat values
  mono-label:  { fontFamily: mono, fontSize: 10px, fontWeight: "600", letterSpacing: 0.14em }  # UPPERCASE micro-labels
  mono-meta:   { fontFamily: mono, fontSize: 11px, fontWeight: "500", letterSpacing: 0.02em, fontFeature: "tnum" }  # time/status

# ----------------------------------------------------------------------------
# SHAPE  — radius is grammar: pill = action/tag, angular = content/utility
# ----------------------------------------------------------------------------
rounded: { xs: 4px, sm: 7px, DEFAULT: 10px, md: 12px, lg: 16px, full: 9999px }

# ----------------------------------------------------------------------------
# SPACING  — strict 4px base; 8 inside groups, 16 between, 24-32 sections
# ----------------------------------------------------------------------------
spacing: { unit: 4px, sm: 8px, card-gap: 8px, card-padding: "12px 14px 13px 17px", gutter: 16px, section: 24px }

# ----------------------------------------------------------------------------
# MOTION  — one gesture per event; "radar lock" spring
# ----------------------------------------------------------------------------
motion:
  lock:    "cubic-bezier(0.16,1,0.3,1) 240ms"   # gem arrival spring
  control: "120ms ease"                          # hover/press
  afterglow: "age-decay opacity 1.0 -> 0.64 down the feed (steady state, no animation)"
  at-rest: "ONLY the live dot 2.2s pulse"
  reduced: "prefers-reduced-motion: drop spring/pulse; instant insert + 150ms tint fade"
---

# Overview

Highlight Radar is an **instrument, not a feed** — a radar scope or studio VU meter left
running on a second monitor: calm at rest, snapping to attention only when the channel
produces something worth reacting to.

The cardinal rule: **do not echo Twitch.** The platform is purple (`#9146FF`); a companion
that is also purple reads as a fan overlay, not a flagship. So the chrome is true cool-neutral
near-black at near-zero chroma, and the product owns a single non-Twitch signal color —
**radar aqua `#3FE0BE`** — for the brand mark, focus, active state, and the one primary action.
Saturation is a budget, spent almost entirely on the gem category colors, because that
color-coding *is* the product's reason to exist. Desaturated chrome makes a colored gem parse
in a single glance — the whole job of a glanceable second-monitor tool.

# Typography

Two voices, both system stacks. **Sans** (tight negative tracking, -0.02 to -0.03em, weight
600) for chrome, brand, titles. **Mono** (tabular-nums) is **load-bearing** — every number,
timestamp, status, stat, and category chip — so the chrome reads like a calibrated readout.
The **gem message body is the deliberate exception**: warm sans 16px/1.45/450 so what people
*say* still sounds human inside the engineered frame.

# Elevation & Depth

Depth is a **surface ladder + 1px hairlines** (Linear/Geist), never shadow:
L0 frame `#07080A` → L1 surface `#0C0D10` → L2 card `#121317` + `outline` → L3 hover/priority
`#181A1F` + `outline-strong`. Glass is spent in **exactly one place**: the sticky header
(`surface-glass` + `blur(20px) saturate(170%)` + a 1px top inset highlight). The only glow is
the one-shot priority-arrival flash. Optional **phosphor grain** (≤3.5%, accent-tinted SVG
`feTurbulence`, chrome only, `--grain` kill switch) gives the near-black a CRT/radar soul.

# Do / Don't

**Do** keep chrome near-zero chroma so gem colors are the only saturated thing · make mono
load-bearing · build depth from the surface ladder + hairlines · spend aqua sparingly · one
motion gesture per event · `tabular-nums` everywhere digits change.

**Don't** use purple in chrome or as the accent (the original slop tell) · use `#000`/`#FFF` ·
shadow or glass on gem cards · fill a gem card with its category color · apply uniform
radius/padding (radius is grammar; gem padding is asymmetric for the stripe) · add gratuitous
gradients/spinners/fade-ins · let the grain exceed 3.5% or touch message text.
