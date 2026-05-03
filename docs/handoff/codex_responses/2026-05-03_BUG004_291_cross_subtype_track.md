# 2026-05-03 BUG-004+291 cross-subtype publish-path stop track

## scope / method

- target window: **2026-05-03 09:00:00-13:59:59 JST** (`2026-05-03T00:00:00Z`-`2026-05-03T05:00:00Z`)
- mode: **read-only only**
- touched systems:
  - Cloud Logging read: `resource.labels.service_name="yoshilover-fetcher"`
  - Cloud Logging read: `resource.labels.job_name="publish-notice"`
  - Cloud Logging read: `resource.labels.job_name="guarded-publish"` for `duplicate_target_integrity_check` count only
- not used: WP REST, Gemini call, deploy, env change, Scheduler change, mail send, repo src/tests/config edit

## evidence basis

### fetcher-side candidate accounting

- `rss_fetcher_run_summary`
- `rss_fetcher_flow_summary`
- `title_template_selected`
- `article_skipped_post_gen_validate`
- `body_validator_fail`
- `title_player_name_review`
- `weak_title_narrow_unlock`

### publish-notice-side accounting

- `[summary] sent=... suppressed=... errors=... reasons=...`
- `post_gen_validate_history_scan_summary`
- `preflight_skip_history_scan_summary`

### guarded-publish-side accounting

- `duplicate_target_integrity_check` count only

## window summary

- fetcher runs in window: **62**
- fetcher raw totals:
  - `drafts_created=24`
  - `skip_duplicate=1017`
  - `skip_filter=6876`
  - `error_count=0`
- publish-notice runs in window: **60**
  - `sent_total=8`
  - `suppressed_total=20`
  - `errors_total=0`
  - suppress reasons: `PUBLISH_ONLY_FILTER=19`, `BACKLOG_SUMMARY_ONLY=1`

## phase 1: raw subtype x gate table

This is the **raw attempt** table for candidates that reached `prepared_subtype_counts`.  
Counts are consistent with `prepared_subtype_counts - created_subtype_counts` and candidate-level stop events.

| subtype | created | strict_review_fallback | body_contract_validate | weak_title | close_marker | post_gen_validate_no_game_but_result | post_gen_validate_intro_echo | pregame_started | total |
|---|---|---|---|---|---|---|---|---|---|
| postgame | 0 | 415 | 290 | 0 | 0 | 0 | 0 | 0 | 705 |
| farm | 8 | 0 | 124 | 77 | 4 | 0 | 0 | 0 | 213 |
| manager | 0 | 0 | 0 | 62 | 0 | 0 | 0 | 0 | 62 |
| pregame | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 345 | 345 |
| lineup | 4 | 0 | 0 | 0 | 0 | 11 | 0 | 0 | 15 |
| general | 4 | 0 | 0 | 0 | 8 | 0 | 1 | 0 | 13 |
| player | 3 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 5 |
| farm_lineup | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 |

### read-through

- **postgame** is the main starvation lane: `705 prepared / 0 created`
  - `415` raw stops at `strict_review_fallback`
  - `290` raw stops at `body_contract_validate`
- **pregame** is not missing because of duplicate/title. It is blocked by `pregame_started=345` and creates `0`.
- **manager** is not blocked by duplicate/body. It is entirely `weak_title=62`.
- **farm_lineup** is currently healthy in this window: `5 prepared / 5 created`.
- **lineup** is mostly healthy except for one repeated Yahoo lineup class: `11` raw stops at `NO_GAME_BUT_RESULT`.

## phase 2: pre-prepared gates outside acceptance

These counts are visible only as run-level skip reasons in `rss_fetcher_flow_summary`; current logs do **not** give subtype-tagged candidate ledgers for them.

| gate | raw count | acceptance relation |
|---|---:|---|
| `not_giants_related` | 3101 | scope outside |
| `social_too_weak` | 1677 | scope outside |
| `history_duplicate` | 1017 | fails duplicate guard |
| `live_update_disabled` | 397 | excluded by policy |
| `stale_postgame` | 246 | fails freshness guard |
| `pregame_started` | 345 | stale/timing fail for pregame lane |
| `video_promo` | 62 | scope outside |
| `comment_required` | 54 | source quality fail |

## phase 3: unique candidate terminal tracking

To avoid double-counting retry loops, I built the unique candidate universe from **`title_template_selected` unique `source_url`** and then looked only at stop events **after the last `title_template_selected`** for that URL.

- unique `title_template_selected` candidates in window: **48**
- unique fetcher-side terminal gates:
  - `created_or_downstream=24`
  - `strict_review_fallback=12`
  - `body_contract_validate=9`
  - `close_marker=2`
  - `post_gen_validate_no_game_but_result=1`

### unique subtype x gate table

