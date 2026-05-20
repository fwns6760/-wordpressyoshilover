# 348-INSIGHT-whitelist-implementation-step1-to-3

## 1. ticket header

- **status**: CLOSED (2026-05-15 LANDED + production verified、 README L1803 で CLOSED 確定済、 doc 側 stale だったので update。 commits `86d4724` → `bf010ba` → `8b962e5` → `7a10c6e` → `21a8e7a`、 tests 389 passed、 production で 4 巨人データ post 生成 verify 済)
- **priority**: high (× metric 漏れが現状起きている)
- **owner**: Claude (実装) / user (GO 判断)
- **依存**: `doc/reference/data-insight-metric-whitelist.md` (2026-05-15 lock)
- **依存**: `docs/handoff/session_logs/2026-05-15_data_insight_metric_implementation_audit.md` (audit findings)

## 2. 目的 / 背景

2026-05-15 user lock した metric whitelist (◯ 13 群 / × サバメトリクス系) を実コードで守る。 audit findings から、現状 3 つの問題:

1. **× metric 漏れ**: `all_batter_metrics()` / `all_pitcher_metrics()` が ISO / wOBA / BABIP / FIP / xFIP 等 × metric を全部計算 → publish 経路に metric_name 単位の whitelist gate が無い → 流出。 大城 UZR が連日 publish された件の根本原因。
2. **◯ 新規項目の未実装**: 直近 5 試合 / 10 試合 / 月別 / 週別 / counting stats publisher / 連勝連敗 / record-milestone 等が未実装。
3. **設定値が code に散在**: whitelist / 閾値 / title format が Python source 内 hardcode、 spec doc (`doc/reference/data-insight-metric-whitelist.md`) と code が分離。 実装時に spec を見落とすと bug 起こる risk。

本 ticket は audit ステップ 1-3 を実装する。ステップ 4 (球場別 / WAR / 得点圏打率 schema 改修) は本 ticket では触らない、別 phase。

## 2.5. 設計確定事項 (2026-05-15 user lock、 実装はこの仕様に従う)

### 閾値方針 (BCD 採用 + 具体値)

- 率系の閾値 = **1.5σ** (上位 7% 拾う、 タイトル争い圏内)
- counting (本塁打数 / 勝利数 等) = **ranking TOP 10** (12 球団から抽出)
- record / milestone = 発生時のみ、 閾値無し
- 対象選手 = **巨人選手のみ** (記事 title 主語、 比較計算は 12 球団 baseline)
- 期間 slice: 直近 5 試合 / 直近 10 試合 / 月別 / 週別 / シーズン 全部 1.5σ ベース

### title format 仕様

**共通 rule**:
- prefix: **`【巨人データ】`**
- 主語: 巨人選手 / 巨人 チーム
- metric 表記: **日本語** (例外で英略号 OK = OPS / UZR / WAR の 3 つだけ)
- 数値: `.XXX` 形式 (省略小数点)
- 期間: **末尾の括弧書き**
- 短すぎ / `…` truncation / event 重複 NG

**case A: 個人記録 (期間 stat)** — 順位 + 期間 入れる
```
【巨人データ】<選手> <metric> <値>、 リーグ N 位 (<期間>)
例: 【巨人データ】<選手> 打率 .315、 リーグ 3 位 (今シーズン)
```

**case B: 試合後イベント (1 試合の活躍)** — 順位 入れない、 試合日 を期間に
```
【巨人データ】<選手> <event> (<試合日> vs <対戦相手>)
例: 【巨人データ】<選手> 本塁打 + 4 打点 (5/15 vs 阪神)
```

**case C: 通算 / record / milestone** — 順位 入れない、 達成日
```
【巨人データ】<選手> <達成内容> (<達成日>)
例: 【巨人データ】<選手> 通算 300 号本塁打 (5/14)
     【巨人データ】<選手> サイクル安打 達成 (5/15 vs 阪神)
     【巨人データ】<選手> 11 試合連続安打 (5/15 時点)
```

