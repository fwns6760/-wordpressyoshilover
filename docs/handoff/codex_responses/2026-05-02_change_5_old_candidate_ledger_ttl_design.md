# 改修 #5 old_candidate ledger TTL design

Date: 2026-05-02 JST  
Mode: doc-only / read-only analysis + test plan + Acceptance pre-pack  
Implementation status: not started  
Decision now: HOLD

## 0. Scope of this document

- `old_candidate` permanent dedup ledger の現状分析
- narrow TTL prune 案
- impl 便向け test plan
- Acceptance Pack 13 項目の草案
- `CLAUDE_AUTO_GO` 14 条件の pre-evaluation

This document does **not** change `src/`, `tests/`, env, Scheduler, Cloud Run, GCS state, or ticket state.

## 1. Current-state analysis(read-only)

### 1.1 実装場所

Primary implementation:

- `src/publish_notice_scanner.py:65-69`
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE`
  - `PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS`
  - `PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_PATH`
  - default local path `/tmp/pub004d/publish_notice_old_candidate_once.json`
- `src/publish_notice_scanner.py:388-407`
  - `_load_history()` / `_write_history()` が ledger を JSON object として load/save
- `src/publish_notice_scanner.py:1143-1150`
  - `scan_guarded_publish_history()` 開始時に ledger を load
- `src/publish_notice_scanner.py:1250-1260`
  - `hold_reason == "backlog_only"` かつ old candidate age threshold 超過時のみ permanent dedup を参照
- `src/publish_notice_scanner.py:1287-1293`
  - emit 対象になった old candidate を ledger に追記
- `src/publish_notice_scanner.py:1354-1359`
  - run 終了時に ledger write
- `src/publish_notice_scanner.py:2067-2109`
  - class reserve path でも selected review ids に応じて ledger write

Cloud Run / GCS persistence:

- `src/cloud_run_persistence.py:27-28`
  - local default path `/tmp/pub004d/publish_notice_old_candidate_once.json`
  - remote object name `publish_notice_old_candidate_once.json`
- `src/cloud_run_persistence.py:258-275`
  - entrypoint arg / env wiring
- `src/cloud_run_persistence.py:359-370`
  - runner env に ledger path を注入し、`gs://<bucket>/publish_notice/publish_notice_old_candidate_once.json` を restore/upload

### 1.2 Serialize 形式

Current on-disk format is **JSON object**, not JSONL.

Example:

```json
{
  "63003": "2026-05-01T09:00:00+09:00",
  "63005": "2026-05-01T09:05:00+09:00"
}
```

Properties:

- key: `post_id` string
- value: ISO8601 timestamp string in JST
- writer: `_write_history()` sorts keys and pretty-prints with `indent=2`
- storage:
  - local: `/tmp/pub004d/publish_notice_old_candidate_once.json`
  - remote: `gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json`

This is separate from:

- `logs/publish_notice_history.json` 24h dedup history
- `guarded_publish_history.jsonl`
- `publish_notice_queue.jsonl`

### 1.3 ledger entry の意味

An entry means:

- this `post_id` already emitted once through the `old_candidate once` path
- scope is **only** `hold_reason == "backlog_only"` and only when `_is_old_candidate_over_threshold(...)` is true
- recorded value is **not** the article's original publish date
- recorded value is `review_recorded_at_iso`, i.e. the scanner-side queued/emitted timestamp for that notice

Important contract boundaries:

- `cleanup_required`, `real review`, `289/post_gen_validate`, `preflight_skip`, and normal error paths do **not** use this ledger for suppression
- when `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=0`, baseline behavior reverts to 24h dedup only

### 1.4 Current row count / size estimate(as of 2026-05-02 11:00 JST)

Direct live GCS inspection is **not** available in this doc-only turn, so the estimate is based on repository evidence plus the user-provided 11:00 JST observation.

Read-only evidence:

- `docs/ops/OPS_BOARD.yaml:207-210`
  - ledger count recorded as `106`
- `docs/ops/CURRENT_STATE.md:48-52`
  - `104 -> 106` after pre-seed + auto append
- `docs/ops/NEXT_SESSION_RUNBOOK.md:83-89`
  - `permanent_dedup skip count: 106+ stable`
- `docs/handoff/session_logs/2026-05-02_morning_verify.md:30-34`
  - one run observed `OLD_CANDIDATE_PERMANENT_DEDUP` skip `40+`
- user note for this ticket:
  - at `2026-05-02 11:00 JST`, ledger has `100+` rows in production

