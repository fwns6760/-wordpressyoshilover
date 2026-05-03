# BUG-003 + BUG-004+291 status revert broad audit

更新日時: 2026-05-03 JST

## Scope

- read-only / doc-only / live-inert
- 目的: 2026-05-03 JST 時点で「一度 publish に到達した後、non-publish 側で再観測される post_id」を broad scan する
- write scope: この文書のみ
- read source:
  - `gcloud logging read` for `yoshilover-fetcher`, `guarded-publish`, `publish-notice`
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
  - `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
  - `gs://baseballsite-yoshilover-state/publish_notice/history.json`
- local helper copies were written only to `/tmp/status_revert_audit`
- 制約:
  - sandbox からの direct WP REST GET は `NameResolutionError` で失敗
  - したがって live current status は internal state / log ベースの best-effort
  - ただし field report により `64196 / 64198 / 64352` の current 401 は別経路で確認済み

## Executive Summary

- broad upper-bound では、known `publish_at` を持ち、その後 2026-05-03 JST 中に `guarded_publish_history` 上で non-sent (`refused` / `skipped`) を再観測した numeric `post_id` は **146 件**。
- そのうち、2026-05-03 の `publish_notice` queue に per-post で surfaced した numeric post は **20 件**。
- そのうち、`publish_at` の直後に **same-day で初めて** non-sent へ落ちた fresh cohort は **3 件**:
  - `64331`
  - `64352`
  - `64368`
- field-confirmed current non-publish は **3 件**:
  - `64196`
  - `64198`
  - `64352`
- BUG-003 の「mail が飛んだら non-publish 化する」仮説は、この broad scan では **支持されない**。
  - 2026-05-03 に mail-surfaced した 20 件すべてで、**first non-sent observed_at < first notice today**
  - mail / queue は後追い symptom で、先行 cause ではない
- cleanup relation:
  - 2026-05-03 に `cleanup_failed_post_condition` / `cleanup_backup_failed` / `cleanup_*` の same-day row は **0**
  - cleanup path は historical first-failure reason として 14 件に残るが、今日の主因ではない

## Cohort Summary

| cohort | count | meaning |
|---|---:|---|
| field-confirmed current non-publish | 3 | Claude field check で current 401 を確認した subset |
| fresh same-day first-observed revert | 3 | `publish_at` 後の first non-sent が 2026-05-03 JST に初めて出た subset |
| today queue-surfaced numeric subset | 20 | 2026-05-03 の `publish_notice_queue` に queued reason が現れた numeric subset |
| broad active upper-bound | 146 | known `publish_at` あり + 2026-05-03 に `guarded_publish_history` で non-sent を再観測した numeric population |

## Initial Revert-Cause Proxy

以下は「first non-sent after publish」の hold reason を cause proxy として grouped したもの。  
注意: これは **actual WP mutator の証明ではない**。`guarded-publish` が publish 後に non-sent state を最初に観測した理由であり、actual mutator actor は別に居る可能性がある。

| first non-sent hold_reason | count | observed service classification |
|---|---:|---|
| `hard_stop_injury_death` | 56 | scheduled task / guarded-republish hard stop |
| `burst_cap` | 32 | scheduled task / guarded-republish cap gate |
| `review_duplicate_candidate_same_source_url` | 25 | scheduled task / guarded-republish duplicate gate |
| `cleanup_failed_post_condition` | 14 | scheduled task / guarded cleanup failure |
| `review_date_fact_mismatch_review` | 8 | scheduled task / guarded review gate |
| `backlog_only` | 7 | scheduled task / guarded backlog reevaluation |
| `hard_stop_death_or_grave_incident` | 3 | scheduled task / guarded hard stop |
| `review_farm_result_required_facts_weak_review` | 1 | scheduled task / guarded review gate |

実務的な読み:

- broad population の observable source は **guarded-publish scheduled task** に集中している
- ただし actual mutation actor は **unknown**
- manual API / plugin / WP-side actor を否定する証拠はこの scan では取れていない
- mail path が first mover だった証拠は 0

## BUG-003 Mail Correlation

結論:

- **mail first ではない**
- 2026-05-03 に surfaced した numeric 20 件すべてで、first non-sent observed が first notice today より前

