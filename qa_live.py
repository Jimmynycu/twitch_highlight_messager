"""Live QA against the BUSIEST channel on Twitch right now.

Finds the current top-viewer live channels (public GQL, no auth), connects to #1,
runs the real pipeline, and prints what each brain actually surfaces + the signal
ratio. This is the standing QA bar: if it reads trash on the #1 channel, it's trash.

    python qa_live.py            # top channel, default brains, 25s
    python qa_live.py 40 heuristic community   # 40s, specific brains
"""
from __future__ import annotations
import asyncio, json, sys, urllib.request
from collections import deque

sys.path.insert(0, ".")
from radar.source import TwitchSource
from radar.scorer import get_scorer

GQL = "https://gql.twitch.tv/gql"
CID = "kimne78kx3ncx6brgo4mv6wki5h1ko"


def top_channels(n=6):
    q = {"query": "query{streams(first:%d,options:{sort:VIEWER_COUNT}){edges{node{viewersCount broadcaster{login displayName} game{name}}}}}" % n}
    req = urllib.request.Request(GQL, data=json.dumps(q).encode(),
                                 headers={"Client-Id": CID, "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=10).read())
    out = []
    for e in d["data"]["streams"]["edges"]:
        nd = e["node"]; b = nd["broadcaster"]
        if not b:
            continue
        out.append((b["login"], b.get("displayName"), nd["viewersCount"], (nd.get("game") or {}).get("name")))
    out.sort(key=lambda x: x[2], reverse=True)   # the API sort isn't reliable — sort by viewers ourselves
    return out


async def capture(channel, brains, dur):
    scs = {b: get_scorer(b) for b in brains}
    for s in scs.values():
        if hasattr(s, "streamer"):
            s.streamer = channel
    win: deque = deque(maxlen=200)
    out = {b: [] for b in brains}
    total = 0
    firstmsg = 0
    src = TwitchSource(channel)

    async def run():
        nonlocal total, firstmsg
        async for m in src.stream():
            total += 1
            if m.tags.get("first-msg") == "1":
                firstmsg += 1
            win.append(m)
            for b, s in scs.items():
                h = s.score(m, win)
                if h:
                    out[b].append(h.to_event())
    try:
        await asyncio.wait_for(run(), timeout=dur)
    except asyncio.TimeoutError:
        pass
    return total, firstmsg, out


async def main():
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    brains = sys.argv[2:] or ["heuristic", "community", "question"]
    tops = top_channels(6)
    print("TOP LIVE CHANNELS RIGHT NOW:")
    for login, disp, v, game in tops:
        print(f"  {v:>7,}  {login:<20} {game or ''}")
    ch = tops[0][0]
    print(f"\nQA target: #1 {ch} ({tops[0][2]:,} viewers) — {dur}s\n")
    total, firstmsg, out = await capture(ch, brains, dur)
    print(f"messages read: {total}  ({total/max(1,dur):.1f}/s)  | real first-msg tags: {firstmsg}\n")
    for b in brains:
        gems = out[b]
        ratio = 100 * len(gems) / max(1, total)
        print(f"=== brain={b} | msgs={total} gems={len(gems)} ({ratio:.0f}% surfaced) ===")
        for g in gems[:18]:
            print(f"   [{g['cat']:<5}] {g.get('reason',''):<26} {g['user']}: {g['text'][:64]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
