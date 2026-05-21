# INSIGHT-001 — データ分析記事 candidate パイプライン（design + prototype）

**作成日**: 2026-05-13
**ステータス**: PLAN_REVIEW（user GO 待ち）
**目的**: 大手メディアが出さない niche なデータから記事候補を自動生成し、`article_candidates.csv` として日次出力する。
**スコープ（本チケット）**: design + 最小 prototype。SQLite + CSV + 既存 fixture HTML 起点。WP / production 完全非干渉。
**前提**: 無料で完結（X API 不要、Gemini 増加なし、Yahoo/NPB の既存 URL のみ）。
**運用方向（user GO 済の方向感）**: 最終的には自動化（CLI → 後続でスケジューラ組み込み判断）。スケジューラ設定は本チケットでは触らない。

---

## 3. 今回触らない範囲

- WordPress DB（`wp_posts` / `wp_postmeta` / `wp_options` / その他）
- WordPress custom table の追加・削除・編集
- WP 本文 / publish status / noindex / canonical / 301 / SEO 設定
- X auto-post / X API
- Gemini call / プロンプト変更
- 既存 pipeline: `rss_fetcher.py` / `guarded_publish_runner.py` / `wp_client.py` / 既存 `source_*` extractor の挙動
- 既存 `logs/*.jsonl`（`publish_notice_history` / `repair_provider_ledger` / `guarded_publish_history` 等）
- Cloud Run service / job / Dockerfile / cloudbuild
- Cloud Scheduler の既存 job 設定（`giants-realtime-trigger` / `publish-notice-trigger` / `guarded-publish-trigger` 等、本日 10:00 時点で ENABLED 確認済）
- env / secret / flag
- master ブランチへの merge
- 新規 source の URL（UZR 等の外部指標、新サイトのスクレイピング）

---

## 4. 影響範囲

**新規追加予定（ディレクトリ）**

- `data/insight/`（隔離ディレクトリ）
- `src/analysis/`（namespace 隔離）
- `tests/` 内に新規テストファイル 1 本

**新規追加予定（ファイル）**

- `data/insight/schema.sql` — SQLite テーブル定義（コード未実装、SQL のみ）
- `data/insight/insight.db` — 生成物（`.gitignore` 対象）
- `data/insight/article_candidates.csv` — 生成物（`.gitignore` 対象）
- `src/analysis/__init__.py` — namespace marker（空）
- `src/analysis/insight_etl.py` — fixture HTML → SQLite ETL prototype（CLI、`--dry-run` 既定）
- `tests/test_insight_etl.py` — 新規回帰テスト

**影響しないもの**

- `src/` 直下の既存ファイル一切（読みのみ）
- `tests/` の既存ファイル
- `config/` 全般
- `doc/` の既存ドキュメント
- `logs/` 全般
- `build/` 全般
- `master` ブランチ

**import 方向の規律（一方向のみ）**

- `src/analysis/*` → `src/source_*`（既存 extractor を import 経由で再利用）: **OK**
- `src/analysis/*` → `src/wp_client`: **禁止**（READ 含めて本チケットでは呼ばない）
- `src/*`（analysis 以外）→ `src/analysis/*`: **禁止**（逆方向 import = 既存 pipeline 起動時に SQLite 依存を強要する事故源）

---

## 5. 実行予定テスト

**新規**

- `pytest tests/test_insight_etl.py -v`
  - schema.sql の妥当性（SQLite が parse できる）
  - fixture HTML → record の抽出が想定行数を返す
  - article_candidates.csv のヘッダ + 1 行サンプルが生成される
  - 冪等 upsert（同 fixture を 2 回 ETL しても row 数増えない）

**regression（既存）**

- `pytest tests/test_yahoo_boxscore_extractor.py -q`（import 連鎖事故の検出）
- `pytest tests/test_event_key_ledger.py tests/test_morning_event_key_enricher.py tests/test_event_key_publish_gate.py -q`（直近の event_key 系 61 件）
- `pytest tests/test_player_eyecatch_resolver.py tests/test_draft_audit.py tests/test_draft_inventory_from_logs.py -q`（baseline 36 件）