Representative examples:

| post_id | publish_at | first non-sent observed | first notice today | result |
|---|---|---|---|---|
| 64196 | 2026-05-01 14:30:28 JST | 2026-05-01 14:30:40 JST | 2026-05-03 14:40:39 JST | non-sent precedes notice by ~48h |
| 64198 | 2026-05-01 14:30:34 JST | 2026-05-01 14:35:36 JST | 2026-05-03 14:40:39 JST | non-sent precedes notice by ~48h |
| 64352 | 2026-05-03 14:10:55 JST | 2026-05-03 14:15:39 JST | 2026-05-03 14:20:40 JST | non-sent precedes notice by ~5m |
| 64331 | 2026-05-03 13:00:20 JST | 2026-05-03 13:00:38 JST | 2026-05-03 13:05:38 JST | non-sent precedes notice by ~5m |
| 64368 | 2026-05-03 15:46:11 JST | 2026-05-03 15:50:37 JST | 2026-05-03 15:55:34 JST | non-sent precedes notice by ~5m |

判定:

- BUG-003 の「mail が飛んで来たら全公開が non-publish」仮説は **time-correlation 上は不成立**
- mail / publish-notice queue は causal trigger ではなく、**既に non-sent 化した state の downstream symptom**

## Cleanup Relation

- 2026-05-03 row では `cleanup_failed_post_condition` / `cleanup_backup_failed` / `cleanup_*` の same-day evidence は **0**
- `guarded_publish_today.json` で見える cleanup は `guarded_publish_cleanup_log.jsonl` の bucket copy only
- したがって **today-scope の fresh 3件** と **today queue-surfaced 20件** を cleanup mutation で説明する証拠は無い
- ただし broad upper-bound の historical first reason として `cleanup_failed_post_condition` が **14 件**残っており、legacy source としては無視できない

## Today Queue-Surfaced Numeric Inventory (20)

この 20 件は 2026-05-03 に `publish_notice_queue` 上で reason 付き queued row が出た numeric subset。  
`gap` は `publish_at -> first_non_sent_at`。

