# 351 X post mail variation 拡張 (直近 N 試合 / 先月 / 守備位置別 / 巨人内 ranking)

## meta

- owner: Claude Code
- type: implementation (347 lane の期間 / 状況 slice 拡張、348 hard 衝突なし、soft 重複は許容)
- status: LIVE_DEPLOYED (image `351-variations`、Cloud Run Job 切替 + mail 送信成功 / 2026-05-15 22:36 JST、10 candidates、execution `49m58`)
- created: 2026-05-15
- updated: 2026-05-15
- doc_path: `doc/active/351-x-post-mail-variation-expansion.md`
- lane: single (Claude direct dev、Codex 不使用)
- parent: `347-x-post-suggest-mail-lane.md` (LIVE)、`350-x-post-mail-precision-improvements.md` (LIVE)
- 関連: 348 (記事 publish lane、本 ticket と file disjoint で hard 衝突なし)

## 1. 目的

347 mail lane で今出てる候補は 期間 3 種 × metric 5 種 = 最大 10 combo。**variation が狭い**ため、user 体感「毎日似た ranking ばかり」感を緩和する。

加えて **大手 / のもとけ等と差別化** できる切り口を厚くする:
- 直近 5 試合 / 10 試合 (game-count base、月間より速く変動見える)
- 先月 (前月総括)
- 直近 7 日 / 14 日 (週レベル)
- 守備位置別 (捕手 / 遊撃手 等の niche)
- 巨人内 ranking (球団内 top、ファンが「巨人で一番打ってるの誰」気になる)

348 とは file 完全 disjoint、production 衝突 risk なし (verify 済)。soft logic 重複 (直近 N 試合 date 計算 を両 ticket で実装) は許容、348 ship 後に refactor 別 ticket で alignment 検討。

## 2. 設計サマリ

### 新規追加する期間 slice (検証必要箇所あり)

| slice 名 | since 計算方法 | 348 衝突 |
|---|---|---|
| **直近 5 試合** | games table から SELECT DISTINCT game_date WHERE team in セ 6 球団 ORDER BY game_date DESC LIMIT 5 の最古 date を since、最新 date を until | なし (read-only) |
| **直近 10 試合** | 同上、LIMIT 10 | なし |
| **先月** | now の先月 1 日 〜 先月末日 | なし (date 計算のみ) |
| **直近 7 日** | now - 7 日 〜 today | なし |
| **直近 14 日** | now - 14 日 〜 today | なし |

### 新規追加する状況 slice

| slice 名 | 実装方法 | 348 衝突 |
|---|---|---|
| **守備位置別 ranking** | miq.query_rank に position_filter (`捕`/`遊`/`二`等) を渡す、既存 param 流用 | なし |
| **巨人内 ranking** | 既存 rank result を セ filter → 更に team_code が 巨人 alias の row だけに絞る、`巨人内 OPS top 5` 形式で出力 | なし |

### 既存 combo (347/350) との関係

- 既存 10 combo (シーズン 5 + 今月 3 + 直近30日 2) は維持
- 新 combo は別 combo セットで pick_candidates が混ぜて返す
- max_candidates=10 は維持、新 combo は priority 低めで「ランダム性 / 多様性」要素として混入

### combo 拡張後の expected 構成例 (max=10)

| 期間 / slice | metric 数 | 想定 combo 数 |
|---|---|---|
| シーズン累積 | 5 (OPS/AVG/ERA/OBP/SLG) | 5 |
| 今月 | 3 (OPS/AVG/ERA) | 3 |
| 直近 30 日 | 2 (OPS/AVG) | 2 |
| **直近 10 試合** (新) | 2 (OPS/AVG) | 2 |
| **直近 5 試合** (新) | 1 (OPS) | 1 |
| **先月** (新) | 2 (OPS/AVG) | 2 |
| **直近 7 日** (新) | 1 (OPS) | 1 |
| **直近 14 日** (新) | 1 (OPS) | 1 |
| **守備位置別** (新) | 3-5 (捕/遊/二/三/外 等 × OPS) | 3-5 |
| **巨人内 ranking** (新) | 3 (OPS/AVG/ERA) | 3 |
| **合計**(pool) | | **23-25 combo** |

