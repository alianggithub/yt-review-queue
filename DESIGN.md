# YouTube Priority Queue — Design Document v1.0

Author: GLM-5.2 via Hermes Agent
Date: 2026-07-16
Status: Ready for implementation
Predecessor: ~/yt-queue-spec.md (v0.1 — superseded; kept for history)
Prototype: ~/workspace/prototype/yt-queue-poc/ (verified ad-hoc, 8/8 check groups pass)

---

## 1. Problem

User watches YouTube on a phone/tablet with limited typing ability. While browsing,
they flag clips for later deep watching with a priority level — a few words max, no
URLs, no timestamps. Later, at a workstation, they want a clean table showing every
flagged clip with the timestamp inside the clip, the resolved YouTube jump URL, a
priority-sorted view newest-on-top, and optionally a knowledge-base wiki entry.

The system must resolve the YouTube link lazily, after the clip shows up in the
user's YouTube Watch History, by correlating the wall-clock time of the Telegram
comment against playback intervals in a Google Takeout export.

Multiple users, each with their own YouTube account, share the same Hermes bot.
Each user gets their own queue table. Telegram identity maps to account tables
automatically once bound.

## 2. What the Prototype Proved

All claims below were verified with running code in ~/workspace/prototype/yt-queue-poc/.
Ad-hoc verification script passed all 8 check groups (EXIT=0).

| Claim | Evidence | Code |
|-------|----------|------|
| Takeout JSON `time` field is parseable per row | takeout_parse.py parsed 4+2+2 rows across 3 accounts, zero drops | takeout_parse.py |
| Timestamp → clip matching works | match.py matched 2/3 dan rows + 2/2 alice rows + 2/2 carol rows correctly | match.py |
| Asymmetric tolerance is required | Symmetric TOL caused false match 100s before clip B started; asymmetric (pre=30s, post=120s) fixed it | match.py, carol overlap test |
| Multiple YouTube accounts can be auth'd | accounts.py builds N independent Credentials objects from one client_id + N refresh_tokens | accounts.py |
| Multi-user Telegram dispatch works | dispatch.py: unknown→reject, unmapped→prompt, self-bind→push, all 8 scenarios pass | dispatch.py |
| Account isolation is real | dan's clips never leaked into alice's queue and vice versa | match.py + queue CSVs |
| Newest-on-top ordering is stable | Every write_queue() sorts by created_at desc; verified across insert, drop, match-rewrite | dispatch.py, match.py |

### What was NOT proven (carried forward as implementation risks)

1. Real Takeout export format — synthetic fixtures modeled the documented schema. Must
   validate against a real export before go-live.
2. Live YouTube Data API call for video durations — accounts.py is structured for it
   but no OAuth client_id was configured in the prototype environment.
3. KB classification + llm-wiki integration — columns reserved in the CSV, no code yet.
4. Hermes gateway wiring — dispatch.py simulated via CLI args; real integration needs
   the gateway to pass sender tg_id into agent context.

## 3. Architecture

```
Telegram user sends: "priority 5"
         │
         ▼
   Hermes Gateway (existing Telegram bot)
         │  passes: sender telegram_user_id + message text
         ▼
   Hermes Agent (this workflow)
         │
         ├── dispatch: resolve telegram_user_id → account_label
         │              (users.yaml mapping; self-bind if unmapped)
         │
         ├── insert row into queues/queue-<account>.csv
         │              (newest-on-top, status=pending, yt_video_id empty)
         │
         ├── reply to user: "Queued: <id> (p5)"
         │
         └── [later, on Takeout refresh]:
              ├── takeout_parse: parse watch-history-<account>.json
              ├── durations: fetch video durations via YouTube Data API
              ├── match: correlate created_at → clip playback window
              │           (asymmetric tolerance: pre=30s, post=120s)
              ├── fill row: yt_video_id, yt_url?t=<s>, clip_title, etc.
              ├── classify: pick KB category from ~/knowledge_base/ dirs
              └── [if priority >= 4]: wiki write via llm-wiki skill
```

## 4. Multi-Account Design

### 4.1 Account Configuration