| post_id | publish_at | first_non_sent_at | last_non_sent_at | first_reason | first_notice_today | gap | subject |
|---|---|---|---|---|---|---|---|
| 62420 | 2026-04-16T18:00:23+09:00 | 2026-04-27T08:05:36.042736+09:00 | 2026-05-03T07:30:40.991945+09:00 | burst_cap | 2026-05-03T07:35:35.319688+09:00 | 10d 14h 5m 13s | 【要review】田中将大、雨天中止スライド登板で何を見るか / YOSHILOVER |
| 62442 | 2026-04-16T22:01:33+09:00 | 2026-04-27T08:05:36.042736+09:00 | 2026-05-03T07:30:40.991945+09:00 | burst_cap | 2026-05-03T07:35:35.319688+09:00 | 10d 10h 4m 3s | 【要review】田中将大「粘り強い見事でしたね」 実戦で何を見せるか / YOSHILOVER |
| 62627 | 2026-04-18T21:30:34+09:00 | 2026-04-27T08:05:36.042736+09:00 | 2026-05-03T07:30:40.991945+09:00 | burst_cap | 2026-05-03T07:35:35.319688+09:00 | 8d 10h 35m 2s | 【要review】式野球クラブは何を見せたか / YOSHILOVER |
| 63259 | 2026-04-22T16:51:09+09:00 | 2026-04-26T18:51:29.547524+09:00 | 2026-05-03T07:30:40.991945+09:00 | hard_stop_injury_death | 2026-05-03T07:35:35.319688+09:00 | 4d 2h 0m 20s | 【要review】宇都宮葵星が登録抹消 前日の長野で走塁中に足を滑らせる / YOSHILOVER |
| 63679 | 2026-04-26T19:30:38+09:00 | 2026-04-27T00:00:38.376883+09:00 | 2026-05-03T07:30:40.991945+09:00 | hard_stop_injury_death | 2026-05-03T07:35:35.319688+09:00 | 4h 30m 0s | 【要review】巨人DeNA戦 回表は何を見せたか / YOSHILOVER |
| 63787 | 2026-04-27T12:25:17+09:00 | 2026-04-27T12:25:40.424729+09:00 | 2026-05-03T07:30:40.991945+09:00 | cleanup_failed_post_condition | 2026-05-03T07:35:35.319688+09:00 | 23s | 【要review】巨人中日戦 石塚選手先発でどこを見たいか / YOSHILOVER |
| 63920 | 2026-04-29T00:20:38+09:00 | 2026-04-29T00:25:34.553410+09:00 | 2026-05-03T07:30:40.991945+09:00 | backlog_only | 2026-05-03T07:35:35.319688+09:00 | 4m 56s | 【要review】本日の広島戦（東京ドーム）で「春のプロデュースグルメ総選挙2026＆アゲアゲ… / YOSHILOVER |
| 63933 | 2026-04-29T07:30:54+09:00 | 2026-04-29T07:35:37.908745+09:00 | 2026-05-03T07:40:36.260157+09:00 | review_date_fact_mismatch_review | 2026-05-03T07:45:39.403254+09:00 | 4m 43s | 【要review】投手コーチ「ただ球が高いだけではないかも」 ベンチ関連発言 / YOSHILOVER |
| 64080 | 2026-04-30T11:00:35+09:00 | 2026-04-30T11:05:35.022357+09:00 | 2026-05-03T11:10:45.100750+09:00 | review_date_fact_mismatch_review | 2026-05-03T11:15:35.836095+09:00 | 5m 0s | 【要review】長嶋茂雄終身名誉監督「長嶋追悼展」 ベンチ関連発言 / YOSHILOVER |
| 64085 | 2026-04-30T12:11:07+09:00 | 2026-04-30T12:15:43.323048+09:00 | 2026-05-03T16:25:39.218517+09:00 | review_duplicate_candidate_same_source_url | 2026-05-03T12:15:36.425320+09:00 | 4m 36s | 【要確認(古い候補)】巨人ドラ1・竹丸 リーグトップタイ4勝 「地元のチーム」広島相手に6回2失点… / YOSHILOVER |
| 64167 | 2026-05-01T12:40:33+09:00 | 2026-05-01T12:45:38.234036+09:00 | 2026-05-03T16:25:39.218517+09:00 | review_duplicate_candidate_same_source_url | 2026-05-03T13:00:37.941356+09:00 | 5m 5s | 【要確認(古い候補)】巨人スタメン 岡本和真 第3打席は三ゴロ 13連戦7戦目も4戦連 / YOSHILOVER |
| 64169 | 2026-05-01T12:40:44+09:00 | 2026-05-01T12:45:38.234036+09:00 | 2026-05-03T16:25:39.218517+09:00 | review_duplicate_candidate_same_source_url | 2026-05-03T13:00:37.941356+09:00 | 4m 54s | 【要確認(古い候補)】巨人スタメン 岡本和真 第4打席は左飛 13連戦7戦目も4戦連続 / YOSHILOVER |
| 64177 | 2026-05-01T13:00:22+09:00 | 2026-05-01T13:00:35.031332+09:00 | 2026-05-03T16:25:39.218517+09:00 | review_duplicate_candidate_same_source_url | 2026-05-03T13:05:38.169435+09:00 | 13s | 【要確認(古い候補)】【三軍】巨人 vs 全足利クラブ HARD OFF ECOスタジアム新潟🏟… / YOSHILOVER |
| 64183 | 2026-05-01T13:30:25+09:00 | 2026-05-01T13:30:36.414506+09:00 | 2026-05-03T16:25:39.218517+09:00 | review_duplicate_candidate_same_source_url | 2026-05-03T13:35:36.691969+09:00 | 11s | 【要確認(古い候補)】巨人スタメン 岡本和真 3戦連続V打なるか 13連戦7戦目ツイン / YOSHILOVER |
| 64196 | 2026-05-01T14:30:28+09:00 | 2026-05-01T14:30:40.796045+09:00 | 2026-05-03T14:35:39.986483+09:00 | review_date_fact_mismatch_review | 2026-05-03T14:40:39.583947+09:00 | 12s | 【要review】「2026江戸前スーシーズ」グッズを発売🍣 読売巨人軍は、粋でいなせな江戸っ… / YOSHILOVER |
| 64198 | 2026-05-01T14:30:34+09:00 | 2026-05-01T14:35:36.503837+09:00 | 2026-05-03T16:25:39.218517+09:00 | review_duplicate_candidate_same_source_url | 2026-05-03T14:40:39.583947+09:00 | 5m 2s | 【要確認(古い候補)】新イニング間イベント 「RINOKA’s BEEEATS!」 を開催🎵 「R… / YOSHILOVER |
| 64201 | 2026-05-01T14:40:32+09:00 | 2026-05-01T14:45:42.306614+09:00 | 2026-05-03T16:25:39.218517+09:00 | review_duplicate_candidate_same_source_url | 2026-05-03T15:00:42.482063+09:00 | 5m 10s | 【要確認(古い候補)】RT 【公式】ジャイアンツタウンスタジアム: ／ 🆕カスタムグッズに新商品が… / YOSHILOVER |
| 64331 | 2026-05-03T13:00:20+09:00 | 2026-05-03T13:00:38.042209+09:00 | 2026-05-03T13:00:38.042209+09:00 | review_date_fact_mismatch_review | 2026-05-03T13:05:38.169435+09:00 | 18s | 【要review】RT 【公式】ジャイアンツタウンスタジアム: 【二軍】巨人🆚 広島 ジャイア… / YOSHILOVER |
| 64352 | 2026-05-03T14:10:55+09:00 | 2026-05-03T14:15:39.310890+09:00 | 2026-05-03T14:15:39.310890+09:00 | review_date_fact_mismatch_review | 2026-05-03T14:20:40.383957+09:00 | 4m 44s | 【要review】阿部監督「野球って不思議。いろいろなことを考えさせられた」 ベンチ関連発言 / YOSHILOVER |
| 64368 | 2026-05-03T15:46:11+09:00 | 2026-05-03T15:50:37.938431+09:00 | 2026-05-03T15:50:37.938431+09:00 | review_farm_result_required_facts_weak_review | 2026-05-03T15:55:34.777913+09:00 | 4m 26s | 【要review】が2軍戦で実戦復帰＆2安打「問題なくプレーできた。いつ呼ばれてもいい状態」 / YOSHILOVER |