Working estimate for this design:

- current row count: **106-120 rows**
- current raw JSON size:
  - 5-digit entry line with comma/newline is about `40 bytes`
  - `106 rows` -> about `4.2 KB`
  - `120 rows` -> about `4.8 KB`

Why this still matters:

- raw object is still small today
- but growth is monotonic and unbounded
- scanner loads the whole object each run
- GCS state object size and Python in-memory dict size both scale linearly with row count
- `365 rows` would already be about `14.6 KB`
- `1000 rows` would be about `40 KB+` before Python object overhead

### 1.5 Current risk summary

Todayの問題は immediate outage ではなく、hot-state の単調増加です。

- short-term: safe enough
- medium-term: unbounded growth
- safety priority: storm suppression must win over aggressive cleanup

That means the TTL change must be:

- default OFF
- schema-preserving
- scoped only to this ledger
- safe even when no new emits happen in a run

## 2. Narrow TTL design

### 2.1 Design goal

Keep the permanent dedup benefit for recent old-candidate storms while preventing the ledger from growing forever.

### 2.2 Proposed env knobs

Primary flag(default OFF):

- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL`

TTL value env:

- `PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL_DAYS`

Defaults:

- flag default: OFF / absent
- TTL default: `7`

Resolver behavior:

- blank / invalid value -> `7`
- minimum clamp: `1 day`

Rationale:

- `*_DAYS` matches existing `PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS`
- `1 day` minimum avoids accidental `0` day full wipe

### 2.3 Schema choice

Do **not** widen the ledger schema in 改修 #5.

Keep:

- `dict[str, str]`

Interpretation for TTL:

- the existing value string is the effective ledger `ts`

Why not add a nested `{"ts": ...}` object here:

- would force schema migration for existing GCS object
- would widen blast radius to persistence + compatibility logic
- is unnecessary for the narrow prune goal

### 2.4 Proposed prune rule

When both conditions are true:

- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL=1`

then prune once at the start of `scan_guarded_publish_history()`:

```text
expire_before = now - timedelta(days=ttl_days)
drop ledger entry if parsed_ts < expire_before
```

Important detail:

- use the stored ledger timestamp, not post date, not modified date, not guarded history ts

### 2.5 Invalid timestamp handling

Recommendation: **preserve unparseable rows fail-closed**.

Reason:

- deleting malformed rows can re-open old candidates and recreate mail-storm risk
- malformed rows do not match the explicit "older than TTL" condition anyway
- safety priority here is suppress-storm-first

Optional observation metric if implemented:

- `invalid_ts_count`

but no new mail path or user-visible contract is required.

### 2.6 Prune frequency

Exactly once per publish-notice run:

- after ledger load
- before review candidate scan loop

Why:

- O(n) once per run is minimal overhead
- avoids repeated checks per candidate

### 2.7 Write semantics

This is the most important implementation detail for the follow-up coding turn.

Current code writes the old-candidate ledger only when a new old candidate is selected/emitted. TTL prune adds a new case:

- prune-only run with zero new emits still needs a write

Therefore the impl should:

1. load current ledger
2. prune in memory when TTL flag is ON
3. carry the pruned dict forward as the new base state
4. set a dedicated "prune changed state" boolean, or merge it into `old_candidate_ledger_write_needed`
5. write at end when either:
   - prune removed rows, or
   - new old-candidate emit added rows

This must hold for:

- normal path
- `max_per_run <= 0` early-return path
- class reserve path
- zero-emitted path

### 2.8 Non-scope / non-touch contract

This change must not alter:

- `24h` history dedup
- `PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS`
- `hold_reason` classification
- `cleanup_required`
- `real review`
- `289/post_gen_validate`
- `preflight_skip`
- class reserve quotas / priority
- mail sender / subject / recipients
- Gemini calls
- Cloud Run / Scheduler / Secret / source list

### 2.9 Why default TTL = 7 days

Why `7d` is the best narrow default for 改修 #5:

- longer than the current `3 day` old-candidate threshold
- long enough to suppress week-scale repeated backlog storms
- much tighter than the earlier `30/60/90d` placeholder ideas in `docs/ops/POLICY.md:849-857`
- meaningfully bounds growth earlier

Tradeoff:

- a `post_id` older than `7d` can be re-emitted if it still reappears as `backlog_only` and remains over threshold
- that is acceptable only because the feature stays default OFF until separately enabled

## 3. Impl test plan

