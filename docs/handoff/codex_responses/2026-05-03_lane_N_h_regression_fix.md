# 2026-05-03 Lane N' widgets.js duplicate regression fix

作成: 2026-05-03 19:49 JST

## mode

- live ops request received
- scope: BUG-004+291 Lane H widgets.js duplicate false-positive recurrence
- execution status: Step 1-7 完了、Step 8 record 作成
- git push: 未実行
- non-scope files/env/scheduler/service: 未変更

## scope summary

- Step 1-4: live audit
- Step 5: code patch + test + commit
- Step 6: guarded-publish image build + job image update
- Step 7: widgets.js anchor recovery for fixed target set
- Step 8: record

Fixed target set for Step 7:

- `64386`
- `64394`

Explicit non-target:

- `64280`
  - widgets.js anchor recurrence ではあったが、`general / 球団情報` 系の古い東京ドーム一般記事であり、user policy の「injury/return / ベンチコメント等は publish 寄り」の本線から外れるため rescue 対象に含めなかった

## Step 1 live verify

### live job describe

- job: `guarded-publish`
- project / region: `baseballsite` / `asia-northeast1`
- pre-fix live image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:565ef9a`
- pre-fix env confirmed:
  - `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`
  - `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT=1`

### existing implementation before fix

Target helper:

- `src/guarded_publish_runner.py:_should_exempt_widget_script_same_source_duplicate(...)`

Pre-fix behavior:

- widgets.js exempt は「matching same-source pair が widgets.js」であるだけでは発火しなかった
- 実際には以下を同時要求していた
  - candidate 側 source anchors が widget-only
  - reference 側 source anchors が widget-only
  - exact title / normalized title / same_game 系 duplicate signal が立っていない

Conclusion:

- env は正しく live に入っていた
- recurrence は deploy 漏れではなく、helper 条件が user policy より狭すぎたことが原因

## Step 2 root cause for `64394`

### refused event

- timestamp: `2026-05-03T19:00:40.855040+09:00`
- `post_id=64394`
- hold reason: `review_duplicate_candidate_same_source_url`
- duplicate target: `post_id=64343`
- duplicate target source url: `https://platform.twitter.com/widgets.js`
- duplicate target source url hash: `176756fe6e5a7d6f`

### candidate / target titles

- candidate `64394`
  - title: `橋上コーチ「イメージを変えるような投球」 ベンチ関連発言`
  - subtype: `manager`
- duplicate target `64343`
  - title: `立岡「立岡コーチとともに…」 関連発言`
  - subtype: `player`

### integrity confirmation

Execution:

- `guarded-publish-kk6js`

Observed integrity facts:

- `candidate_source_url_hash=176756fe6e5a7d6f`
- `duplicate_target_source_url_hash=176756fe6e5a7d6f`
- `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- `integrity_ok=true`

Local hash verification:

- `176756fe6e5a7d6f` == `https://platform.twitter.com/widgets.js`

### why Lane H exempt did not fire

Reference post backup used:

- `gs://baseballsite-yoshilover-state/guarded_publish/cleanup_backup/64343_20260503T050537.json`

Extracted reference source URL set included mixed anchors:

- `https://platform.twitter.com/widgets.js`
- hochi / SportsHochi tweet URLs
- related-post URLs on `yoshilover.com`

Conclusion:

- at least one of the old 4 AND conditions was false
- deterministically proven false condition:
  - `reference widget-only`
- therefore the helper refused to exempt even though the actual duplicate anchor that matched was only `widgets.js`

## Step 3 18:00+ refused audit

### live history input

- source: `/tmp/guarded_publish_history_live_20260503.jsonl`
- row count in mirror: `171372`
- filtered window: `status=refused` and `ts >= 2026-05-03T18:00:00+09:00`
- filtered refused count: `46`

### hold reason counts