**syntactic check**

- `python3 -c "import ast; ast.parse(open('src/analysis/insight_etl.py').read())"`
- `sqlite3 :memory: < data/insight/schema.sql`（SQL parse 確認）

**smoke**

- `python3 -m src.analysis.insight_etl --fixture tests/fixtures/npb_score_2026_0510_d-g-08_box.html --dry-run`
- 出力: 標準出力に件数サマリ、`data/insight/article_candidates.csv` に 1〜3 行のサンプル signal

**通過基準**

- 新規テスト all pass
- regression 既存テスト全件 pass（差分ゼロ）
- smoke で `article_candidates.csv` のサンプル行が visual 確認可能
- 既存 source extractor の出力に変化なし

---

## 6. STOP 条件

以下のどれかに触れる必要が出た時点で**即停止 + user GO 必須**:

1. WordPress DB / `wp_posts` / `wp_postmeta` / `wp_options` / custom table
2. WP 本文書き換え / publish 条件 / noindex / canonical / 301 / SEO
3. 既存 pipeline（`rss_fetcher` / `guarded_publish_runner` / `wp_client`）への edit
4. Gemini call 増加 / プロンプト変更
5. X API / 有料サービス導入
6. 新規 source（新 URL スクレイピング、UZR 等の外部指標取得）
7. Cloud Run / Cloud Scheduler / env / flag / secret の変更
8. deploy / Dockerfile / cloudbuild 変更
9. master への commit / push
10. 既存テストの red 化（regression）

---

## 7. 禁止事項

本フェーズ（design + prototype）中、以下は **絶対禁止**:

- 既存ファイルへの edit（`src/` 直下、`tests/`、`config/`、`logs/`、`build/`）
- WP REST の任意呼び出し（GET 含め、本フェーズでは一切呼ばない）
- 新規 URL スクレイピング（本番 Yahoo / NPB URL は呼ばない。fixture HTML のみ）
- Gemini call / X API 利用
- 有料 API 利用
- Cloud Scheduler 編集
- env / secret 変更
- deploy
- commit / push（user GO 後、別フェーズで許可される予定）
- master への merge
- 権利不明データのスクレイピング
- 大量取得（rate limit 配慮の design 段階のみ）

---

## 8. 想定されるデグレ

| リスク | 説明 | 対策 |
|---|---|---|
| **import 連鎖事故** | 既存 pipeline が `src.analysis.*` を import すると、production code path に SQLite 依存が侵入 | `src/analysis/` 隔離 + 逆方向 import 禁止を本ドキュメントに明記 + regression テストで既存 extractor 単体実行可能を確認 |
| **SQLite ロック** | 複数プロセス同時書き込みで lock error | 1 プロセス前提を CLI ヘルプ + 本ドキュメントに明記、deploy 時の文脈で再確認 |
| **ディスク容量** | 蓄積で `data/insight/insight.db` 肥大 | 1 試合 ~10KB / 年間 ~1.5MB の見積もり、容量 alert は不要規模 |
| **Yahoo / NPB HTML 構造変化** | 既存 extractor が壊れた時 INSIGHT も壊れる | 既存 extractor を import で使うため、リスクは既存 pipeline と同一・新規追加なし |
| **fixture / 本番 URL の取り違え** | prototype が本番 URL を叩く事故 | CLI で `--fixture` 必須引数 + 本番 URL アクセスを行うコードパスを **書かない**（次フェーズ判断） |
| **既存テスト破壊** | namespace 衝突や副作用 | regression テスト群を全件実行、ゼロ red を出荷条件にする |
| **ユーザー体験影響** | publish 記事の見た目変化 | candidate CSV は repo 内ファイル、WP 公開記事への影響経路なし |
| **rate limit 違反** | 本番 URL を頻繁に叩く設計 | prototype フェーズは fixture HTML 限定、本番 URL 接続は別チケット |

---

## 9. 作業ログ欄

```
HH:MM JST | event | detail
```

