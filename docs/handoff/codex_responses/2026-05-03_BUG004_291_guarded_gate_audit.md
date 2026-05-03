# 2026-05-03 BUG-004+291 guarded-publish post-gate audit

作成: 2026-05-03 14:43 JST

## scope

- read-only / dry-run only
- code / tests / config change: 0
- deploy / env / Scheduler / WP REST / Gemini / mail mutation: 0
- target runtime: `guarded-publish` Cloud Run Job only

## live target confirmation

`gcloud run jobs describe guarded-publish --project=baseballsite --region=asia-northeast1`

| item | value |
|---|---|
| job generation | `21` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc` |
| strict duplicate env | `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1` |
| audit window | `2026-05-03 09:00-14:00 JST` |

## method

1. Code trace:
   - `src/guarded_publish_runner.py`
   - `src/guarded_publish_evaluator.py`
   - upstream-only contrast check: `src/rss_fetcher.py`
2. Live evidence:
   - durable state: `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
   - subject/subtype補助: `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
3. Log sanity:
   - `gcloud logging read` で `duplicate_target_integrity_check` を spot check

Note:

- Cloud Logging の stdout 行は集計向けに断片化しやすく、full count 復元より durable history の方が正確だった。
- count は `guarded_publish_history.jsonl` を正とし、subtype は history に title/subtype が無いため `publish_notice/queue.jsonl` の subject から推定した。
- `farm_result_placeholder_body` だけは code path 上 `farm_result` 系限定なので、subject 不在でも subtype を直接確定できる。

## phase 1: post-gate code trace

| gate | code path | current behavior | 2026-05-03 09:00-14:00 JST |
|---|---|---|---|
| numeric guard | evaluator `check_consistency(...)` at `src/guarded_publish_evaluator.py:1754-1798`, review/hard-stop materialization at `:1915-1972`, runner review hold at `src/guarded_publish_runner.py:1941-1955`, `:2213-2246` | numeric/date系は evaluator 側で `review_*` / `hard_stop_*` に落ち、runner はそのまま hold | `review_date_fact_mismatch_review = 4` |
| placeholder body | evaluator `_placeholder_body_reason(...)` at `src/guarded_publish_evaluator.py:1585-1629`, append at `:1804-1815`, runner red hold at `src/guarded_publish_runner.py:1412-1429`, `:2154-2204` | `farm_result_placeholder_body` は hard-stop | `hard_stop_farm_result_placeholder_body = 12` |
| body_contract validate | `src/guarded_publish_runner.py` に `body_contract` 分岐なし。実際の fail ledger は upstream `src/rss_fetcher.py:15372-15420` | guarded-publish 後段 gate ではなく fetcher/post-gen validate 側 | `0` |
| duplicate target integrity | runner `_duplicate_target_integrity_payload(...)` at `src/guarded_publish_runner.py:1685-1724`, `_detect_duplicate_candidate(...)` at `:1800-1841`, duplicate hold at `:2581-2643` | strict env ON でも `duplicate_integrity_fail` は別 hold。`same_source_url` は integrity OK 時に review hold | `review_duplicate_candidate_duplicate_integrity_fail = 0`; `review_duplicate_candidate_same_source_url = 6` |
| freshness / stale | evaluator `freshness_check(...)` at `src/guarded_publish_evaluator.py:1044-1106`, entry flag at `:1906-1945` | freshness fail は `entry.backlog_only = true` に畳み込まれる | freshness起因 hold はすべて `backlog_only` で観測 |
| backlog_only enforcement | runner backlog suppression at `src/guarded_publish_runner.py:2292-2358`; fresh/backlog arbitration at `:2360-2410` | current code に `BACKLOG_SUMMARY_ONLY` / `FORCED_SUMMARY_THRESHOLD` 分岐は無い。実体は freshness由来 `backlog_only` stop | `backlog_only = 7784` raw hits / `130` unique posts; `backlog_deferred_for_fresh = 0` |
| review-hold | runner review path at `src/guarded_publish_runner.py:2213-2246`, verdict filter at `:1371-1408`, `:2254-2258`, duplicate review at `:2581-2643` | `review_*`, `codex_review_*`, `review_duplicate_candidate_*` がここに入る | live hit は `review_date_fact_mismatch_review = 4`, `review_duplicate_candidate_same_source_url = 6`; `codex_review_* = 0` |
| other cleanup / postcheck / cap | cleanup plan at `src/guarded_publish_runner.py:903-1054`, candidate error hold at `:2545-2579`, cap branches at `:2427-2509`, live publish/cleanup failure at `:2690-2704`, postcheck batch at `:2035-2051` and `:2731-2733` | current window では hidden publish-path stop は未観測 | `cleanup_failed_post_condition = 0`, `cleanup_backup_failed = 0`, `publish_failed = 0`, `hourly_cap = 0`, `burst_cap = 0`, `daily_cap = 0` |

## phase 2: live gate hit counts

### raw execution counts

`guarded_publish_history.jsonl` in `2026-05-03 09:00-14:00 JST`

| metric | count |
|---|---|
| window rows | `7819` |
| `status=sent` | `6` |
| `status=skipped` | `7784` |
| `status=refused` | `29` |
| `judgment=yellow` | `7796` |
| `judgment=hard_stop` | `19` |
| `judgment=review` | `4` |

### hold_reason breakdown

| hold_reason | raw hits | unique post_ids | strict acceptance subset? |
|---|---:|---:|---|
| `backlog_only` | `7784` | `130` | no |
| `hard_stop_farm_result_placeholder_body` | `12` | `12` | no |
| `review_duplicate_candidate_same_source_url` | `6` | `6` | no |
| `hard_stop_death_or_grave_incident` | `6` | `6` | no |
| `review_date_fact_mismatch_review` | `4` | `4` | no |
| `hard_stop_lineup_duplicate_excessive` | `1` | `1` | no |
| `review_duplicate_candidate_duplicate_integrity_fail` | `0` | `0` | n/a |
| `cleanup_failed_post_condition` | `0` | `0` | n/a |
| `cleanup_backup_failed` | `0` | `0` | n/a |
| `publish_failed` | `0` | `0` | n/a |
| `hourly_cap` / `burst_cap` / `daily_cap` | `0` | `0` | n/a |

### immediate read

- Volume の主因は `backlog_only`。ただし `7784` は 130 件の stale/backlog 候補が 5 分周期で再評価され続けた増幅値で、distinct blocker は `130` 件。
- strict duplicate integrity env ON でも `duplicate_integrity_fail` は 0。現在止まっている duplicate 系は strict mismatch ではなく `same_source_url` review。
- cleanup / cap / postcheck 系の hidden stop は当該時間帯では観測されなかった。

## phase 3: subtype × gate cross-table

Subtype は `publish_notice/queue.jsonl` の subject 推定。`farm_result_placeholder_body` は code path から直接確定。

| gate | subtype split (`unique post_ids`) | note |
|---|---|---|
| freshness-origin `backlog_only` | `general 65`, `lineup 25`, `roster_notice 12`, `injury_recovery_notice 8`, `coach_comment 7`, `manager 4`, `postgame 3`, `young_player 2`, `farm_result 2`, `player_comment 1`, `pregame 1` | history に subtype 無し。subject heuristic |
| `review_duplicate_candidate_same_source_url` | `farm_result 2`, `lineup 2`, `farm_lineup 1`, `injury_recovery_notice 1` | duplicate target post subject から逆引き |
| `review_date_fact_mismatch_review` | `player_comment 2`, `manager 1`, `farm_result 1` | subject heuristic |
| `hard_stop_farm_result_placeholder_body` | `farm_result 12` | evaluator の placeholder classifier が `farm_result` 系限定 |
| `hard_stop_lineup_duplicate_excessive` | `lineup 1` | lineup duplicate/title cluster hard-stop |
| `hard_stop_death_or_grave_incident` | `unknown 6` | queue subject 不足。scope-eligible subset ではない |

### duplicate review details

`same_source_url` review hold 6 件のうち、strict duplicate integrity log で確認できた 4 件はすべて `integrity_ok=true` だった。

`gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="guarded-publish" AND jsonPayload.event="duplicate_target_integrity_check"' ...`