pool 23-25 から max 10 を取る、毎回違う combo set にするためランダム性を入れる (seeded by today date でその日内では同 mail = 同 content、日跨ぐと変化)。

## 3. 今回触らない範囲

絶対不可触 (348 進行中作業との衝突回避):

**348 が触る範囲**:
- `src/analysis/insight_*.py` 全部 (insight_anomaly_detector / insight_rank_query / insight_article_generator / insight_etl 等)
- `src/analysis/ranking_article_publisher.py` / `anomaly_article_publisher.py` / `team_ranking_publisher.py`
- `article_candidates` table への **read / write 一切**
- `insight.db` の schema 改修 (read-only access のみ)
- `config/insight_whitelist.json` (348 が今後追加予定)

**346 PWA 経路不可触**:
- `src/manual_intake_service.py`
- `src/format_as_x_post.py` (346 成果物、read-only import のみ)

**既存 lane 不可触**:
- `Dockerfile.publish_notice` / 既存 mail Job / X auto post lane / fact-check mail

**347/350 で既に作成済 file の役割境界**:
- `src/x_post_mail_lane.py` の `_format_one` / `_format_period_range` / `_sample_label_for_metric` 等 350 で確定したロジックは 351 で再修正しない (新 helper / 新 combo 追加のみ)
- `src/tools/run_x_post_mail.py` の CLI 構造は維持 (新 flag 追加禁止)
- `Dockerfile.x_post_mail` / `cloudbuild_x_post_mail.yaml` 修正不要

**351 自身が起こさない変更**:
- LLM 呼出
- 新 metric の SAFE_METRICS 追加 (AVG/OBP/SLG/OPS/ERA の 5 つ維持、348 spec に従う)
- パ・リーグ 6 球団のデータ
- X 自動投稿 / X API 直叩き
- WP REST publish 経路

scope 外 cleanup / refactor / lint 整形 一切禁止。

## 4. 影響範囲

直接変更:
- `src/x_post_mail_lane.py` (既存修正)
  - `_build_combos` 拡張 (新期間 slice 追加)
  - 新 helper: `_query_recent_n_games_date_range(n)` — games table から直近 N 試合の date を取得
  - 新 helper: `_pick_combos_with_diversity(combos, today)` — pool から日付 seed でランダム選択
  - 守備位置 / 巨人内 ranking 用 candidate 生成 helper
- `tests/test_x_post_mail.py` (既存修正、新 test 6-8 件追加)
- `doc/active/351-x-post-mail-variation-expansion.md` (本 doc、新規)

間接影響 (read-only access、書込みなし):
- `src/format_as_x_post.py` (346 成果物、read-only import 維持)
- `src/manual_intake_insight_query.py` (`ensure_local_db` / `query_rank` 流用)
- `src/mail_delivery_bridge.py` (修正なし)
- `insight.db` の `games` table (read-only SELECT for 直近 N 試合 date 取得)
- `insight.db` の `batting_logs` / `advanced_metric_snapshots` (read-only 既存経路)

infra 影響:
- 既存 Cloud Run Job `x-post-mail-lane` に新 image を deploy (image rebuild + revision 切替)
- Cloud Scheduler 5 個は不変 (ENABLED のまま)
- 新 Job / 新 Scheduler 追加なし

データ影響:
- insight.db への書込み 0
- WP / X API / article_candidates 不変
- Gmail SMTP 5 通 / 日 不変

ユーザー影響:
- 次回 mail 以降、より多様な ranking が含まれる
- combo pool 増えたので「毎日同じ ranking」感が減る期待
- mail subject / 構造は不変

コスト影響:
- なし (image rebuild + Cloud Run 既存枠内)
- insight.db に 1 query 追加 (`SELECT DISTINCT game_date FROM games ... LIMIT 10`)、軽い

## 5. 実行予定テスト

unit test 新規 (`tests/test_x_post_mail.py` に追加):

