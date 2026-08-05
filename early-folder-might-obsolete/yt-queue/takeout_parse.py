#!/usr/bin/env python3
"""
Takeout parser prototype. Two jobs:
  (1) Validate that the JSON has the `time` field we depend on, per row.
  (2) Return rows in a stable shape: {video_id, channel, title, watched_at_utc (unix s), duration_s?}

Usage:
  python3 takeout_parse.py <path/to/watch-history.json>

Prints:
  - schema check stats (rows with/without `time`, with/without `titleUrl`)
  - first 5 rows in normalized form
  - total count + earliest/latest `time`
"""
import json, sys, re, os
from datetime import datetime

VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})")

def parse_watch_history(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        return None, "Top-level JSON is not a list"
    rows = []
    missing_time = 0
    missing_url = 0
    earliest, latest = None, None
    for i, item in enumerate(raw):
        t = item.get("time")
        if not t:
            missing_time += 1
            continue
        try:
            ts = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError as e:
            missing_time += 1
            continue
        ts_unix = int(ts.timestamp())
        if earliest is None or ts_unix < earliest:
            earliest = ts_unix
        if latest is None or ts_unix > latest:
            latest = ts_unix
        url = item.get("titleUrl") or ""
        m = VIDEO_ID_RE.search(url)
        video_id = m.group(1) if m else ""
        if not video_id:
            missing_url += 1
        channel = ""
        subs = item.get("subtitles") or []
        if subs and isinstance(subs, list) and isinstance(subs[0], dict):
            channel = subs[0].get("name", "")
        rows.append({
            "video_id": video_id,
            "channel": channel,
            "title": item.get("title", ""),
            "watched_at_unix": ts_unix,
            "watched_at_iso": ts.isoformat(),
        })
    return {
        "total_raw": len(raw),
        "rows_kept": len(rows),
        "missing_time": missing_time,
        "missing_url_or_id": missing_url,
        "earliest_unix": earliest,
        "latest_unix": latest,
        "earliest_iso": datetime.fromtimestamp(earliest).isoformat() if earliest else None,
        "latest_iso": datetime.fromtimestamp(latest).isoformat() if latest else None,
        "rows": rows,
    }, None

def main():
    if len(sys.argv) < 2:
        print("ERROR: need path to watch-history.json", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    result, err = parse_watch_history(path)
    if err or result is None:
        print("PARSE ERROR:", err or "unknown")
        sys.exit(1)
    print("=== Takeout validation ===")
    print(f"  total raw rows      : {result['total_raw']}")
    print(f"  rows kept (w/ time) : {result['rows_kept']}")
    print(f"  missing `time`      : {result['missing_time']}")
    print(f"  missing titleUrl/id : {result['missing_url_or_id']}")
    earliest_iso = result["earliest_iso"] or "(none)"
    latest_iso = result["latest_iso"] or "(none)"
    print(f"  earliest watched_at : {earliest_iso}")
    print(f"  latest watched_at   : {latest_iso}")
    print()
    print("=== first 5 normalized rows ===")
    for r in result["rows"][:5]:
        print(f"  {r['watched_at_iso']}  vid={r['video_id'] or '(none)':<12}  ch={r['channel'][:30]:<30}  title={r['title'][:60]}")
    print()
    # Write the normalized list to disk so the matcher can read it.
    out_path = os.path.expanduser("~/yt-queue/history-normalized.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in r.items() if k != "watched_at_iso"} for r in result["rows"]], f, ensure_ascii=False, indent=2)
    print(f"wrote normalized history to {out_path}")

if __name__ == "__main__":
    main()