| candidate post_id | duplicate target post_id | duplicate target source url | inferred subtype |
|---|---:|---|---|
| `64328` | `64297` | `https://platform.twitter.com/widgets.js` | `farm_result` |
| `64333` | `64326` | `https://platform.twitter.com/widgets.js` | `farm_lineup` |
| `64335` | `64299` | `https://platform.twitter.com/widgets.js` | `lineup` |
| `64341` | `64299` | `https://platform.twitter.com/widgets.js` | `lineup` |

History only に残った 2 件も `duplicate_of_post_id` は以下だった。

| candidate post_id | duplicate_of_post_id | inferred subtype |
|---|---:|---|
| `64311` | `64297` | `farm_result` |
| `64322` | `64319` | `injury_recovery_notice` |

Read:

- strict env は壊れていない。`duplicate_integrity_fail` ではなく `same_source_url` 判定が通っている。
- 通っている source anchor が `platform.twitter.com/widgets.js` なので、duplicate source extraction が広すぎる可能性が高い。
- ここは global duplicate 緩和ではなく、widget script を source anchor から外す narrow fix 候補。

## phase 4: strict acceptance subset evaluation

User定義の strict acceptance subset:

- `source_url` あり
- `YOSHILOVER` 対象
- subtype 高 confidence
- `body_contract` / `numeric` / `placeholder` / `duplicate` / `stale` 各 pass
- title 明確
- それでも guarded-publish 後段で publish 化されない

