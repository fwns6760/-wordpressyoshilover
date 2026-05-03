# 291 publish-only mail audit

| field | value |
|---|---|
| ticket | BUG-004+291 subtask-6 |
| date | 2026-05-03 JST |
| mode | read-only audit before impl |
| scope | publish-notice normal Gmail path only |

## 1. function / path inventory

### runner entry

- `src/cloud_run_persistence.py:23`
  - Cloud Run publish-notice job runner is `src.tools.run_publish_notice_email_dry_run`.
- `src/tools/run_publish_notice_email_dry_run.py:228-315`
  - `--scan` path calls `scan(...)`, then loops `result.emitted` and calls `send(...)` once per request.
  - after each `send(...)`, it always appends queue/send result via `append_send_result(...)`.
  - it also mirrors the result to durable runner ledger via `_emit_notice_ledger(...)`.
  - summary mail is a separate path via `send_summary(...)`.

### request assembly

- `src/publish_notice_scanner.py:2684-3035`
  - `scan()` merges 4 sources into one per-post send loop:
  - published WP posts (`publish`)
  - guarded publish review / hold (`scan_guarded_publish_history`)
  - `post_gen_validate` skip ledger (`scan_post_gen_validate_history`)
  - `preflight_skip` skip ledger (`scan_preflight_skip_history`)
  - after merge, scanner still applies:
  - 24h budget governor (`evaluate_24h_budget_state` + `_apply_24h_budget_governor`)
  - 289 digest transform (`evaluate_289_digest_state` + `apply_289_digest`)
  - scanner writes queue-visible rows before send:
  - published posts at `scan():2741-2749`
  - selected review / skip / digest rows at `_append_selected_review_queue_logs():2665-2671`

### final subject / Gmail send gate

- `src/publish_notice_email_sender.py:1657-1703`
  - `send(...)` derives the final mail class with `_classify_mail(...)`.
  - `notice_kind=publish` is not sufficient to know the final subject:
  - published posts can still become `【要確認】...` or `【投稿候補】...` after classification.
  - therefore the narrow filter condition must sit after final subject resolution, not on raw `notice_kind` alone.
- `src/publish_notice_email_sender.py:2114-2165`
  - per-post Gmail delivery is centralized in `send(...)`.
  - this is the only place that can suppress diagnostics without breaking scanner queue / history / digest generation.

## 2. local artifact snapshot

- local `logs/publish_notice_queue.jsonl` / `logs/publish_notice_history.json` / `logs/guarded_publish_history.jsonl` are present.
- local `logs/post_gen_validate_history.jsonl` / `logs/preflight_skip_history.jsonl` / `logs/publish_notice_24h_budget_history.jsonl` are absent in this sandbox snapshot.
- local queue / guarded history timestamps stop at `2026-04-30 13:27 JST`; no local evidence newer than that exists here.

### local queue count snapshot

- `logs/publish_notice_queue.jsonl`
  - `queued:publish = 82`
  - `sent:publish = 82`
  - `sent:summary = 6`
  - diagnostic prefixes are not present in this local queue copy
- last 24h sent count from local queue, using `now=2026-05-03 00:00 JST`
  - total sent = `0`
  - publish = `0`
  - real_review = `0`
  - guarded_review = `0`
  - old_candidate = `0`
  - post_gen_validate = `0`
  - preflight_skip = `0`
  - post_gen_validate_digest = `0`

### local guarded history snapshot

- `logs/guarded_publish_history.jsonl`
  - total rows = `204`
  - `status=sent = 68`
  - `status=refused = 98`
  - `status=skipped = 38`
  - top `hold_reason`
  - `hard_stop_injury_death = 70`
  - empty / publish path = `68`
  - `burst_cap = 27`
  - `cleanup_failed_post_condition = 13`
  - `daily_cap = 11`
- this confirms durable review/hold evidence exists even when normal Gmail is later filtered.

## 3. mail class audit

| mail class | normal Gmail path today | durable ledger / log path | digest path | local last24h normal Gmail sent | audit note |
|---|---|---|---|---:|---|
| `publish` | yes. `scan()` emits published WP posts, runner calls `send(...)` | queue (`publish_notice_queue.jsonl`), duplicate history (`publish_notice_history.json`), runner ledger | no diagnostic digest; separate publish burst summary only | 0 | keep under flag ON |
| `real_review` | yes. `scan_guarded_publish_history()` -> `send(...)` | `guarded_publish_history.jsonl` + queue + runner ledger | no | 0 | suppress under flag ON |
| `guarded_review` | yes. same as above | `guarded_publish_history.jsonl` + queue + runner ledger | no | 0 | suppress under flag ON |
| `old_candidate` | yes. same as above | `guarded_publish_history.jsonl` + old-candidate ledger + queue + runner ledger | no | 0 | suppress under flag ON |
| `post_gen_validate` | yes. `scan_post_gen_validate_history()` -> `send(...)` | `post_gen_validate_history.jsonl` + queue + runner ledger | yes. `apply_289_digest(...)` can replace overflow per-post mail | 0 | suppress per-post under flag ON; ledger/digest stay |
| `preflight_skip` | yes. `scan_preflight_skip_history()` -> `send(...)` | `preflight_skip_history.jsonl` + queue + runner ledger | no dedicated digest in current code | 0 | suppress per-post under flag ON |
| `post_gen_validate_digest` | yes today because digest request also goes through `send(...)` | queue + runner ledger, source rows remain in `post_gen_validate_history.jsonl` | this row *is* the digest path | 0 | suppress from normal Gmail under flag ON |
| `24h_budget_summary_only` proxy | no per-post delivery; sender already suppresses backlog/burst summary only | budget ledger + queue | summarized through batch summary path | 0 | out of scope; unchanged |

## 4. filter condition conclusion

### why raw `notice_kind` is too broad

- `notice_kind=publish` only means "came from published-post scan".
- final subject is decided later by `_classify_mail(...)` + `build_subject(...)`.
- a published post can still become:
  - `【要確認】...`
  - `【投稿候補】...`
  - `【要確認・X見送り】...`
- if the filter used `notice_kind == "publish"` only, these non-`【公開済】` mails would still reach normal Gmail and would violate the user instruction.

### narrow filter to implement

- keep only per-post mail whose final subject starts with `【公開済】`
- suppress every other per-post subject with:
  - `status=suppressed`
  - `reason=PUBLISH_ONLY_FILTER`
- do **not** remove scanner queue/history/digest generation
- do **not** change:
  - `post_gen_validate_history`
  - `preflight_skip_history`
  - `guarded_publish_history`
  - 289 digest transform
  - runner ledger mirror

## 5. implementation boundary selected from audit

- primary hook: `src/publish_notice_email_sender.py:send(...)`
  - only place with final subject and final mail classification
  - preserves existing scanner queue/history writes
  - produces the required dry-run / send result line: `status=suppressed reason=PUBLISH_ONLY_FILTER`
- scanner-side addition is limited to a coarse helper / audit-visible classification preview so the repo still has an explicit publish-only class notion without moving durable ledger ownership away from current scan paths.
