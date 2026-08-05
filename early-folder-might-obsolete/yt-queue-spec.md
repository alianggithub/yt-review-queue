# YouTube Priority Queue — Spec v0.1
Author: GLM-5.2 via Hermes  Date: 2026-07-16

## 1. Problem

User watches YouTube on a phone/tablet with limited typing ability. While browsing, they want to flag clips for later deep watching with a priority level, without hunting for pen/paper or leaving the YouTube app. Since hands are busy, input must be voice-length — a few words max. Later, at a workstation, user wants a clean table showing every flagged clip, the timestamp inside the clip, the resolved YouTube URL ready to jump to that moment, a priority-sorted view, and (optionally) a knowledge-base wiki entry for high-priority items.

The hard part: the user sends the priority comment before (or while) the clip is still playing — they don't want to copy/paste URLs. The system must resolve the YouTube link lazily, after the clip has had time to show up in the user's YouTube Watch History, by correlating the wall-clock time of the Telegram comment against the playback intervals in Watch History.

## 2. Actors & Surfaces

- **User** on phone, inside Telegram, inside Hermes bot chat.
- **Hermes Agent** — existing Hermes stack, running on this DGX host. Has `hermes-gateway` (Telegram), `execute_code`, terminal, `web_extract`, `search_files`, `read_file`, `write_file`, `patch`, and the `llm-wiki` + `youtube-content` skills.
- **YouTube Data API v3** — source of Watch History (via private playlist `OAuth` export; see §5.2 for the "watch history export" caveat) and of video metadata (title, channel, duration).
- **Telegram bot** — already configured per `telegram-messaging` skill. No new bot required; the existing Hermes bot accepts text commands.
- **Telegram bot** — already configured per `telegram-messaging` skill. No new bot required; the existing Hermes bot accepts text commands.

## 3. Commands (User Side)

All commands sent as plain text to the existing Hermes Telegram chat. Telegram-side parsing must be tolerant of voice transcription noise.

| Input                        | Meaning                                                       |
|------------------------------|---------------------------------------------------------------|
| `priority 5`                 | Flag the clip currently playing at highest priority (watch deep). |
| `priority 4` / `priority 3`  | Mid-priority bookmark.                                        |
| `priority 2` / `priority 1`  | Low-priority bookmark.                                        |
| `priority 0`                 | Mark "do not watch again" — keep record for context but exclude from watch queue. |
| `priority 5 <note>`          | Same as `priority 5` plus a free-text user note stored in the row. |
| `queue`                      | Show current unresolved queue, sorted by priority desc then time. |
| `queue resolve <id>`         | Mark a row resolved (manually watched / done).               |
| `queue drop <id>`            | Delete a row (typo / wrong clip).                            |
| `queue wiki <id>`            | Force a wiki write for a specific row now (normally auto for priority >= 4 on resolve). |
| `queue list`                 | Show last N resolved rows with URL + KB link.                |
| `queue status`               | How many pending, how many unresolved URLs, last fetch time. |

Notes:
- User is not expected to provide a URL or timestamp — the system derives both. They just send a short priority command.
- If the user includes a note after the priority number, keep the raw text verbatim. Do not "interpret" it.
- The literal string `priority 0` is special: it is a keep-but-skip flag, not a delete. Deletes use `queue drop`.

## 4. Data Model

A single append-only CSV (or SQLite db, see §8) at `~/yt-queue/queue.csv` plus a working JSON for in-flight state. CSV keeps it human-auditable and easy to `read_file` from the agent.

CSV columns:

| column | type | meaning |
|---|---|---|
| id | string (8-char) | Short ID like `a3f9b2c1`. Assigned on insert. |
| created_at | ISO-8601 UTC | Wall-clock time the Telegram comment was received by the agent. |
| priority | int 0-5 | User-supplied. 0 = keep/skip, 1-5 = watch queue. |
| user_note | string | Verbatim text after the priority token, may be empty. |
| yt_video_id | string or empty | 11-char video ID resolved from Watch History. Empty until resolved. |
| yt_url | string or empty | `https://youtu.be/<id>?t=<seconds>` — jump URL to the matched playback moment. |
| timestamp_in_clip | int seconds or empty | Offset within the clip matching the wall-clock `created_at`. Empty until resolved. |
| clip_title | string or empty | YouTube title at resolve time. |
| clip_channel | string or empty | Channel name. |
| clip_duration_s | int or empty | Video duration in seconds. |
| kb_category | string or empty | One of the existing `~/knowledge_base/` top-level dirs (see §6). |
| kb_article_path | string or empty | Full path to the generated wiki markdown, once wiki is written. |
| kb_wiki_date | date or empty | Date the wiki entry was generated. |
| resolve_status | enum | `pending` / `resolved` / `dropped`. Default `pending`. |
| resolved_at | ISO-8601 or empty | When user marked resolved. |
| resolve_attempts | int | How many Watch History fetch cycles we've already tried (for backoff). |
| last_fetch_at | ISO-8601 or empty | Last time we attempted to resolve the URL for this row. |