### conclusion

- 当該 window では **strict acceptance subset に該当する stop は 0 件**。
- 理由:
  - `body_contract` stop は upstream `rss_fetcher.py` 側であり runner には入っていない
  - `numeric` stop は `review_date_fact_mismatch_review = 4` のみで strict subset から除外
  - `placeholder` stop は `farm_result_placeholder_body = 12` で strict subset から除外
  - `duplicate` stop は `same_source_url = 6` で strict subset から除外
  - `stale/freshness` stop は `backlog_only = 7784 raw / 130 unique` で strict subset から除外
  - strict subset 通過後に起きうる `cleanup_failed_post_condition` / `publish_failed` / cap 系 / `codex_review_*` はすべて `0`

### practical meaning

- 「全部 pass したのに guarded-publish 後段だけで詰まる hidden gate」は、少なくとも `2026-05-03 09:00-14:00 JST` には観測されなかった。
- publish 数を落としている主因は hidden cleanup gate ではなく、`freshness -> backlog_only` と `same_source_url duplicate review` の 2 系統。

## publish=0 / notice減 の原因分解

1. 最大ボリューム原因は freshness由来 `backlog_only`
   - raw `7784`
   - unique `130`
   - lineup / roster / injury_recovery / coach / manager に広く跨る
2. 狭いが高レバレッジな false positive 候補は `review_duplicate_candidate_same_source_url`
   - raw `6`
   - unique `6`
   - `farm_result`, `farm_lineup`, `lineup`, `injury_recovery_notice` に跨る
   - strict integrity mismatch ではなく `widgets.js` anchor が原因
3. numeric / placeholder は volume は小さいが正当 stop 側
   - numeric review `4`
   - placeholder hard-stop `12`
4. hidden post-cleanup / cap / postcheck path は今回の publish 減少の主要因ではない

## narrow unlock design recommendations

### 1. duplicate narrow unlock: ignore widget-script-only source anchors

対象 gate:

- `review_duplicate_candidate_same_source_url`

提案:

- `platform.twitter.com/widgets.js` だけで成立している `same_source_url` 判定は duplicate source anchor として採用しない
- strict integrity 自体は維持する
- exempt 条件は narrow にする:
  - candidate に非-widget source url が無い
  - duplicate target source url も widget script のみ
  - other duplicate signals (`exact_title_match_*`, `normalized_title_match_*`, `same_game_subtype_speaker`) は不一致

期待効果:

- `farm_result` / `farm_lineup` / `lineup` / `injury_recovery_notice` に跨る 6 件の false duplicate review を直接減らせる
- global duplicate 緩和を避けつつ unlock できる

### 2. freshness narrow unlock: subtype-aware backlog publish, not global stale relaxation

対象 gate:

- freshness起因 `backlog_only`

提案:

- global stale relaxation は不要
- narrow に許可するなら subtype-aware 条件で十分:
  - `lineup` / `pregame`: `source_date` or `created_at` があり、`age_hours` が subtype threshold を小幅超過した範囲だけ
  - `manager` / `coach_comment` / `player_comment`: source anchor 明示、duplicate signal なし、title が発言主体を明示しているものだけ
  - `roster_notice` / `injury_recovery_notice`: roster movement の event が title に明示され、同 game / same source duplicate が無いものだけ
- 既存 `_backlog_narrow_publish_context(...)` branch を使うなら subtype allowlist と max age を明示し、`general` は対象外に維持

期待効果:

- `130` unique backlog 候補のうち high-confidence subtype だけを narrow に再浮上できる
- `general 65` のような広い stale 群を巻き込まずに済む

### 3. observability補強: subtype/title を guarded history に残す

対象:

- `guarded_publish_history.jsonl`

提案:

- `resolved_subtype`
- `title`
- `source_url_hash_count`

を history row に加える

理由:

- 今回の cross-table は `publish_notice/queue.jsonl` subject 推定に依存した
- runner 単体 history に subtype/title があれば、次回の gate audit が deterministic になる

## final conclusion

- guarded-publish 後段 gate は trace 完了
- live hit count は freshness起因 `backlog_only` が圧倒的
- strict acceptance subset を満たすのに後段だけで止まったケースは当該 window では `0`
- narrow unlock の主対象は hidden cleanup gate ではなく:
  - `widgets.js` 起点の `same_source_url` duplicate review
  - subtype-aware freshness/backlog narrow unlock
