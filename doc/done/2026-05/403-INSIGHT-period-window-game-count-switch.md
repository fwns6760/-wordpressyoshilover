# 403-INSIGHT-period-window-game-count-switch

**恒久 spec (2026-05-20 PM lock)**: 新 scope vocabulary は今後の恒久 default。 既存 post (`(週別)` / `(直近1週間)` 等の旧 label を持つもの) は **retroactive 書き換えなし**、 新 spec は cutover deploy 後の新規 publish にだけ適用。 user 明示「今後でいい。恒久的に」。


## 1. ticket header

- **status**: CLOSED LIVE_DEPLOYED_VERIFIED (image `insight-nightly:415-vs-lr-mvp` gen 81、 2026-05-21 10:02 JST 自然 fire で新 scope の publish 6 件成功、 `skip_dedup_cooldown` / `insufficient_sample` 0 件、 0 件問題解消確認)
- **priority**: high (5/20 12:00/15:00/17:00 publish 0 件の主因、 サンプル不足を構造的に直す)
- **owner**: Claude (実装) / user (GO 判断、 受け入れ試験)
- **lane**: Claude
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/77
- **stage**: Phase 1 stage 1 / 段階式 (404 / 405 は follow-up)
- **progress (2026-05-20 PM、 全 commit 直列)**:
  - Stage A1 `ee1d73d`: scope window helpers additive (game-count / PA / appearance / IP cumsum) + tests
  - Stage A2 `dabe355`: aggregate_* 統一 + focus_player kw
  - Stage A3 `17c32d6`: insight_quality_gate min_sample scope-aware (audit 値反映)
  - Stage A5 `b2a62a3`: title period labels (打席 / 登板 / 投球回) + config
  - Stage A4 prep `b46ffaa`: ETL window helpers + dispatch (PA / appearance / IP)
  - Stage A4 cutover `03a49ee`: default_jobs / counting_scopes / split scope を last_7d/weekly → last_5_games
  - Stage A4 cutover fix `e343479`: inline scope_label dict 廃止 → title_guard.period_label_for_scope 統一 (二重 label bug 回避)
  - 恒久 lock `f1df3be`: spec 恒久化 + status LIVE_DEPLOYED_OBSERVE
  - Stage B `febb2f0`: 打順別 publisher 新規 (band 化、 4 番固定回避)
- **deploy 履歴**: image `403-cutover-03a49ee` (gen 73) → `403-cutover-e343479` (gen 74、 二重 label fix) → `403-stage-b-febb2f0` (gen 75、 Stage B 同梱)
- **verify 状況 (2026-05-21 10:02 JST 自然 fire)**: image `415-vs-lr-mvp` gen 81 で 6 件 publish 成功 (平山功太/大城卓三/キャベッジ 打点 ranking + マルティネス 防御率/奪三振率 last_5_games + 平山功太 長打率)、 `skip_dedup_cooldown last_7d` / `insufficient_sample` 0 件。 新 scope vocabulary が全 path で稼働中、 5/20 12-17時 publish 0 件 の主因 (sample 不足) 解消確認。 follow-up 412 / 413 / 404 も同 image に含まれ動作確認済 (412: team_ranking last_5_games 打順別 publish / 413: マルティネス last_5_games rate metric publish / 404: 登板 inning publisher wire 完了、 inning 別 post は次回以降観察)
- **verified evidence**:
  - post 69977: 平山功太 長打率 last_5_games (403 batter rate)
  - post 69979: マルティネス 防御率 last_5_games (413 pitcher rate fix の証拠)
  - post 69981: マルティネス 奪三振率 last_5_games (413 同)
  - post 69983/85/87: 打順別 + 打点 ranking last_5_games (412 team_ranking cutover)
- **依存**: [[project_data_insight_period_scope_2026_05_20]] memory (新 scope spec lock)
- **関連**: 348 (whitelist 実装、 CLOSED) / 349 (dedup cooldown、 LIVE_OBSERVE) / 356 (data quality gate、 LIVE_OBSERVE) / 357 (mail human period labels、 LIVE_OBSERVE)

## 2. 目的 / 背景

2026-05-20 user lock。 data-insight 期間 cut を **日付 base (last_7d / last_30d) から 試合数 / 打席 / 登板数 / 投球回 base に全面切替**。 ファン視点 cut (打順別 / 本拠地 / vs 球団別) を同 stage で同梱。

### 現状の問題 (5/20 logs)