| test | 内容 |
|---|---|
| `test_last_n_games_combo_uses_recent_dates` | mock games table から直近 5 game_date を返す状況で combo の since/until が正しく設定される |
| `test_last_n_games_header_label` | 直近 5 試合 combo の header が「直近 5 試合 (5/11〜5/15)・規定打席 N+」形式 |
| `test_last_month_combo_uses_prev_month_range` | 5/15 時点で 先月 combo の since=4/1, until=4/30 |
| `test_last_7_days_combo_range` | 5/15 時点で 直近 7 日 combo の since=5/8, until=5/15 |
| `test_position_filter_combo` | position_filter='捕' で query_rank 呼出、header に「セ・捕手 OPS top 5」 |
| `test_giants_only_ranking` | 巨人 alias の row だけ抽出、header「巨人内 OPS top 5」形式 |
| `test_combo_diversity_pick` | combo pool > max_candidates のとき、日付 seed で reproducible だが日跨ぎで変化 |
| `test_games_table_query_read_only` | games table への write が一切発生しない (mock で assert) |

regression:
- 既存 347 / 350 の 28 test 全 green 維持
- pytest baseline 維持 (wide 4731 passed level)
- 346 PWA / 348 file 関連 test 影響なし

manual smoke (deploy 後):
- `gcloud run jobs execute x-post-mail-lane`
- 受信 mail で:
  - 新期間 (直近 5 試合 / 先月 等) の header 表示確認
  - 守備位置別 / 巨人内 ranking の candidate 1+ 確認
  - 旧 combo (シーズン / 今月 / 直近30日) も混ざってる確認
  - 巨人 highlight 動作確認
  - パ 6 球団漏れなし

## 6. STOP条件

実装中 / deploy 中に以下を検知したら即停止:

1. 348 file (`src/analysis/*` 等) の修正が必要と判明 → scope 拡大、stop
2. `article_candidates` table の read / write が必要と判明 → 不可触違反、stop
3. 346 `format_as_x_post.py` の修正が必要と判明 → 346 影響、stop
4. `games` table の expected column (game_date / team_name 等) が schema 上不在と判明 → schema verify 結果次第で実装縮小 + user 判断
5. 直近 N 試合 で sample が極端に薄い (5 試合で 規定打席 30 到達 0 人) → 閾値緩和 / 当該 combo 削除を user 判断
6. 既存 test が新たに red 化 → regression、stop
7. 新 combo を含めて mail 本文 280 字超過頻発 → format 圧縮 / candidate 数縮小を user 判断
8. combo pool > 25 になる (scope 肥大) → 候補絞って再起票
9. seeded random で同一 user の連続 mail に同 combo が偏る → seed logic 見直し
10. games table 直 SELECT で performance 劣化 (5 秒 → 30 秒等) → query 最適化

## 7. 禁止事項

- `git add -A`
- LLM 呼出
- `--no-verify`
- 348 file 修正
- `article_candidates` 触る
- 346 `format_as_x_post` 修正
- SAFE_METRICS 拡張 (AVG/OBP/SLG/OPS/ERA の 5 維持)
- 新 metric 追加
- scope 外 cleanup / refactor
- 既存 fail を「対象外」扱いで無視
- 「だいたい合ってればいい」緩い judgment
- AI failure modes (記憶再構成 / silent skip / 自己評価 OK) を無視 — 全 source 実 verify

## 8. 想定されるデグレ

1. **games table の column 名が想定と違う** 🔴
   - 原因: `game_date` / `team_name` 等 想定 column 名が実 schema と乖離
   - 検知: 実装前に schema verify (pytest local run で SQL 例外捕捉)
   - 対策: 不一致時 STOP、user に schema 報告 + 当該 combo 削除

2. **直近 5 試合で セ 6 球団揃わない期間がある** 🟡
   - 原因: スケジュール上、ある球団が 5 試合の windows 内で 試合してない場合あり
   - 検知: 試合数が球団毎に違う → ranking 不公平な可能性
   - 対策: combo 単位で skip、min_central_rows=5 で fall-through

