# BUG-003 WP status mutation read-only audit

更新日時: 2026-05-03 09:55 JST

## Finding

**AT_RISK**

- `publish_notice_scanner` / `publish_notice_cron_health` / `x_published_poster_trigger` から WordPress post status を変更するコードは見つからず、mail 到達そのものが `publish -> draft/private/trash` を起こす静的経路は確認できなかった。
- 一方で、`publish` へ上げる経路は central runner を通らない bypass が残っている。特に `src/rss_fetcher.py:finalize_post_publication()` は current mainline から live 実行される publish path で、`guarded_publish_runner` の backup / history / postcheck を経由しない。
- 直近24時間の local ledger/log (`2026-05-02 09:55:01+09:00` から `2026-05-03 09:55:01+09:00`) には status transition 記録が 0 件で、この workspace 上では recent live mutation の証拠は残っていない。
- `publish -> draft/private/trash` の mainline demotion path は静的には未検出。ただし `publish` 側 bypass があるため `CLEAN` ではない。

## Scope / method

- read-only inspection only
- code search target: `src/`
- ledger/log review target: `logs/guarded_publish_history.jsonl`, `logs/guarded_publish_yellow_log.jsonl`, `logs/guarded_publish_cleanup_log.jsonl`, `logs/publish_notice_queue.jsonl`, `logs/publish_notice_history.json`
- no code change in `src/` / `tests/`
- no WP REST GET/POST/PATCH/DELETE execution
- no deploy / no Gemini / no Cloud mutation

## Static inventory

Audit count:

- mutation-capable primitives audited: 4
- concrete caller / utility paths audited: 15
- total audited paths: 19

### Core primitives

| path | status effect | gate / guard review | classification | risk |
|---|---|---|---|---|
| `src/wp_client.py:_reuse_existing_post` | existing `draft/pending/future/auto-draft -> publish` when caller requested `publish` and title/source matched | no dedicated publish gate; status upgrade is hidden inside reuse helper; no guarded history append here | `SILENT_BYPASS` | high |
| `src/wp_client.py:create_post` | create new post with requested status; delegates to `_reuse_existing_post` on reuse hit | primitive only; caller decides whether this becomes direct publish or draft | `PRIMITIVE` | medium |
| `src/wp_client.py:create_draft` | create new `draft` or reuse existing draft-like post | searches only `draft/pending/future/auto-draft`; does not demote `publish` posts | `PRIMITIVE` | low |
| `src/wp_client.py:update_post_status` | arbitrary status update on `/posts/{id}` | primitive only; real callers audited separately below | `PRIMITIVE` | medium |

### Concrete caller paths

| path | status effect | gate / guard review | classification | risk |
|---|---|---|---|---|
| `src/guarded_publish_runner.py:run_guarded_publish` | `draft -> publish` | duplicate index on both `publish` and `draft`, preflight build, backup, cleanup verify, postcheck batch, history/yellow/cleanup ledgers | `GUARDED` | low |
| `src/rss_fetcher.py:_create_draft_with_same_fire_guard` | create `draft` | same-fire source/title guard, `allow_title_only_reuse=False`; uses `create_post(..., status="draft")` | `DRAFT_CREATE` | low |
| `src/rss_fetcher.py:finalize_post_publication` | `draft -> publish` | only inline `get_publish_skip_reasons()` + `_evaluate_publish_quality_guard()` checks before call; no `guarded_publish_runner` backup/history/postcheck | `BYPASS` | high |
| `src/x_api_client.py:cmd_collect` | create `draft` | `create_draft()` only; no publish | `DRAFT_CREATE` | low |
| `src/wp_draft_creator.py:process_url` | create `draft` | `create_draft()` only; no publish | `DRAFT_CREATE` | low |
| `src/tools/run_notice_fixed_lane.py:_create_notice_draft` | create `draft` | direct draft create; no publish transition | `DRAFT_CREATE` | low |
| `src/tools/run_notice_fixed_lane.py:_run_wp_post_dry_run` | create `draft`, then hard-delete probe post | canary-only probe; uses force delete after successful create | `CANARY_DELETE` | low |
| `src/data_post_generator.py:cmd_caught_stealing` | create `draft` or `publish` depending on CLI `--publish` | no guarded runner; publish can also trigger `_reuse_existing_post` implicit upgrade | `MANUAL_BYPASS` | medium |
| `src/data_post_generator.py:cmd_on_base` | create `draft` or `publish` depending on CLI `--publish` | same as above | `MANUAL_BYPASS` | medium |
| `src/manual_post.py:main` | create `publish` | manual CLI; bypasses guarded runner/history | `MANUAL_BYPASS` | medium |
| `src/sports_fetcher.py:main` | create `publish` | legacy/manual CLI; bypasses guarded runner/history | `MANUAL_BYPASS` | medium |
| `src/weekly_summary.py:main` | create `publish` | scheduled/manual weekly path; bypasses guarded runner/history | `MANUAL_BYPASS` | medium |
| `src/create_test_posts.py:TestPostCreator.create_posts` | create `draft` or `publish` test posts | test utility; bypasses guarded runner/history | `TEST_BYPASS` | low |
| `src/delete_test_posts.py:delete_posts` | force delete posts (`DELETE ... force=true`) | test cleanup only; no `trash` intermediate state | `TEST_DELETE` | low |
| `src/setup_phase1.py:step4_hide_top_page` | fixed page `publish -> private` | setup-time page mutation only; outside article-post scope | `PAGE_ONLY` | info |

