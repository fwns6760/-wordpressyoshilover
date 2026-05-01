# 300-COST read-only test plan v1

Date: 2026-05-01 JST  
Lane: Codex B round 19  
Mode: doc-only / read-only / production unchanged  
Status: impl-prep supplement for future fire after user GO

Source alignment:

- `docs/handoff/codex_responses/2026-05-01_300_COST_impl_prep_narrow_spec.md` (`e14c944`)
- `docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis_v2.md`
- `docs/handoff/codex_responses/2026-05-01_300_COST_pack_supplement.md`
- `docs/ops/POLICY.md` §3.5 / §3.6 / §20.6

This document does not authorize implementation, deploy, env mutation, Scheduler mutation, or production behavior change. It only fixes the future impl-round test contract and the pre-fire capture items that were still implicit in `e14c944`.

## 1. Current source-side path: what actually repeats today

Current live behavior is driven by the guarded history append path inside `src/guarded_publish_runner.py`:

- `src/guarded_publish_runner.py:1108-1128`
  - `_history_attempted_post_ids(...)` dedupes only `status=sent` and recent `status=refused`.
  - `status=skipped` rows are not treated as attempted, so the same `post_id` can re-enter on the next `*/5` run.
- `src/guarded_publish_runner.py:2093-2143`
  - `backlog_only` candidates that fail narrow-allowlist checks are converted to `refused[]` + `live_history_rows[]` as `status=skipped`, `hold_reason=backlog_only`.
- `src/guarded_publish_runner.py:2162-2194`, `2212-2294`, `2330-2416`
  - other `skipped` states such as `backlog_deferred_for_fresh`, `hourly_cap`, `burst_cap`, `daily_cap` and some `refused` states are also appended per run.
- `src/guarded_publish_runner.py:2423-2425`
  - every row accumulated in `live_history_rows` is appended to `guarded_publish_history.jsonl`.

Downstream, `src/publish_notice_scanner.py:1228-1362` consumes those new rows:

- same-run duplicate scan is suppressed by `seen_post_ids`.
- cross-run review dedupe is still `24h` history-based unless old-candidate-once is enabled.
- repeated source-side `backlog_only` rows are therefore still fuel for later reminder-layer reappearance.

Relevant downstream baseline tests already exist:

- `tests/test_publish_notice_scanner.py:700-747`
  - flag ON old-candidate ledger suppresses repeated re-emit.
- `tests/test_publish_notice_scanner.py:749-792`
  - flag OFF baseline still re-emits after `24h` dedupe expiry.

## 2. `src/cron_eval.py` reality check

`src/cron_eval.py` does not exist in the current tree. `cron_eval.json` is also not referenced anywhere in current source/tests outside handoff docs.

Implication for the future impl round:

- preferred v1 shape is a private helper in `src/guarded_publish_runner.py`
- create `src/cron_eval.py` only if the helper extraction is strictly necessary
- tests should assert idempotence semantics, not a broad new module contract

## 3. Current behavior vs future `300-COST` v1 behavior

| case | current | future v1 contract |
|---|---|---|
| same `post_id`, latest row = unchanged `skipped/yellow/backlog_only` | reevaluates and appends another identical history row | reevaluates, but append is skipped and explicit runner log is emitted |
| same `post_id`, latest row changed (`hold_reason`, `status`, or `judgment` differs) | appends fresh row | must still append fresh row |
| same `post_id`, latest row = `daily_cap` / `burst_cap` / `hourly_cap` / `backlog_deferred_for_fresh` | appends per run | must remain unchanged in v1 |
| same `post_id`, latest row = `refused` | deduped only by existing refused window in `_history_attempted_post_ids(...)` | unchanged |
| downstream `publish_notice_scanner` | sees every new source row and can re-open review/reminder visibility | unchanged code; fewer source rows only for unchanged `backlog_only` |

Important nuance:

- `300-COST` v1 is **append-idempotence only** for unchanged `backlog_only`.
- It is **not** a general per-post skip framework.
- It must not silently absorb `review`, `cleanup_required`, cap, or duplicate-candidate paths.

## 4. Local fixture reality

Read-only inspection of current local logs:

- `logs/guarded_publish_history.jsonl`: `204` rows
- `logs/publish_notice_queue.jsonl`: `170` rows
- local checked-out copies currently contain `0` `backlog_only` matches

Implication:

- real local log copies are not sufficient as golden fixtures for this ticket
- future tests should use fully synthetic temp JSONL / JSON fixtures
- this is consistent with existing guarded-publish and scanner tests, which already use synthetic per-test ledgers

## 5. Proposed test cases for the impl round

Minimum target is `7+`; recommended v1 matrix is `10` cases.

### A. New dedicated source-side idempotence tests

Recommended new file:

- `tests/test_guarded_publish_runner_dedupe_idempotent.py`

Recommended cases:

1. `unchanged_backlog_only_latest_row_skips_append`
   - history has latest row `{post_id=901, status=skipped, judgment=yellow, hold_reason=backlog_only}`
   - same candidate is reevaluated live
   - assert returned `refused` still contains `backlog_only`
   - assert no additional history row is appended
   - assert explicit log event exists

2. `new_post_without_prior_state_appends_once`
   - empty history
   - assert one new row appended

3. `same_post_changed_hold_reason_appends`
   - latest row is `backlog_only`, current run yields `backlog_deferred_for_fresh`
   - assert fresh row is appended

4. `same_post_changed_status_appends`
   - latest row is `skipped/backlog_only`, current run yields `refused/review`
   - assert fresh row is appended

5. `same_post_changed_judgment_appends`
   - latest row is `yellow/backlog_only`, current run yields `hard_stop/...`
   - assert fresh row is appended