## Fresh Same-Day First-Observed Cohort (3)

| post_id | publish_at | first non-sent observed | first reason | subject |
|---|---|---|---|---|
| 64331 | 2026-05-03 13:00:20 JST | 2026-05-03 13:00:38 JST | `review_date_fact_mismatch_review` | RT 【公式】ジャイアンツタウンスタジアム: 【二軍】巨人🆚 広島... |
| 64352 | 2026-05-03 14:10:55 JST | 2026-05-03 14:15:39 JST | `review_date_fact_mismatch_review` | 阿部監督「野球って不思議。いろいろなことを考えさせられた」 |
| 64368 | 2026-05-03 15:46:11 JST | 2026-05-03 15:50:37 JST | `review_farm_result_required_facts_weak_review` | 2軍戦で実戦復帰＆2安打「問題なくプレーできた。いつ呼ばれてもいい状態」 |

## Subtype / Title Pattern Snapshot

subject-based heuristic only:

| cohort | subtype distribution |
|---|---|
| queue-surfaced 20 | `other=7`, `pregame_lineup=4`, `farm=4`, `manager_quote=3`, `team_info_event=2` |
| fresh 3 | `farm=2`, `manager_quote=1` |

source-hint heuristic only:

| cohort | source-hint distribution |
|---|---|
| queue-surfaced 20 | `unknown=13`, `sports_media_inferred=3`, `official_team_inferred=2`, `official_x_giants_town=2` |
| fresh 3 | `official_x_giants_town=1`, `sports_media_inferred=1`, `unknown=1` |

Notes:

- source domain は allowed data だけでは全件復元できない
- `64352` だけは fetcher log 上で `https://www.nikkansports.com/baseball/news/202605020001323.html` を確認できた
- `64331` は `RT 【公式】ジャイアンツタウンスタジアム` から official X source と推定
- `64196` / `64198` は subject 文面から official team event / goods と推定

## Broad Population Inventory (146)