**case D: 球団 ranking (球団主語)**
```
【巨人データ】チーム <metric> <値 or 順位> (<期間>)
例: 【巨人データ】チーム本塁打数 リーグ 2 位 (今シーズン)
     【巨人データ】チーム 4 連勝 (5 月)
```

**判定軸**: 「読者が気になる」を base に、 個人記録なら順位 + 期間 default 表示、 「いらない場合」あり (個別判断)。

### 周辺 policy 確定 (2026-05-15 user lock)

- **eyecatch**: 既存 `src/player_eyecatch_resolver.py` + `src/eyecatch_fallback.py` + `config/player_eyecatch_map.json` の rule をそのまま使用、 data 系記事の特別扱いなし
- **noindex**: data 系記事も noindex **維持**
- **X 投稿**: 自動 publish 禁止、 X 候補が自動生成された時点で **mail で user 通知** → user 手動投稿判断
- **規定打席**: DB query で sample 分布を verify ベースで判断 (推測しない、 期間別の緩い/厳しいは設けない)

### 画面設計 policy 確定 (2026-05-15 user lock、 昨日の form ベース)

**昨日の form 流用 (2026-05-14)**:
- 表中心 layout (ranking 表形式)
- 焦点選手 = 赤太字 + ★ marker
- 「ひとこと」 section (平易解説)
- ranking 上位 10 のみ表示
- セ / パ リーグ別 ranking (リーグ横断 NG)

**今日変更点**:
- ❌ 「大手にない」 banner 廃止 (全種類で省略)
- ❌ SVG chart 廃止 (崩れリスク、 表形式で代替)
- ❌ 試合後記事冒頭の試合スコア表示 入れない
- ✅ 史上 N 人目 / 何年ぶり (record/milestone) 入れる、 lookup は手動 (record DB 整備しない)

**全種類で表形式 layout 採用**:
- ranking 系: 既存 ranking 表 (昨日と同じ)
- 試合後イベント: box score 抜粋を表形式 (打数 / 安打 / 本塁打 / 打点 / 走塁 等)
- record / milestone: 過去 record リスト + 本日達成者を強調 行
- 球場別: schema 改修着手時に一緒に decide (= 後回し、 今 lock しない、 whitelist には ◯ で残す)

### config file 化方針 (新規追加、 user 「追加して」確定、 形式 = JSON)

- 新規 JSON config file 作成: `config/insight_whitelist.json` (既存 config/ pattern fit、 stdlib のみ)
- 内容: ◯/× metric list / threshold (1.5σ, TOP 10, 巨人のみ) / period_scopes / title_format (case A/B/C/D)
- code 改修: `insight_anomaly_detector.py` / `anomaly_article_publisher.py` 等が起動時に JSON 読み込み
- ENV override 維持 (緊急時 hotfix 用)
- spec doc (`doc/reference/data-insight-metric-whitelist.md`) は人間 / AI 用 source of truth として並列維持、 JSON との同期は手動 (git commit 時に両方更新)
- 着手位置: 348 ticket **ステップ 1 の前半** で config file を先に作る、 その後 whitelist gate を wire
- 形式変更 history (2026-05-15 user 「バグデグレ少ない方」発言で YAML → JSON):
  - YAML 採用時の risk: PyYAML 追加依存 → Cloud Run image rebuild → デグレ面積拡大
  - JSON 採用の merit: stdlib `json` のみ / 既存 config/ pattern fit (12 file 全部 JSON verify 済 by ls) / 新規依存なし

### 重複記事抑制 plan (別 ticket 349 で起票済)

2026-05-15 user 「起票が必要なら起票していいよ。デグレバグの観点で判断して」発言を受け、 デグレバグ防止観点で **C (別 ticket 起票)** を Claude が judgment、 349 として独立 ticket 化:

- **349-INSIGHT-dedup-cooldown-cascade** (`doc/active/349-INSIGHT-dedup-cooldown-cascade.md`)
- GH Issue #27: https://github.com/fwns6760/-wordpressyoshilover/issues/27
- memory: `project_data_insight_duplicate_prevention_plan_2026_05_15.md`