### 3.1 New targeted test file

Proposed new file:

- `tests/test_publish_notice_ledger_ttl_prune.py`

Purpose:

- isolate TTL prune semantics from the already-large scanner regression file

### 3.2 Proposed test cases(9 cases)

1. `expired_entry_is_pruned`
   - setup: one ledger row older than TTL
   - expect: row removed, write needed

2. `entry_within_ttl_is_preserved`
   - setup: one recent row within TTL
   - expect: row kept, no prune write

3. `flag_off_keeps_ledger_baseline`
   - setup: expired row exists but TTL flag OFF
   - expect: no prune, baseline permanent dedup behavior unchanged

4. `empty_ledger_is_noop`
   - setup: `{}` or missing file
   - expect: empty result, no error, no write

5. `all_entries_expired_prune_to_empty_object`
   - setup: all rows older than TTL
   - expect: `{}` persisted, no crash

6. `mixed_expired_and_recent_rows_prunes_only_old_subset`
   - setup: 3-5 rows mixed old/recent
   - expect: only rows older than cutoff disappear

7. `prune_only_run_still_persists_when_no_new_old_candidate_emit_occurs`
   - setup: TTL removes rows but current scan emits zero old candidates
   - expect: pruned ledger still saved

8. `serialized_size_is_non_increasing_after_prune`
   - setup: mixed ledger, prune applied
   - expect: output JSON byte size `<=` input size

9. `invalid_timestamp_is_preserved_fail_closed`
   - setup: one malformed ts + one expired valid ts
   - expect: malformed row kept, valid expired row removed

### 3.3 Existing regression subset that must still pass

These existing tests already cover the current once-ledger contract and should remain green:

- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_old_candidate_over_threshold_emits_once_and_records_permanent_ledger`
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_old_candidate_over_threshold_is_suppressed_after_permanent_ledger_hit`
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_backlog_only_under_threshold_still_uses_existing_24h_recent_dedup`
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_cleanup_review_bypasses_old_candidate_once_ledger`
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_repeated_old_candidate_after_24h_dedup_expiry_with_flag_on_does_not_re_emit`
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_repeated_old_candidate_after_24h_dedup_expiry_with_flag_off_still_re_emits_baseline`
- `tests/test_publish_notice_scanner_class_reserve.py`
- `tests/test_cloud_run_persistence.py::test_entrypoint_restores_and_uploads_old_candidate_once_ledger`

### 3.4 Suggested test commands for the impl turn

Targeted first:

```bash
python3 -m unittest tests.test_publish_notice_ledger_ttl_prune
python3 -m unittest tests.test_publish_notice_scanner
python3 -m unittest tests.test_publish_notice_scanner_class_reserve
python3 -m unittest tests.test_cloud_run_persistence
```

Then repo-standard full sweep:

```bash
python3 -m unittest discover -s tests
```

### 3.5 Acceptance criteria for the impl turn

- TTL flag OFF -> behavior identical to current production
- TTL flag ON -> only expired ledger rows are removed
- no effect on non-`old_candidate` review paths
- prune-only runs persist updated ledger
- no GCS persistence regression
- no mail path regression

## 4. Acceptance Pack draft(13 items)

This is a draft pack for the future impl ticket. Current recommendation remains `HOLD`.

### 1. Decision

- `HOLD`
- reason: this turn produced design/test/acceptance material only; no implementation or deploy evidence exists yet

### 2. Scope

- add a default-OFF TTL prune path for `publish_notice_old_candidate_once.json`
- prune only the old-candidate permanent dedup ledger
- run prune once per publish-notice execution

### 3. Non-Scope

- no change to `src/` in this turn
- no Cloud Run / Scheduler / Secret / env mutation
- no change to review criteria, `289`, `cleanup_required`, source, SEO, mail routing, or Gemini provider behavior

### 4. Why now

- the ledger is already `100+` rows as of `2026-05-02 11:00 JST`
- one run still shows `40+` `OLD_CANDIDATE_PERMANENT_DEDUP` skips
- current object is small, but the growth model is unbounded
- this is a low-risk bounded cleanup target while both Codex lanes are otherwise idle-capable

### 5. Preconditions

All must be true before future GO:

- impl commit exists
- targeted tests green
- full repo unittest green
- rollback anchor written(runtime + source)
- default OFF deploy path and future flag ON path are explicitly split

### 6. Evidence

