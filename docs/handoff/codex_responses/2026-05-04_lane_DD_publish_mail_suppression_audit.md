# 2026-05-04 Lane DD publish mail suppression audit

作成: 2026-05-04 JST  
scope: read-only audit + design only  
write scope used: `docs/handoff/codex_responses/2026-05-04_lane_DD_publish_mail_suppression_audit.md` only

## method

- repo read-only inspection:
  - `src/publish_notice_email_sender.py`
  - `src/publish_notice_scanner.py`
  - `tests/test_publish_notice_email_sender.py`
- Cloud Logging read-only inspection:
  - `publish-notice`
  - `guarded-publish`
  - `guarded-publish-manual-single`
- direct WordPress REST re-check from this sandbox was not possible because outbound DNS to `yoshilover.com` failed.
- for rows marked `*`, the publish timestamp is reconstructed from guarded-publish live evidence already recorded in repo docs or from the `cleanup_backup` filename seen in Cloud Logging.

## Step 1-2 outcome table

### target 11 posts

| post_id | publish 時刻 JST | publish-notice 受信 timestamp JST | status | reason | subject prefix |
| --- | --- | --- | --- | --- | --- |
| `64272` | `2026-05-03 19:05:39*` | `2026-05-03 19:11:10.576` | `sent` | `-` | `【要確認】` |
| `64294` | `2026-05-03 21:25:37*` | `2026-05-03 21:31:04.772` | `sent` | `-` | `【要確認】` |
| `64238` | `2026-05-03 22:40:40*` | `2026-05-03 22:46:11.331` | `sent` | `-` | `【要確認】` |
| `64361` | `2026-05-04 00:10:45.437` | `2026-05-04 00:16:03.093` | `sent` | `-` | `【要確認・X見送り】` |
| `64382` | `2026-05-04 00:30:43.711` | `2026-05-04 00:36:05.059` | `sent` | `-` | `【要確認】` |
| `64386` | `2026-05-03 19:34:21` | `2026-05-03 19:36:33.508` and `19:37:41.572` | `sent x2` | `overlap between manual and scheduler executions` | `【要確認】` |
| `64394` | `2026-05-03 19:34:19` | `2026-05-03 19:36:31.963` and `19:37:39.164` | `sent x2` | `overlap between manual and scheduler executions` | `【要確認】` |
| `64396` | `2026-05-03 19:05:39*` | `2026-05-03 19:11:09.070` | `sent` | `-` | `【要確認】` |
| `64402` | `2026-05-03 19:55:38*` | `2026-05-03 20:01:14.545` | `sent` | `-` | `【緊急】` |
| `64405` | `2026-05-03 20:05:39*` | `2026-05-03 20:11:02.091` | `sent` | `-` | `【要確認】` |
| `64366` | `2026-05-03 15:50:41` | `2026-05-03 15:55:58.607` | `suppressed` | `PUBLISH_ONLY_FILTER` | `【要確認・X見送り】` |

### summary

- target 11 aggregate:
  - `sent`: `8`
  - `sent x2`: `2` (`64386`, `64394`)
  - `suppressed`: `1` (`64366`)
  - `errors`: `0`
- within the target 11, no row was suppressed by `BACKLOG_SUMMARY_ONLY`.
- however, current live behavior still suppresses already-published posts by `BACKLOG_SUMMARY_ONLY`; see the additional exemplar below.

### additional live exemplar outside the 11

| post_id | publish 時刻 JST | publish-notice 受信 timestamp JST | status | reason | subject prefix |
| --- | --- | --- | --- | --- | --- |
| `64416` | `2026-05-04 05:15:39*` | `2026-05-04 05:21:07.430` | `suppressed` | `BACKLOG_SUMMARY_ONLY` | `【公開済】` |

- `64416` is the cleanest proof that the current runtime can still suppress a real published post even after the `PUBLISH_ONLY_FILTER` direct-publish bypass was restored.

## Step 3 root cause

### 1. direct publish scan does not carry an explicit non-backlog exemption

