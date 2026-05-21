# INSIGHT-007 — 全 12 球団 data + 20+ advanced metrics + UZR 代理 + rank UI

**作成日**: 2026-05-13
**前提**: INSIGHT-001〜006 着地済、`insight-nightly` Cloud Run + Scheduler 稼働、`manual-intake-service` に 2 タブ UI 配信中
**目的**: 全 12 球団 batting/pitching を蓄積、計算式で 20+ advanced metrics を出し、UZR 代理 (打球方向 + 守備位置から) で 12 球団内 rank を出す。manual-intake-service の 「データ要望」タブから検索可能にする。
**スコープ**: schema 拡張 (additive) + 全球団 roster + 全 NPB 試合 ETL + advanced metrics module + atbats parse + rank query + UI 連携。

## 3. 今回触らない範囲

- WordPress 全般（DB / 本文 / publish / SEO / noindex）
- 既存 `/manual-intake` POST 挙動、認証 flow
- 既存 INSIGHT-001〜006 の public API シグネチャ（追加は OK、改名 NG）
- 既存 Cloud Run service / job の env / secret / SA permission（追加 OK、既存削除 NG）
- 既存 Cloud Scheduler の **enable / pause / schedule** 設定
- 既存 publish 系 service / job への影響
- `master` ブランチ
- Gemini call / X API

## 4. 影響範囲

**新規追加**

- `config/all_teams_roster.json` — 12 球団の選手一覧 (name / position / role / active)
- `src/analysis/insight_advanced_metrics.py` — 計算式 module:
  - 打撃: AVG/OBP/SLG/OPS/ISO/wOBA/K%/BB%/BABIP/得点圏OPS
  - 投球: ERA/WHIP/K9/BB9/HR9/K_BB/FIP/xFIP/ERA+
  - 集計: league total / per-position aggregate
- `src/analysis/insight_atbats_parser.py` — atbats text を解析:
  - 打球方向 (左/中/右/三/遊/二/一/投/捕)
  - 打球種類 (ゴロ/フライ/ライナー/本/直)
  - 出力結果 (安打/凡退/失策)
- `src/analysis/insight_defense_proxy.py` — 守備機会 + out 変換率:
  - position × team で集計
  - 12 球団 rank 計算
  - **真の UZR ではない** が directional rank が出る
- `src/analysis/insight_rank_query.py` — rank query API:
  - 「player + position + metric」→ "X 位 / 全 N 人"
  - manual-intake-service から呼ばれる
- `tests/test_insight_advanced_metrics.py` / `test_insight_atbats_parser.py` /
  `test_insight_defense_proxy.py` / `test_insight_rank_query.py`

**追加 (schema migration、additive)**

- `data/insight/schema.sql` に新規 table 追加:
  - `teams` — 12 球団 master
  - `players` — 全球団選手 master (canonical / aliases / position / role)
  - `defense_opportunities` — 試合 × position × team の打球機会集計
  - `advanced_metric_snapshots` — 計算済み指標を月次 / 週次でスナップ
- 既存 table は不変（後方互換維持）。`batting_logs.team_role` の "giants" / "opponent" は維持しつつ、`team_name` 列を新規追加 (additive)。

**修正 (additive)**

- `src/analysis/insight_etl.py`:
  - 全 12 球団分の Giants 視点を 12 回 ETL するのではなく、1 試合あたり home/away 両方を team_name 付きで insert (既存挙動を破壊しない)
  - 既存 `etl_from_html` / `etl_fixture` の戻り値 keys は維持、追加 keys 可
- `src/analysis/insight_nightly.py`:
  - `--auto` モードで NPB schedule から **その日の全 6 試合 slug** を取得 → 順次 ETL (5 秒間隔の polite 規律維持)
  - 既存 `--slug` single モードは挙動不変
- `src/manual_intake_service.py` の Tab 2 (データ要望):
  - rank query 結果テーブル列追加 (rank / total / metric_name)
  - 検索 form に "metric" dropdown 追加 (OPS / FIP / wOBA / Range Factor 代理 etc.)
- `src/manual_intake_insight_query.py`:
  - 既存 query_candidates は不変
  - 新規 `query_rank(player, position, metric)` を追加

**修正 (Dockerfile / cloudbuild)**

- `Dockerfile.insight_nightly`:
  - 必要なら `config/all_teams_roster.json` を COPY
- `Dockerfile.manual_intake_service`:
  - 同上
- `cloudbuild_*.yaml` 変更なし
- env 変更なし

**触らないファイル**