| hold_reason | count | post_id list |
|---|---:|---|
| `hard_stop_farm_result_placeholder_body` | 13 | `64123, 64388, 63253, 63255, 63318, 63325, 63327, 63131, 63170, 63215, 63645, 63655, 63865` |
| `hard_stop_lineup_duplicate_excessive` | 13 | `63172, 63180, 63191, 63203, 63207, 63216, 63220, 63224, 63246, 63274, 63304, 63348, 63507` |
| `hard_stop_death_or_grave_incident` | 11 | `64012, 64129, 64392, 64131, 63175, 63197, 63385, 63468, 63482, 63517, 63661` |
| `review_duplicate_candidate_same_source_url` | 3 | `64386, 64394, 64280` |
| `hard_stop_lineup_no_hochi_source` | 3 | `63195, 63268, 63395` |
| `review_date_fact_mismatch_review` | 1 | `64390` |
| `hard_stop_ranking_list_only` | 1 | `63499` |
| `review_farm_result_required_facts_weak_review` | 1 | `63157` |

### per-row list

History rows in this window do not carry stable `title` / `resolved_subtype` for most legacy recrawl candidates. Enrichment from fetcher draft logs was available only for the widgets.js recurrence set.

| ts (JST) | post_id | hold_reason | duplicate_target_source_url | duplicate_of_post_id | freshness_source | title / subtype note |
|---|---:|---|---|---:|---|---|
| `2026-05-03T18:05:38.916436+09:00` | 64012 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T18:25:41.115990+09:00` | 64123 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T18:40:41.741413+09:00` | 64386 | `review_duplicate_candidate_same_source_url` | `https://platform.twitter.com/widgets.js` | 64343 | `source_date` | `阿部監督「あと1本が先に出ていれば…」 ベンチ関連発言` / `manager` |
| `2026-05-03T18:50:39.173956+09:00` | 64129 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T18:50:39.173956+09:00` | 64388 | `hard_stop_farm_result_placeholder_body` |  |  |  | fetcher draft title known, subtype not material |
| `2026-05-03T18:50:39.173956+09:00` | 64390 | `review_date_fact_mismatch_review` |  |  |  | fetcher draft title known, subtype not material |
| `2026-05-03T18:50:39.173956+09:00` | 64392 | `hard_stop_death_or_grave_incident` |  |  |  | fetcher draft title known, subtype not material |
| `2026-05-03T18:55:37.642971+09:00` | 64131 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:00:40.855040+09:00` | 64394 | `review_duplicate_candidate_same_source_url` | `https://platform.twitter.com/widgets.js` | 64343 | `source_date` | `橋上コーチ「イメージを変えるような投球」 ベンチ関連発言` / `manager` |
| `2026-05-03T19:05:39.742769+09:00` | 63172 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63175 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63180 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63191 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63195 | `hard_stop_lineup_no_hochi_source` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63197 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63203 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63207 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63216 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63220 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63224 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63246 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63253 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63255 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63268 | `hard_stop_lineup_no_hochi_source` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63274 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63304 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63318 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63325 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63327 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63348 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63385 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63395 | `hard_stop_lineup_no_hochi_source` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63468 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63482 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63499 | `hard_stop_ranking_list_only` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63507 | `hard_stop_lineup_duplicate_excessive` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63517 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 63661 | `hard_stop_death_or_grave_incident` |  |  |  | history-only |
| `2026-05-03T19:05:39.742769+09:00` | 64280 | `review_duplicate_candidate_same_source_url` | `https://platform.twitter.com/widgets.js` | 64194 | `source_date` | `井上尚弥vs中谷潤人、グッズ売り場大行列 試合前から東京ドーム盛り上がる` / `general` |
| `2026-05-03T19:15:37.909738+09:00` | 63131 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:15:37.909738+09:00` | 63157 | `review_farm_result_required_facts_weak_review` |  |  |  | history-only |
| `2026-05-03T19:15:37.909738+09:00` | 63170 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:15:37.909738+09:00` | 63215 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:15:37.909738+09:00` | 63645 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:15:37.909738+09:00` | 63655 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |
| `2026-05-03T19:15:37.909738+09:00` | 63865 | `hard_stop_farm_result_placeholder_body` |  |  |  | history-only |

## Step 4 widgets.js same_source_url recurrence set

Widgets.js-anchored refused rows in the 18:00+ window:

| post_id | ts (JST) | duplicate_of_post_id | freshness_source | title | subtype | decision |
|---|---|---:|---|---|---|---|
| 64386 | `2026-05-03T18:40:41.741413+09:00` | 64343 | `source_date` | `阿部監督「あと1本が先に出ていれば…」 ベンチ関連発言` | `manager` | recover |
| 64394 | `2026-05-03T19:00:40.855040+09:00` | 64343 | `source_date` | `橋上コーチ「イメージを変えるような投球」 ベンチ関連発言` | `manager` | recover |
| 64280 | `2026-05-03T19:05:39.742769+09:00` | 64194 | `source_date` | `井上尚弥vs中谷潤人、グッズ売り場大行列 試合前から東京ドーム盛り上がる` | `general` | leave as draft |

## Step 5 code patch

### implementation

Changed files:

- `src/guarded_publish_runner.py`
- `tests/test_guarded_publish_runner.py`

Commit:

- `ec250dc27c87fccd190d2ee4b99769c4cf6ae1a1`
- subject: `bug-004-291: broaden widgets.js duplicate exempt`

Patch summary:

- `_should_exempt_widget_script_same_source_duplicate(...)` を簡素化
- new rule:
  - matching same-source pair の `duplicate_target_source_url` が widget-script allowlist に一致するなら exempt
- removed from exempt predicate:
  - candidate に非-widget source がないこと
  - reference に非-widget source がないこと
  - title mismatch / same_game mismatch を要求すること
- retained safety:
  - env flag は既存 `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT` を再利用
  - `exact_title_match`
  - `normalized_title`
  - `same_game_subtype_speaker`
  - duplicate integrity strict
  - これら他 signal 自体は削っていない

### tests

Added / updated test coverage:

- mixed-source candidate/reference でも matching same-source pair が widgets.js のみなら exempt になる positive case
- matching pair が非-widget URL の場合は duplicate 維持の negative case
- existing widget allowlist helper tests kept

Pytest results in this lane:

- `python3 -m pytest tests/test_guarded_publish_runner.py -q`
  - `101 passed, 3 warnings, 4 subtests passed`
- `python3 -m pytest`
  - `2169 passed, 3 warnings`

## Step 6 build + job update

### build

Build submission:

- build id: `f9d4fe87-bb1c-4dad-8184-fc2abc52fc6e`
- status: `SUCCESS`
- image tag: `guarded-publish:ec250dc`
- image digest: `sha256:5edb38c03287000281331a2206e8316f6b8ddf23c010d4fdacca9cd89f51f087`
- image fq digest:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish@sha256:5edb38c03287000281331a2206e8316f6b8ddf23c010d4fdacca9cd89f51f087`

Sandbox workaround only:

- `CLOUDSDK_CONFIG` was copied to a writable `/tmp` location so `gcloud` could write local auth/cache files
- no Cloud Run env / secret contents were changed by this workaround

### live update

Applied command effect:

- updated `guarded-publish` job image to `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:ec250dc`

Post-update describe:

- job name: `guarded-publish`
- generation: `24`
- lastUpdatedTime: `2026-05-03T10:27:46.315525Z`
- current image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:ec250dc`
- env preserved:
  - `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`
  - `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT=1`
- job `Ready=True`

Note:

- Cloud Run Job なので service revision ではなく `generation=24` を current runtime marker として記録

## Step 7 publish recovery

### dedupe state issue found

Runner dedupe behavior:

- `src/guarded_publish_runner.py:75` `REFUSED_DEDUP_WINDOW_HOURS = 24`
- `_history_attempted_post_ids(...)` が直近 refused を再評価対象から除外

Therefore:

- code deploy だけでは `64386` / `64394` は 24h window 内で自動再評価されない
- recovery には history の該当 refused row を narrow delete する必要があった

### backups and narrow delete

Local backup dir:

- `/tmp/lane_n_step7.entVLy`

Remote backup objects:

- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_N_widgets_fix/guarded_publish_history.before.jsonl`
- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_N_widgets_fix/guarded_publish_history.deleted_rows.jsonl`

Mutation:

- live `guarded_publish_history.jsonl` から deleted rows = `2`
- deleted post_id:
  - `64386`
  - `64394`
- non-widget entries touched: `0`
- `64280` untouched

### guarded-publish rerun

Execution:

- `guarded-publish-2477s`

Outcome from live history:

| post_id | latest ts (JST) | status | hold_reason | cleanup_success | note |
|---|---|---|---|---|---|
| 64386 | `2026-05-03T19:34:16.079687+09:00` | `sent` | `null` | `true` | recovered |
| 64394 | `2026-05-03T19:34:16.079687+09:00` | `sent` | `null` | `true` | recovered |
| 64280 | unchanged | `refused` | `review_duplicate_candidate_same_source_url` | n/a | intentionally not retried |

Backup paths stored in those success rows:

- `/tmp/pub004d/cleanup_backup/64386_20260503T103416.json`
- `/tmp/pub004d/cleanup_backup/64394_20260503T103416.json`

Interpretation:

- `status=sent` in `run_guarded_publish(..., live=True)` is the success path after `WPClient.update_post_status(..., "publish")` or `update_post_fields(..., status="publish")`
- direct WP REST re-check from this sandbox was not possible because outbound name resolution to `yoshilover.com` failed
- publish outcome is therefore recorded from guarded-publish live history and publish-notice follow-up evidence, not from a direct sandbox GET to WordPress

### publish-notice follow-up

Manual execution:

- `publish-notice-j9k66`

Overlapping scheduled execution:

- `publish-notice-jbnz9`

Results observed:

- `publish-notice-jbnz9`
  - `64394` mail sent at `2026-05-03T10:36:31.963564Z`
  - `64386` mail sent at `2026-05-03T10:36:33.508432Z`
  - summary: `sent=2 suppressed=0 errors=0`
- `publish-notice-j9k66`
  - `64394` mail sent at `2026-05-03T10:37:39.164581Z`
  - `64386` mail sent at `2026-05-03T10:37:41.572018Z`
  - summary: `sent=2 suppressed=0 errors=0`
- later execution `publish-notice-pwcjp` had no `64386` / `64394` result rows

Observed mail subject format:

- both executions sent `【要確認】...` subjects, not `【公開済】...`

History file evidence after send:

- `publish_notice/history.json`
  - `64394 -> 2026-05-03T19:34:19+09:00`
  - `64386 -> 2026-05-03T19:34:21+09:00`

### per-id recovery outcome

| post_id | recovery action | final ops outcome | mail outcome | comment |
|---|---|---|---|---|
| 64386 | refused row deleted, rerun executed | published via guarded-publish success path | 2 sends observed because scheduler execution overlapped manual execution | widgets.js false-positive cleared |
| 64394 | refused row deleted, rerun executed | published via guarded-publish success path | 2 sends observed because scheduler execution overlapped manual execution | widgets.js false-positive cleared |
| 64280 | no mutation | draft / refused left unchanged | no new send from this lane | intentionally excluded |

## mail delta actual

- expected minimum if manual execution were isolated: `2`
- actual observed send count: `4`
- reason:
  - scheduler execution `publish-notice-jbnz9` and manual execution `publish-notice-j9k66` overlapped in the same minute
  - each execution sent 2 per-post mails for `64386` / `64394`
- later execution `publish-notice-pwcjp` showed no additional sends for these two post IDs

## rollback

### code

- `git revert ec250dc27c87fccd190d2ee4b99769c4cf6ae1a1`

### runtime image

- `gcloud run jobs update guarded-publish --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:565ef9a`

### history state

Restore full pre-recovery history file from:

- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_N_widgets_fix/guarded_publish_history.before.jsonl`

Or surgically reinsert deleted rows from:

- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_N_widgets_fix/guarded_publish_history.deleted_rows.jsonl`

### post state

- if rollback must also revert published posts, change `64386` / `64394` back to `draft` from a live WP-capable environment

## remaining stuck list

Within the Step 4 widgets.js recurrence set:

- recovered:
  - `64386`
  - `64394`
- intentionally left stuck:
  - `64280`

Outside that 18:00+ widgets.js set, this lane did not mutate any older same-source refusals from earlier in the day.

## next Claude action

1. `git push` the two new commits from this lane if external sync is desired
2. decide whether duplicate `【要確認】` mail caused by `publish-notice-jbnz9` + `publish-notice-j9k66` overlap needs a separate notify dedupe ticket
3. monitor next guarded-publish cycles for any new `review_duplicate_candidate_same_source_url` rows whose `duplicate_target_source_url` is `widgets.js`