- scanner direct-publish path creates `PublishNoticeRequest` with `notice_origin="direct_publish_scan"` and `publish_time_iso`, but no explicit `is_backlog=False` or publish-status exemption marker:
  - `src/publish_notice_scanner.py:1383-1390`
- the direct-publish scan also queues a provisional subject using `build_subject(request.title)` before sender-side classification:
  - `src/publish_notice_scanner.py:2749-2757`
- consequence:
  - queue rows can look like `【公開済】...` even when the final sender result is reclassified to `【要確認】` or `【要確認・X見送り】`.
  - `64366` is the concrete example: repo docs recorded queued subject `【公開済】...`, but Cloud Logging result row shows final sender subject `【要確認・X見送り】...`.

### 2. sender applies direct-publish bypass only to `PUBLISH_ONLY_FILTER`, not to backlog suppression

- sender order is:
  1. classify the mail and build the final subject
  2. run `_should_suppress_publish_only_mail(...)`
  3. run `BURST_SUMMARY_ONLY`
  4. resolve backlog by history lookup
  5. suppress with `BACKLOG_SUMMARY_ONLY` if backlog
- relevant code:
  - `src/publish_notice_email_sender.py:1694-1716`
  - `src/publish_notice_email_sender.py:2186-2212`
- `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS` only exempts:
  - `notice_kind == "publish"`
  - `notice_origin == "direct_publish_scan"`
  - from `PUBLISH_ONLY_FILTER`
- it does **not** exempt the same request from `_resolve_is_backlog(...)` followed by `BACKLOG_SUMMARY_ONLY`.

### 3. backlog state is inherited from guarded history by post_id lookup

- `_resolve_is_backlog(...)` falls back to the latest guarded-publish history row for that `post_id` when `request.is_backlog` is unset:
  - `src/publish_notice_email_sender.py:465-479`
- once the latest guarded row has `is_backlog=true`, a later direct-publish scan of the already-published post can still be suppressed as backlog even though the live WP status is now `publish`.
- `64416` matches this failure mode:
  - sender subject is `【公開済】...`
  - result is `suppressed`
  - reason is `BACKLOG_SUMMARY_ONLY`

### 4. there is also an intentional synthetic backlog path that must not be broken

- scanner 24h budget governor can intentionally transform requests into summary-only proxies:
  - `src/publish_notice_scanner.py:2441-2467`
  - `src/publish_notice_scanner.py:2470-2504`
- those synthetic requests set:
  - `is_backlog=True`
  - `notice_kind="publish"`
  - `record_type="24h_budget_summary_only"`
- therefore a naive rule like "if `notice_kind == publish`, never suppress backlog" is unsafe, because it would also break the intentional budget-governor summary-only path.

### 5. live env flags relevant to this behavior

Live `publish-notice` job env confirmed by `gcloud run jobs describe publish-notice`:

- `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1`
- `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1`
- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL=1`
- `ENABLE_PUBLISH_NOTICE_CLASS_RESERVE=1`
- `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR=1`
- `ENABLE_289_POST_GEN_VALIDATE_DIGEST=1`
- `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
- `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`
- unset in live env, so code defaults apply:
  - review cap: `10` (`src/publish_notice_scanner.py:34-35`)
  - review window: `24h` (`src/publish_notice_scanner.py:34-35`)
  - budget thresholds: `80 / 95 / 100` (`src/publish_notice_scanner.py:42-47`)

### 6. tests confirm the current contract

- direct-publish review subject is suppressed when bypass is off:
  - `tests/test_publish_notice_email_sender.py:1399-1422`
- direct-publish review subject is sent when bypass is on:
  - `tests/test_publish_notice_email_sender.py:1424-1446`
- direct-publish publish subject is sent regardless of bypass:
  - `tests/test_publish_notice_email_sender.py:1448-1473`
- backlog rows are intentionally suppressed today:
  - `tests/test_publish_notice_email_sender.py:1537-1570`

## Step 4 design proposal

### comparison

