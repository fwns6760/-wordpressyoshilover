# 2026-05-04 Lane LL 64424 revert actor identification + Lane GG extension

作成: 2026-05-04 JST

## scope

- lane: `LL`
- target family: `BUG-003`
- primary pivot: `post_id=64424`
- repo write scope used:
  - `src/wp_client.py`
  - `src/wp_revert_audit_ledger.py`
  - `tests/test_wp_client.py`
  - `doc/active/assignments.md`
  - `docs/handoff/codex_responses/2026-05-04_lane_LL_64424_revert_actor.md`
- untouched on purpose:
  - `src/publish_notice_*.py`
  - `src/draft_body_editor*`
  - `src/rss_fetcher.py`
  - Cloud Run / Scheduler / Secret / env live mutation

## verdict

- `64424` について、repo-visible evidence では **publish -> draft/private/trash revert は確認できない**。
- 確認できた actor は **`publish_notice_scanner.scan()` の direct-publish path が phantom publish marker を seed したこと**。
- current `draft` は revert 後状態ではなく、fetcher が最初に作った `draft` のままという解釈が最も強い。
- したがって `64424` は **Lane GG hardening miss ではない**。
- ただし repo 側で将来の本物 `publish -> draft/private` を止める narrow hardening は入れた。

## Step 1: 64424 chronology

### exact timeline (JST)

| ts | source | evidence | judgment |
|---|---|---|---|
| `2026-05-04 07:35:41.641` | `yoshilover-fetcher` | `[WP] 記事draft post_id=64424 ...` | first visible state is `draft` |
| `2026-05-04 07:35:42.832` | `yoshilover-fetcher` | `[下書き止め] post_id=64424 reason=draft_only` | fetcher did not publish |
| `2026-05-04 07:35:43.113` | `yoshilover-fetcher` | `[下書き維持] post_id=64424 reason=draft_only image=あり` | state kept `draft` |
| `2026-05-04 07:40:41.515-518` | `guarded-publish` | execution `guarded-publish-cvj8c` contains `post_id=64424` | later durable row is hold / not publish |
| `2026-05-04 07:46:03.608` | `publish-notice` | `publish_notice_24h_budget_demoted` / `notice_class=guarded_review` / `post_id=64424` | mail classifier treated it as review-like |
| `2026-05-04 07:46:03.747` | `publish-notice` | `[result] kind=per_post post_id=64424 status=suppressed reason=PUBLISH_ONLY_FILTER subject='【要確認】...'` | phantom publish-scan result, not publish confirmation |

### durable state evidence

- `guarded_publish_history.jsonl`: no `status=sent` row for `64424`
- `guarded_publish_yellow_log.jsonl`: no success-side publish row for `64424`
- `guarded_publish_cleanup_log.jsonl`: no cleanup publish row for `64424`
- `publish_notice/history.json`: key `64424` exists with `2026-05-04T07:45:37.045732+09:00`
- `publish_notice/queue.jsonl`: `post_id=64424`, `status=suppressed`, `reason=PUBLISH_ONLY_FILTER`, `publish_time_iso=2026-05-04T07:35:41+09:00`

### code-level meaning of `publish_time_iso`

- `src/publish_notice_scanner.py:_request_from_post()` sets `publish_time_iso` from `post.date`
- `scan()` then writes `next_history[post_id] = request.publish_time_iso`
- therefore `publish_notice/history.json` for `64424` is a **scanner-side timestamp proxy**, not proof of a publish write

### missing evidence

- direct WP REST `/posts/64424?context=edit` and `/revisions` re-check was not possible from this sandbox because outbound DNS to `yoshilover.com` failed
- because of that, no authenticated revision author / revision timestamp proof was obtainable here

## Step 2: same-pattern audit

### narrow current-day family

The same state-drift family is already visible in repo evidence for:

| post_id | repo-visible state | drift shape |
|---|---|---|
| `64424` | fetcher `draft_only`, guarded non-`sent`, notice suppressed | direct publish marker seeded although no guarded publish success exists |
| `64437` | guarded `skipped backlog_only`, current public `404` in prior ledger | notice queue/history stamped it as published |
| `64447` | guarded `skipped backlog_only`, current public `404` in prior ledger | notice queue/history stamped it as published |
| `64416` | fetcher `draft_only`, guarded `refused`, notice surfaced/suppressed | same phantom publish marker family in prior GG audit |

### broader prior audit reference

Prior read-only audits in this repo already showed the larger pattern:

- `docs/ops/bug003_bug004_291_status_revert_broad_audit.md`
  - broad upper-bound `146`
  - queue-surfaced numeric subset `20`
  - fresh same-day first-observed non-sent subset `3`
- `docs/ops/bug003_wp_status_mutation_audit.md`
  - no static repo path was found that demotes published article posts back to `draft`

Interpretation:

- the visible recurring problem is **publish marker / notify drift**, not repo-proven `publish -> draft/private/trash`
- the old user hypothesis “mail arrival causes non-publish mutation” remains unsupported by repo-visible timing

## Step 3: actor finding

### 64424 concrete actor

Best-supported actor for the observed anomaly:

1. `publish_notice_scanner.scan()` fetched the post from the direct publish scan path
2. it seeded `publish_notice/history.json` and `queue.jsonl` using `post.date`
3. `publish_notice_email_sender.send()` then classified the request as review-like and suppressed it with `PUBLISH_ONLY_FILTER`

This explains all repo-visible facts for `64424` **without requiring any publish->draft revert**.

### what was ruled out

- `yoshilover-fetcher`: explicit `draft_only`, not a publisher here
- `guarded-publish`: no `sent`, no cleanup publish success, no `wp_publish_status_guard_publish_write` event for `64424`
- repo static search: no article-runtime writer was found that sets published posts back to `draft/private/trash`

### what remains unproven

- a WP-side manual/plugin/external actor could still exist for other incidents, but `64424` itself is not repo-proven as such a revert case
- exact WordPress revision author/timestamp cannot be proven from this sandbox due the DNS block above

## Step 4: implemented narrow fix

### goal

Even though `64424` was not a true revert, repo-owned future attempts to move published posts back to `draft/private` should be auditable and blockable.

### implementation

Added a new default-OFF guard in `WPClient`:

- new module: `src/wp_revert_audit_ledger.py`
- new env flags:
  - `ENABLE_WP_REVERT_AUDIT_LEDGER=1`
  - `ENABLE_WP_PUBLISHED_REVERT_GUARD=1`
  - optional path override: `WP_REVERT_AUDIT_LEDGER_PATH`

Behavior:

- when repo code calls `WPClient.update_post_status(..., "draft"|"private"|"trash")` or `update_post_fields(status=...)`
- and current live post status probes as `publish`
- then:
  - append structured JSONL audit row
  - if target is `draft` or `private` and `ENABLE_WP_PUBLISHED_REVERT_GUARD=1`, raise and block the mutation
  - if target is `trash`, audit only and allow the write

Why `trash` is audit-only:

- user goal was “published posts should not be silently returned to `draft/private`”
- keeping `trash` as audit-only avoids breaking legitimate cleanup/delete operations by default

## Step 5: tests

Executed:

```bash
python3 -m unittest tests.test_wp_client
python3 -m unittest tests.test_guarded_publish_runner
```

Results:

- `tests.test_wp_client`: `33` passed
- `tests.test_guarded_publish_runner`: `101` passed

Coverage added:

- positive:
  - publish -> draft attempt is audited
  - publish -> draft attempt is blocked when guard flag is ON
- negative:
  - publish -> trash remains allowed and is audit-only
- regression:
  - with both flags OFF, no status probe or ledger write happens

## Step 6: live apply plan

Status: `plan only`

Reason:

- this sandbox cannot complete authenticated live WP verification against `yoshilover.com`
- no Cloud Run image build / env apply was executed in this lane

If Claude/authenticated executor wants runtime enablement later:

1. rebuild `yoshilover-fetcher`
2. rebuild `guarded-publish`
3. optionally enable audit only first:
   - `ENABLE_WP_REVERT_AUDIT_LEDGER=1`
4. only after observing safe audit output, enable hard block:
   - `ENABLE_WP_PUBLISHED_REVERT_GUARD=1`

`publish-notice` was intentionally untouched in this lane.

## rollback

- source rollback: revert this lane commit
- runtime rollback for future enablement:
  - remove `ENABLE_WP_REVERT_AUDIT_LEDGER`
  - remove `ENABLE_WP_PUBLISHED_REVERT_GUARD`

## final judgment on 64424 rescue

- `64424` should **not** be “re-published as a rescue action” from this lane
- reason:
  - the post is a review-stop row with `review_date_fact_mismatch_review`
  - the evidence does not show a lost publish that needs restoration
  - the observed incident is a notify-state drift, not a publish-state revert