### Non-mutation findings

- `src/publish_notice_scanner.py`: no `update_post_status`, no `update_post_fields(... status=...)`, no `requests.post(... /posts/{id})`, no `requests.delete(... /posts/{id})`
- `src/publish_notice_cron_health.py`: reads `/wp-json/wp/v2/posts` with `status=publish`, no write path
- `src/x_published_poster_trigger.py`: reads published posts only, no write path
- `src/move_old_articles.py`: updates categories only, not post status

## Path-by-path review

### 1. Active mainline guarded publish path

`src/guarded_publish_runner.py:run_guarded_publish` is the only article publish path that clearly satisfies the expected gate discipline:

- duplicate scan on both published and draft pools
- preflight / candidate refusal before mutation
- backup creation before live write
- cleanup verify before `publish`
- postcheck after write
- append to `guarded_publish_history.jsonl`
- append yellow / cleanup side ledgers on success

This path is not the suspected source of a silent demotion.

### 2. Active mainline bypass path

`src/server.py:_run_fetcher` launches `src/rss_fetcher.py` from Cloud Run mainline, and `README.md` documents the same runtime contract. Inside that path, `src/rss_fetcher.py:finalize_post_publication` calls `wp.update_post_status(post_id, "publish")` directly after local skip/quality checks.

What is missing compared with the guarded runner:

- no guarded history append
- no backup before publish
- no post-publish verification batch
- no central duplicate scan at publish time

This is not a `publish -> draft` path, but it is a live-capable status mutation bypass and therefore enough to fail `CLEAN`.

### 3. Implicit upgrade path inside reuse helper

`src/wp_client.py:_reuse_existing_post` upgrades an existing `draft/pending/future/auto-draft` to `publish` whenever a caller invokes `create_post(... status="publish")` and the title/source lookup reuses an existing post.

This matters because the status transition is not visible at the caller boundary:

- caller may look like “create a publish post”
- actual effect can be “promote an existing draft-like post to publish”
- no explicit `allow_status_upgrade` flag exists
- no guarded ledger is written from this helper

This is the clearest silent mutation helper in the current codebase.

### 4. Draft / reroll paths

Draft creation paths are materially safer:

- `create_draft()` searches only `draft/pending/future/auto-draft`
- `create_draft()` does not downgrade an existing `publish` post to `draft`
- `rss_fetcher._create_draft_with_same_fire_guard()` forces `status="draft"` and disables title-only reuse
- notice-lane and X-collect paths only create drafts

No static path was found that reverts a published article back to `draft`.

### 5. Trash / private / pending review

- `trash`: no article `trash` writer found in `src/`; only hard delete utilities (`delete_test_posts.py`, `run_notice_fixed_lane.py` canary delete) use `DELETE ... force=true`
- `private`: only `setup_phase1.py` mutates fixed pages to `private`; no article-post private mutation path found
- `pending`: no writer sets post status to `pending`; the string appears only in list filters and in `_reuse_existing_post()` / `create_draft()` reuse eligibility sets