- 12:00 / 15:00 / 17:00 JST の 3 便で publish 0 件
- 主因: 356 quality gate `insufficient_sample`
  - 浦田俊輔 OPS/AVG/OBP last_7d sample=13 / min=20
  - 平山功太 SLG last_7d sample=13 / min=20
  - マルティネス ERA/K_per_9 last_7d sample=3 / min=10
- 日付 window が試合のない日に sample 不足で潰れる構造問題

### 切替方針

固定 sample 数 (試合数 / 打席 / 登板数 / 投球回) で切れば「最近の活躍」 が常に同じ粒度で出せる。

## 3. 新 scope spec (lock、 user 確定 2026-05-20 / audit 反映)

### 期間 cut (4 軸、 日付 cut 全廃)

| 対象 | scope vocabulary | counting base |
|---|---|---|
| 打者 試合 base | `last_3_games` / `last_5_games` / `last_10_games` | 巨人試合数 cnt (出場有無関係なし、 ベンチ含む) |
| 打者 打席 base | `last_30_pa` / `last_50_pa` / `last_100_pa` | 当該選手 PA cumsum |
| 投手 登板 base | `last_3_appearances` / `last_5_appearances` / `last_10_appearances` | 当該投手 appearance cnt |
| 投手 IP base | `last_5_ip` / `last_10_ip` | IP cumsum (last_20_ip は audit で 4/22 達成のみ → 廃止) |

`last_7d` / `last_30d` 等日付 window は **全廃止** (`season` scope は維持)。

### ファン視点 追加 cut (2 軸、 既存 schema で実装可能)

| cut | 使う field | 例 |
|---|---|---|
| 打順別 | `batting_logs.slot_order` + `is_sub=0` | 「3 番打者として last_5_games で .380」 |
| vs 球団別 | `games.opponent` | 「対阪神 last_5_games .400」 |

**廃止 cut (audit で発覚)**:
- 本拠地 / ビジター: 実 ETL が `games.home_away` を fill していない (直近30日 23/23 試合 `unknown`)。 user 判断 (2026-05-20) で **完全 drop** (404 への格上げもしない)。

### サバメ NG line 維持

WHIP / BABIP / wOBA / FIP / xFIP / ISO は引き続き NG。 [[project_data_insight_final_whitelist_2026_05_15]] の whitelist (counting + 標準率 + 投手 /9 系率 + WAR + UZR + 得点圏打率 + 球団 ranking + record/milestone) は据え置き、 scope vocabulary だけ入れ替え。

### title 表記

| 旧 | 新 |
|---|---|
| `(直近1週間)` | `(直近5試合)` / `(直近30打席)` 等 |
| `(直近1ヶ月)` | `(直近10試合)` / `(直近50打席)` 等 |
| `(直近5試合)` (既存 348 case) | 維持 (新 scope vocabulary に統一) |

case A-D title format ([[project_data_insight_final_whitelist_2026_05_15]] 定義) は据え置き、 期間 label だけ入れ替え。

### min_sample (audit 結果反映、 2026-05-20 確定)

| scope | min_sample 確定 | audit 達成数 (29名/22名 base) |
|---|---|---|
| 打者 `last_3_games` | **8 AB** | 上位 5 名 (仮置き 12 → 1 名のみ → 8 に下げ) |
| 打者 `last_5_games` | **12 AB** | 7 名 (仮置き 20 → 1 名のみ → 12 に下げ) |
| 打者 `last_10_games` | **20 AB** | 8 名 (仮置き 35 → 2 名のみ → 20 に下げ) |
| 打者 `last_30_pa` | 30 | 19 名 (仮置きそのまま OK) |
| 打者 `last_50_pa` | 50 | 16 名 (OK) |
| 打者 `last_100_pa` | 100 | 12 名 (OK) |
| 投手 `last_3_appearances` | 登板数 3 のみ (IP min 無し) | 17 投手 |
| 投手 `last_5_appearances` | 登板数 5 のみ | 14 投手 |
| 投手 `last_10_appearances` | 登板数 10 のみ | 7 投手 |
| 投手 `last_5_ip` | 5 IP | 17/22 |
| 投手 `last_10_ip` | 10 IP | 14/22 |
| ~~投手 `last_20_ip`~~ | ~~廃止~~ | 4/22 → publish 過疎で廃止 |

audit 詳細: `docs/handoff/session_logs/2026-05-20_403_audit_and_spec_finalization.md`

