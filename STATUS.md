# YouTube Review Queue — Project Status

Last updated: 2026-07-16

## Overview

Implementation of the YouTube Review Queue per DESIGN-v2.md at
~/workspace/prototype/yt-queue-poc/DESIGN-v2.md

Project home: ~/workspace/yt-review-queue/

## Task Progress

| Task | Description | Status | Files |
|------|-------------|--------|-------|
| A | Project scaffold | DONE | pyproject.toml, uv.lock, .gitignore, dirs |
| B | SQLite schema + migration runner | DONE | migrations/001_initial.sql, db.py, test_db.py (7 tests) |
| C | Telegram capture + commands + identity | DONE | commands.py, capture.py, identity.py, test_capture.py (11 tests), test_commands.py (13 tests) |
| D | Google OAuth enrollment | DONE | google_oauth.py, enroll.py, ENROLLMENT_GUIDE.md, test_google_oauth.py (4 tests + 2 skipped) |
| E | Activity normalizer (DP/Takeout -> activity_event) | PENDING | |
| F | Candidate matcher (confidence scoring) | PENDING | |
| G | YouTube metadata fetcher | PENDING | |
| H | KB classifier | PENDING | |
| I | Wiki job runner | PENDING | |
| J | Telegram webhook server | PENDING | |
| K | Queue/status view | PENDING | |
| L | Data Portability scheduler | PENDING | |
| M | E2E integration tests | PENDING | |

## Test Suite

39 passed, 2 skipped (integration tests needing real Google credentials), 0 failures

Run: `cd ~/workspace/yt-review-queue && . .venv/bin/activate && python -m pytest tests/unit/ -v`

## Dependency Graph (remaining tasks)

```
E (normalizer)  — needs C's bookmark model
F (matcher)     — needs E
G (YT metadata) — needs D's OAuth
H (KB classify) — standalone
I (wiki job)   — needs H
J (webhook)    — needs C
K (queue view) — needs C
L (DP scheduler)— needs J + D
M (E2E tests)  — needs everything
```

Parallel waves:
- Wave 3: E + H + K (3 agents, all depend on completed A-D)
- Wave 4: F + G + J (after E + H land)
- Wave 5: I + L (after F + G + J)
- Wave 6: M (after everything)

## Notes

- Subagents (minimax-m3) failed repeatedly with 429/internal server errors. All code was written inline by the main agent.
- Google OAuth import fix: use `google_auth_oauthlib.flow` (top-level package), NOT `google.auth.oauthlib.flow` (namespace path).
- Command parser preserves case on IDs and notes by using re.IGNORECASE on original text instead of lowercasing.
- Next step: implement Tasks E-M or retry subagents when rate limit resets.