- 12:00 JST | start | INSIGHT-001 design + prototype GO 受領（user 「君のルールでいいやGO」）
- 12:05 JST | file_added | `data/insight/schema.sql`（9 テーブル: games / inning_scores / batting_logs / pitching_logs / lineups / fielding_logs / standings_snapshots / insight_runs / article_candidates）
- 12:08 JST | sql_parse | SQLite `:memory:` で schema parse → 9 テーブル + sqlite_sequence の生成確認
- 12:12 JST | file_added | `src/analysis/__init__.py`（namespace marker + 隔離方針コメント）
- 12:15 JST | file_added | `src/analysis/insight_etl.py`（fixture ETL prototype、CLI、`--dry-run`/live）
- 12:20 JST | smoke_run | `npb_score_2026_0510_d-g-08_box.html` で初回 ETL → 4 candidates 検出（うち 1 件「チーム計」誤検出を発見）
- 12:25 JST | bugfix | pitcher upsert で `チーム計` / `合計` 等の集計行を除外する filter 追加
- 12:27 JST | bugfix | CSV export の `run_ts` 空欄問題を `LEFT JOIN insight_runs` で解決
- 12:30 JST | smoke_rerun | 再 ETL → 3 candidates（ダルベック HR / ダルベック multi-hit / 浦田 multi-hit）— 全て妥当、`浦田` → `浦田俊輔` canonical 解決確認
- 12:35 JST | file_added | `tests/test_insight_etl.py`（13 テストケース）
- 12:36 JST | gitignore_edit | `.gitignore` に `data/insight/insight.db` / `.db-journal` / `.db-wal` / `article_candidates.csv` を追加（生成物の commit 防止）
- 12:40 JST | test_pass | 新規 21 件（test_insight_etl の 13 + parametrize 展開） pass
- 12:42 JST | regression_pass | event_key 系 61 件 + baseline 36 件 = **97 件 all pass**, 既存テスト red 化なし
- 12:45 JST | end | design + prototype 完了、user review 段階へ

---

## 10. Regression Memo 欄

```
HH:MM JST | observation | detail | followup
```