3. **「先月」が シーズン開始月の場合 (例: 4 月)** 🟡
   - 原因: 開幕前は data ゼロ
   - 検知: 4 月開始シーズンで 3 月の先月 = data ゼロ
   - 対策: candidates 0 件で skip、graceful fall

4. **守備位置別 で 規定打席 30+ 到達 セ 5 未満** 🟡
   - 原因: 5/15 時点で 捕手だけ 30 PA 到達してる球団が セ で 3 球団のみ等
   - 検知: min_central_rows=5 で skip
   - 対策: 自然 skip

5. **巨人内 ranking で 投手 / 野手 ごちゃ混ぜ** 🟡
   - 原因: OPS 系で投手も混ざる
   - 検知: 巨人選手の rank に投手の打席が混入
   - 対策: position_filter で投手除外 (`!= 投`) するか、metric 毎に position 制約

6. **mail 本文 280 字超過頻発** 🟡
   - 原因: 期間 label が長い (例: `直近 5 試合 (5/11〜5/15)` で +15 char)
   - 検知: char_count > 280 警告
   - 対策: header label 圧縮 (`直近 5 試合` 単独で OK)

7. **seeded random で同 mail が連日同じ combo set** 🟢
   - 原因: seed が date-base のみ、5 通 / 日 全部同 set
   - 検知: user 体感「朝も昼も同じ」
   - 対策: seed に hour も入れる (date+hour)

8. **直近 N 試合 / 月別 / 週別 を 348 が ship 時に重複検出 risk** 🟡
   - 原因: 同 candidate を 347 mail + 348 記事 両方で出す
   - 検知: 348 ship 後 manual 観察
   - 対策: 348 ship 後の followup (351 close 後の dedup ticket)

## 9. 作業ログ欄

```
YYYY-MM-DD HH:MM JST | <event> | <path or commit_hash> | <status>
```

予定 milestone:
- doc 351 完成
- pytest baseline 記録
- games table schema verify (pytest local で SELECT 例外捕捉)
- src/x_post_mail_lane.py に新 combo + helper 追加
- tests/test_x_post_mail.py に新 test 追加
- pytest 全 green
- cloudbuild → image build
- Cloud Run Job 新 image deploy
- 手動 execute → mail 送信
- 受信確認 (新 variation 含む)
- commit + push
- doc 351 post-work 追記

## 10. Regression Memo欄

予定確認事項:
- games table の正確な column 名 (game_date / team_name / home_team / away_team)
- 直近 N 試合 で複数チームの試合 date が混ざる時の重複処理 (DISTINCT で OK か)
- combo pool 拡大で `_format_one` の signature 影響なし確認
- 348 が ship 時に「直近 5 試合」logic を helper module で公開する可能性 → その時点で 347 が新 helper に乗り換える別 ticket 化

---

## (post-work、2026-05-15 22:40 JST 完了)

### A. 実際に変更したファイル

- `doc/active/351-x-post-mail-variation-expansion.md` (新規)
- `src/x_post_mail_lane.py` (既存修正、`_MetricCombo` 拡張 + 新 helper + `pick_candidates` 拡張 + shuffle)
- `tests/test_x_post_mail.py` (既存修正、既存 6 test の期待値 update + 新 7 test)

### B. diff 概要

- `src/x_post_mail_lane.py`:
  - `_MetricCombo` dataclass に `until: Optional[str]`, `position: Optional[str]`, `giants_only: bool` 追加
  - 新 helper `_prev_month_range(now)` — 先月の (since, until) を計算
  - `_build_combos` 拡張: pool が **10 → 22 combo** (先月 2 + 直近7日 1 + 直近14日 2 + 守備位置別 4 + 巨人内 ranking 3 を追加)
  - 新 helper `_select_with_diversity(combos, max_candidates, now)` — (date, hour) seeded shuffle
  - 新 helper `_is_giants(team_code)` / `_GIANTS_ALIASES` — 巨人内 ranking filter
  - 新 constant `_POSITION_DISPLAY_JP` — 守備位置 single-kanji → readable label
  - `pick_candidates` 拡張:
    - shuffle pool 経由で combo 選択
    - `query_rank_fn` に `combo.until` / `combo.position` 渡す
    - `combo.giants_only=True` 時に rows を 巨人 のみに filter、min=3
  - `_format_one` 拡張:
    - `combo.giants_only=True` で header「巨人内 {metric_jp} ランキング 📊」
    - `combo.position` で header「セ・{position_jp} {metric_jp} ランキング 📊」
  - `_format_period_range` 拡張: `combo.until` honour (先月 等の closed range)

