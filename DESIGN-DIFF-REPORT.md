# DESIGN.md (v1) vs DESIGN-v2.md (v2) — Diff Report

Generated: 2026-07-16

## Overview

DESIGN.md (v1): 25KB, 551 lines
DESIGN-v2.md (v2): 50KB, ~1,200 lines (+ sections 22-24 added by agent)

v2 is a substantial rewrite — nearly doubles the size, adds formalized design
principles, normalized SQLite schema, Data Portability API as primary acquisition
path, confidence scoring, configuration layer, and test matrix.

## What v2 RETAINED from v1 (reorganized)

| v1 Section | v2 Equivalent | Notes |
|------------|---------------|-------|
| §3 Architecture | §6 System Architecture | Same topology, clarified |
| §4 Multi-Account Design | §7 Identity and Multiple Accounts | Expanded with secure binding, live proof |
| §5.3 Commands (User Side) | §5.1 Commands | Added `switch`, `queue <id>`, `choose`, `link`, `watched`, `wiki` |
| §7.3 Matching | §11 Matching Algorithm | Expanded with confidence scoring |
| §8 Classification | §12 Metadata and Classification | |
| §9 Wiki Write | §13 Wiki Workflow | |
| §10 Security | §14 Security and Privacy | |
| §12 Phased Build Plan | §18 Phased Delivery | Expanded 6→7 phases, added Phase 0 |
| §4.2 Enrollment / §7.2 Duration Fetch | §7.3 Enrollment and live proof | |

## What v2 ADDED (new in v2, not in v1)

- §2 Design Principles (6 principles: idempotency, ambiguity-as-data, etc.)
- §3.2 Non-goals for first release
- §4.1 History availability constraint
- §4.2 Offset accuracy (exact vs estimated)
- §4.3 OAuth separation (two independent grants — major architectural change)
- §5.2 Capture acknowledgement
- §5.3 Ambiguous result handling
- §8 Storage Model (9 normalized SQLite tables replacing v1's flat CSV)
- §10.1 Data Portability API as PRIMARY acquisition path (v1 only had Takeout)
- §11.2 Confidence scoring and decision
- §11.3 URL construction
- §15 Reliability and Observability
- §16 Configuration (all tunables in one place)
- §17 Implementation Layout (src/ structure)
- §19 Test Matrix
- §20 Decisions Still Needed
- §21 Official References
- §22-24 Review Notes, Task Breakdown, Changes from v1 (added by agent 2026-07-16)

## What v2 DROPPED from v1 (and where they might still exist)

### 1. "What was NOT proven" (§2 in v1)
The 4 implementation risks found in the prototype:
- Real Takeout export hasn't been validated against live export
- Live YouTube Data API call not tested (no OAuth client in prototype)
- KB classification + llm-wiki integration not built
- Hermes gateway wiring only simulated via CLI args

**Status in v2**: Partially covered by §20 (Decisions Still Needed), but the
explicit "prototype risk" framing with confidence levels is gone. Phase 0 in
§18 addresses some of these but doesn't enumerate them as explicitly.

### 2. "Failure Modes & Pitfalls" (§11 in v1)
9 specific failure scenarios with mitigation strategies:
1. Stale Takeout export → nightly nudge
2. User sends priority before pressing play → no match, eventual unresolvable
3. Two clips overlap (two devices) → newest-first proven, user can disambiguate
4. Clip later deleted/private → wiki abort with log, row preserved
5. Takeout retention cap (~8 months) → unresolvable marker, document per-user
6. Takeout format changes → parser counts missing_time, refuses unsafe parse
7. Voice transcription noise → fuzzy match, ask clarification, no row on ambiguity
8. Multiple users sharing same YouTube account → acceptable, distinguishable by created_at
9. OAuth refresh token expiry (6 months) → check on each API call, report failures

**Status in v2**: §15 Reliability covers some concepts. §19 Test Matrix covers some
edge cases. But the EXPLICIT per-failure-mode walkthrough with concrete mitigation
is gone. This was one of the most practically useful sections of v1.

### 3. "Open Questions for User" (§13 in v1)
6 decisions needing user input:
1. OAuth client creation in Google Cloud Console
2. Takeout refresh cadence (weekly vs daily)
3. Self-report mode (Mode B) — drop for v1.0 or keep as escape hatch?
4. Wiki auto-write threshold (priority >= 4? priority 3 only on explicit command?)
5. Storage path (~/yt-queue/ vs ~/knowledge_base/yt-queue/)
6. Single vs dedicated bot (use existing Hermes bot or @yt_queue_bot?)

**Status in v2**: §20 partially covers #1, #3 (via link command), and #5. But
drops #2 (cadence question), #4 (wiki threshold), and #6 (bot choice).

### 4. "Per-Account Queue CSV" (§6.1 in v1)
Replaced by §8's SQLite schema — intentional design upgrade, not a loss.

### 5. "Dispatch Flow (proven in prototype)" (§5.2 in v1)
The detailed flow of how a Telegram message becomes a queued priority item.
**Status in v2**: §9 Capture Pipeline covers the same flow at a higher level.
The "proven" label on specific steps is gone.

### 6. "Asymmetric Tolerance" (§7.4 in v1)
The critical prototype finding: tolerance windows must be asymmetric
(harder to overshoot than undershoot, because user can seek backward but
can't know the future). This was explicitly flagged as "proven — critical."
**Status in v2**: §11.2 discusses confidence scoring but doesn't call out
asymmetric tolerance by name or mark it as a proven finding.

### 7. "Supporting Files" (§6.3 in v1)
Details about accounts.yaml, users.yaml, per-account CSV files layout.
**Status in v2**: Replaced by §8 schema tables and §16 configuration.

## Significance Assessment

The MOST significant losses are #2 (Failure Modes & Pitfalls) and #3 (Open
Questions), because both contain specific operational knowledge that's now
dispersed across multiple sections without the same density.

#1 (What was NOT proven) is also important for risk tracking through the
phased build.

Recommendation: These three sections could be added back as subsections
under §20 (Decisions Still Needed) for #3, and as a new §15.x or standalone
appendix for #1 and #2.