## 4. 実装 scope

### 4.1. affected files (grep 結果、 67 reference)

- `src/analysis/ranking_article_publisher.py`
- `src/analysis/insight_anomaly_detector.py`
- `src/analysis/insight_nightly.py`
- `src/analysis/insight_title_guard.py`
- `src/x_post_mail_lane.py`
- `src/analysis/insight_etl.py`
- `src/analysis/anomaly_article_publisher.py`
- `src/analysis/team_ranking_publisher.py`
- `src/insight_quality_gate.py` (356 で追加された min_sample 判定)
- `data/insight/schema.sql` (advanced_metric_snapshots.scope の comment 更新、 schema 変更なし)

### 4.2. 段階

1. **audit 便** (read-only): 上記 8 file の `last_7d` / `last_30d` 使用箇所を list 化、 DB 実分布で min_sample 仮置きを詰める
2. **scope vocabulary 切替**: `last_Nd` 名称を新 vocabulary に置換、 advanced_metric_snapshots へ insert 時の scope 文字列も更新
3. **counting logic 実装**: 試合数 / PA / 登板 / IP の cumsum で window 切り出す関数追加 (insight_etl.py)
4. **min_sample 再算出**: insight_quality_gate.py の `min_sample` table を新 scope に対応
5. **dedup scope_family 更新**: 349 の `metric_all_periods` family を新 scope set 対応
6. **追加 cut publisher**: 打順別 / 本拠地 / 球団別 で既存 metric を cross product
7. **title 表記**: insight_title_guard.py の期間 label 一覧更新

### 4.3. 不可触

- DB schema 変更なし (advanced_metric_snapshots.scope は TEXT、 文字列値だけ拡張)
- env / Secret / Scheduler / RUN_DRAFT_ONLY / WP既存記事 / X / publish-notice / x-post-mail-lane の wiring / frontend
- 348 whitelist (metric 一覧) / 349 cooldown 日数 (7 日) / 356 quality gate の他 check (stale snapshot / ranking coverage)
- title format case A-D (期間 label だけ入替、 構造変更なし)
- 既存 published 記事の retroactive cleanup (新規分だけ新 scope、 既存はそのまま)

## 5. 成功条件

- audit 便: `last_7d` / `last_30d` 使用箇所 list + DB 実分布 + min_sample 仮置き決定
- 実装便: 上記 8 file 改修、 targeted pytest green、 既存 regression 0
- deploy 後 verify: 1 nightly で新 scope の publish が出る、 サンプル不足 skip が 5/20 比で減る、 dedup cooldown が新 scope_family で blocked

## 6. 動作確認

- ローカル: `pytest tests/test_insight_*` 全 green
- production DB copy: 新 scope vocabulary で SELECT が走る、 sample 分布が想定範囲
- live deploy 後: `gcloud run jobs execute insight-nightly` 手動 trigger は **追加 publish/mail 回避のため未実行**、 翌朝 (07:00 JST) の自然 fire 観察待ち
- post 観察: 新 scope 表記 (`(直近5試合)` 等) が title に出る、 打順別 / 本拠地 / 球団別 cut の post が新規に出る

## 7. 段階式 follow-up (別 ticket)

- **404** (Stage 2、 DRAFT): Phase 2 ETL 改修 (デーゲーム / vs 左右 / 登板 inning) — 403 完了 + 観察後
- **405** (Stage 3、 PARKED): Phase 3 (打席内カウント / 走者状況詳細) — pitch-by-pitch source 検討から

## 8. open question (audit 後の残)

- **打順別の slot_order 集約単位**: 1番 / 2番 / 3番 を個別か、 「先頭打者 (1-2)」 「中軸 (3-5)」 「下位 (6-9)」 で band 化するか。 audit 結果 (1番 5名 / 4番 1名固定) を見ると個別 publish は 4 番 (固定選手なら岡本) で同じ選手だらけになるリスク、 band 化が無難
- **vs 球団別の min 試合数**: 直近30日 で vs 阪神 3 / ヤクルト 4 試合のみ → last_5_games スコープだと取れる試合が 1-3 程度。 vs 球団別 cut は last_30_pa / last_10_games の長 scope のみ enable、 short scope は disable が現実的
- **打順 × 期間 cut の cross product**: 全部出すと publish 過剰、 max_per_run cap で抑える前提

## 9. audit 詳細

`docs/handoff/session_logs/2026-05-20_403_audit_and_spec_finalization.md`