| subtype | created_or_downstream | strict_review_fallback | body_contract_validate | close_marker | post_gen_validate_no_game_but_result | total |
|---|---|---|---|---|---|---|
| postgame | 0 | 12 | 7 | 0 | 0 | 19 |
| farm | 8 | 0 | 2 | 1 | 0 | 11 |
| lineup | 4 | 0 | 0 | 0 | 1 | 5 |
| general | 4 | 0 | 0 | 1 | 0 | 5 |
| player | 3 | 0 | 0 | 0 | 0 | 3 |
| farm_lineup | 5 | 0 | 0 | 0 | 0 | 5 |

### strict acceptance result

Strict scope excludes `general` fallback unless subtype confidence is separately proven.  
On that stricter basis:

- **scope-eligible but stuck unique candidates: 14**
  - `postgame / strict_review_fallback = 12`
  - `farm / close_marker = 1`
  - `lineup / post_gen_validate_no_game_but_result = 1`
- if the single `general + close_marker` fallback item is included as broad scope, total becomes **15**

### scope-eligible but stuck list (strict)

| subtype | gate | terminal reason | title | source_url |
|---|---|---|---|---|
| postgame | strict_review_fallback | `postgame_strict:strict_contract_fail:postgame_opponent_missing,postgame_decisive_event_missing` | 巨人戦 終盤の一打で動いた試合 | `https://baseballking.jp/ns/694560/` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:giants_score,required_facts_missing:opponent_score` | 巨人阪神戦 田中将大の試合後発言整理 | `https://www.nikkansports.com/baseball/news/202605020000169.html` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:giants_score` | 【巨人】9回2発の反撃も届かず… | `https://www.nikkansports.com/baseball/news/202605020001031.html` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:giants_score,required_facts_missing:opponent_score` | 巨人阪神戦 阿部の試合後発言整理 | `https://www.nikkansports.com/baseball/news/202605020001323.html` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date` | 巨人5-7 勝利の分岐点 試合の流れ | `https://twitter.com/TokyoGiants/status/2050493960901320727` |
| postgame | strict_review_fallback | `postgame_strict:strict_contract_fail:postgame_opponent_missing,postgame_decisive_event_missing` | 巨人戦 岡本和真の試合後発言整理 | `https://baseballking.jp/ns/694514/` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:giants_score,required_facts_missing:opponent_score` | 【とっておきメモ】巨人田中将大は… | `https://www.nikkansports.com/baseball/news/202605010002189.html` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:giants_score,required_facts_missing:opponent_score` | 【巨人】阿部監督「最近四球がキーワード…」 | `https://www.nikkansports.com/baseball/news/202605010002047.html` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:giants_score,required_facts_missing:opponent_score` | 【巨人】阿部監督「いた投手みんな頑張ってくれた」… | `https://www.nikkansports.com/baseball/news/202605010002095.html` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:giants_score,required_facts_missing:opponent_score` | 【巨人】田中将大ホッとした203勝目… | `https://www.nikkansports.com/baseball/news/202605010002174.html` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:opponent` | 巨人戦 田中瑛斗の試合後発言整理 | `https://baseballking.jp/ns/694482/` |
| postgame | strict_review_fallback | `postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:opponent,required_facts_missing:giants_score,required_facts_missing:opponent_score` | 【巨人】田中将大が日米203勝目… | `https://www.nikkansports.com/baseball/news/202605010001921.html` |
| farm | close_marker | `close_marker` | 脳しんとう特例措置で登録抹消中の泉口友汰が2軍戦「3番・遊撃」で実戦復帰… | `https://twitter.com/hochi_giants/status/2050798376833126835` |
| lineup | post_gen_validate_no_game_but_result | `NO_GAME_BUT_RESULT` | 巨人スタメン 阪神戦（甲子園） 1番吉川尚輝、2番キャベッジ… | `https://baseball.yahoo.co.jp/npb/game/2021038805/top` |

## phase 4: what actually recovered

### fetcher-side downstream success set

Strict scope success on fetcher side in this window:

- `farm=8`
- `farm_lineup=5`
- `lineup=4`
- `player=3`
- total non-general `created_or_downstream = 20`

There is **no** fetcher-side created postgame candidate in this window.

### subtask-9 (`ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE=1`) effect

Observed live evidence is `weak_title_narrow_unlock`, not a separate `narrow_unlock_subtype_aware` event.

- emit count in window: **2**
- both emits occurred at **2026-05-03 09:41 JST**
- both later reached `created_or_downstream` on the fetcher side:
  - `farm`: 森田駿哉 2戦連続快投記事
  - `player`: 阿部「野球って不思議だな」関連記事
- immediate corroborating run:
  - `2026-05-03T00:43:09Z` `rss_fetcher_run_summary` shows `drafts_created=2`
  - same `rss_fetcher_flow_summary` shows `created_subtype_counts={"farm":1,"player":1}`

Interpretation:

- **subtask-9 fetcher-side effective rate = 2 / 2**
- however, this only recovered the `farm` / `player` weak-title lane
- it did **not** move `manager`, `postgame`, or `pregame`

### weak-title lane left behind

Raw weak-title stop families still present:

- `manager / weak_generated_title:blacklist_phrase:ベンチ関連の発言ポイント`
  - raw `62`
  - unique source_url `1`
  - still blocked
- `farm / weak_generated_title:no_strong_marker`
  - raw `77`
  - unique source_url `3`
  - rescued `1`, unresolved `2`
- `player / weak_generated_title:no_strong_marker`
  - raw `2`
  - unique source_url `1`
  - rescued `1`

## phase 5: publish-notice-side findings

- window totals:
  - `sent_total=8`
  - `suppressed_total=20`
  - `errors_total=0`
- suppress reasons:
  - `PUBLISH_ONLY_FILTER=19`
  - `BACKLOG_SUMMARY_ONLY=1`
- `post_gen_validate_history_scan_summary` totals in window:
  - `emitted_count=18`
  - `skipped_by_dedup=118230`
  - `skipped_by_payload=0`
- `preflight_skip_history_scan_summary` totals in window:
  - `emitted_count=0`
  - `scanned_records=0`

Interpretation:

- publish-notice reduction is **partly intentional** in this window because `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1` is suppressing non-publish mail classes.
- review-path visibility is also heavily deduped at the post-gen ledger scan layer.
- this means `publish=0` and `normal Gmail volume down` are not identical problems:
  - fetcher-side starvation is real
  - publish-notice-side suppression is also real

## phase 6: subtask-8 (`ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`) visibility

- `duplicate_target_integrity_check` count in window: **4**
- `integrity_ok=true`: **4 / 4**
- nearby publish-notice summaries after the visible checks:
  - around `2026-05-03T03:36Z`: `sent=0`, then `sent=0 suppressed=2`
  - around `2026-05-03T04:45Z`: `sent=0`, then `sent=0 suppressed=1`

What A-side logs can prove:

- subtask-8 is **executing** and integrity mismatch is not tripping in the observed checks
- A-side fetcher/publish-notice logs do **not** prove a downstream publish conversion from those 4 checks
- exact `check -> guarded-publish judgment -> publish` conversion needs B-side guarded-publish history correlation

## conclusions

### strict answer to the user question

- strict `scope eligible but stuck` count: **14 unique candidates**
- broad count including one `general` fallback `close_marker` case: **15 unique candidates**

### dominant stop reason

- the dominant cross-subtype blocker is **not duplicate**, **not stale**, and **not weak title** inside the eligible universe
- it is overwhelmingly **`postgame_strict` review fallback**
  - `12 / 14` strict eligible unique stops
  - `415` raw repeated stop attempts in the window

### subtype-specific readout

- `postgame`: main blocker is `strict_review_fallback` + `body_contract_validate`
- `pregame`: blocked by `pregame_started`, not by title/body/duplicate
- `manager`: blocked by weak title only
- `farm_lineup`: healthy
- `lineup`: one repeated Yahoo lineup class still dies on `NO_GAME_BUT_RESULT`

## narrow unlock reinforcement candidates

### 1. postgame strict fallback is the real next unlock target

- gate: `strict_review_fallback`
- subtype: `postgame`
- fail axes:
  - `required_facts_missing:game_date`
  - `required_facts_missing:giants_score`
  - `required_facts_missing:opponent_score`
  - `required_facts_missing:opponent`
  - `postgame_decisive_event_missing`
- reason: current subtype-aware narrow unlock fixed title rescue, but **did not touch postgame strict fact recovery**

### 2. manager comment rescue still has one unresolved narrow class

- gate: `weak_title`
- subtype: `manager`
- current blocker: `blacklist_phrase:ベンチ関連の発言ポイント`
- reason: one unique source keeps retrying and never reaches `title_template_selected`
- this is **outside** strict acceptance as-is, but it is the cleanest remaining title-side unlock candidate after subtask-9

### 3. lineup Yahoo page class still misfires on `NO_GAME_BUT_RESULT`

- gate: `post_gen_validate_no_game_but_result`
- subtype: `lineup`
- unique candidate count: `1`
- raw repeated attempts: `11`
- reason: title/lineup context is strong, but body/post-gen still treats the page as result-fragment contamination

### 4. observability gap remains for early gates

- `social_too_weak`
- `history_duplicate`
- `live_update_disabled`
- `stale_postgame`

These gates are only visible as run-level counters in current logs, so a **true subtype-tagged cross-table** for them cannot be proven from current live evidence alone.

## final judgment

- fetcher-side `publish path unlock` is **partially working** for narrow weak-title rescue
- the current live bottleneck is **postgame strict review fallback**, not the subtype-aware unlock itself
- duplicate target integrity strict is visible and healthy in the limited A-side evidence, but **no publish conversion is attributable from A-side logs alone**
- if the next narrow unlock is chosen strictly by evidence, it should be:
  1. `postgame_strict` fact recovery / fallback refinement
  2. then manager-comment title concretization
  3. then the single Yahoo lineup `NO_GAME_BUT_RESULT` class