Rows are keyed by `id`. Re-issuing a priority command for the currently-playing clip appends a new row — the user is expected to `queue drop` mistakes. (Linking two commands to the "same clip" is out of scope for v0.1.)

## 5. Resolution Workflow (URL + Timestamp)

The trickiest part. User sends `priority 5` at wall-clock `T`. Some seconds/minutes earlier, they started playing a clip on YouTube; the clip's playback interval must contain `T` (approximately, with a tolerance for the user's reaction time — see §5.3).

### 5.1 Tray Icon, Not Polling the Bot

When the agent receives a `priority N` message over Telegram, it immediately:
1. Inserts a row with `yt_video_id` empty, `resolve_status=pending`.
2. Replies to the user with the short ID: e.g., `Queued: a3f9b2c1 (p5)`. No URL yet.

### 5.2 YouTube Watch History Access (VERIFIED 2026-07-16)

FACT-CHECK RESULT — the available sources and what they carry:

| Source | Has timestamp? | Live/real-time? | Viable for phone user? |
|---|---|---|---|
| Google Takeout JSON (`watch-history.json`) | **YES** — per-row `time` field, UTC ISO-8601 | **NO** — manual export, latency minutes-to-hours, possible ~8-month retention cap (per one 2024 user report; unconfirmed as universal) | YES, batch only |
| YouTube Data API v3 `playlistItems?playlistId=HL` | n/a | would be near-realtime | **NO — endpoint is dead.** Returns empty placeholder since ~2016. `channels.contentDetails.relatedPlaylists.watchHistory` still shows the literal string "HL" but the playlist contents are not retrievable. No OAuth scope exists for history. `activities` endpoint also deprecated. Multiple sources (bhanueso.dev blip, Stack Overflow, Google Issue Tracker #35172816). |
| Browser content script (Chrome MV3 extension beaconing watch page DOM) | YES (the beacon time is the playback time) | YES | **NO** — user watches in the YouTube phone app, not a desktop browser. Path is irrelevant to this user's setup. |
| Third-party (Gandalf Network) | claims yes | claims yes | not Google-blessed; requires handing OAuth to a third party. Listed for completeness; not recommended. |

CONCLUSION — the only Google-blessed source of the playback timestamp is the Takeout JSON export. There is NO real-time API for YouTube watch history and there has not been one since ~2016. Any spec claiming live resolution via the official API is wrong; the original v0.1 of this spec was wrong on that point. Revised below.

### 5.2' Revised Resolution Architecture

Two operating modes, user picks per-session or globally:

**(A) Batch mode (default, recommended).** User periodically exports Takeout `watch-history.json` and drops it at `~/yt-queue/watch-history.json`. The resolver matches pending rows against that file. Resolution is not real-time — rows stay pending until the next Takeout drop. Practically: user can trigger a Takeout export from `/takeout` (web or mobile browser), wait for the email, download, and `scp`/`curl` the file to `~/yt-queue/`. A single helper script `~/yt-queue/refresh.sh` swaps in the new file and re-runs the matcher.

**(B) Self-report mode (opt-in fallback).** If the user is willing to tolerate one extra tap, they can include the watch timestamp in their Telegram command itself — e.g., `priority 5 12:34` means "I am watching right now at 12:34 clip-internal time." The agent then needs only the *video identity* (not its playback start time) to build the jump URL. Video identity can come from either:
   - the user pasting the youtu.be link they're currently watching (one tap via the YouTube share button — the only realistic "one-tap" input), or
   - a separate lightweight mechanism (see open question §12 Q1 below — possibly YouTube share-sheet → Telegram share → Hermes bot).
   `timestamp_in_clip` is then literally the user-spoken `12:34` converted to seconds, and `yt_url = https://youtu.be/<id>?t=<seconds>` is exact, not inferred.

Mode (A) costs the user zero extra taps but gets answers in batches; Mode (B) gets instant, exact jump URLs at the cost of one share/paste.

For v0.1 we ship Mode (A) only and leave Mode (B) as a planned enhancement. The acceptance bar for Mode (A): end-to-end, drop a Takeout JSON → all pending rows whose `created_at` falls inside some clip's `[watched_at, watched_at + duration_s ± TOL]` interval get their `yt_video_id` and `yt_url` filled within one resolver pass.

### 5.2'' Takeout JSON Shape

Verified shape (from Saksham Arora 2021 analysis, still accurate per 2024 SO answer):
```json
[
  {"header": "YouTube", "title": "...", "titleUrl": "https://www.youtube.com/watch?v=VIDEO_ID",
   "subtitles": [{"name": "Channel", "url": "https://www.youtube.com/channel/..."}],
   "time": "2024-07-11T15:23:01.000Z", ...},
  ...
]
```
- `time` = when the user watched (UTC, `Z` suffix).
- `subtitles[0].name` = channel name.
- Video duration is NOT in the Takeout JSON. `duration_s` must be fetched separately via the YouTube Data API v3 `videos.list?part=contentDetails&id=<video_id>` (this endpoint is alive and returns `contentDetails.duration` as ISO-8601 duration string). One batched call per resolver pass is cheap.
- The `time` field is the playback START time as YouTube measured it; pause/scrub isn't represented. For our `timestamp_in_clip` estimate we treat the playback interval as `[time, time + duration_s]` and assume the user issued `priority N` somewhere inside that interval. Tolerance `TOL` absorbs small drifts.

### 5.3 Matching a Pending Row → a Video

For each `pending` row with empty `yt_video_id`, the resolver:

1. Fetches recent N (default N=50) Watch History items via `fetch_history.py`.
2. Sorts by `watched_at` descending.
3. Finds the item whose playback interval contains `row.created_at`. Concretely:
   - `watched_at_k` is when the user started playing clip k.
   - `end_k = watched_at_k + duration_s_k` (approx, ignoring pauses/scrubbing — see caveat).
   - A row matches clip k if `watched_at_k - TOL <= row.created_at <= end_k + TOL` where `TOL = 120s` (accounts for reaction lag + clock drift between phone and server). User-tunable in config.
   - If multiple rows match the same clip (user pressed priority twice), each row maps to the same `yt_video_id` but a different `timestamp_in_clip` (see §5.4).
4. If a match is found: write `yt_video_id`, `yt_url`, `timestamp_in_clip`, `clip_title`, `clip_channel`, `clip_duration_s` to the row. Status stays `pending` (user hasn't watched yet) but the row is now "resolved URL" (visible in `queue` with a link).
5. If no match: leave empty. Increment `resolve_attempts` and `last_fetch_at`. Trigger the next attempt on the scheduler (see §5.5).

### 5.4 Computing `timestamp_in_clip`

`timestamp_in_clip = row.created_at - watched_at` (clamped to `[0, clip_duration_s]`). This is the approximate moment in the clip the user was at when they pressed priority. The `yt_url` includes `?t=<seconds>` so clicking it on the workstation jumps roughly there. Document in the row's UI that this is an estimate.

### 5.5 Scheduling (revised for batch mode)

There is no live API to poll (see §5.2), so there is no 5-minute cron against YouTube. Instead:

- The resolver runs on **demand**, triggered by `~/yt-queue/refresh.sh` after the user drops a new Takeout `watch-history.json`. One run = one match pass over all pending rows.
- A nightly cron at 09:00 (Hermes `cronjob`, `deliver='telegram'`) runs `queue status` — it reports how many rows are pending, how many are unresolvable (>14d old), and when the last Takeout ingest happened. This nudges the user to refresh Takeout when the pending count climbs.
- The `resolve_attempts` and `last_fetch_at` columns are repurposed: `resolve_attempts` now counts how many Takeout ingests have occurred since the row was inserted without a match; `last_fetch_at` is the timestamp of the most recent ingest that tried to match this row. After 14 days or 4 failed ingests with no match, row is auto-marked `unresolvable` (4th enum value for `resolve_status`).

## 6. Classification

On URL resolution, the agent attempts to classify the clip into one of the existing top-level directories of `~/knowledge_base/`. The agent reads the current directory list (cached but refreshed weekly) and picks the best match by:
1. Fetching the clip's title + channel + description (via YouTube Data API `videos.list?id=...&part=snippet`).
2. Comparing against each known category's existing article titles/keywords (cheap: just the directory names matching against the description).
3. Falling back to a small LLM call that returns ONE directory name from the list, or `<none>` if none fit. Output is strictly limited to that enum; no new categories are invented.

Existing categories (as of 2026-07-16): `llm-model-trends`, `travel`, `ai-infrastructure`, `daily-life`, `harness`, `ai-economy`, `hermes-usage`, `claude-usage`, `world-model`, `startups`, `llm-architecture`, `llm`, plus whatever `find ~/knowledge_base -maxdepth 1 -type d` returns at resolve time — do not hard-code.

If classification returns `<none>`, `kb_category` stays empty and the wiki step is skipped (priority >= 4 still flags for manual triage in `queue status`).

## 7. Wiki Write (llm-wiki integration)

Triggered automatically when (a) `priority >= 4` AND (b) the row's URL has been resolved AND (c) no `kb_article_path` yet — OR on the `queue wiki <id>` command.

Process (mirrors the `llm-wiki` "Ingest" workflow):
1. Orient: `find ~/knowledge_base -name SCHEMA.md` to identify any wiki owning this category; read its `index.md` and `log.md`. Most top-level dirs in this user's KB are wiki roots (each has its own conventions).
2. If no wiki root exists for the chosen `kb_category`, skip wiki write; user hasn't stood one up yet. Log this to `~/yt-queue/warnings.log`.
3. Fetch the transcript using the `youtube-content` skill (`scripts/fetch_transcript.py --text-only --timestamps`) — cap at ~50K chars.
4. Save raw source under the wiki's `raw-articles/` folder (or its `raw/articles/` if the wiki uses that convention) following `references/raw-source-format.md`.
5. Write a single summary wiki page under the wiki's `concepts/` or root (as that wiki's `SCHEMA.md` dictates) with:
   - Frontmatter: `title`, `created`, `updated`, `type: summary`, `tags` (from the wiki's taxonomy), `sources:` pointing to the raw file.
   - Body: one-line user note (verbatim), the jump URL, a short summary of the transcript.
6. Update that wiki's `index.md` (add the new page under the right section) and append to `log.md`.
7. Write `kb_article_path` (absolute) and `kb_wiki_date` back to the CSV row.
8. Optionally reply to the user in Telegram: "Wiki: <short path>".

Gate: if the wiki write would touch >10 pages (cross-refs trigger mass update), pause and ask the user first per `llm-wiki` pitfalls.

## 8. Storage Choice

Single `~/yt-queue/queue.csv` for v0.1 — human-readable, easy to git, agent edits with `patch`. If rows exceed ~5,000 or resolution writes become hot, move to SQLite at `~/yt-queue/queue.db` with the same schema. The CSV is the source of truth in v0.1; everything else is a cache.

Supporting files under `~/yt-queue/`:
- `fetch_history.py` — OAuth'd Watch History fetcher.
- `resolve_loop.py` — the 5-minute backoff worker.
- `classify.py` — wraps the LLM call (§6).
- `watch-history.json` — Takeout fallback snapshot (user-supplied).
- `history-cache.json` — 60s cache of Watch History fetches.
- `config.yaml` — `tolerance_s`, `resolve_interval_s`, `min_priority_for_wiki`, OAuth token path.
- `warnings.log` — append-only.
- `.gitignore` — exclude only OAuth token files; CSV is tracked if user wants version history under KB or a dedicated repo.

## 9. Cron / Scheduling

Hermes `cronjob` (action=create) for the resolver. One job, `every 5m`, runs `python3 ~/yt-queue/resolve_loop.py` and delivers a Telegram message ONLY when it resolves a new URL after a long wait (>1h since the command was issued). Silent otherwise — per the cronjob `no_agent=True` watchdog pattern, the script emits stdout only when there's something to report.

A second daily cron at 09:00 runs a `queue status` summary and delivers to Telegram via `deliver='telegram'`.

The crons run server-side; the live-delivery channel on this DGX CLI does not exist, so `deliver` MUST point to Telegram explicitly. (Confirmed in SOUL.md.)

## 10. Security

- OAuth token file for YouTube Watch History sits at `~/yt-queue/.oauth-token.json`, in `.gitignore`, never committed.
- No tokens, bot secrets, or user-identifying strings ever in the CSV.
- The KB wiki pages are markdown only; no embedded tokens.
- Existing Telegram allowed-users list gates all commands — no new attack surface.

11. **Failure Modes & Pitfalls**

1. **Watch History `playlistId=HL` endpoint disappears.** Fall back to weekly Google Takeout; degrade `timestamp_in_clip` accuracy.
2. **User sends `priority 5` before pressing play.** No matching clip → row never matches any Takeout entry → eventually flagged `unresolvable` after 14d or 4 failed ingests. Show these in `queue status`.
3. **Takeout latency exceeds expected window.** If the user only refreshes Takeout monthly, recent rows sit pending until then. Mode (B) is the escape hatch — paste the youtu.be link for immediate resolution.
4. **Takeout retention cap (~8 months reported by one 2024 user; unconfirmed).** Old rows with `created_at` older than the earliest Takeout entry can never be matched → auto-marked `unresolvable`. Document the cap per-user once the first ingest lands.
5. **Classification picks wrong category.** `queue wiki <id> as travel` re-runs with a category override: agent updates `kb_category`, deletes stale page, rewrites.
6. **Two clips overlapping `created_at` (user watching two devices).** Resolver picks the most recent `watched_at`; row note field can be used to disambiguate later.
7. **Clip later deleted/private.** `yt_url` still in the row; transcript fetch for wiki will fail, wiki-write aborted with a warning logged, row stays intact.
8. **Voice transcription turns "priority 5" into "priority five" or "prior to 5".** Bot does numeric-equivalence expansion and a fuzzy match; if ambiguous, replies with a clarifying question (no row inserted).
9. **Takeout import is stale (user forgot to refresh).** `queue status` nightly cron shows "last ingest 12 days ago — X pending rows" as a prompt.

## 12. Open Questions for User

1. **Resolution mode.** The official YouTube API has no watch-history endpoint (verified — see §5.2). The only Google-blessed source of playback timestamps is the Takeout JSON export, which is a manual batch download. Do you accept Mode (A) — drop a fresh Takeout `watch-history.json` periodically (say weekly) and let pending rows resolve in batches? Or do you want Mode (B) — you also paste the youtu.be link (one extra tap via YouTube's share button) so the agent gets instantaneous, exact jump URLs without waiting for Takeout? Mode (A) is zero-tap but batch-late; Mode (B) is one-tap and immediate. We can ship both and let the user pick per-message.
2. **Takeout retention.** One 2024 Stack Overflow user reported Takeout YouTube history was capped at ~8 months. This hasn't been confirmed as universal. If your account has longer history, please let us know so we can document it. It only affects how far back retroactive resolution can reach — not a v0.1 blocker.
3. **Timestamp tolerance.** Are 120 seconds of slack on either side about right for the inference in Mode (A), or do you typically delay sending `priority N` longer than that after the interesting moment in the clip? Tighter TOL = fewer false matches; looser TOL = catches more true matches but risks mapping your command to the wrong clip if you watched two clips close together.
4. **Single bot or new bot.** OK to use the existing Hermes Telegram bot, or do you want a dedicated `@yt_queue_bot` for this workflow to keep chat history clean?
5. **Wiki auto-write threshold.** Confirm auto-wiki at priority >= 4 (not 5)? Priority 3 and below would only wiki on explicit `queue wiki <id>`.
6. **Storage.** CSV for v0.1 is fine, or jump straight to SQLite?
7. **Naming.** Is `~/yt-queue/` the path you want, or somewhere under `~/knowledge_base/yt-queue/` so it syncs with the KB?

## 13. Phased Build Plan

- **Phase 0** — Approve spec, answer §12.
- **Phase 1** — CSV + Telegram command parser + `priority N` insert + `queue` view. No URL resolution yet; verify the chat-bot loop end to end.
- **Phase 2** — `fetch_history.py` + `resolve_loop.py` + first successful URL resolution.
- **Phase 3** — Classification step (§6).
- **Phase 4** — Wiki write pipeline (§7) via `llm-wiki` skill.
- **Phase 5** — Two crons (resolver + daily status), polish, edge cases.

Each phase is independently testable. Stop after each for user review.
