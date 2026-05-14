# 343-INSIGHT-007-data-population-audit-and-backfill

| field | value |
|---|---|
| ticket_id | 343-INSIGHT-007-data-population-audit-and-backfill |
| priority | P1(342-INSIGHT の prerequisite、INSIGHT 系全体の data quality 基盤) |
| status | DRAFT(本 doc 作成のみ、user GO 待ち) |
| owner | Claude Code |
| lane | INSIGHT |
| created | 2026-05-14 |
| doc_path | doc/active/343-INSIGHT-007-data-population-audit-and-backfill.md |
| ready_for | user GO → Phase 0 audit(`insight-nightly-trigger` 実 run log + `insight_etl.py` / `insight_nightly.py` populate path 確認) |
| blocked_by | user GO(本 ticket scope 確定) |
| numbering_reserved | 完了(同 commit で doc/README.md に追記)、3 source verify 完了(gh label / gh issue / ls 全部 343 不在) |
| gh_issue | #23(https://github.com/fwns6760/-wordpressyoshilover/issues/23、label `ticket:343-INSIGHT` + `enhancement` 付与済) |
| related_tickets | 342-INSIGHT(本 ticket 完了が 342 impl 着手の prerequisite、GH Issue #21)、INSIGHT-001〜009(既存 INSIGHT 系 base) |

## 目的

342-INSIGHT Phase 1 spec 精度上げで(2026-05-14 PM、commit `1058845`)、production DB(`gs://baseballsite-yoshilover-insight/insight.db` pull で verify)に **INSIGHT-007 schema 4 table が schema 上は存在するが data がほぼ空** であることが判明。

| table | rows | 期待状態 |
|---|---|---|
| `teams` | 0 | 12 球団 fixed roster |
| `players` | 0 | active 選手 ~300 名 |
| `advanced_metric_snapshots` | 0 | nightly job が出力すべき OPS / wOBA / FIP / RF_proxy snapshot |
| `defense_opportunities` | 163 | 唯一 populated(atbats parser 由来) |
| `games` | 11 | 期間 2026-05-12〜05-13 のみ(2 日分) |

**343 の目的**: INSIGHT-007 nightly job(`insight-nightly-trigger` Cloud Scheduler、`insight-nightly` Cloud Run job)が `teams` / `players` / `advanced_metric_snapshots` を populate していない原因を audit し、不足 path を backfill して、INSIGHT-007 系の data quality を本来の設計水準まで引き上げる。

これにより 342-INSIGHT impl 着手が unblock され、INSIGHT-008/009 既存機能(rank → article generator、NL question → draft)も活性化する。

## scope

### 含む

- `insight_etl.py` / `insight_nightly.py` / `insight_advanced_metrics.py` 内の populate path 監査
- `teams` / `players` の seed 経路調査(現在 hardcode かどうか、別 source 必要か)
- `advanced_metric_snapshots` の計算 + insert path 実装または有効化
- `insight-nightly-trigger` Cloud Scheduler の run log audit(直近 30 run の success / failure 確認)
- `insight-nightly` Cloud Run job の execution log audit(直近 30 execution)
- 不足 path の追加実装(pure Python、LLM 不使用)
- `tests/test_insight_*` 系の unit test 追加 / 修正
- `data/insight/seed/` への seed file 追加(必要時、12 球団 fixed roster JSON 等)
- production への deploy(image rebuild + Cloud Run job update、`feedback_release_composition_verify_before_deploy` 準拠)
- Phase 完了後の data 蓄積観察(7 日 / 30 日)

### 含まない

- 342-INSIGHT 自体の impl(本 ticket は 342 の prerequisite)
- 新規 data source の追加(NPB 公式 API 等の新接続、別 ticket 必要時に分離)
- INSIGHT-001 base table(`games` / `batting_logs` / `pitching_logs` 等)の schema 変更
- WordPress / publish flow / mail / X / SEO への一切の影響
- LLM call 追加(rule-based / hardcoded seed のみ)
- noindex / SEO / canonical / 301 設定変更
- 既存 INSIGHT-* module の signature 変更(rename / 削除 NG、追加 OK)
- master 以外への force push / master の history rewrite

## 3. 今回触らない範囲

- 既存 publish flow(postgame / manager / lineup / pregame / farm / broadcast / notice / player_voice_digest 等)の title / body 生成ロジック
- `src/rss_fetcher.py` 既存 entry point
- `src/wp_client.py` / `src/guarded_publish_runner.py` / `src/publish_evaluator.py`(本 ticket scope 外)
- `src/title_template_assembler.py`
- master ブランチ / 既存 Cloud Run service(yoshilover-fetcher / publish-notice / guarded-publish 等)image build pipeline
- Cloud Scheduler **既存** job の enable / pause / schedule(`insight-nightly-trigger` 自体の schedule は変更しない、内部処理改修のみ)
- WordPress 本文 / publish status / noindex / canonical / 301 / SEO
- WP custom table / `wp_postmeta` schema
- Gemini call / GEMINI_API_KEY 経路 / X API / X 自動投稿
- 既存 publish 済 post の body / title / status / meta(retroactive 一切なし)
- 既存 mail 通知の format
- player_eyecatch_map / giants_roster.json の構造(read 専用、追加 OK)

## 4. 影響範囲

### 改修対象(audit + backfill)

- `src/analysis/insight_etl.py`:
  - `teams` / `players` への seed insert path 確認 / 追加
  - 既存 `batting_logs` / `pitching_logs` の `team_name` 列から `players` table を induce する logic 追加検討
- `src/analysis/insight_nightly.py`:
  - `advanced_metric_snapshots` への計算 + insert path 確認 / 追加
  - `insight_advanced_metrics.calc_*()` 関数(woba / fip 等)の集約呼び出し path
  - scope 値('season' / 'last_7d' / 'last_30d' / 'last_5_games')別 snapshot 生成
- `src/analysis/insight_defense_proxy.py`:
  - `position_summary_for_player()` / `league_position_baseline()` を nightly run で 12 球団 + position 別に計算 + snapshot insert する path

### 新規追加

- `data/insight/seed/teams.json`(12 球団 fixed roster):
  ```json
  [{"team_code": "g", "team_name": "巨人", "league": "central", "home_park": "東京ドーム"}, ...]
  ```
- `data/insight/seed/players.json`(active 選手 ~300 名、source 検討):
  - 案 A: `config/giants_roster.json` を 12 球団拡張(work 大、別 ticket?)
  - 案 B: `batting_logs` / `pitching_logs` から `team_name` + `player_canonical` を SELECT DISTINCT して insert
  - 案 C: NPB 公式 / Yahoo box score の roster page を scrape(scope 拡大、別 ticket)
  - **推奨 = 案 B**(既存 data から induce、新 source 不要、scope 最小)
- `tests/test_insight_etl_seed_teams.py`
- `tests/test_insight_etl_seed_players.py`
- `tests/test_insight_nightly_advanced_metric_snapshots.py`

### 既存への影響(read-only / additive)

- `src/analysis/insight_advanced_metrics.py`(INSIGHT-007 step 7b、formulas): read 利用、変更なし
- `src/analysis/insight_rank_query.py`: read 利用、変更なし(本 ticket は data populate、query は 342 で利用)
- production DB(GCS): nightly job が download → ETL → upload する既存 path で更新、本 ticket では direct upload しない

### 影響しない(verify した上で記載)

- 既存 publish post の表示 / SEO / canonical / 出力 HTML
- 既存 X 自動投稿(本 ticket は publish flow 完全 disjoint)
- 既存 fetcher / publish-notice / guarded-publish / broadcast-auto / lineup-auto / postgame-auto / publish-notice / draft-body-editor の image / env / scheduler

## 5. 実行予定テスト

### Phase 0(audit、user GO 後 read-only)

- `gcloud run jobs executions list --job=insight-nightly --region=asia-northeast1 --project=baseballsite --limit=30` で直近 run の success / failure 確認
- `gcloud run jobs describe insight-nightly --region=asia-northeast1 --project=baseballsite` で image / env / SA / command 確認
- `gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=insight-nightly" --limit=100 --format=json` で実 log 確認
- `src/analysis/insight_nightly.py` 内で `advanced_metric_snapshots` への INSERT 文の有無 grep
- `src/analysis/insight_etl.py` 内で `teams` / `players` への INSERT 文の有無 grep
- production DB 再 pull で audit 中の data 状態変化確認

### Phase 1(narrow impl、user GO 後)

- 各 backfill function の unit test(fixture-based):
  - `seed_teams()`: 12 球団 fixed insert、idempotent(2 回実行で row 数変わらず)
  - `seed_players_from_logs()`(案 B): batting_logs / pitching_logs から induce、idempotent
  - `compute_advanced_metric_snapshots(scope='last_30d')`: 既存 batting_logs / pitching_logs から計算、advanced_metric_snapshots に insert
- regression: 既存 pytest baseline 維持(pass 数 増減 0)
- INSIGHT-001 base table への影響 0(`git diff --stat src/analysis/` で確認)

### Phase 2(production deploy + 観察、user GO 後)

- image rebuild(`gcloud builds submit`)+ Cloud Run job update(`gcloud run jobs update insight-nightly`)
- 1 回手動 trigger(`gcloud scheduler jobs run insight-nightly-trigger` または `gcloud run jobs execute insight-nightly`)
- 完了後 production DB pull で `teams` / `players` / `advanced_metric_snapshots` row 数増加確認
- 7 日観察で nightly run 自動蓄積確認
- 30 日観察で `last_30d` scope の snapshot 充足確認
- 充足後に 342-INSIGHT impl 着手 unblock(別 chain)

## 6. STOP 条件

- 既存 INSIGHT-001 base table(`games` / `batting_logs` / `pitching_logs` 等)に regression(row 消失 / 形式変化)が出たら STOP
- nightly job が新 path で error 発生し、既存 path も巻き添え failure になったら STOP
- production DB に **過去 data の mutation**(既存 row の値変更)が観測されたら STOP(forward-only / additive insert のみ)
- pytest baseline が 1 件でも新規 fail を出したら STOP
- Cloud Scheduler の **既存** job の enable / pause / schedule を変更したら STOP(本 ticket は内部処理のみ)
- 既存 publish flow への副作用が出たら STOP(publish 数 / publish 失敗数の regression)
- LLM call 追加(Gemini / GPT / 他)が観測されたら STOP
- WP / X / mail / SEO への一切の影響が出たら STOP

## 7. 禁止事項

- env / secret(GCP Secret Manager / Cloud Run env)変更
- master 以外への force push / master の history rewrite
- LLM(Gemini / GPT / 他)への新規 call 追加
- noindex / SEO / canonical / 301 設定変更
- WP custom table の schema 変更
- 既存 publish 済 article の body / title / status / meta 変更
- X 自動投稿の enable / 新カテゴリの X 投稿対象化
- 既存 Cloud Scheduler job の enable / pause / schedule 変更
- 既存 INSIGHT-* module の signature 変更(rename / 削除 NG、追加 OK)
- INSIGHT-001 schema の変更(`games` / `batting_logs` / `pitching_logs` 等)
- INSIGHT-007 schema の変更(`teams` / `players` / `defense_opportunities` / `advanced_metric_snapshots` の column 削除 / 改名 NG、追加 OK)
- 過去 game / batting / pitching log の mutation
- `git add -A` 使用(明示 path のみ stage)
- `--no-verify` / hook skip
- 新規 data source の追加(別 ticket、本 ticket scope 外)

## 8. 想定されるデグレ

- **nightly job の長時間化**: `advanced_metric_snapshots` 計算 + insert で 12 球団 × 4 scope × ~30 metric = 大量計算、現在の Cloud Run job timeout(default 10 min?)を超える可能性 → batch 分割 / timeout 延長 / scope 限定
- **GCS upload size 増加**: `insight.db` が現在 290 KB、`advanced_metric_snapshots` 充足後は MB scale になる → upload 時間増加、cost 増加微量
- **既存 INSIGHT-008/009 の挙動変化**: 既存 article generator / NL query が `advanced_metric_snapshots` 空前提で fallback を持っていた場合、data 充足で挙動変化(これは本来の意図、ただし観察)
- **`players` table seed の逆 contamination**: case B (logs から induce) で `player_canonical` が NULL の row が混入 → unique 制約 / NULL handling 要 design
- **`teams` table seed の hardcode 衝突**: 既に手動で teams insert 履歴があった場合、idempotent 処理(`INSERT OR IGNORE` / `INSERT OR REPLACE`)で安全化必須
- **GCS download 遅延**: insight.db が大きくなって job 起動時 download に時間かかり、retry / timeout の境界変化
- **scope='season' snapshot の sample 偏り**: season 早期は sample 少なく rank 不安定 → 最小 sample 閾値で skip

## 9. 作業ログ欄

| 日時 (JST) | 内容 | 結果 |
| --- | --- | --- |
| 2026-05-14 PM | 本 ticket doc 作成(342-INSIGHT Phase 1 spec で発見した data 不足 への補強として起票) | user GO 待ち、3 source verify 完了(gh label / gh issue / ls 全部 343 不在) |

## 10. Regression Memo 欄

### current observation(本 ticket 着手前、2026-05-14 production DB pull で確認済)

- production DB は GCS bucket `baseballsite-yoshilover-insight` に存在(290 KB)
- INSIGHT-007 schema 4 table は schema 存在も data ほぼ空(本 ticket §目的 表参照)
- `defense_opportunities` のみ 163 rows populated(INSIGHT-007 atbats parser 由来、これは正常稼働している証拠)
- `games` 11 rows / 2026-05-12〜05-13 の 2 日分のみ → INSIGHT-001 base ETL も低頻度?
- `insight-nightly-trigger` Cloud Scheduler は ENABLED `0 2 * * *` UTC = 11:00 JST、Phase 0 で実 run log audit 必要

### guard hypothesis

- guard A: 全 backfill function は idempotent(`INSERT OR IGNORE` / `INSERT OR REPLACE`)、複数回実行で row 増えない / 値破壊しない
- guard B: 既存 INSIGHT-001 base table への影響 0(`git diff --stat src/analysis/` で確認、touch するのは additive insert path のみ)
- guard C: nightly job の既存処理(defense_opportunities 計算等)は変更せず、新 path を additive 追加
- guard D: production DB への直接 mutation はせず、nightly job 経由でのみ更新(本 ticket では direct upload 経路を使わない)
- guard E: pre-commit baseline + post-commit log diff(`feedback_commit_safety_protocol_*` 全 commit 適用)

### feasibility 確認事項(Phase 0 で audit)

- `insight-nightly` Cloud Run job の直近 30 execution の success / failure 状況
- `insight_nightly.py` 内で `advanced_metric_snapshots` への INSERT path の有無(現状 missing 仮説)
- `insight_etl.py` 内で `teams` / `players` への seed path の有無(現状 missing 仮説)
- nightly job の実行時間 + memory 使用量(backfill 追加で timeout 余裕あるか)
- `INSIGHT_GCS_BUCKET` の SA 権限 + bucket lifecycle 設定
- 既存 INSIGHT-007 atbats parser が defense_opportunities に書く path(参考実装、advanced_metric_snapshots に同形式で書く path を spec)

---

## 作業後に追記すること

1. 実際に変更したファイル
2. diff 概要
3. 実行したテスト
4. テスト結果
5. 残った懸念
6. 新しく見つかったデグレ
7. 追加した回帰テスト
8. 次回触ってはいけない範囲

## 作業後追記

(空、作業完了後に追記)
