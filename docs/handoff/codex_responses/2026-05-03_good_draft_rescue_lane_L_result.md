# 2026-05-03 Good Draft Rescue Lane L result

## mode

- live ops request received for fixed target set `64346 / 64335 / 64328 / 64311 / 64294 / 64272`
- execution status: STOP before Step 4 live re-eval
- mutation status: no live mutation performed
- scope guard: no rescue target outside the fixed 6 was processed
- `64278` was checked read-only only to confirm HOLD/manual_review reason; it was not treated as a rescue target

## stop reason

Lane L can only proceed to Step 4 if both of the following are true:

1. per-id gate check is clear or widgets.js-only duplicate is safely reconstructable
2. live runner can reach WordPress for preflight / publish / verify

This sandbox failed both required live prerequisites:

- `64346` could not be deterministically reconstructed from the available local log mirrors, so Step 3 failed for that ID
- live WordPress access is unavailable from this sandbox, so Step 4 and Step 6 cannot be executed safely for any ID

Direct sandbox check:

```text
RuntimeError
[WP] request failed after 4 attempts (記事取得 post_id=64335): ConnectionError(... Failed to establish a new connection: [Errno -2] Name or service not known)
```

Relevant code paths require live WP access:

- `src/guarded_publish_runner.py:2152-2167` postcheck calls `wp_client.get_post(post_id)`
- `src/guarded_publish_runner.py:2265-2269` live runner instantiates `WPClient()`
- `src/guarded_publish_runner.py:2779-2805` live path backs up the current post and then calls `update_post_fields(... status="publish")` or `update_post_status(..., "publish")`

Result: safe action is `mutation 0` plus record only.

## authoritative read-only inputs used

- latest available local mirror of guarded publish history: `/tmp/lane_i_live_20260503T175449/guarded_publish_history.jsonl`
- secondary mirror for cross-check: `/tmp/lane_i_probe_20260503T172712/guarded_publish_history.jsonl`
- older audit mirror: `/tmp/guarded_publish_history_20260503_audit.jsonl`
- evaluator snapshot: `/tmp/good_draft_rescue_eval_20260503.json`
- publish-notice queue audit snapshot: `/tmp/publish_notice_queue_20260503_audit.jsonl`
- Cloud Logging export mirror: `/tmp/gcloud-config-dkatcxfx/gcloud/logs/2026.05.03/`

Note: this session could not re-download GCS or query live WP/Cloud Run because network access is restricted in the current sandbox. All Step 1 findings below are from the latest available local mirrors captured earlier on 2026-05-03.

## step 1 latest history check

| post_id | latest ts (JST) | status | hold_reason | freshness_source | duplicate_of_post_id | candidate_source_url_hash | duplicate_target_source_url | WP REST |
|---|---|---|---|---|---:|---|---|---|
| 64346 | `2026-05-03T14:10:37.184961+09:00` | refused | `review_duplicate_candidate_same_source_url` | `created_at` | 64299 | `176756fe6e5a7d6f` | `https://platform.twitter.com/widgets.js` | unverified |
| 64335 | `2026-05-03T13:20:37.462565+09:00` | refused | `review_duplicate_candidate_same_source_url` | `created_at` | 64299 | `176756fe6e5a7d6f` | `https://platform.twitter.com/widgets.js` | unverified |
| 64328 | `2026-05-03T12:36:22.947307+09:00` | refused | `review_duplicate_candidate_same_source_url` | `created_at` | 64297 | `176756fe6e5a7d6f` | `https://platform.twitter.com/widgets.js` | unverified |
| 64311 | `2026-05-03T09:45:37.678896+09:00` | refused | `review_duplicate_candidate_same_source_url` | `source_date` | 64297 | `(null)` | `(null)` | unverified |
| 64294 | `2026-05-02T21:25:37.545642+09:00` | refused | `review_duplicate_candidate_same_source_url` | `source_date` | 64206 | `(null)` | `(null)` | unverified |
| 64272 | `2026-05-02T19:00:41.761618+09:00` | refused | `review_duplicate_candidate_same_source_url` | `created_at` | 64206 | `(null)` | `(null)` | unverified |

Scope confirmation:

- only the fixed 6 rescue targets were evaluated for Lane L
- `64278` remained out of scope
- no evidence was used to expand the target set to `64333` / `64341` or any other ID

## step 2 gate evaluation and step 3 reconstruction result