着手 timing: **348 deploy 完了 → 観察 → 重複問題実態 verify 後** に 349 着手 (段階 deploy / regression リスク isolate)。 本 348 ticket では重複対策の実装は **行わない**。

---

## 3. 今回触らない範囲

- **ステップ 4 領域** (本 ticket 対象外):
  - 球場別 slice (schema migration が必要、別 ticket で扱う)
  - WAR (NPB 公式計算式なし、community 値選定が要る、別 ticket)
  - 得点圏打率 (`atbats_json` 走者情報 verify が必要、verify 結果次第で本 ticket か別 ticket かを決める)

- **既存稼働 detector / publisher** (動作維持のため触らない):
  - 試合後イベント 5 種類 (game_hero_batter / game_pitcher_perf / milestone_crossed / standings_shift / 大幅好成績 σ外れ値)
  - 守備率 outlier (`anomaly_defense_fielding_pct`)
  - z-score 異常値 detector の core logic (whitelist gate の追加のみ、existing logic はそのまま)

- **インフラ / 設定**:
  - env / Secret Manager の値
  - Cloud Run revision の deploy 設定
  - Scheduler の起動時刻 / 頻度
  - WP REST 経由の content 削除 / 書き換え
  - X / SNS / mail 経路の wholesale 改修

- **repo 外**:
  - 親 repo `baseballwordpress` の code
  - 他 repo

- **DB schema (本 ticket では migration なし)**:
  - `games` table への column 追加 (球場名カラム等は本 ticket では触らない)
  - 既存 table の constraint / PK 変更
  - 例外: `advanced_metric_snapshots.scope` は TEXT 列で新 scope 値 (`last_5_games` / `last_10_games` / `monthly` / `weekly`) を受けるだけなので migration 不要 (verify 済)

---

## 4. 影響範囲

### code 変更が入る file

| file | 変更内容 |
|---|---|
| `src/analysis/insight_anomaly_detector.py` | × metric whitelist gate 追加 (`metric_name` 単位の filter)、 ALL_ANOMALY_SIGNALS は不変 |
| `src/analysis/insight_etl.py` | `compute_advanced_metric_snapshots` 拡張: `last_5_games` 分岐実装、`last_10_games` / `monthly` / `weekly` 追加。`_scope_window` 拡張。`_aggregate_last_n_games_batting_line` / `_aggregate_last_n_games_pitching_line` 新規追加 |
| `src/analysis/insight_advanced_metrics.py` | 日本語 label mapping helper 追加 (`metric_name_ja(metric_name)`)。勝率 / 守備率 (個別計算) を `all_*_metrics` に追加 |
| `src/analysis/ranking_article_publisher.py` | counting stats ranking publisher 拡張 (本塁打数 / 勝利数 / 奪三振数 等)。 ホーム/アウェイ別 / 対戦相手別 grouping |
| `src/analysis/anomaly_article_publisher.py` | publish 経路に whitelist gate 連携。 metric_name → 日本語表記の mapping (OPS / UZR / WAR 以外は日本語)。新 scope (`last_5_games` 等) の日本語表記 |
| `src/analysis/insight_nightly.py` | 新 scope (`last_5_games` / `last_10_games` / `monthly` / `weekly`) を nightly 実行に追加 |
| `src/analysis/team_ranking_publisher.py` | 連勝 / 連敗 / 得失点差 / 対戦相手別 (vs 阪神 / vs DeNA 等) の球団 ranking 拡張 |
| `tests/test_insight_*.py` | 既存テスト維持 + 新規追加 |

### 新規追加 test file (見込み)

| file | 内容 |
|---|---|
| `tests/test_insight_whitelist_gate.py` | × metric が article_candidates に insert されないことを確認 |
| `tests/test_insight_etl_last_n_games.py` | 直近 5 / 10 試合 aggregation の logic test |
| `tests/test_insight_etl_monthly_weekly.py` | 月別 / 週別 aggregation の logic test |
| `tests/test_counting_stats_publisher.py` | counting stats ranking publisher 動作確認 |
| `tests/test_record_milestone_detector.py` | サイクル / ノーノー / 完全試合 / 連続安打 / 連続奪三振 検出 |