- code references: `src/publish_notice_scanner.py`, `src/cloud_run_persistence.py`
- state references:
  - `docs/ops/OPS_BOARD.yaml:207-210`
  - `docs/ops/CURRENT_STATE.md:48-52`
  - `docs/ops/NEXT_SESSION_RUNBOOK.md:83-89`
  - `docs/handoff/session_logs/2026-05-02_morning_verify.md:30-34`
- policy references:
  - `docs/ops/POLICY.md:39-58`
  - `docs/ops/POLICY.md:849-857`

### 7. User-visible impact

- this turn: none
- future default OFF deploy: none
- future flag ON enablement:
  - only very old already-recorded `old_candidate` ids may become eligible again after TTL expiry
  - `real review`, `289`, `cleanup_required`, and normal error mail should remain unchanged

### 8. Mail volume impact

- `NO` for this doc-only turn
- expected `NO` for default OFF deploy
- future flag ON enablement needs separate verify because pruned rows can eventually re-enter the pool

### 9. Gemini / cost impact

- Gemini call increase: `NO`
- expected Cloud cost delta: negligible
- GCS object size impact: bounded downward when prune is enabled

### 10. Rollback(Tier 1)

Future impl / deploy rollback should be:

- Tier 1 runtime:
  - remove or disable `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL`
- Tier 2 source:
  - `git revert <impl_commit>`

This turn itself needs no rollback because production is untouched.

### 11. Stop conditions

Future enablement should stop if any of these appear:

- unexpected mail increase
- `OLD_CANDIDATE_PERMANENT_DEDUP` protection collapses for known recent cohorts
- candidate disappearance or misrouting
- malformed ledger handling deletes rows broadly
- rollback target is not concretely written

### 12. Expiry

- this design draft expires on `2026-05-09 23:59 JST` or when superseded by an impl-ready pack, whichever comes first

### 13. Recommended decision

- accept this design doc
- fire a separate impl ticket next
- keep current state `HOLD` until code + tests + rollback anchors exist

## 5. `CLAUDE_AUTO_GO` 14-condition pre-evaluation

This section uses the practical 14 core conditions plus the separate `post-deploy verify plan` item from `docs/ops/POLICY.md:39-58`.

Interpretation:

- **Pack A** = impl landed, deploy with TTL flag still OFF -> possible `CLAUDE_AUTO_GO`
- **Pack B** = later TTL flag ON enablement -> **not** `CLAUDE_AUTO_GO`; this becomes `USER_DECISION_REQUIRED`

| # | condition | Pack A pre-judgment | note |
|---|---|---|---|
| 1 | flag OFF deploy | YES | design is default OFF |
| 2 | live-inert deploy | YES | TTL path unreachable while flag absent/OFF |
| 3 | behavior-preserving image replacement | YES | only for Pack A, not Pack B |
| 4 | tests are green | PENDING | impl not written yet |
| 5 | rollback target confirmed | PENDING | needs exact commit/image anchors in impl pack |
| 6 | Gemini call increase none | YES | ledger prune only |
| 7 | mail volume increase none | YES for Pack A | Pack B needs separate verify |
| 8 | source addition none | YES | no source touch |
| 9 | Scheduler change none | YES | none proposed |
| 10 | SEO/noindex/canonical/301 change none | YES | none proposed |
| 11 | publish/review/hold/skip criteria unchanged | YES for Pack A | Pack B changes retention semantics for old_candidate suppression window |
| 12 | cleanup mutation none | YES | no WP cleanup mutation |
| 13 | candidate disappearance risk none/proven unchanged | YES for Pack A | Pack B needs production-safe proof |
| 14 | stop condition written | PARTIAL | draft exists here, not yet impl-ready |

`+1` from POLICY §3.1:

- post-deploy verify plan written -> `PARTIAL`
  - this doc provides the outline
  - a concrete impl-ready verify table is still needed

### 5.1 Pre-evaluation summary

For the future coding turn:

- default OFF deploy path is a plausible `CLAUDE_AUTO_GO` candidate **after** impl/test/rollback anchors are complete
- later flag ON enablement is **not** `CLAUDE_AUTO_GO`
  - behavior changes
  - old candidates older than TTL can re-enter
  - production-safe regression and explicit user decision are required

## 6. Recommended next step

Next ticket should be impl-only and narrow:

- touch only scanner + persistence + new targeted tests
- keep TTL default OFF
- produce rollback anchors and a concrete post-deploy verify table
- do not combine with #4, 288, 290, or any mail/Gemini/source work
