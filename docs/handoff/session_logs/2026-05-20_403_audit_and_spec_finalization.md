# 2026-05-20 403 audit + spec finalization

## audit 実施

- production DB `gs://baseballsite-yoshilover-insight/insight.db` を `/tmp/yoshilover-insight-latest.db` に pull (`src.tools.pull_insight_db_from_gcs`)
- DB stats: batting_logs 4572 / pitching_logs 2057 / games 254 / staleness 1 日
- 巨人選手 直近30日 出場: 打者 29 名 / 投手 22 名

## findings

### 🔴 1. `games.home_away` 列が直近30日 全部 `unknown` (23/23)

schema 定義は `'home' | 'away' | 'unknown'` だが、 実 ETL が NPB box から本拠地 / ビジター判定を fill していない。

→ user 判断 (2026-05-20 PM): **本拠地 / ビジター cut は完全 drop** (404 への格上げもしない)。

### 🟡 2. min_sample 仮置きが厳しすぎ (publish 過疎リスク)

| scope | 当初仮置き | audit 達成数 | 確定 |
|---|---|---|---|
| 打者 last_3_games | 12 AB | **1 名のみ** | **8 AB** |
| 打者 last_5_games | 20 AB | **1 名のみ** | **12 AB** |
| 打者 last_10_games | 35 AB | 2 名のみ | **20 AB** |
| 打者 last_30/50/100 PA | 30/50/100 | 19/16/12 名 | 仮置きそのまま (PA 自体 = threshold) |
| 投手 last_3/5/10 登板 | 登板数自体 | 17/14/7 投手 | 登板数自体を threshold (IP min なし) |
| 投手 last_5_ip | 5 IP | 17/22 | 5 IP (OK) |
| 投手 last_10_ip | 10 IP | 14/22 | 10 IP (OK) |
| 投手 last_20_ip | 20 IP | **4/22** | **廃止** (last_5/10_ip の 2 軸のみ) |

### ✅ 維持 (audit 通過)

- 打順別 (slot_order): 1番 5名 / 2番 6名 / 3番 3名 / 4番 1名固定 / 5番 3名 / 6番 4名 / 7-9番 5-7名 → ranking 成立
- vs 球団別 (opponent): DeNA 6 / 広島 5 / 中日 5 / ヤクルト 4 / 阪神 3 → 5 球団 publish 候補成立
- PA cumsum / 登板数 cumsum / IP cumsum → 既存 schema で集計可

## 確定 spec (403 反映)

**期間 cut 4 軸**:
- 打者 試合 base: last_3_games / last_5_games / last_10_games (min AB = 8 / 12 / 20)
- 打者 PA base: last_30_pa / last_50_pa / last_100_pa (PA 自体 = threshold)
- 投手 登板 base: last_3_appearances / last_5_appearances / last_10_appearances (登板数自体)
- 投手 IP base: **last_5_ip / last_10_ip** (last_20_ip 廃止、 達成 4/22 で過疎)

**ファン視点 追加 cut 2 軸** (本拠地 / ビジター 廃止):
- 打順別 (`batting_logs.slot_order` + `is_sub=0`)
- vs 球団別 (`games.opponent`)

**サバメ NG line 維持**: WHIP / BABIP / wOBA / FIP / xFIP / ISO 引き続き NG。

## 次便

- 403 ticket / README / assignments / memory `project_data_insight_period_scope_2026_05_20.md` を audit 結果で update
- update 後、 実装便 fire (audit findings 反映の新 scope vocabulary 切替 + 打順 / vs 球団別 publisher 追加)
- 影響 file: ranking_article_publisher.py / insight_anomaly_detector.py / insight_nightly.py / insight_title_guard.py / x_post_mail_lane.py / insight_etl.py / anomaly_article_publisher.py / team_ranking_publisher.py / insight_quality_gate.py