|案|概要|安全性|mail volume 影響|主な risk|impl 工数|live mutation|
|---|---|---|---|---|---|---|
|`A`|sender に `BACKLOG_SUMMARY_ONLY` bypass を追加。条件は `notice_kind=publish` + `notice_origin=direct_publish_scan` + `record_type != 24h_budget_summary_only`|高|低。実 publish の direct-scan backlog だけ増える|`direct_publish_scan` marker に依存。別 origin の将来 caller には効かない|小|この Lane ではなし|
|`B`|`PublishNoticeRequest` に explicit publish-status flag を追加し、sender は `status=publish` を見て backlog suppress を skip|中|中。publish status を正しく運べれば user policy に最も素直|request schema 追加が必要。scanner / tests / synthetic summary-only path の切り分けをミスると 24h budget governor を壊す|中|この Lane ではなし|
|`C`|scanner 側で publish 済み row を per-post 強制扱いにして sender backlog 判定に入れない|低-中|中-高。scanner semantics を変えるため影響面が広い|queue/history/class reserve/budget governor との整合が崩れやすい。observability も変わる|中-大|この Lane ではなし|

### recommended

`A` を推奨。

理由:

- 既存の Lane G pattern をそのまま backlog suppression に拡張する形で、最小変更で live mismatch を止められる。
- `record_type="24h_budget_summary_only"` を明示的に除外すれば、budget governor の intentional summary-only path を守れる。
- scanner contract を増やさず sender 内の narrow helper で完結でき、既存 test 追加も素直。
- `64416` 型の published-but-backlog-suppressed incident を止めるには十分で、`64366` のような pre-fix `PUBLISH_ONLY_FILTER` suppress replay とは干渉しない。

### recommended shape

- add helper in sender, e.g. `_should_bypass_backlog_summary_only(request)`
- return `True` only when:
  - `notice_kind == "publish"`
  - `notice_origin == "direct_publish_scan"`
  - `record_type != "24h_budget_summary_only"`
- wire it immediately before `if not review_only_notice and is_backlog:`
- add tests for:
  - direct-publish + backlog + publish subject => `sent`
  - direct-publish + backlog + review subject => `sent`
  - `24h_budget_summary_only` => still `BACKLOG_SUMMARY_ONLY`
  - non-direct backlog rows => still `BACKLOG_SUMMARY_ONLY`

## Step 5 unsent published list

### from the target 11

| post_id | publish 時刻 JST | suppression reason | replay candidate value |
| --- | --- | --- | --- |
| `64366` | `2026-05-03 15:50:41` | `PUBLISH_ONLY_FILTER` | `high` |

Why `64366` is worth replay:

- the post is already published.
- the only observed mail outcome is pre-fix suppression.
- current live env now has `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`, so a replay after code-neutral queue re-entry would likely deliver.
- expected subject on replay, under current classifier, is still likely `【要確認・X見送り】...`, not necessarily `【公開済】...`.

### additional non-target replay candidate

| post_id | publish 時刻 JST | suppression reason | replay candidate value |
| --- | --- | --- | --- |
| `64416` | `2026-05-04 05:15:39*` | `BACKLOG_SUMMARY_ONLY` | `highest` |

Why `64416` matters more than `64366` for the fix lane:

- it reproduces the **current** spec mismatch after the direct-publish filter bypass was already restored.
- subject is already `【公開済】`, so this is the clearest published-post backlog bug.
- it is the best regression fixture for Lane EE if the repo fix is implemented next.

## next action

Recommended user action: `go` for a narrow Lane EE repo fix based on proposal `A`, plus a separate replay decision pack for `64366` and `64416`.

Suggested EE scope:

- code:
  - `src/publish_notice_email_sender.py`
  - targeted tests in `tests/test_publish_notice_email_sender.py`
- non-goals:
  - no env change
  - no scheduler change
  - no mail replay in the same implementation ticket
  - no scanner contract change unless `A` is rejected

Suggested replay order after the fix is deployed and observed:

1. `64416` first: best regression proof for `BACKLOG_SUMMARY_ONLY` bypass
2. `64366` second: cleanup of the one missed published post from the target 11