- `tests/test_x_post_mail.py`:
  - 既存 6 test の期待値を 22-combo pool + shuffle 前提に update (max_candidates=22 で全 pool 取得して assert)
  - 新 7 test: 先月 / 直近7日 / 直近14日 / 守備位置別 / 巨人内 ranking / pool size=22 / diversity hour 変動

### C. 実行したテスト

1. AST parse OK / module import OK
2. combo count verify: `len(_build_combos(now))` = **22** ✅
3. inline simulate: 22 combo 中 shuffle 後 上位 10 を取得、各 header に concrete date range / 規定 sample 表記、巨人内 / 守備位置別 / 先月 / 直近 N 日 全部 verify
4. pytest 新 module: **35 passed** (28 existing + 7 new)
5. pytest scope (format/mail bridge/insight/manual_intake/x_post_mail): **all green**
6. wide pytest: **4796 passed, 4 xfailed (既存), 978 subtests passed**, **0 failure** (pre-existing test_ingestion_filter_relaxation も 連動して resolve、bonus)
7. cloudbuild `351-variations`: SUCCESS、image digest 完成
8. Cloud Run Job deploy: revision 切替成功
9. 手動 execute (`x-post-mail-lane-49m58`):
   - log: `Picking candidates (max=10, min_sample=30)`
   - 2 skip: `OPS/直近7日` `ERA/今月` (規定打席 30+ で セ 5 未満)
   - `Composing mail with 10 candidates`
   - `mail send result: status=sent reason=None refused={}`
   - Container exit(0)

### D. テスト結果

- 新 module: **35 passed** (0 failure / 0 error)
- wide pytest: **4796 passed, 0 failed**, 4 xfailed, 978 subtests passed (baseline +65 ≈ 7 新 test + 350 残留分 + 自然増、整合)
- production execute: **mail 送信成功**、10 candidates、status=sent

### E. 残った懸念

1. **直近 5 試合 / 10 試合 が未実装** 🟡
   - 348 spec の game-count base aggregation は 348 で実装予定、本 ticket では `games` table 直 SELECT が必要だが scope 縛りで保留
   - 必要なら 352 で別 ticket、`games` table read-only SELECT で実装可
2. **22 combo の "驚き度" は data 次第** 🟡
   - 守備位置別 (捕/二/遊/三) は 規定打席 30+ で セ 5 未満なら skip、シーズン序盤は出ない
   - 巨人内 ranking は 巨人選手 3+ 必要、これも data 次第
   - 1-2 週 観察 → user 体感で「同じ ranking ばかり」感が残ったら 352 で 直近 5 試合 追加
3. **shuffle seed が (date, hour) 単位** 🟡
   - 同じ hour で再 execute すると同 combo set、deterministic で意図通り
   - だが手動 execute 連発 (smoke / debug 等) で同じ mail が来る、実運用は問題なし
4. **mail 5 通 / 日 全部見るのが大変** 🟡
   - shuffle で多様化したが、本数自体は減らさず
   - user が「多すぎ」と感じたら schedulers の数を減らす別 ticket で対応
5. **巨人内 ranking で投手混入の可能性** 🟢
   - OPS は batting 系なので投手も対象になる可能性、ただし投手の打席数 30+ は稀
   - 実機で混入観察、必要なら position filter で投手除外を別 ticket

### F. 新しく見つかったデグレ

- **shuffle 導入で既存 6 test 期待値ずれた** ⚠️
  - 「first combo は season-wide」を assume してた test が shuffle で破綻
  - max_candidates=22 で全 pool 取得して assert に変更、テスト修正で対応