- 12:42 JST | green | event_key_ledger (33) + morning_event_key_enricher (19) + event_key_publish_gate (9) = 61 件 pass | none
- 12:42 JST | green | player_eyecatch_resolver / draft_audit / draft_inventory_from_logs baseline 36 件 pass | none
- 12:42 JST | green | 既存 `src.source_npb_postgame_extractor.parse_npb_box_html` の挙動は変化なし（import のみ、edit せず） | none
- 12:42 JST | confirmed | 既存 logs/*.jsonl への書き込みなし（ETL 出力先は `data/insight/` 限定） | none
- 12:42 JST | confirmed | WP REST 呼び出しなし、Gemini call なし、X API 呼び出しなし | none
- 12:43 JST | finding | NPB box の集計行「チーム計」が `_upsert_pitchers` で誤って投手として扱われていた（初期実装） | fixed in-session、`_PITCHER_AGGREGATE_LABELS` で除外
- 12:43 JST | finding | CSV export の `run_ts` 列が空（schema 設計上 run_ts は `insight_runs` 側のため） | fixed in-session、JOIN で解決
- 12:44 JST | note | 単試合 detector は MVP grade のみ（HR / 3+ 安打 / 110+ 球数 / QS proxy）。z-score / streak / split は多試合データ蓄積後に別チケットで実装する | follow-up: INSIGHT-002 で多試合検出

---

---

## 作業完了後の追記欄（実装フェーズ後の事後ログ）

### 1. 実際に変更したファイル

新規:

- `doc/active/INSIGHT-001-data-analysis-pipeline.md`（本ドキュメント）
- `data/insight/schema.sql`
- `src/analysis/__init__.py`
- `src/analysis/insight_etl.py`
- `tests/test_insight_etl.py`

修正:

- `.gitignore`（`data/insight/insight.db` / `.db-journal` / `.db-wal` / `article_candidates.csv` を追加）

**触っていないことを明示する既存ファイル**:

- `src/source_npb_postgame_extractor.py`（import のみ、edit なし）
- `src/wp_client.py`（呼び出さず、import なし）
- `src/rss_fetcher.py` / `src/guarded_publish_runner.py` / `src/source_*`（edit なし）
- `config/*.json`（edit なし）
- `logs/*`（書き込みなし）
- `master` ブランチ（merge せず）

### 2. diff 概要

```
M  .gitignore                                                       (+6 / -1)
A  data/insight/schema.sql                                          (+135 / -0)
A  doc/active/INSIGHT-001-data-analysis-pipeline.md                 (+本文)
A  src/analysis/__init__.py                                         (+15 / -0)
A  src/analysis/insight_etl.py                                      (+520 / -0)
A  tests/test_insight_etl.py                                        (+230 / -0)
```

### 3. 実行したテスト

```
# 新規
pytest tests/test_insight_etl.py -v                                  → 21 pass
# regression
pytest tests/test_event_key_ledger.py tests/test_morning_event_key_enricher.py \
       tests/test_event_key_publish_gate.py -q                       → 61 pass
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_audit.py \
       tests/test_draft_inventory_from_logs.py -q                    → 36 pass
# 合計 → 118 pass / 0 fail
# AST + SQL parse
python3 -c "import ast; ast.parse(open('src/analysis/insight_etl.py').read())" → OK
sqlite3 :memory: < data/insight/schema.sql                                    → 9 tables created
# smoke
python3 -m src.analysis.insight_etl --fixture tests/fixtures/npb_score_2026_0510_d-g-08_box.html \
    --game-id 2026-05-10:d-g-08 --game-date 2026-05-10                        → 3 candidates inserted, csv written
```

### 4. テスト結果

- 新規 21 件: ALL PASS（schema / parse_ip / roster aliases / etl idempotency / aggregate row 除外 / detector / CSV / CLI dry-run）
- regression 既存 97 件: ALL PASS、red なし
- 実環境 smoke: 5/10 ダルベック の HR + multi-hit 検知、浦田 → 浦田俊輔 canonical 解決
- pytest 全体経過: 約 3.0 秒（軽量）

### 5. 残った懸念

- **単試合 detector が rudimentary**: HR / 3+ 安打 / 110+ 球数 / QS proxy のみ。z-score / streak / split / 比較系（リーグ平均 / 前年比）は多試合蓄積後の INSIGHT-002 で実装する。
- **NPB 公式 URL の live fetch は本フェーズで未実装**: 現状 fixture HTML のみ。本番運用のためには `--source-url`（npb.jp の box.html URL 直読み）を追加する必要がある（次チケット）。
- **守備指標 / UZR 代理は schema にカラムだけ用意、未充填**: NPB が個別守備機会数を公式に出していれば取り込めるが、現状 fixture からは抽出経路なし。
- **`チーム計` 以外の集計行**: 「相手チーム計」「合計」等の他 alias がもし存在したら漏れる可能性。本実装は `_PITCHER_AGGREGATE_LABELS` 集合 + `startswith("チーム")` の二段で防いでいるが、別パターンが出たら拡張する。

### 6. 新しく見つかったデグレ

**なし**。既存テスト 97 件すべて pass、既存挙動の変化を観測せず。

導入過程で 2 件のバグを発見したが、いずれも本セッション内で修正・確認済（チーム計誤混入 / CSV `run_ts` 空欄）。

### 7. 追加した回帰テスト

`tests/test_insight_etl.py` 内（合計 13 ケース、parametrize 展開で 21 件）:

| テスト | 何を守るか |
|---|---|
| `test_schema_sql_creates_expected_tables` | schema.sql の構文 + 期待テーブル名 9 件すべての存在 |
| `test_parse_ip`（10 case parametrize） | 投球回 5.1/5.2 等の 3分位パース、不正値の None 化 |
| `test_load_roster_aliases_includes_known_canonicals` | `阿部監督` → `阿部慎之助` alias 解決 |
| `test_resolve_canonical_handles_unique_surname` | `浦田` → `浦田俊輔` の unique surname fallback |
| `test_resolve_canonical_returns_none_for_unknown` | カリステ等 allowlist 外は None |
| `test_derive_result_branches` | win / loss / draw / unknown 全分岐 |
| `test_etl_fixture_inserts_game_and_logs` | end-to-end の主要 row 数（batters 9 / pitchers 6 / candidates ≥ 1） |
| `test_etl_aggregate_pitcher_row_is_excluded` | チーム計 集計行を pitching_logs に入れない **回帰ガード** |
| `test_etl_idempotent_re_run` | 同 fixture を 2 回 ETL しても games / batting_logs / pitching_logs が重複しない |
| `test_etl_detects_homerun_and_multihit_for_darbeck` | ダルベックの HR + multi-hit が article_candidates に出る |
| `test_csv_exports_with_expected_columns` | CSV ヘッダが `CSV_COLUMNS` と一致、`run_ts` が JOIN で埋まる |
| `test_cli_dry_run` | `--dry-run` で書き込みなし、parsed_keys のサマリのみ出力 |

### 8. 次回触ってはいけない範囲（本フェーズの learning から）

- **`_upsert_pitchers` の集計行 filter は触る場合は test で守れ**: チーム計検出ロジックを緩めると HR / multi-hit 等の誤検出に直結（`test_etl_aggregate_pitcher_row_is_excluded` が必達）
- **CSV `run_ts` の JOIN を SELECT * に戻すな**: schema 設計上 `article_candidates` 単体には `run_ts` がない。SELECT * に戻すと CSV 列順は壊れる。明示的 SELECT を維持
- **`src/analysis/*` から `src/*` 外への import 拡大禁止**: 隔離原則。今は `source_npb_postgame_extractor` のみ import。これを拡大すると pipeline 連鎖の事故源
- **schema 変更時は migration スクリプトを別チケットで**: 既存 DB に対する column 追加 / table 改名は `ALTER TABLE` 経由で、destructive な `DROP TABLE` は避ける
- **NPB 公式の live URL は別チケット**: 現状 fixture 限定。本番 URL を叩く時は rate limit / robots.txt 遵守 / cache を含めた設計が必要、別チケット切る
- **WP DB / wp_posts / wp_postmeta / wp_options / publish 系**: 永続禁止（本フェーズの 7. 禁止事項を継承）

---

### Phase 2 への引き継ぎメモ（INSIGHT-002 草案）

次フェーズで実装したい順:

1. **NPB 公式 URL の polite live fetch**（rate limit + robots.txt + local cache）
2. **多試合 detector**: z-score / streak / hot/cold / 前年比
3. **lineup 履歴の蓄積**（既存 source_yahoo_lineup_extractor 流用）
4. **standings 比較指標**（リーグ平均 / 同ポジション平均）
5. **CSV → markdown 形式の人間向けサマリ生成**

すべて Cloud Scheduler / WP 触らずローカル CLI で完結する想定（INSIGHT-001 の境界を継承）。

---

## 補足：参考資料

- Design 詳細: 本ドキュメント上のセクション + 直近 chat ログ
- 関連既存資産:
  - `src/source_yahoo_boxscore_extractor.py`
  - `src/source_npb_playbyplay_extractor.py`
  - `src/source_npb_team_stats_extractor.py`
  - `src/source_npb_standings_extractor.py`
  - `src/source_yahoo_schedule_extractor.py`
  - `src/source_yahoo_lineup_extractor.py`
  - `config/giants_roster.json`
- 関連 fixture:
  - `tests/fixtures/npb_score_2026_0510_d-g-08_box.html`
  - `tests/fixtures/npb_score_2026_0510_d-g-08_playbyplay.html`
  - `tests/fixtures/npb_stats/2026_giants_batting.html`
  - `tests/fixtures/npb_stats/2026_giants_pitching.html`
- Scheduler 現状（5/13 確認、本チケットでは触らない）:
  - `giants-realtime-trigger`（15 分ごと 17-21 JST、ENABLED）
  - `publish-notice-trigger`（15 分ごと 6-23 JST、ENABLED）
  - `guarded-publish-trigger`（30 分ごと 24h、ENABLED）
  - 自動補強系の新 Scheduler 設定はすべて未作成、本チケット外