One file: `~/yt-queue/accounts.yaml`

```yaml
client_id: "<Google OAuth client ID>"
client_secret: "<Google OAuth client secret>"
scopes:
  - https://www.googleapis.com/auth/youtube.readonly
accounts:
  dan:
    refresh_token: "<dan's refresh token>"
  alice:
    refresh_token: "<alice's refresh token>"
  bob:
    refresh_token: "<bob's refresh token>"
```

Architecture (proven in prototype):
- Single OAuth client (client_id + client_secret) shared across all accounts
- N refresh tokens, one per Google account, keyed by label
- The previous claim that "you can't authenticate multiple YouTube channels" is wrong.
  Nothing in the Google OAuth flow limits one client to one channel. The confusion
  comes from tutorials that only store one token — but the OAuth flow itself is
  per-user. One client_id, N refresh_tokens, N independent Credentials objects.

### 4.2 Enrollment

```bash
python3 ~/yt-queue/accounts.py enroll <label>
```

Runs the interactive OAuth flow (`InstalledAppFlow.run_local_server`) while the user
is logged in as that Google account. Stores the per-user `refresh_token` in
`accounts.yaml` under the label. Repeat for each account.

### 4.3 YouTube API Usage

The only YouTube Data API call this system needs is:

```
GET https://www.googleapis.com/youtube/v3/videos?part=contentDetails,snippet&id=<video_id>
```

- `contentDetails.duration` → ISO-8601 duration string → parse to seconds
- `snippet.title`, `snippet.channelTitle` → clip metadata fallback (Takeout JSON also has these)