### 直接触らない file (依存先のみ)

- `data/insight/schema.sql` (本 ticket では migration なし、scope TEXT 列に新値が入るだけ)
- `data/insight/insight.db` (実 production data、 ETL 経由で更新のみ)
- `config/*.json` (既存 file は touch 不要、 新規 `config/insight_whitelist.json` のみ追加)
- WP 側 plugin / theme

---

## 5. 実行予定テスト

### 既存テスト (regression 防止)

`pytest tests/test_insight_*.py` 全部 pass 必須。 関係 file:

- `test_insight_advanced_metrics.py`
- `test_insight_anomaly_detector.py`
- `test_insight_etl.py`
- `test_insight_etl_seed_teams.py`
- `test_insight_etl_seed_players_from_logs.py`
- `test_insight_etl_compute_advanced_metric_snapshots.py`
- `test_insight_etl_team_aware_roster.py`
- `test_insight_multi_game_detector.py`
- `test_insight_defense_proxy.py`
- `test_insight_atbats_parser.py`
- `test_insight_nightly.py`
- `test_insight_schedule.py`
- `test_insight_fetcher.py`
- `test_insight_lineup_history.py`
- `test_insight_nl_query.py`
- `test_insight_rank_query.py`
- `test_insight_article_generator.py`
- `test_insight_markdown_summary.py`
- `test_insight_gcs_sync.py`
- `test_manual_intake_insight_query.py`
- `test_cache_hit_split_metric.py`

### 新規追加テスト

ステップ別:

**ステップ 1 (× フィルター)**:
- ISO / wOBA / BABIP / FIP / xFIP / WHIP / K_BB / 守備RF / 守備UZR が `article_candidates` table に insert されないことを確認
- ◯ metric (OPS / ERA / K_per_9 / 守備率 等) は通常通り insert されることを確認
- 既存 published article への side effect 無し

**ステップ 2 (軽修正)**:
- metric_name → 日本語 label mapping が OPS / UZR / WAR 以外を日本語化
- 勝率 / 守備率 個別計算が `all_*_metrics` に含まれる
- ホーム/アウェイ別 / 対戦相手別 grouping が正しい count を返す

**ステップ 3 (中作業)**:
- 直近 5 試合 / 10 試合 aggregation: fixture data (game_id 6 件) で 5 件 / 10 件 window の OPS 計算が手計算と一致
- 月別 / 週別 aggregation: game_date `2026-04` / `2026-W18` 等のグルーピングが正しい
- counting stats ranking publisher: 本塁打数 top 5 が ranking 通り出る
- 連勝 / 連敗 / 得失点差: standings_snapshots fixture から正しく算出
- サイクル安打 / ノーノー / 完全試合 detection: fixture per-PA で陽性 / 陰性ケース両方 test

### 実行コマンド

```
cd /home/fwns6/code/wordpressyoshilover
python -m pytest tests/test_insight_*.py -v
python -m pytest tests/test_insight_whitelist_gate.py -v
python -m pytest tests/test_insight_etl_last_n_games.py -v
# (他新規 test 同様)
```

---

## 6. STOP 条件

実装中に以下のいずれかを検出したら即停止 + user 報告:

1. **既存テスト regression**: pytest 既存 test が 1 件でも fail
2. **動作中 detector 破壊**: 試合後イベント / 守備率 outlier / 標準率 z-score の output が変化
3. **× metric 流出**: 修正後に × metric が新たに publish 経路に流れる
4. **scope 外破壊**: env / Secret / Scheduler / WP REST / 親 repo / 球場別 / WAR の改修が必要になる
5. **schema migration 要請**: 計画外で table column 追加 / 制約変更が必要になる
6. **得点圏打率 data verify 結果が NG**: `atbats_json` に走者情報が無く ETL 改修が必要 → ステップ 4 級と判定して本 ticket から外す
7. **既存 published article への impact 検出**: title / 本文形式 / link 構造の wholesale 変更
8. **AI 事故源 trigger**: 「記憶から再構成 / silent skip / 自己評価 OK」を自分が踏みかけた時点で stop & 訂正

