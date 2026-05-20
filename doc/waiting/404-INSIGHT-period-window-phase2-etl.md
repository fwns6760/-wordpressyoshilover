# 404-INSIGHT-period-window-phase2-etl

## 1. ticket header

- **status**: BLOCKED_BY=403 (Stage 2、 403 完了 + 観察後着手)
- **priority**: medium (ファン視点 cut の第二弾、 403 安定後に追加)
- **owner**: Claude / **lane**: Claude
- **stage**: Phase 2 / 段階式 ([[403]] の follow-up)
- **依存**: [[project_data_insight_period_scope_2026_05_20]] memory
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/79

## 2. 目的

[[403]] では既存 schema で実装できる cut (期間 / 打順 / 本拠地 / vs 球団別) を全部入れた。 本 ticket は **ETL 軽改修 (列追加 + parse 追加) で実装できる cut 3 件** を Phase 2 として追加する。

## 3. scope

### 3.1. デーゲーム / ナイター

**追加 schema**:
- `games` に `start_hour INTEGER` 列追加 (試合開始時刻、 0-23、 NPB box 「18:00 試合開始」 から parse)
- migration: `ALTER TABLE games ADD COLUMN start_hour INTEGER`(既存 row は NULL)

**ETL parse**:
- `src/analysis/insight_etl.py` の NPB box 取り込みで「試合開始 HH:MM」 を抽出 (現状 source_kind=`npb_box` / `yahoo_box` 両方)

**publisher cross product**:
- 既存 metric × `start_hour < 17` (デーゲーム) / `start_hour >= 17` (ナイター) で分岐
- title 例: 「ナイターでの本塁打率」「デーゲーム OPS」

### 3.2. vs 左右投手

**追加 schema**:
- `pitching_logs` に `pitcher_throws TEXT` 列追加 (`'L'` / `'R'` / `'S'` / NULL)
- roster JSON (`config/giants_roster.json` + 12 球団 roster) の `throws` field を fill

**ETL parse**:
- ETL 時に投手 canonical → roster lookup で `throws` を fill
- atbats_json に投手 ID が入っているか要確認、 入ってなければ「先発 + 救援 lineup から推定」 fallback

**publisher cross product**:
- 打者 × vs 左投手 / vs 右投手 (既存 lineups.batting_side との platoon split)
- title 例: 「対左投手 .280 / 対右 .250」

### 3.3. 登板 inning 別 (リリーフ専)

**追加 schema**:
- `pitching_logs` に `start_inning INTEGER` / `end_inning INTEGER` 列追加 (登板回数)
- 既存 `appearance_order` (登板順) と組合せ

**ETL parse**:
- NPB box の登板回数表記「7 回登板」「8 回中継ぎ」 を parse
- 先発投手は `start_inning=1`, 救援は実際の回数

**publisher cross product**:
- 投手 × start_inning (7 回登板 / 8 回 / 9 回クローザー)
- title 例: 「7 回登板の防御率 1.20」「8 回 setup マン 3.50」

## 4. 不可触

- [[403]] が固めた期間 cut 体系 (試合数 / PA / 登板数 / IP) — そのまま使う
- 348 whitelist / 349 cooldown / 356 quality gate の他 check
- env / Secret / Scheduler / RUN_DRAFT_ONLY / WP既存記事 / X / publish-notice / frontend
- 既存 publisher の title format case A-D

## 5. 段階

- [[403]] 完了 + 1 週間以上の自然 fire 観察後に着手判断
- audit 便: NPB box / yahoo box の生 HTML を grep して「開始時刻 / 投手 throws / 登板回数」 取得可能性を確認
- 取得不能な field は schema 列だけ追加して NULL のまま運用 (機能無効化)

## 6. 成功条件

- migration 1 つで 3 列追加、 既存 ETL の冪等性破壊なし
- 新 cut publisher 3 種 (デーゲーム / vs 左右 / 登板 inning) が新規 post を生成
- 既存 publish に regression なし

## 7. open question (audit で詰める)

- NPB box の試合開始時刻はどの HTML element に入っている?
- 投手 throws の信頼できる source (NPB公式 roster / 各球団公式 / Wikipedia) どれを採用?
- 登板回数の parse 精度 — 「7 回中継ぎ」 か「7 回登板」 か media によって表記揺れあり