This endpoint is alive and has been since API v3 launched. It's NOT the dead `HL`
playlist endpoint. Batch up to 50 video IDs per call. Cache durations in
`durations.json` keyed by video_id (durations don't change).

Watch History itself comes from Google Takeout, NOT from any API. The `playlistId=HL`
endpoint has returned empty since ~2016 and is unusable. This was verified in the
previous spec's research and confirmed by multiple sources.

## 5. Multi-User Telegram Dispatch

### 5.1 User Configuration

One file: `~/yt-queue/users.yaml`

```yaml
allowed_telegram_ids:
  - 8227016435    # dan
  - 8584778396    # alice
mapping:
  "8227016435": dan
  "8584778396": alice
```

`allowed_telegram_ids` is the Telegram whitelist (already configured on the existing
Hermes bot via TELEGRAM_ALLOWED_USERS env var). `mapping` binds each tg_id to an
account label.

### 5.2 Dispatch Flow (proven in prototype)

```
Inbound message arrives with telegram_user_id U:
  1. Is U in allowed_telegram_ids?
     NO  → reject: "not whitelisted on this bot"
     YES → continue
  2. Is U in mapping?
     NO  → reply: "You're whitelisted but not bound. Reply: use account <label>"
           (lists available account labels from accounts.yaml)
     YES → account = mapping[U]; route all commands to queue-<account>.csv
  3. If user sends "use account <label>" and is whitelisted:
     → self-bind: write mapping[U] = label, confirm
```

This means:
- If the agent can recognize the Telegram ID (it's mapped), no user specification needed.
- If it can't (whitelisted but unmapped), the user must self-bind once with
  `use account <label>`. After that, all future messages route automatically.
- Unknown users are rejected entirely.

### 5.3 Commands (User Side)

| Input                        | Meaning |
|------------------------------|---------|
| `priority N`                 | Flag the clip currently playing at priority N (0-5). Inserts a pending row. |
| `priority N <note>`          | Same, plus a free-text note stored verbatim. |
| `priority 0`                 | "Don't watch again" — keep record but exclude from watch queue. |
| `use account <label>`        | Self-bind this Telegram user to a YouTube account table. |
| `queue`                      | Show my queue, newest-on-top, with resolved URLs where available. |
| `queue drop <id>`            | Delete a row from my queue. |
| `queue resolve <id>`         | Mark a row as manually watched / done. |
| `queue wiki <id>`            | Force a wiki write for this row now. |
| `queue status`               | How many pending, how many unresolvable, last Takeout ingest time. |

Tolerance for voice transcription: numeric expansion ("five" → 5), fuzzy match on
"priority"/"prior". If ambiguous, reply with a clarifying question — do not insert a row.

## 6. Data Model

### 6.1 Per-Account Queue CSV

Each account gets its own CSV: `~/yt-queue/queues/queue-<account>.csv`

Columns:

| Column | Type | Meaning |
|--------|------|---------|
| id | string (8-char hex) | Short ID assigned on insert. |
| created_at | ISO-8601 UTC | Wall-clock time the Telegram comment was received. |
| priority | int 0-5 | User-supplied. 0 = keep/skip, 1-5 = watch queue. |
| user_note | string | Verbatim text after the priority token. |
| yt_video_id | string or empty | 11-char video ID. Empty until resolved. |
| yt_url | string or empty | `https://youtu.be/<id>?t=<seconds>` jump URL. |
| timestamp_in_clip | int seconds or empty | Offset within the clip. Empty until resolved. |
| clip_title | string or empty | YouTube title at resolve time. |
| clip_channel | string or empty | Channel name. |
| clip_duration_s | int or empty | Video duration in seconds. |
| kb_category | string or empty | One of ~/knowledge_base/ top-level dirs. |
| kb_article_path | string or empty | Absolute path to the wiki markdown, once written. |
| kb_wiki_date | date or empty | Date the wiki entry was generated. |
| resolve_status | enum | pending / resolved / dropped / unresolvable. |
| resolved_at | ISO-8601 or empty | When user marked resolved. |
| resolve_attempts | int | Takeout ingests tried without a match. |
| last_fetch_at | ISO-8601 or empty | Most recent ingest that tried this row. |

### 6.2 Newest-on-Top Invariant (proven in prototype)

Every write to the CSV sorts rows by `created_at` descending before writing. This
means the most recent priority command is always the first row in the file. The
prototype verifies this across all three write paths: insert (dispatch.py), drop
(dispatch.py), and match-rewrite (match.py).

### 6.3 Supporting Files

```
~/yt-queue/
├── accounts.yaml          # OAuth client + per-account refresh tokens
├── users.yaml             # Telegram whitelist + tg_id→account mapping
├── durations.json         # {video_id: duration_s} cache
├── config.yaml            # tolerances, wiki threshold, refresh schedule
├── queues/
│   ├── queue-dan.csv      # per-account queue tables (newest-on-top)
│   ├── queue-alice.csv
│   └── ...
├── takeout/
│   ├── watch-history-dan.json    # per-account Takeout exports
│   ├── watch-history-alice.json
│   └── ...
├── history-normalized/
│   ├── dan.json            # takeout_parse.py output
│   └── ...
├── warnings.log            # append-only
├── .gitignore              # exclude accounts.yaml (has tokens), Takeout JSONs
└── src/
    ├── takeout_parse.py
    ├── match.py
    ├── dispatch.py
    ├── accounts.py
    ├── durations.py        # fetches video durations via YouTube Data API
    ├── classify.py         # LLM-based KB classification
    └── wiki_write.py       # llm-wiki integration
```

## 7. Resolution Workflow

### 7.1 Takeout Import (batch mode)

The user periodically exports their YouTube Watch History via Google Takeout:
1. Go to https://takeout.google.com (web or mobile browser)
2. Deselect all, select only "YouTube and YouTube Music"
3. Under "Multiple formats" → "history" → JSON format
4. Export → receive email → download ZIP → extract `watch-history.json`
5. Place at `~/yt-queue/takeout/watch-history-<account>.json`

A helper command runs the import:
```bash
python3 ~/yt-queue/src/takeout_parse.py --account <label>
```

This validates the JSON (every row has a `time` field), extracts video_id from
`titleUrl`, normalizes, and writes `history-normalized/<label>.json`.

### 7.2 Duration Fetch

After parsing Takeout, collect all video_ids that appear in the normalized history
but are not in `durations.json`. Batch-fetch their durations:

```python
# pseudo-code — confirmed endpoint is alive
youtube.videos().list(
    part="contentDetails,snippet",
    id=",".join(batch_of_50_ids)
)
```

Parse `contentDetails.duration` (ISO-8601 duration like `PT3M32S` → 212 seconds).
Store in `durations.json`. This is the only YouTube Data API call the system makes.

### 7.3 Matching (proven in prototype)

For each pending row with empty `yt_video_id`:

1. Read normalized history for this account (newest-first sort)
2. For each clip with a known video_id:
   - `start = watched_at` (when user started playing, from Takeout `time`)
   - `end = start + duration_s` (from durations.json or API)
   - If `(start - pre_tol) <= created_at <= (end + post_tol)`:
     → match found, break (newest-first means most-recently-started wins on overlap)
3. If matched:
   - `timestamp_in_clip = max(0, min(created_at - start, duration_s))`
   - `yt_url = https://youtu.be/<video_id>?t=<timestamp_in_clip>`
   - Fill clip_title, clip_channel, clip_duration_s from history + durations
4. If no match:
   - Increment `resolve_attempts`, update `last_fetch_at`
   - After 14 days or 4 failed ingests → mark `unresolvable`

### 7.4 Asymmetric Tolerance (proven — critical finding)

```
pre_tol  = 30 seconds   (tight — user can't react before a clip starts)
post_tol = 120 seconds  (loose — reaction lag after clip ends is normal)
```

The prototype proved that symmetric tolerance causes false matches. With the old
symmetric TOL=120s, a row created 100s before clip B started was incorrectly matched
to B, because the tolerance window extended 120s before B's start. With asymmetric
tolerance (pre=30s), that same row correctly falls outside B's window and matches A
instead — because 100s > 30s.

Tolerances are user-tunable in `config.yaml`. The defaults are calibrated for a
single-device viewer who reacts within ~2 minutes of seeing something interesting.

### 7.5 Scheduling

There is no live API to poll (the HL playlist endpoint is dead since ~2016). So:

- Resolution runs **on demand**, triggered after the user drops a fresh Takeout
  export. One `refresh.sh` call per account: parse → fetch durations → match.
- A nightly cron at 09:00 (Hermes `cronjob`, `deliver='telegram'`) runs `queue status`
  per account — reports pending count, unresolvable count, and last Takeout ingest
  time. This nudges users to refresh Takeout when pending rows accumulate.

The cron's `deliver` must point to Telegram explicitly (the DGX CLI has no
live-delivery channel; confirmed in SOUL.md).

## 8. Classification (KB Integration)

On URL resolution, the agent classifies the clip into one of the existing top-level
directories of `~/knowledge_base/`.

### 8.1 Current KB Categories (36 as of 2026-07-16)

Do not hard-code this list. At classify time, run:
```bash
find ~/knowledge_base -maxdepth 1 -type d -not -path '*/\.*'
```

Current categories (will change over time):
agent-usage, ai-economy, ai-infrastructure, career-growth, claude-usage, daily-life,
doc, financial, harness, health, hermes-usage, h-net_wiki_122b, h-net_wiki_nemo,
house-remodel, llm, llm-architecture, llm-comparison, llm-hosted, llm-model-status,
llm-model-trends, local-llm-serving, mlops, mlp-fact-storage, model-fine-tune,
pit-storage, qwopus, recipes, small-llm-10b, smart-home, solar-install, startups,
travel, unprocessed, world-model

### 8.2 Classification Method

1. Fetch clip title + channel + description via YouTube Data API `videos.list?id=...&part=snippet`
   (batch this with the duration fetch in §7.2)
2. Compare against each category name + existing article titles in that category
3. If simple keyword match is unambiguous, use it (no LLM cost)
4. Otherwise, a small LLM call returns ONE directory name from the list, or `<none>`
   if nothing fits. Strict enum — no new categories invented.
5. If `<none>`, `kb_category` stays empty. The wiki step is skipped but the row
   is visible in `queue status` for manual triage.

### 8.3 Re-Classification

`queue wiki <id> as travel` — re-runs classification with a forced category override.
Agent updates `kb_category`, deletes the stale wiki page (if any), rewrites.

## 9. Wiki Write (llm-wiki Integration)

### 9.1 Trigger

Automatic when ALL of:
- `priority >= 4` (configurable in config.yaml)
- Row's URL has been resolved (yt_video_id is non-empty)
- No `kb_article_path` yet

OR manual via `queue wiki <id>`.

### 9.2 Process (follows llm-wiki skill's Ingest workflow)

1. **Orient** (critical — per llm-wiki skill):
   ```bash
   find ~/knowledge_base/ -name 'SCHEMA.md'
   ```
   Read the SCHEMA.md, index.md, and last 20 lines of log.md for the target wiki
   (the directory matching `kb_category`). Never skip orientation.

2. **If no wiki root exists** for the chosen `kb_category` (no SCHEMA.md):
   - Skip wiki write. Log to `~/yt-queue/warnings.log`.
   - The row stays in the queue; user can manually create the wiki or pick a
     different category via `queue wiki <id> as <category>`.

3. **Fetch transcript** using the `youtube-content` skill:
   - `yt-dlp --write-auto-sub` first (per llm-wiki pitfalls)
   - If no subtitles, use video description + chapter markers as structured source
   - Cap at ~50K chars

4. **Save raw source** under the wiki's raw-articles/ or raw/transcripts/ folder
   (per that wiki's SCHEMA.md convention). Use the raw-source-format.md frontmatter
   (source_url, ingested date, sha256). Compute sha256 AFTER writing the file, not
   before (per llm-wiki pitfall).

5. **Write summary wiki page** under the wiki's concepts/ or root (per SCHEMA.md):
   - Frontmatter: title, created, updated, type: summary, tags (from taxonomy),
     sources: pointing to the raw file
   - Body: user note (verbatim), the jump URL, a short summary of the transcript
   - Minimum 2 outbound [[wikilinks]] to existing pages

6. **Update navigation**: add the new page to index.md, append to log.md

7. **Write back**: `kb_article_path` (absolute) and `kb_wiki_date` back to the CSV row

8. **Reply to user** in Telegram: "Wiki: <short path>"

### 9.3 Safety Gates

- If the wiki write would touch >10 existing pages (cross-refs trigger mass update),
  pause and ask the user first (per llm-wiki pitfall).
- Run health-check BEFORE editing (per llm-wiki pitfall).
- Always read full page content before patching.
- Verify wikilink targets exist on disk before writing.

## 10. Security

- `accounts.yaml` contains OAuth refresh tokens — in `.gitignore`, never committed.
  (The existing Hermes config already has this pattern; verify before deploying.)
- `users.yaml` contains Telegram user IDs — not secrets, but gitignore anyway.
- No tokens, secrets, or PII in the queue CSVs.
- KB wiki pages are markdown only — no embedded tokens.
- Existing Telegram allowed-users list gates all commands — no new attack surface.
- **OAuth credential scan before any git push:** scan all tracked files for
  credential patterns (refresh_token, client_secret) before pushing. This is a
  hard rule per the memory about the Google OAuth credentials that were previously
  pushed to a public GitHub repo.

## 11. Failure Modes & Pitfalls

1. **Takeout export is stale.** User forgets to refresh. Rows sit pending until the
   next Takeout drop. Nightly `queue status` cron nudge shows "last ingest 12 days
   ago — N pending rows." Not a data-loss risk, just latency.

2. **User sends `priority 5` before pressing play.** No matching clip → row never
   matches any Takeout entry → auto-marked `unresolvable` after 14d or 4 failed
   ingests. Visible in `queue status`.

3. **Two clips overlap (user watching two devices).** Matcher picks the most
   recently started clip (newest-first sort, proven in prototype). User note can
   disambiguate later; `queue drop` the wrong one.

4. **Clip later deleted/private.** `yt_url` stays in the row. Transcript fetch for
   wiki will fail; wiki-write aborted with warning logged. Row stays intact.

5. **Takeout retention cap.** One 2024 user reported YouTube history capped at ~8
   months in Takeout. Old rows with `created_at` older than the earliest Takeout
   entry can never be matched → auto-marked `unresolvable`. Document per-user once
   the first real ingest lands.

6. **Takeout format changes.** Google has changed export formats before. The parser
   counts `missing_time` rows and reports them. If the count is suspiciously high,
   the parser should refuse to produce a normalized file and warn the user.

7. **Voice transcription noise.** "priority five" → expand to 5. "prior to 5" →
   fuzzy match, ask for clarification if ambiguous. No row inserted on ambiguity.

8. **Multiple users, same YouTube account.** If two Telegram IDs map to the same
   account label, both users' rows go into the same queue CSV. This is acceptable
   but rows are distinguishable by `created_at` and `user_note`. If this becomes a
   problem, add a `sender_tg_id` column in a future version.

9. **OAuth refresh token expiry.** Google refresh tokens can expire if unused for
   6 months. The durations API call will fail with 401; `accounts.py status`
   should refresh each token on check and report any that fail. Re-enroll the
   expired account.

## 12. Phased Build Plan

### Phase 1 — Core pipeline (port from prototype)
- Copy takeout_parse.py, match.py, dispatch.py, accounts.py from prototype to ~/yt-queue/src/
- Add durations.py (live YouTube Data API call for video durations)
- Wire dispatch.py into the Hermes agent's Telegram handling
- Verify: user sends `priority 5` via Telegram → row appears in queue CSV → reply with ID

### Phase 2 — Real Takeout validation
- User exports real Takeout from their YouTube account
- Run takeout_parse.py against the real JSON
- Confirm: zero rows dropped, timestamps parse correctly, video_ids extract properly
- This is the critical "trust but verify" step — the prototype used synthetic fixtures

### Phase 3 — Live OAuth + duration fetch
- Create a Google OAuth client in Google Cloud Console
- Run `accounts.py enroll dan` interactively
- Run durations.py to fetch real video durations
- Run the full match loop against real Takeout + real durations
- Verify: a real `priority N` command resolves to a real youtu.be URL with a real timestamp

### Phase 4 — Classification
- Implement classify.py
- Test against the 36 KB categories
- Verify: a resolved row gets a `kb_category` that makes sense

### Phase 5 — Wiki write
- Implement wiki_write.py following the llm-wiki skill's Ingest workflow
- Test with a priority >= 4 row
- Verify: a wiki page appears in the correct KB directory with proper frontmatter,
  the jump URL, the transcript summary, and index.md / log.md are updated

### Phase 6 — Cron + polish
- Nightly `queue status` cron (deliver to Telegram)
- Edge case handling (re-classification, stale Takeout nudge, voice transcription)
- Config.yaml with all tunables
- Final E2E: user sends `priority 5` on phone → Takeout refresh → row resolves →
  shows up with URL in queue → auto-classified → wiki page written → user sees
  "Wiki: ~/knowledge_base/<category>/<page>.md" in Telegram

Each phase is independently testable. Stop after each for user review.

## 13. Open Questions for User

1. **OAuth client.** Need a Google Cloud Console OAuth client withyoutube.readonly
   scope. You create it (or I walk you through it), then paste client_id + client_secret
   into accounts.yaml. This is the only piece I can't do unilaterally.

2. **Takeout refresh cadence.** Weekly? Daily? The nightly cron will nudge you, but
   the cadence determines how quickly priority commands resolve. If you watch a lot,
   weekly may leave many rows pending for days.

3. **Self-report mode (Mode B from old spec).** Drop this for v1.0, or keep as an
   escape hatch? If the user pastes a youtu.be link alongside their priority
   command, resolution is instant and exact — no Takeout needed. Costs one extra
   tap (YouTube share button → paste into Telegram). Not required for v1.0 but
   cheap to add.

4. **Wiki auto-write threshold.** Priority >= 4 (not 5)? Priority 3 and below
   only wiki on explicit `queue wiki <id>`?

5. **Storage path.** `~/yt-queue/` or under `~/knowledge_base/yt-queue/` so it
   syncs with the KB? The KB is a git repo; the queue CSV would be tracked too.

6. **Single bot or dedicated.** OK to use the existing Hermes Telegram bot, or do
   you want a dedicated `@yt_queue_bot` to keep chat history clean?
