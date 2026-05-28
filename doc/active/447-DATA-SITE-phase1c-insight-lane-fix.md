# 447 data-site Phase 1.0c — insight.db data-insight lane 修復 (Phase 1.0c BLOCKED 解除)

> **note**: 元 id = 445 で作成、 別 thread で `445-SNS-realtime-topic-daily.md`
> が並行作成中だったため 2026-05-28 PM4 に **447** へ rename。 GH issue #117 は
> 既存維持 (title 「【445】 ...」 のまま、 本 ticket への link は 447 へ訂正)。

## 1. ticket header

- **ticket id**: 447
- **status**: DRAFT (user 判断 pending、 data-insight lane 触る risk あるため scope 確定後着手)
- **owner**: Claude Code
- **lane**: data-insight / insight.db
- **created**: 2026-05-28
- **priority**: P2 (Phase 1.5 完成後の差別化 metric 解放、 cluster authority は 444 で既達成済)
- **parent**: 444 (data-site Phase 1.5)
- **github_issue**: PENDING

## 2. 背景

ticket 444 で実装した data-site Phase 1.5 (31 player Pillar) で、 「大手にない data metric pack」 候補 11 個のうち以下 5 個が insight.db data の質的 gap で BLOCK 中:

| # | data | block 真因 |
|---|---|---|
| 1 | 得点圏打率 (RISP) / 走者状況別 | `at_bat_details.batter_canonical` が **全件 NULL**、 raw `batter` column は 「吉川」「代打・ 吉川」 形式で player canonical join 不可 |
| 2 | 球場別 (本拠地 / ビジター) | `games.home_away` が **全件 'unknown'**、 推定 logic 未実装 |
| 3 | vs 左右投手 打率 | at_bat_details.batter_canonical + 投手 hand 必要 (両方 missing) |
| 4 | count split (初球 / 2 strike 後) | at_bat_details.batter_canonical 必要 |
| 5 | イニング別 打率 | at_bat_details.batter_canonical 必要 |

at_bat_details は 1,185 行存在、 batter raw 値はあるが canonical 補完がない。

## 3. 修復 plan (2 PR 想定)

### Phase A: at_bat_details.batter_canonical 補完 (修復 #1)

- 既存 1,185 row backfill: `batter` raw → `batter_canonical` 解決 (1 行ずつ)
  - 「代打・ {name}」 prefix 除去
  - giants_roster.json player + alias 全件で fuzzy match (姓 prefix / 姓名間空白吸収)
  - 残りは「{team_code}_{name}」 で別 team players も補完
- 新規 insert 時 batter_canonical を必ず set (insight ingest lane 修正)

### Phase B: games.home_away 推定 (修復 #2)

- `games.opponent` + `games.game_id` で home_away 推定:
  - game_id 形式 = `YYYY-MM-DD:{home_short}-{away_short}-{game_no}` (例: `2026-05-27:g-h-02` = 巨人 home vs ソフトバンク)
  - 巨人 (g) が左 = home / 右 = away
- 1,185 game backfill + 新規 ingest 修正

### Phase C: data-site-publisher 側で 5 metric 解放 (本 ticket scope 外、 444 拡張)

修復完了後 444 phase 1.0c で query helper + Pillar section 追加:
- `fetch_risp_stats` (走者 2/3塁 状況別 batting_logs from at_bat_details aggregate)
- `fetch_venue_split_stats` (home/away 別 batting_logs)
- `fetch_vs_pitcher_hand_stats` (要 投手 roster の dominant_hand 補完も別途)
- `fetch_count_split_stats` (初球 / 2-2 等)
- `fetch_inning_split_stats` (1-3 / 4-6 / 7-9 別)

## 4. 触らない範囲

- 既存 rss_fetcher / publish-notice / x-post-mail-lane / guarded-publish / WP REST mutation lane は **完全不可触**
- data-insight (anomaly 439) も既存 lane で運用中、 触らない (本 ticket は insight.db **書き手** の lane を変更する、 同じ Job)
- 既に insight.db を read してる side (data-site-publisher / x-post-mail-lane data-ranking 等) は data 質改善で恩恵を受けるだけ、 schema breaking 変更なし (新 column 追加なし、 既存 NULL 値を埋めるだけ)

## 5. risk / 副作用

- batter_canonical 補完で間違った人を join (例: 巨人吉川 vs 他球団吉川) する risk → roster の team_code で絞り込み
- home_away 推定で game_id format 例外があると wrong (極稀)
- ingest 修正は test 通って production deploy、 24h 観察必要

## 6. cost / 工数

- 工数: backfill script 1 日 + ingest 修正 1 日 + verify 1 日 = 計 3 日
- cost: insight.db file size 微増 (~1 MB)、 Cloud Run runtime 増なし

## 7. next action (user 判断後)

- (user 判断) priority 確定 (P2 → P1 へ昇格 if Phase 1.0c metric 早期に欲しい)
- (Claude 自律) Phase A backfill script 着手 → backfill 実行 → Phase B → 444 phase 1.0c で metric 解放
