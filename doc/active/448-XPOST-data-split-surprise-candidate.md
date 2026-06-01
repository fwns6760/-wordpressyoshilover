# 448 XPOST 差別化データ「驚き」候補 — inning/venue split surprise

## 1. ticket header

- **ticket id**: 448
- **status**: READY_FOR_IMPL (設計確定、 実装は次の focused 便)
- **owner**: Claude Code
- **lane**: x-post-mail-lane (候補生成のみ。 公開 X 自動投稿はしない)
- **created**: 2026-06-01
- **parent**: 447 (inning split) / 既存 data-site venue split
- **priority**: P2 (SNS 差別化、 ①②シェアカード修復の次)

## 2. 背景・ゴール

大手メディアに無い data 切り口 (序盤/中盤/終盤・本拠地/ビジター別打率) を X 投稿の
「驚き」ネタにする。 例: 「終盤に強い」「本拠地と敵地で打率が大きく違う」。
447 で inning split、 既存で venue split が **production data で検証済** (read-side only)。

**重要 (§11 遵守)**: 本 ticket は既存 **x-post-mail-lane の候補 (メール) 生成のみ**。
公開 X への自動投稿は実装しない。 user が手で投稿する既存運用を維持。

## 3. データ源 (実装済・検証済)

- `data_site_query.fetch_inning_split_stats(canonical)` → `[(phase, AB, H, AVG), ...]`
- `data_site_query.fetch_venue_split_stats(canonical)` → `[VenueSplitStat(venue, games, ab, hits, rbi, avg), ...]`
- production 検証: 吉川 終盤.296 / 序盤.200、 大城 本拠地.151 / ビジター.333 等、
  帯別 AB/H は season 合計の 97-99% (同一回 collision のみ undercount、 H は完全一致)

## 4. 検出ロジック (driver = 巨人 regular のみ)

- 対象: season AB >= 80 (regular。 小標本ノイズ回避) かつ 巨人選手
- **inning surprise**: max(phase AVG) - min(phase AVG) >= 0.120 かつ 各 phase AB >= 20
  - 例: 「終盤.296 / 序盤.200 — 終盤に強い」
- **venue surprise**: |本拠地 AVG - ビジター AVG| >= 0.120 かつ 両 venue AB >= 30
  - 例: 「敵地.333 / 本拠地.151 — ロード向き」
- 閾値 (.120 / AB gate) は config 化 (`X_POST_DATA_SPLIT_MIN_GAP` 等 env override 可)

## 5. Candidate 仕様 (x_post_mail_lane.Candidate)

- `metric`: `"inning_split_surprise"` / `"venue_split_surprise"`
- `title`: 「{選手フルネーム} {帯}に強い (打率{高}/{低})」 ([[feedback_x_post_player_naming_full_name]] フルネーム・敬称なし)
- `post_text`: 100-180 字、 熱量 ramp ([[feedback_x_post_player_naming_full_name]] と同 voice)
- `db_fact_line`: 「{帯}打率 {AVG} ({H}/{AB})」 の DB-verified 1 行
- `sample_size` = 該当 split の AB、 `sample_label` = 「season {帯} {AB}打数」
- `period_label` = "今シーズン"、 `why_now` = 「data-site 差別化 metric」
- `signature` / topic_key: `{canonical}:{metric}` で 24h+ dedup (連日同一選手の同一切り口を抑制)
- 画像: 既存 437 ranking PNG path は使わず text only (Phase 1)。 PNG は Phase 2

## 6. 統合ポイント

- 新 `build_data_split_candidate(now, db_path) -> list[Candidate]` を x_post_mail_lane に追加
- `pick_candidates` の候補源 list に追加 (既存 comment_numeric / news_opinion / fan_voice と並ぶ)
- 既存 `_select_with_diversity` / dedup / char-count gate に自然に乗せる
  (新 metric family tag を `_candidate_metric_family_tag` に追加し、 同 family 連投を抑制)
- env flag `ENABLE_X_POST_DATA_SPLIT=1` で gate (default OFF → 観察後 ON)

## 7. 触らない範囲

- 公開 X 自動投稿 path / X live posting は不可触 (候補=メールまで)
- 既存 comment/news/fan/ranking 候補ロジックは不可触 (新 builder 追加のみ)
- data-site publisher / fetcher / scheduler / env (flag 追加以外) 不可触

## 8. test 計画

- 検出: gap>=.120 で候補化、 gap<.120 / 小標本で skip、 AB gate
- Candidate: フルネーム・敬称なし、 db_fact_line 形式、 char_count 100-180
- dedup: 同一 {canonical}:{metric} の 24h 連投抑制
- pick_candidates 統合で既存候補を壊さない (回帰)

## 9. cost / 副作用

- insight.db read-only のみ、 追加コスト ¥0、 LLM 不使用 (post_text は template)
- 公開影響なし (メール候補。 user 手動投稿)

## 10. next action

- (Claude 自律) build_data_split_candidate 実装 → tests → pick_candidates 統合 →
  x-post-mail image rebuild + Job update + `ENABLE_X_POST_DATA_SPLIT=1` → 翌日メール候補を観察
- 公開 X 自動投稿への昇格は **user 判断** (§11)