| post_id | title / subtype / category estimate | source reconstruction result | gate result | Step 4 re-eval | verdict |
|---|---|---|---|---|---|
| 64346 | `巨人スタメン RT 極トラ・プレミアム（日刊スポーツ）: 【阪神` / `lineup` / `repairable` | failed; only same-hash widgets.js duplicate cluster evidence was recovered, no deterministic `source_url` or body metadata from local logs | widgets.js-only duplicate, freshness clear, no hard stop flags in evaluator; but reconstruction incomplete | not run | unreconstructable |
| 64335 | `巨人スタメン 甲子園 スタメン 【巨人】 【阪神】 4吉川 7高` / `lineup` / `repairable` | success; `title_template_selected` + `media_xpost_embedded` recovered `https://twitter.com/hochi_giants/status/2050791476620296421` | widgets.js-only duplicate; freshness clear; no hard stop flags in evaluator | not run because WP REST unreachable in sandbox | draft 維持 |
| 64328 | `【巨人】主力続々カムバック 泉口友汰＆山崎伊織が実戦復帰 ４番はリチャード……` / `roster` / `repairable` | success; `title_template_selected` recovered `https://twitter.com/hochi_giants/status/2050780711846617128` | widgets.js-only duplicate; freshness clear; no hard stop flags in evaluator | not run because WP REST unreachable in sandbox | draft 維持 |
| 64311 | `阿部「野球って不思議だな」 関連発言` / `comment` / `repairable` | success; `media_xpost_embedded` recovered `https://twitter.com/hochi_giants/status/2050667568357069237` | publish不可: duplicate target is not widgets.js and evaluator also marks `backlog_only=true` with stale-for-breaking-board freshness | not run | draft 維持 |
| 64294 | `ドラ５・小浜佑斗が自身初の甲子園で貴重なタイムリー！ 「どんな形でもいい。な…` / `notice` / `repairable` | partial only; cleanup heading recovered `【巨人】ドラ５・小浜佑斗が自身初の甲子園で貴重なタイムリー。` but no deterministic `source_url` from local mirrors | publish不可: duplicate target is not widgets.js | not run | draft 維持 |
| 64272 | `リチャードが復帰戦で特大弾「久しぶりなのでかみ締めて走った」 ３月のオープン…` / `roster` / `repairable` | partial only; cleanup heading recovered `【巨人】リチャードが復帰戦で特大弾「久しぶりなのでかみ締めて走った」 ３月のオープン戦で左手指を骨折…２軍・広島戦。` but no deterministic `source_url` from local mirrors | publish不可: duplicate target is not widgets.js | not run | draft 維持 |

Notes:

- `64346` / `64335` / `64328` are the only three IDs whose latest local-history row points at `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- `64311` is blocked twice: non-widgets duplicate plus freshness/backlog hold
- `64294` and `64272` are blocked by non-widgets duplicate alone even though evaluator freshness was still `fresh`

## 64278 hold confirmation

`64278` remains Lane L scope external.

Latest local-history mirror row:

```json
{
  "post_id": 64278,
  "ts": "2026-05-02T19:00:41.761618+09:00",
  "status": "refused",
  "hold_reason": "review_duplicate_candidate_same_source_url",
  "freshness_source": "source_date",
  "duplicate_of_post_id": 64206,
  "duplicate_target_source_url": null
}
```

Lane L treatment:

- verdict: HOLD / manual_review
- reason: user contract explicitly excludes `64278`, and the latest local-history row is not widgets.js-authoritative

## non-actions confirmed

- no backup directory created for Lane L
- no guarded publish history rows deleted
- no widgets.js entry removal attempted
- no GCS object rewritten
- no `publish_notice_cursor.txt` / `publish_notice_history.json` / `publish_notice_queue.jsonl` wipe or edit
- no WordPress write executed
- no publish-notice mail newly sent by this execution

## counts

- widgets.js-target rows among the 6 rescue targets: `3`
- deleted entry count: `0`
- non-widgets entry touched: `0`
- remaining history row count observed in latest local mirror: `169026`
- mail delta actual: `0`
- backup path: none created

## publish / mail outcome

No post was published in this sandbox execution.

Therefore:

- public URL created by this execution: none
- publish-notice sent evidence created by this execution: none

Observed prior sent notices for duplicate-anchor posts in audit snapshots only:

- duplicate anchor `64206`: notice sent `2026-05-02T16:20:54.427448+09:00`
- duplicate anchor `64297`: notice sent `2026-05-03T09:41:05.798369+09:00`
- duplicate anchor `64299`: notice sent `2026-05-03T09:41:02.518789+09:00`

These are historical observations only, not Lane L output.

## rollback

This execution is a no-op, so rollback is also a no-op.

If Claude later reruns Lane L from a live-capable environment and performs widgets.js-only deletion or publish, the rollback contract should be:

1. restore deleted guarded-publish history rows from the per-run backup directory
2. revert any newly published post back to `draft` in WordPress
3. record the restoration timestamp and restored row count in a follow-up ops note

## open risks

- `64335` and `64328` are plausible widgets.js-only rescue candidates, but they were not re-evaluated live here; current status therefore remains draft
- `64346` still lacks deterministic local source reconstruction, so even in a live-capable shell it should not be published without fresh reconstruction evidence
- `64294` and `64272` may have richer live evidence outside this sandbox, but the latest local-history mirror still blocks them as non-widgets duplicates