---

## 7. 禁止事項

- code commit / push (本 ticket は plan phase、user GO 後のみ)
- deploy / gcloud / Cloud Run / Cloud Build 実行
- env / Secret Manager 値変更
- Scheduler の起動時刻 / 頻度変更
- WP REST 経由の content 削除 / 書き換え / 新規 publish
- X / SNS への発信
- 親 repo `baseballwordpress` への変更
- 球場別 / WAR / 得点圏打率 schema 改修への scope 拡張
- × metric の whitelist 化 (◯ 化、これは user 確定済 whitelist に違反)
- 試合後イベント detector / 守備率 outlier / 標準率 path の wholesale 改修
- `data/insight/insight.db` (production data) への直接 SQL 操作 (read-only のみ可、書き込みは ETL 経由)
- `auth.json` / Secret 値の chat / log / commit / mail への露出
- `git add -A` (移動・更新した path だけ明示 stage)
- `--no-verify` / `--no-gpg-sign` 等の hook skip

---

## 8. 想定されるデグレ

### 高確率デグレ

- **既存 published 記事の title / 本文 形式の意図しない変化**: label 日本語化が記事 title に直接反映されると、過去記事との表記揺れが発生
- **直近 5/10 試合 publish 過剰**: 349 ticket の cooldown / dedup を deploy しないと連日重複発生 (ただし 5/15 DB verify で実 publish 件数は 15-30 件 / 日 と判明、 元推測「50-80 件」より小さい)
- **whitelist gate の誤検出**: gate logic が ◯ metric も誤って block すると publish 件数 0 になる

### 中確率デグレ

- **nightly job 処理時間増加**: 新 scope (5_games / 10_games / monthly / weekly) 追加で aggregation 計算量が倍増、Cloud Run 無料枠超過 risk
- **DB 容量増**: `advanced_metric_snapshots` row 数が scope 数 × snapshot 数で増加 (現状 1 snapshot で 1625-2634 行)
- **既存 candidate status 上書き**: 新 detector が `status='NEW'` の旧 candidate を意図せず変える
- **mail layer 既存 dedup と干渉**: `publish_notice_email_sender.py` に 30 分 dedup / 10 分 replay / 10 件 burst 抑制 / 100 件 daily cap 既存、 publish 件数増加で burst threshold (10 件) 超えると summary 化される可能性

### 低確率デグレ

- 既存 nightly schedule の起動順序を意図せず変える
- 既存 test fixture が新 scope 値を含まない / 含む parse 失敗
- DB integrity (FK / PK) 制約違反

### user 影響

- **mail 配信件数の急増 (verify 済で訂正)**: 5/15 DB verify で 1.5σ 採用時 ~13 件 / 日 (3 scope 合計)、 新 scope 追加で +10-20 件 / 日、 合計 **15-30 件 / 日** が妥当な予測 (元推測 50-80 件は過剰評価)、 mail layer の 100 件 daily cap には余裕あり
- **記事 title 表記揺れ** (label 日本語化前後で同 metric が違う表記になる可能性)

---

## 9. 作業ログ欄

(実装中追記、 user GO 後に作業開始)

```
YYYY-MM-DD HH:MM JST | <event> | <step> | <task> | <next>
```

---

## 10. Regression Memo 欄

(実装中追記、 検知した regression / 回避策 を 1 行で記録)

```
YYYY-MM-DD HH:MM JST | <test> | <regression> | <fix> | <test added>
```

---

# 作業後追記 (user GO 後、各 step 完了時に埋める)

## 1. 実際に変更したファイル

(未記入)

## 2. diff 概要

(未記入)

## 3. 実行したテスト

(未記入)

## 4. テスト結果

(未記入)

## 5. 残った懸念

(未記入)

## 6. 新しく見つかったデグレ

(未記入)

## 7. 追加した回帰テスト

(未記入)

## 8. 次回触ってはいけない範囲

(未記入)