## Ledger / log review

Review window:

- start: `2026-05-02 09:55:01+09:00`
- end: `2026-05-03 09:55:01+09:00`

### Last 24h result

| file | last 24h rows | note |
|---|---:|---|
| `logs/guarded_publish_history.jsonl` | 0 | no local runner evidence in window |
| `logs/guarded_publish_yellow_log.jsonl` | 0 | no yellow publish evidence in window |
| `logs/guarded_publish_cleanup_log.jsonl` | 0 | no cleanup publish evidence in window |
| `logs/publish_notice_queue.jsonl` | 0 | no local mail queue evidence in window |

Conclusion for the requested 24h review:

- this workspace contains **no local evidence** of a status transition in the last 24h
- therefore there is also no local evidence here that a mail send coincided with a recent `publish -> draft/private/trash` mutation

### Last available local evidence snapshot

| file | min ts | max ts | notable counts |
|---|---|---|---|
| `logs/guarded_publish_history.jsonl` | `2026-04-26T10:23:30.081474+09:00` | `2026-04-26T17:45:10.549798+09:00` | `sent=68`, `skipped=38`, `refused=98` |
| `logs/guarded_publish_yellow_log.jsonl` | `2026-04-26T10:23:30.081474+09:00` | `2026-04-26T17:45:10.549798+09:00` | 68 success-side yellow rows |
| `logs/guarded_publish_cleanup_log.jsonl` | `2026-04-26T10:23:30.081474+09:00` | `2026-04-26T17:45:10.549798+09:00` | 68 cleanup rows |
| `logs/publish_notice_queue.jsonl` | `2026-04-26T11:15:09.434432+09:00` | `2026-04-26T18:15:11.349208+09:00` | `queued=82`, `sent=88` |

Additional checks on the available historical ledgers:

- no `status` values `draft`, `private`, `trash`, or `pending` appeared in these files
- 31 `post_id`s had multiple guarded-publish rows, but `sent -> non-sent` reversion count was `0`
- `publish_notice_queue.jsonl` had `queued` rows that all eventually reached `sent`; `queued-only without sent` count was `0`
- 14 mail `sent` post_ids were not present in `guarded_publish_history.jsonl`, but all 14 are earlier than the guarded-history window (`2026-04-25 19:47` to `2026-04-26 08:50`), so the local files do not show a contradiction

## Verdict logic

- `CLEAN` not met
  - reason: 7 publish-side bypass / silent-upgrade paths remain
- `CONTAMINATED` not met
  - reason: no confirmed recent live demotion, no `sent -> non-sent` reversion in available ledger, no mail-path writer found
- final verdict: **AT_RISK**

## Narrow fix subtasks inside BUG-003

1. Route mainline `rss_fetcher` publish through a single guarded status-mutation helper.
   - Minimum acceptance: `src/rss_fetcher.py:finalize_post_publication()` no longer calls `update_post_status()` directly.
   - Required evidence: backup/history/postcheck parity with `guarded_publish_runner`.

2. Remove or make explicit the implicit status upgrade in `src/wp_client.py:_reuse_existing_post`.
   - Minimum acceptance: draft-like reuse does not become `publish` unless caller opts in with an explicit flag.
   - Required evidence: caller-by-caller review of `manual_post`, `weekly_summary`, `sports_fetcher`, `data_post_generator`.

3. Fence manual/test publish utilities from autonomous runtime.
   - Minimum acceptance: direct-publish utilities are clearly manual-only or excluded from live runtime image/entrypoint contracts.
   - Required evidence: read-only runtime map showing which entrypoints remain live-capable.

## Claude handoff

- No static evidence supports “mail arrival itself mutated published posts back to non-public”.
- The strongest repo-level risk is not demotion but **publish-side bypass** in active mainline plus implicit status upgrade in the WP client reuse helper.
- Recommended next decision: keep BUG-003 as narrow follow-up work, not P0/P1 contamination escalation, unless new live evidence outside this workspace shows actual `publish -> draft/private/trash`.