- `src/source_*` 既存 extractor は import で再利用、edit なし
- `src/wp_client` / `src/rss_fetcher` / `src/guarded_publish_runner` / 既存 publish 系
- 既存 logs/* / 既存 Cloud Run service / job の挙動

## 5. 実行予定テスト

```
pytest tests/test_insight_advanced_metrics.py -v       # 新規
pytest tests/test_insight_atbats_parser.py -v          # 新規
pytest tests/test_insight_defense_proxy.py -v          # 新規
pytest tests/test_insight_rank_query.py -v             # 新規
pytest tests/test_insight_etl.py -q                    # regression
pytest tests/test_insight_nightly.py -q                # regression
pytest tests/test_insight_*.py -q                       # regression 全 INSIGHT 系
pytest tests/test_manual_intake_insight_query.py -q    # regression
pytest tests/test_manual_intake_service.py -q          # regression
pytest tests/test_manual_intake.py -q                  # regression
pytest tests/test_event_key_*.py tests/test_morning_*.py -q  # regression
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q  # baseline
```

実環境 smoke:
- Cloud Run job `insight-nightly` を新 image で execute → 6 試合分の data が 1 run で入る
- manual-intake-service の Tab 2 で「player=吉川, position=2B, metric=Range Factor 代理」検索 → rank 表示
- GCS bucket 容量増加 1 桁 MB (年間)、無料枠内維持

## 6. STOP 条件

INSIGHT-001〜006 継承 + 追加:

16. 既存 `etl_fixture` の戻り値 keys が変わる → 即停止 (backward compat)
17. 既存 manual-intake `/` GET 形式変化で `id="intake"` 等の form id が消える → 即停止
18. atbats text parser がアンカリングミスで誤ったポジションを位置に割り当てる → 即停止、parser fixture 拡充
19. 全球団 ingest で 1 試合 ETL が 5 分超え → 即停止、batch / async 設計見直し
20. NPB box の HTML 構造が球団によって違う (Pacific League 用に parser が壊れる) → 即停止、リーグ別 parser 必要なら別チケット
21. rank query が SQL injection 可能 → 即停止、allowlist + parameter binding 強化

## 7. 禁止事項

INSIGHT-001〜006 継承 + 以下:

- 既存 INSIGHT 系 module の public API シグネチャ変更（追加は OK）
- 既存 Cloud Run job / service の env 削除（追加は OK）
- 既存 Scheduler の enable / disable / schedule 変更（新規追加は OK、user 判断境界）
- atbats text の直接 SQL 文字列連結
- player_canonical の改名（既存 Giants 選手の名前は維持）
- `commit -a` / `git add -A` (並行 333-QA 事故再発防止、明示 path のみ stage)
- 真の UZR を装って計算結果を出す（必ず "Range Factor 代理" 等の名称で正直に表記）

## 8. 想定されるデグレ

| リスク | 対策 |
|---|---|
| schema migration で既存 DB との互換性破綻 | additive のみ（既存 column / table 不変）、CREATE TABLE IF NOT EXISTS で冪等 |
| 全球団 ingest で polite ルール違反 (NPB が rate limit) | 5 秒間隔強制を継承、6 試合 = 30 秒以上の総 fetch、cache hit で skip |
| GCS 容量爆発 | 1 試合 ~10KB × 6 × 365 = ~22 MB/年、無料枠余裕 |
| atbats text parser のミス → 守備代理が変な数字 | parser を fixture 駆動で書く、test ケース最低 30 件、誤検出は出力に "approximate" 表記 |
| 既存 etl_fixture test の期待値変化 | etl_from_html の戻り値 keys 完全維持、新規 keys のみ追加 |
| manual-intake-service revision 失敗で「手動投入」が壊れる | no-traffic deploy → smoke → flip の手順を継承 |
| advanced metric 計算が正しくない (誤った FIP 公式 etc.) | 公式定数を専用 module に集約、各 metric に独立 test で expected value 検証 |
| rank query が遅い (12 球団 × 全選手 × 全 metric) | metric snapshot を月次で precompute、live クエリは snapshot lookup のみ |
| 並行 git 干渉 (INSIGHT-006 で発生) | 明示 path のみ stage、commit 前に `git status --short` + `git diff --cached --name-status` で必ず確認 |
| Cloud Run 5 分 task-timeout 超過 | 1 試合 ETL は ~5 秒、6 試合 + sleep = ~60 秒、余裕 |

## 9. 作業ログ欄

（user GO 後着手で追記）

```
HH:MM JST | event | detail
```

## 10. Regression Memo 欄

```
HH:MM JST | observation | detail | followup
```

---

## 作業完了後の追記欄

### 1. 実際に変更したファイル
（TBD）

### 2. diff 概要
（TBD）

### 3. 実行したテスト
（TBD）

### 4. テスト結果
（TBD）

### 5. 残った懸念
（TBD）

### 6. 新しく見つかったデグレ
（TBD）

### 7. 追加した回帰テスト
（TBD）

### 8. 次回触ってはいけない範囲
（TBD）

---

## 補足: 実装する metric 一覧 (全 20+)

**打撃**: AVG / OBP / SLG / OPS / ISO / wOBA / K% / BB% / BABIP / 得点圏OPS / 打順別 OPS / vs L/R split

**投球**: ERA / WHIP / K/9 / BB/9 / HR/9 / K/BB / FIP / xFIP / ERA+ / 球数 trend / 登板間隔

**守備 (代理)**: 守備機会 / out 変換率 (Range Factor 代理) / 失策率 (data 取れれば) / 守備イニング

**リーグ比較**: 全 metric を position 別 + 全選手で 12 球団 rank 出力

**真の UZR は出さない**。出力 UI には常に「Range Factor 代理 (RF-proxy)」等の表記で「これは近似」を明示。

---

## ステップ実装計画 (GO 後に順次)

| step | 内容 | 工数 | 中断/再開可能 |
|---|---|---|---|
| 7a | schema additive migration + `config/all_teams_roster.json` 12 球団分作成 | 1日 | ✓ |
| 7b | `insight_advanced_metrics.py` 打撃 + 投球計算式 + tests | 1日 | ✓ |
| 7c | `insight_atbats_parser.py` 打球方向 parser + tests | 0.5日 | ✓ |
| 7d | `insight_defense_proxy.py` 守備機会集計 + rank | 0.5日 | ✓ |
| 7e | `insight_etl.py` を全球団 ingest に拡張 (既存 keys 維持) | 0.5日 | ✓ |
| 7f | `insight_nightly.py` `--auto` で 6 試合/日 fetch | 0.5日 | ✓ |
| 7g | `insight_rank_query.py` + manual-intake-service Tab 2 拡張 | 1日 | ✓ |
| 7h | tests 全件 pass + Cloud Run 両 image rebuild + no-traffic deploy + smoke + flip | 0.5日 | ✓ |

合計 約 5 日相当。各 step で commit + push、step 終了ごとに user に進捗報告。途中で stop OK。