この inventory は **2026-05-03 JST に active な upper-bound**。  
grouping key は **first non-sent after publish** の reason。

### `backlog_only` (7)

`63875, 63920, 63926, 64030, 64054, 64056, 64234`

### `burst_cap` (32)

`61938, 61969, 61971, 61975, 62005, 62007, 62010, 62023, 62030, 62039, 62070, 62072, 62373, 62395, 62398, 62420, 62424, 62439, 62441, 62442, 62451, 62455, 62459, 62463, 62498, 62514, 62527, 62540, 62578, 62598, 62616, 62627`

### `cleanup_failed_post_condition` (14)

`62670, 62943, 63003, 63109, 63118, 63127, 63137, 63155, 63232, 63331, 63634, 63681, 63787, 63811`

### `hard_stop_death_or_grave_incident` (3)

`64008, 64034, 64038`

### `hard_stop_injury_death` (56)

`62201, 62377, 62384, 62385, 62387, 62396, 62469, 62496, 62523, 62534, 62544, 62558, 62564, 62600, 62605, 62658, 62794, 62797, 62888, 62940, 62968, 63091, 63097, 63182, 63184, 63186, 63201, 63213, 63218, 63228, 63241, 63259, 63261, 63292, 63309, 63311, 63456, 63470, 63472, 63475, 63477, 63525, 63632, 63636, 63638, 63649, 63651, 63659, 63679, 63683, 63687, 63708, 63710, 63789, 63793, 63795`

### `review_date_fact_mismatch_review` (8)

`63933, 63940, 64080, 64156, 64196, 64207, 64331, 64352`

### `review_duplicate_candidate_same_source_url` (25)

`64036, 64040, 64042, 64048, 64050, 64052, 64062, 64064, 64066, 64085, 64092, 64114, 64116, 64121, 64167, 64169, 64177, 64183, 64198, 64201, 64222, 64226, 64242, 64258, 64259`

### `review_farm_result_required_facts_weak_review` (1)

`64368`

## Main Hypotheses Ranking

1. **scheduled guarded-republish / guarded-publish reevaluation path is the dominant observable source**
   - all 146 broad IDs are recovered from `guarded_publish_history` after known `publish_at`
   - cause proxy is concentrated in guarded hold reasons, not in mail logs
2. **legacy published posts are being re-observed as backlog / duplicate / hard-stop items for a long time**
   - many IDs first fell out days earlier and are still active on 2026-05-03
   - `64196` and `64198` are not fresh 2026-05-03 incidents; they are legacy-active
3. **publish-notice mail is downstream symptom, not upstream cause**
   - 20/20 queue-surfaced numeric IDs have `first_non_sent_at < first_notice_today`
4. **cleanup path is historical but not today’s lead cause**
   - 14 IDs carry `cleanup_failed_post_condition` as first reason
   - same-day cleanup error evidence is 0
5. **actual WP mutator actor remains unknown**
   - no direct WP mutation log in allowed sources
   - direct WP REST GET from sandbox failed
   - manual API / plugin / WP-side actor cannot be ruled out

## Recommended Next Action

1. Claude / field shell で `64331` と `64368` の current status を direct WP REST で確認する。
2. `64196 / 64198 / 64352 / 64331 / 64368` を pivot に、actual WP status mutator を追う narrow deep audit を継続する。
3. repo 側では、actual mutation point に durable status-transition ledger を追加する候補を切る。
4. live behavior を変える前に、`publish -> non-sent` へ落ちた items を quarantine するのか republish 対象にするのかを分けて考える。

## USER_DECISION_REQUIRED

- **この audit 自体は NO**
- ただし次に live rollback / env change / Scheduler change / WP status repair を入れる場合は YES

## Open Questions

- `64196 / 64198 / 64352 / 64331 / 64368` の actual current WP status は何か
- actual WP mutator は `guarded-publish` 系か、別の manual/API/plugin actor か
- `hard_stop_*` / `burst_cap` / `cleanup_failed_post_condition` を first non-sent に持つ legacy publish 群が、なぜ once publish を通過できたのか
- broad upper-bound 146 件のうち、現在も live で non-publish のまま残っている実数はいくつか