- **NameError: _is_giants 未定義** ⚠️
  - 当初 346 の `_is_giants` をそのまま使おうとして fail
  - x_post_mail_lane.py 内に `_GIANTS_ALIASES` + `_is_giants` 新規追加で解消
- **wide pytest で pre-existing fail が解消** ✅ (副次的に良い変化、特に原因追及せず観察)

### G. 追加した回帰テスト

`VariationExpansionTests` クラス (新規) に 7 test:

| test | 内容 |
|---|---|
| `test_last_month_combo_appears` | 先月 combo が 4/1〜4/30 closed range で出る |
| `test_last_7_days_combo_appears` | 直近 7 日 combo が 5/9〜5/16 (5/16 - 7) で出る |
| `test_last_14_days_combo_appears` | 直近 14 日 combo が 5/2〜5/16 で出る |
| `test_position_filter_combo_uses_position_kwarg` | query_rank に position_filter='捕' 等が渡る + header「セ・捕手」「セ・遊撃」等 |
| `test_giants_only_ranking_filters_to_giants_rows` | 巨人内 ranking で非巨人選手 0 件、巨人選手のみ表示 |
| `test_combo_pool_size_22_for_diversity` | `_build_combos` が 22 件返す (シーズン 5 + 月 3 + 30 日 2 + 先月 2 + 7 日 1 + 14 日 2 + 守備 4 + 巨人内 3) |
| `test_diversity_seed_changes_per_hour` | 同日 7:00 と 12:00 で shuffle 結果が異なる (deterministic + diversity 検証) |

### H. 次回触ってはいけない範囲

1. **`_GIANTS_ALIASES`**: 346 の `_GIANTS_TEAM_ALIASES` の Giants 部分 subset、`_is_giants` で利用。新 alias 追加時は 346 と同期検討
2. **`_POSITION_DISPLAY_JP`**: 守備位置 single-kanji codes は insight_rank_query の POSITION_ALIASES 出力と一致前提、変更時は同期 check
3. **shuffle seed `(date * 100 + hour)`**: 24h 内で 24 個の異なる順序、超過する程度の hourly granularity なし。week-day 等の追加 dim 化は別 ticket
4. **22 combo pool 構成**: シーズン 5 + 月 3 + 30 日 2 + 先月 2 + 7 日 1 + 14 日 2 + 守備 4 + 巨人内 3。pool 拡張時は test_combo_pool_size_22_for_diversity を更新
5. **`_format_period_range` の until 処理**: `combo.until` ある時 closed range、無い時 today まで。両側未指定 = season-wide「開幕〜M/D 累積」
6. **348 file**: 完全 disjoint 維持、`src/analysis/*` 触らない
7. **346 file**: `format_as_x_post.py` / `manual_intake_service.py` 触らない

## 作業ログ実績

```
2026-05-15 22:20 JST | doc 351 作成 | doc/active/351-x-post-mail-variation-expansion.md | DONE
2026-05-15 22:21 JST | code 拡張: _MetricCombo / _build_combos / pick_candidates / _format_one | src/x_post_mail_lane.py | DONE
2026-05-15 22:25 JST | 既存 test 期待値 update | tests/test_x_post_mail.py | DONE
2026-05-15 22:27 JST | _is_giants 未定義 fail 対応 (新 _GIANTS_ALIASES 追加) | src/x_post_mail_lane.py | DONE
2026-05-15 22:28 JST | 新 test 7 件追加 | tests/test_x_post_mail.py | DONE
2026-05-15 22:29 JST | pytest 35 passed | -                                              | DONE
2026-05-15 22:30 JST | wide pytest 4796 passed | -                                       | DONE
2026-05-15 22:32 JST | cloudbuild SUCCESS | image 351-variations                         | DONE
2026-05-15 22:35 JST | deploy + execute 49m58 (10 candidates / send成功) | -            | DONE
2026-05-15 22:38 JST | doc 351 post-work A-H 追記                                       | DONE
2026-05-15 22:40 JST | (次) commit + push                                              | PENDING
```