6. `latest_row_match_is_based_on_state_not_ts`
   - identical logical state but different historical timestamp
   - assert v1 still treats it as unchanged

7. `non_backlog_skip_reasons_remain_appending`
   - `daily_cap`, `burst_cap`, `hourly_cap`, `backlog_deferred_for_fresh`
   - assert no v1 dedupe is applied

8. `latest_visible_row_only`
   - history contains older `backlog_only` row, then newer changed row
   - assert decision keys off the latest visible row, not any older matching row

### B. Existing guarded-publish regression suites to keep green

Keep unchanged:

9. `tests/test_guarded_publish_runner.py`
   - especially `1597-1659` backlog summary suppression
   - especially `1661-1916` backlog-only narrow allowlist/blocklist cases

10. `tests/test_guarded_publish_backlog_narrow.py`
    - backlog summary mode, narrow allowlist order, and review-before-backlog behavior

### C. Existing downstream scanner compatibility to keep green

Keep unchanged:

11. `tests/test_publish_notice_scanner.py:488-792`
    - queueing of backlog-only yellow
    - old-candidate-once permanent ledger behavior
    - flag OFF repeated re-emit baseline for synthetic repeated rows

12. optional smoke: `tests/test_publish_notice_scanner_class_reserve.py`
    - only needed if shared helper behavior or queue payload shape is touched

## 6. Fixture design

### 6.1 Guarded history JSONL fixture

Use temp JSONL rows built from the existing `_history_row(...)` schema in `src/guarded_publish_runner.py:1794-1826`.

Minimal unchanged-row fixture:

```json
{"post_id":901,"ts":"2026-05-01T08:00:00+09:00","status":"skipped","backup_path":null,"error":"backlog_only","judgment":"yellow","publishable":true,"cleanup_required":false,"cleanup_success":false,"hold_reason":"backlog_only","is_backlog":true,"freshness_source":"x_post_date","duplicate_of_post_id":null,"duplicate_reason":null}
```

Why this should be synthetic:

- local logs do not currently contain checked-out `backlog_only` rows
- existing tests already construct synthetic posts/reports via `FakeWPClient`, `_repairable_entry(...)`, and `_report(...)`

### 6.2 Mock report fixture

Reuse the existing guarded-publish test helpers:

- `tests/test_guarded_publish_runner.py`
  - `FakeWPClient`
  - `_post(...)`
  - `_repairable_entry(...)`
  - `_report(...)`

Recommended candidate shape:

- one `yellow` entry
- `backlog_only=True`
- `resolved_subtype` set to a blocked subtype such as `pregame`, `lineup`, or an over-age `postgame`
- `freshness_source="x_post_date"`

This keeps the future test aligned with the current backlog-only path rather than inventing a new evaluator surface.

### 6.3 `cron_eval.json` fixture

Because there is no current source file or schema, keep the future fixture minimal and private to the test:

- file path: temp file under `TemporaryDirectory()`
- payload recommendation: dict keyed by stringified `post_id`
- assertion contract:
  - first write creates the entry
  - second identical write is a no-op
  - original timestamp is preserved
  - full file text remains byte-for-byte unchanged on the second write

The test should not over-specify any larger cron subsystem behavior.

## 7. Baseline test command and expected delta

Current repo baseline measured on 2026-05-01 JST:

```bash
python3 -m unittest discover -s tests
```

Observed result:

- `Ran 1888 tests in 115.011s`
- `OK`

This repo's active baseline is `unittest`, not `pytest`.

Future impl-round expectation:

- baseline before impl: `1888/0`
- expected delta from `300-COST` v1: `+8 to +12 / 0`
- most likely shape:
  - new dedicated file: `+8`
  - existing regression adjustments: `0 to +4`

## 8. Impl-fire pre-capture checklist

Before any future `300-COST` implementation or deploy round, capture all of the following in the same handoff:

1. exact pre-300 guarded-publish image digest/SHA
2. exact pre-300 source HEAD commit
3. exact future revert target commit after impl commit lands
4. whether env rollback dimension is `n/a` or reintroduced
5. the intended test command set and expected pass count delta

Minimum future command set:

- `python3 -m unittest tests.test_guarded_publish_runner`
- `python3 -m unittest tests.test_guarded_publish_backlog_narrow`
- `python3 -m unittest tests.test_publish_notice_scanner`
- `python3 -m unittest tests.test_guarded_publish_runner_dedupe_idempotent`

## 9. POLICY §3.5 / §16.4 reuse block for the future impl prompt

### 9.1 Post-deploy verify 7-point (§3.5)

Future deploy prompt must carry these exact checks from `docs/ops/POLICY.md:164-176`:

1. image / revision
2. env / flag
3. mail volume
4. Gemini delta
5. silent skip
6. Team Shiny From
7. rollback target

### 9.2 Rollback 3 dimensions (§20.6 / §16.4 alignment)

Future impl prompt must spell out all three dimensions, even if one is `n/a`:

- code/source rollback
  - `git revert <bad_commit>`
- runtime image/revision rollback
  - `gcloud run jobs update guarded-publish --image=<pre_300_exact_sha>`
- env/flag rollback
  - `n/a` for current flag-less narrow spec
  - if a future env knob is reintroduced, refresh the pack before fire

## 10. Net

- `e14c944` narrow spec is directionally sufficient, but test scope needed one more layer of precision
- the real implementation target is narrower than "same post re-eval dedupe"; it is `unchanged backlog_only append suppression`
- local checked-out logs are not useful as golden fixtures for this ticket
- future impl round should stay inside `src/guarded_publish_runner.py` unless helper extraction is forced
- current recommendation remains `HOLD` until the already-recorded `298-v4` / `293-COST` gates turn green
