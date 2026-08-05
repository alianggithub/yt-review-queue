#!/usr/bin/env python3
"""
Matcher prototype. Given:
  - a list of pending rows (each with `created_at_unix` from the wall-clock time the user sent `priority N` from Telegram)
  - a normalized Takeout history (output of takeout_parse.py)
  - a per-video `duration_s` lookup (from YouTube Data API videos.list; mocked if missing)

For each pending row, find the clip whose playback interval [watched_at, watched_at + duration_s] contains created_at, within tolerance TOL.

Also computes timestamp_in_clip = created_at - watched_at (clamped to [0, duration_s]).

Usage:
  python3 match.py [<tolerance_seconds>]

Reads:
  ~/yt-queue/history-normalized.json   (produced by takeout_parse.py)
  ~/yt-queue/pending-rows.json         (you create this; see sample below)
  ~/yt-queue/durations.json            (optional; {video_id: duration_s}; if missing, duration defaults to 600s)
Writes:
  ~/yt-queue/match-result.json

A typical pending-rows.json:
[
  {"id": "a3f9b2c1", "priority": 5, "created_at_unix": 1721140000, "user_note": ""},
  {"id": "b2c1d3e4", "priority": 3, "created_at_unix": 1721140500, "user_note": "rewind"}
]
"""
import json, os, sys

HISTORY = os.path.expanduser("~/yt-queue/history-normalized.json")
PENDING = os.path.expanduser("~/yt-queue/pending-rows.json")
DURATIONS = os.path.expanduser("~/yt-queue/durations.json")
OUT = os.path.expanduser("~/yt-queue/match-result.json")

DEFAULT_DURATION_S = 600  # 10min fallback if we don't have a real duration yet
DEFAULT_TOL_S = 120

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    tol = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TOL_S
    history = load_json(HISTORY, default=[])
    pending = load_json(PENDING, default=[])
    durations = load_json(DURATIONS, default={}) or {}
    if not history:
        print("ERROR: no normalized history. Run takeout_parse.py first.", file=sys.stderr)
        sys.exit(1)
    if not pending:
        print("ERROR: no pending rows.", file=sys.stderr)
        sys.exit(1)

    # Sort history newest-first so on overlap we prefer the most recent clip.
    history_sorted = sorted(history, key=lambda r: r["watched_at_unix"], reverse=True)

    results = []
    for row in pending:
        created = row["created_at_unix"]
        match = None
        match_dur = 0
        for h in history_sorted:
            if not h.get("video_id"):
                continue
            start = h["watched_at_unix"]
            dur = durations.get(h["video_id"], DEFAULT_DURATION_S)
            end = start + dur
            if (start - tol) <= created <= (end + tol):
                match = h
                match_dur = dur
                break
        if match is None:
            results.append({
                "id": row["id"], "priority": row["priority"],
                "created_at_unix": created, "user_note": row.get("user_note", ""),
                "match": None,
                "reason": "no clip playback interval contains created_at within tol",
            })
        else:
            start = match["watched_at_unix"]
            t_in_clip = max(0, min(created - start, match_dur))
            results.append({
                "id": row["id"], "priority": row["priority"],
                "created_at_unix": created, "user_note": row.get("user_note", ""),
                "match": {
                    "video_id": match["video_id"],
                    "channel": match["channel"],
                    "title": match["title"],
                    "watched_at_unix": start,
                    "duration_s": match_dur,
                    "timestamp_in_clip": t_in_clip,
                    "yt_url": f"https://youtu.be/{match['video_id']}?t={t_in_clip}",
                },
            })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"matched {sum(1 for r in results if r['match'])}/{len(results)} rows; wrote {OUT}")
    for r in results:
        m = r.get("match")
        if m:
            print(f"  [{r['id']}] p{r['priority']} → {m['video_id']}  t={m['timestamp_in_clip']}s  url={m['yt_url']}")
        else:
            print(f"  [{r['id']}] p{r['priority']} → NO MATCH")

if __name__ == "__main__":
    main()
