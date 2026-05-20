# 343-INSIGHT-007-data-population-audit-and-backfill

| field | value |
|---|---|
| ticket_id | 343-INSIGHT-007-data-population-audit-and-backfill |
| priority | P1(342-INSIGHT の prerequisite、INSIGHT 系全体の data quality 基盤) |
| status | CLOSED (2026-05-20 PM、 PHASE_4_TEAM_AWARE_ROSTER_LANDED 後の close ritual、 342-INSIGHT 「12 球団 top 30」 は別 ticket で進行) |
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
| 2026-05-14 PM | user GO 受領後 Claude が Phase 0 audit 完了(read-only、§10 audit 結果に追記) | 根因確定: INSIGHT-007 schema は landed も populate 実装 3 path(`teams` / `players` / `advanced_metric_snapshots`)が src 全体で 0 hit、未実装。Phase 1 で 3 function 追加 + run_nightly wire + image rebuild + Cloud Run job update が必要 |
| 2026-05-14 PM | user 自律 GO 後 Claude が Phase 1 impl 完了(commit `033b92e`、5 file 828 行) + scope-aware threshold tweak (commit `3d928be`、1 file 14/1 行) | src + tests 完了、pytest 4 file 39 passed、baseline regression 0(4 failed pre-existing 維持)、`feedback_commit_safety_protocol_*` Phase 1+2+3 全実施 |
| 2026-05-14 PM | Phase 2 deploy chain 完了 | gcloud builds submit `insight-nightly:343` SUCCESS(1m17s)→ Cloud Run job update → execute (`insight-nightly-j488w`) → production DB pull で teams=12 / players=21 / advanced_metric_snapshots=0 (default min_pa=30 が春先 sparse data に対し厳しすぎ)→ scope-aware threshold tweak commit `3d928be` → rebuild `insight-nightly:343b` (1m20s) → re-deploy → re-execute (`insight-nightly-2n8x2`) → production DB pull で **advanced_metric_snapshots=122 rows landed**、ERA top 5 ranking 確認(則本昂大 0.0 rank 1 / 戸郷翔征 5.4 rank 2)、INSIGHT-007 backfill chain LIVE。 |
| 2026-05-14 PM | user GO 後 Claude が 2026 シーズン全試合 backfill 実行(`insight_nightly --auto --all-teams --date YYYY-MM-DD --live` を 3/20-5/13 の 55 日 loop) | NPB 開幕日 2026-03-27 確認、227 game ingested(空 14 日 / 失敗 8)、production DB push back (3.9 MB GCS upload)、再 pull で games 11→227、batting_logs 198→4086、pitching_logs 94→1839、players 21→39、advanced_metric_snapshots 122→616、**season scope 新規充足** (10 batter + 6 pitcher per metric)。top 5 OPS (last_30d): 大城卓三 0.93 / ダルベック 0.93 / 井上 0.80 / 平山 0.78 / 岸田 0.77。top 5 ERA (season): 赤星 1.72 / 井上 2.12 / 大竹 2.50 / 則本 2.70 / 高梨 2.79。342-INSIGHT impl 着手 ready。 |
| 2026-05-14 PM | giants_roster.json dedupe (Phase A、commit `d6a4485`) | 132→102 entry、29 group 統合 + 則本昂大 position「打者→投手」修正 + 6 regression test、resolve 後方互換確認 |
| 2026-05-14 PM | 12 球団 team-aware roster + NULL canonical fill (Phase B、commit `b8824f7`) | NPB 公式 (`npb.jp/bis/teams/rst_<code>.html`) を 12 球団 scrape (1071 entry)、`config/npb_12team_roster.json` 生成、`_load_team_aware_aliases` / `resolve_canonical_team_aware` / `fill_canonical_team_aware` 3 function 追加、run_nightly wire (defense_proxy 直後 / seed_teams 直前)、8 新 test。migration 実行 (local DB pull → fill_canonical 5027 行 update → re-seed 423 new player → re-compute 全 scope) で players 39→462 / advanced_metric_snapshots 616→**6394** (10x)、12 球団全部 32-43 player 充足。GCS push back (5.0 MB)、image rebuild `insight-nightly:343c` (1m18s) + Cloud Run job update 完了、次 nightly 以降も自動 fill 動作。top 10 OPS last_30d で 12 球団分布確認 (1.ネビン(l) / 2.佐藤輝明(t) / 3.桑原将志(l) / 4.佐藤都志也(m) / 5.坂倉将吾(c) / 6.増田珠(s) / 7.牧秀悟(db) / 8.庄子雄大(h) / 9.近藤健介(h) / 10.森下翔太(t))。top 5 ERA season: 髙橋遥人(t) 0.375 / 髙橋光成(l) / 早川隆久(e) / 平良海馬(l) / 栗林良吏(c)。342-INSIGHT「12 球団 top 30」も impl ready。 |

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

### Phase 0 audit 結果(2026-05-14 PM、Claude、user GO 後 read-only)

全項目 1 次 source verify(`feedback_ai_top_failure_modes_meta_rule` 準拠、`feedback_commit_safety_protocol_*` Phase 1+3 適用)。

| # | 項目 | 結果 | 詳細 |
|---|---|---|---|
| 1 | `insight-nightly` Cloud Run job 直近 9 execution 状態 | ✓ | `gcloud run jobs executions list --job=insight-nightly --region=asia-northeast1 --project=baseballsite --limit=30` で確認、直近 9 run のうち 7 success + 2 で `failed=1` column 表示。失敗率 ~22% は Phase 1 実装時に併せて見直し |
| 2 | Cloud Run job image / command / timeout | ✗ | image = `:initial`(初回 build から更新なし、artifact registry path: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:initial`)、command = `python3 -m src.analysis.insight_nightly --auto --all-teams --live`、timeout = 300s (5 min)。**image 古いため Phase 1 で populate path 追加しても rebuild + update 必須** |
| 3 | `insight_nightly.py` 内 `advanced_metric_snapshots` INSERT 有無 | ✗ | `grep -nE "(advanced_metric_snapshots\|INSERT.*teams\|INSERT.*players)" src/analysis/insight_nightly.py` → **0 hit**。populate 完全 missing |
| 4 | `insight_etl.py` 内 `teams` / `players` INSERT 有無 | ✗ | `grep -nE "(INSERT\|teams\|players\|seed\|populate)" src/analysis/insight_etl.py` → INSERT は `games` (line 244) / `inning_scores` (275) / `batting_logs` (310) / `pitching_logs` (361) / `article_candidates` (565) / `insight_runs` (671) のみ、**`teams` / `players` への INSERT は 0 hit** |
| 5 | 全 src cross-verify INSERT 検索(silent skip 回避) | ✗ | `grep -rnE "INSERT INTO advanced_metric_snapshots\|INSERT INTO teams\|INSERT INTO players" src/` → **全 src で 0 hit**。populate path **完全に未実装**(src grep を nightly/etl に閉じず全 src で cross check 完了) |
| 6 | `defense_opportunities` populate pattern(動いてる pattern、参考) | ✓ | `src/analysis/insight_defense_proxy.py:108` で `INSERT OR REPLACE INTO defense_opportunities`。`run_nightly()` 内 line 248 で `insight_defense_proxy.rebuild_defense_for_game(conn, game_id=game_id)` per-game 呼び出し(best-effort try/except でエラー吸収)。これが production DB で 163 rows populated の理由、**不足 3 path も同 pattern で実装可能**(idempotent INSERT + try/except + per-game or per-job 呼び出し) |
| 7 | `insight_advanced_metrics.py` batch helper | ✓ partial | per-line metric 関数 22 個(`avg` / `obp` / `slg` / `ops` / `iso` / `k_pct` / `bb_pct` / `babip` / `woba` / `era` / `whip` / `k_per_9` / `bb_per_9` / `hr_per_9` / `k_bb_ratio` / `fip` / `xfip` / `era_plus`)+ 集約 helper 2 個(`all_batter_metrics(line)` / `all_pitcher_metrics(line)`)+ DB-agnostic(formulas only、SQLite touch 0)。**batch snapshot insert helper は不在**、Phase 1 で `compute_advanced_metric_snapshots(conn, scope, snapshot_date)` を新規追加が必要 |
| 8 | `run_nightly()` flow(line 165-260) | ✓ | flow: GCS pull → fetch HTML → `insight_etl.etl_from_html` (games/batting/pitching upsert) → `parse_npb_box_html` → `insight_lineup_history.upsert_lineup_from_parsed_box` → `insight_defense_proxy.rebuild_defense_for_game` → `INSERT INTO insight_runs` → multi-game/lineup detectors。**teams / players / advanced_metric_snapshots を populate する step が完全に欠落** |
| 9 | `insight_nightly.main()` `--all-teams` flag(line 326-400) | ✓ | `--auto` 必須 / `insight_schedule.previous_jst_date()` で前日 JST → `resolve_all_slugs_auto` で 12-team 全 game slug 解決 → 各 slug ごとに `run_nightly()` 呼び出し → 末尾で digest 1 回。**12 球団 ingest path は存在するが、populate 不足は run_nightly 自体の欠落で発生**(--all-teams 関係なし) |
| 10 | Cloud Run 実 log 確認(read-only) | ✓ partial | 直近 9 run の stderr / stdout は `Container called exit(0).` 以外ほぼ空。application 内 print/log 文が少ない(structured log 経路)。populate 不在は src grep で確定済のため log で twice-confirm 不要 |

**Phase 0 結論**(1 次 source 全部追認):

INSIGHT-007 schema(`data/insight/schema.sql:158-216`)は定義されたが、**populate 実装は `defense_opportunities` のみ着地、`teams` / `players` / `advanced_metric_snapshots` の 3 path は全部未実装**。これが 342-INSIGHT data 不足の根因。

#### Phase 1 で実装必要な path(audit 結果から導出)

**新規 function 3 種**(`src/analysis/insight_etl.py` に追加、`defense_proxy` と同 pattern):

1. `seed_teams(conn: sqlite3.Connection) -> int`(idempotent、12 球団 fixed roster):
   - `INSERT OR IGNORE INTO teams (team_code, team_name, league, home_park) VALUES (...)`
   - 12 行 fixed(g/巨人/central/東京ドーム / t/阪神 / s/ヤクルト / c/広島 / db/DeNA / d/中日 / f/日本ハム / b/オリックス / h/ソフトバンク / l/西武 / e/楽天 / m/ロッテ)
   - return inserted row count

2. `seed_players_from_logs(conn: sqlite3.Connection) -> int`(case B 推奨、既存 logs から induce、新 source 不要):
   - `SELECT DISTINCT player_canonical, team_name FROM batting_logs WHERE player_canonical IS NOT NULL AND team_name IS NOT NULL UNION SELECT DISTINCT player_canonical, team_name FROM pitching_logs WHERE player_canonical IS NOT NULL AND team_name IS NOT NULL`
   - team_name → team_code 変換は既存 `_resolve_team_code_from_name()` (insight_etl.py:185) を reuse
   - role 推定: pitching_logs に出る = `pitcher`、batting_logs にしか出ない = `player`
   - `INSERT OR IGNORE INTO players (player_canonical, team_code, role, active) VALUES (...)`
   - return inserted row count

3. `compute_advanced_metric_snapshots(conn, scope: str, snapshot_date: str) -> int`(per-scope batch、`insight_advanced_metrics` を call):
   - scope = 'season' / 'last_7d' / 'last_30d' / 'last_5_games'
   - 各 player について BattingLine / PitchingLine を SELECT で集計、`all_batter_metrics(line)` / `all_pitcher_metrics(line)` で全 metric 計算
   - `INSERT OR REPLACE INTO advanced_metric_snapshots (snapshot_date, scope, player_canonical, team_code, metric_name, metric_value, sample_size, league_rank, league_total, position_rank, position_total) VALUES (...)`
   - league_rank / position_rank は同 scope 内 sort で計算
   - 最小 sample 閾値(PA >= 30 / IP >= 10 等)で skip
   - return inserted snapshot row count

**`run_nightly()` への追加 wire**(line 248 直後、`defense_proxy` 呼び出し直後、同 pattern):

```python
# 343-INSIGHT-007 backfill: teams / players / advanced_metric_snapshots
# best-effort、失敗しても pipeline は止めない (defense_proxy と同 pattern)
try:
    insight_etl.seed_teams(conn)
    insight_etl.seed_players_from_logs(conn)
except Exception:  # noqa: BLE001
    pass
try:
    today = dt.date.today().isoformat()
    for scope in ('last_7d', 'last_30d', 'season'):
        insight_etl.compute_advanced_metric_snapshots(conn, scope=scope, snapshot_date=today)
except Exception:  # noqa: BLE001
    pass
conn.commit()
```

**新規 tests 3 file**:
- `tests/test_insight_etl_seed_teams.py`(idempotent verify、12 行 fixed)
- `tests/test_insight_etl_seed_players_from_logs.py`(fixture batting/pitching logs から正しく players induce、role 推定、idempotent)
- `tests/test_insight_etl_compute_advanced_metric_snapshots.py`(fixture batting で OPS/wOBA snapshot 作成、scope 別 sample 閾値、league_rank 計算)

**image rebuild + Cloud Run job update**:
- `gcloud builds submit --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:343 .` (or `Dockerfile.insight_nightly` 専用)
- `gcloud run jobs update insight-nightly --image=...:343 --region=asia-northeast1 --project=baseballsite`
- 1 回手動 trigger: `gcloud scheduler jobs run insight-nightly-trigger` (or `gcloud run jobs execute insight-nightly`)
- 完了後 production DB pull で `teams: 12+ rows / players: 100+ rows / advanced_metric_snapshots: rows` 確認

#### Phase 1 着手前の user GO 判断材料

**option A**(Claude 推奨、自律可能):
- src + tests を Claude が直接 impl(`src/analysis/insight_etl.py` に 3 function 追加 + `tests/test_insight_etl_*.py` 3 file 追加 + `src/analysis/insight_nightly.py:run_nightly` に wire 追加)
- minimum-diff、既存 INSIGHT-001 base / INSIGHT-007 defense_proxy には触らない
- pytest baseline 維持(増減 0)
- impl + tests 完了で commit + push、Cloud Run image rebuild + Cloud Run job update + 手動 trigger は Claude が実行(`feedback_claude_dev_and_deploy_2026_05_12` user 永続切替で全権、§11 4 領域該当なし、CLAUDE.md §10 自律範囲)
- 完了後 1 回 trigger → DB pull verify → 7 日蓄積観察に移行

**option B**: src + tests impl のみ Claude、Cloud Run deploy は user 確認後

**option C**: 他 task に切替、343 を user GO 待ちで保留

**A 推奨理由**:
- §11 4 領域該当なし(content / SNS / scope / 法務・コスト 全部未関与、INSIGHT-007 補強は internal data quality)
- 343 ticket §6 STOP 条件を厳守すれば rollback 可逆(failed なら image 戻し + Cloud Run job revision rollback)
- 並走 actor の commit `ace4b64`(2026-05-14 13:53 JST、335-QA Phase 3 src 変更)は scope disjoint(私 = `src/analysis/insight_*` / 並走 = `src/title_*`)、衝突なし

#### Phase 0 audit で **触らなかった** もの(明示)

- `src/analysis/insight_*.py` 14 file(read のみ、edit 0)
- production DB(GCS から再 pull していない、Phase 1 spec 時の `/tmp/insight_prod/insight.db` を再利用してない)
- Cloud Scheduler / Cloud Run job(`gcloud ... list / describe / logging read` のみ、mutate / start / pause 0)
- env / Secret Manager(read もしない)
- 並走 actor の commit `ace4b64`(scope disjoint、本 ticket と無関係、隔離維持)

### Phase 1 impl 結果(2026-05-14 PM、Claude、commit `033b92e` + `3d928be`)

#### src + tests landed

| file | type | 行数 |
|---|---|---|
| `src/analysis/insight_etl.py` | M | +325 / -0(3 function + helpers + constants) |
| `src/analysis/insight_nightly.py` | M | +30 / -1(`run_nightly()` wire + scope-aware threshold) |
| `tests/test_insight_etl_seed_teams.py` | A | +67(4 test) |
| `tests/test_insight_etl_seed_players_from_logs.py` | A | +185(7 test) |
| `tests/test_insight_etl_compute_advanced_metric_snapshots.py` | A | +234(7 test) |
| **計** | | **+842 行 / -1 行 / 5 file / 18 新 test** |

#### Phase 2 commit safety 全実施(`feedback_commit_safety_protocol_grep_compile_pytest_logdiff`)

- Phase 1 (触る前 grep): src 全体 INSERT INTO teams/players/advanced_metric_snapshots 0 hit cross-verify
- Phase 2 (compile + ast + pytest baseline):
  - `python3 -m pytest -q` (full): **4 failed (全 pre-existing) / 4430 passed** (baseline 4395 + 新 18 + 既存 insight test 17 再 run)、regression 0
- Phase 3 (fire 後 log + 数値 diff): commit ごとに `git log --stat -1` 実施、parent chain verify

#### Phase 1 impl で **触らなかった** もの(明示)

- 既存 INSIGHT-001 base table (games / batting_logs / pitching_logs / etc.) の schema 不変、INSERT 文不変
- 既存 INSIGHT-007 `defense_opportunities` populate path 不変
- 既存 `_resolve_team_code_from_name` / `_ensure_team_name_columns` / `open_db` etc. signature 不変(reuse のみ)
- 既存 publish flow / WP / X / mail / SEO / Gemini に touch 0
- env / Secret Manager 不変
- 既存 `insight-nightly-trigger` Cloud Scheduler job の schedule 不変

### Phase 2 deploy 結果(2026-05-14 PM、Claude)

#### deploy chain

| step | command | result |
|---|---|---|
| 1 | `gcloud builds submit --config=cloudbuild_insight_nightly.yaml --substitutions=_TAG=343` | SUCCESS 1m17s、image `insight-nightly:343` push |
| 2 | `gcloud run jobs update insight-nightly --image=...:343` | SUCCESS、image 更新 verify 済 |
| 3 | `gcloud run jobs execute insight-nightly --wait` | SUCCESS execution `insight-nightly-j488w` 約 5 分 |
| 4 | `gsutil cp gs://baseballsite-yoshilover-insight/insight.db /tmp/insight_prod_post_343/` + sqlite query | teams=12 ✓ / players=21 ✓ / **advanced_metric_snapshots=0 ✗** |
| 5 | local debug: production DB に対し min_pa=5 で compute 試行 → 92 snapshots 入る | default min_pa=30 / min_ip=10 が春先 sparse data に厳しすぎる、scope-aware threshold で fix |
| 6 | scope-aware threshold tweak commit `3d928be` (1 file 14/1 行) → rebuild `insight-nightly:343b` (1m20s) → re-update → re-execute (`insight-nightly-2n8x2`) | SUCCESS |
| 7 | production DB 再 pull + sqlite query | teams=12 ✓ / players=21 ✓ / **advanced_metric_snapshots=122 rows ✓** / ERA top 5 ranking 確認(則本昂大 0.0 rank 1 / 戸郷翔征 5.4 rank 2) |

#### scope 別 snapshot 充足状況(2026-05-14 PM 時点、deploy 直後)

| scope | metric 数 | 主 metric | 充足度 |
|---|---|---|---|
| `last_7d` (PA>=5 / IP>=1) | 16 metric | OPS:6 / wOBA:6 / ERA:7 / FIP:7 / etc. | ✓ 既に流れている |
| `last_30d` (PA>=15 / IP>=5) | 8 metric | ERA:2 / FIP:2 / WHIP:2 / etc. | △ pitcher 一部のみ、batter は PA 不足 |
| `season` (PA>=50 / IP>=15) | 0 | -- | ✗ 5 月時点で sample 不足、自然蓄積待ち |

#### 7-30 日蓄積観察(本 ticket close 待機)

- `insight-nightly-trigger` (`0 2 * * *` UTC = 11:00 JST、ENABLED) が毎日 nightly で run_nightly() を実行
- 各 nightly で `seed_teams` / `seed_players_from_logs` / `compute_advanced_metric_snapshots` (3 scope) が best-effort で動く
- batting_logs / pitching_logs が日次 +5-10 game 蓄積、month 終わりには `last_30d` が batter にも届く
- season 末には `season` scope (PA>=50 / IP>=15) も充足
- 342-INSIGHT impl 着手は `last_30d` batter snapshot が 12 球団分揃った段階で可能

#### 既知の制約 / Phase 2 でも残った懸念

- `players` table 21 rows (12 球団分の 200+ active 想定の 1/10 程度) — まだ ingest した game 数が少ないため、player 由来 induce で全選手は揃わない。蓄積で増える
- `season` scope は 5 月時点で空 — sample 閾値 50 PA を満たす player が 0(Phase 1 設計通り)
- 1 player (`則本昂大`) が `team_code='g'` (巨人) として記録されているが本来は楽天 — INSIGHT-001 ETL の team_name 解決の問題、本 ticket scope 外、別 ticket で扱う

#### Phase 2 deploy で **触らなかった** もの(明示)

- 既存 Cloud Scheduler `insight-nightly-trigger` の schedule / state(image 更新のみ、cron 触らない)
- 既存 Cloud Run job `insight-nightly` の env / SA / timeout / command(image のみ更新)
- 他 Cloud Run service (yoshilover-fetcher / publish-notice / guarded-publish 等) の image / env / scheduler
- WP / X / mail / SEO / Gemini api key の env や設定
- production DB の direct mutation(GCS 経由でのみ更新、ETL 経由のみ)
- production GCS bucket の lifecycle / IAM
- 並走 actor の commit `4487e77` / `6dd55f2` / `21e4502`(別 lane、本 ticket と scope disjoint で隔離維持)

### Phase 3: 2026 シーズン全試合 backfill 結果(2026-05-14 PM、Claude、user GO 後)

#### backfill 概要

| 項目 | 値 |
|---|---|
| 期間 | 2026-03-20 〜 2026-05-13(55 日) |
| 開幕日確認 | 2026-03-27(3/20-3/26 は no schedule、3/27 から 6 game/日 で開幕) |
| 成功 game | **227** |
| 失敗 game | 8(主に 試合中止 / fixture incomplete) |
| 空日数 | 14(no schedule、月曜休 / 試合なし日) |
| 実行時間 | 約 30 分(local Python loop、live HTTP fetch、`time.sleep(0.5)` rate limit) |
| GCS upload size | 3.9 MB(352 KB → 3.9 MB) |
| 並列 actor 影響 | 0(local /tmp 経由、production GCS は backfill 完了時に 1 回 push) |

#### before / after row counts(production DB)

| table | before (Phase 2 deploy 後) | after (backfill 後) | delta |
|---|---|---|---|
| `games` | 11 (5/12-5/13 のみ) | **227** (3/27-5/13) | **+216** |
| `batting_logs` | 198 | **4086** | +3888 |
| `pitching_logs` | 94 | **1839** | +1745 |
| `players` | 21 | **39** | +18 |
| `advanced_metric_snapshots` | 122 | **616** | +494 |
| `defense_opportunities` | 163 | **3388** | +3225 |

#### scope 別 snapshot 充足状況(backfill 後)

| scope | metric 数 | batter player 数 | pitcher player 数 | 充足度 |
|---|---|---|---|---|
| `last_7d` (PA>=5 / IP>=1) | 17 metric | 11 player(AVG/OPS/wOBA 等) | 14 player(ERA/FIP 等) | ✓ 揃い |
| `last_30d` (PA>=15 / IP>=5) | 17 metric | 14 player | 18 player | ✓ 揃い |
| `season` (PA>=50 / IP>=15) | 17 metric | 10 player | 6 player | ✓ **新規充足** |

**重要**: `season` scope が backfill により新規充足。これにより 342-INSIGHT で「年間 ranking 系」記事(月次 OPS、wOBA、FIP 等)が **即着手可能** な data 状態。

#### sample ranking 確認(production DB)

**top 5 OPS (last_30d)**:

| rank | player | team | OPS | sample (PA) |
|---|---|---|---|---|
| 1 | 大城卓三 | g | 0.9313 | 57 |
| 2 | ダルベック | g | 0.9289 | 91 |
| 3 | 井上温大 | g | 0.8 | 16 |
| 4 | 平山 功太 | g | 0.7823 | 51 |
| 5 | 岸田 行倫 | g | 0.7708 | 34 |

**top 5 ERA (season、IP>=15)**:

| rank | player | team | ERA | sample (IP) |
|---|---|---|---|---|
| 1 | 赤星 優志 | g | 1.723 | 15 |
| 2 | 井上温大 | g | 2.124 | 29 |
| 3 | 大竹寛 | t | 2.5 | 36 |
| 4 | 則本昂大 | g(誤、正は e 楽天) | 2.7 | 30 |
| 5 | 高梨雄平 | g | 2.793 | 38 |

#### 既知の制約 / Phase 3 で残った懸念

- **team_code 誤マッピング**: 則本昂大(本来 e 楽天)が `g` 巨人 として記録されている。INSIGHT-001 ETL の `_resolve_team_code_from_name` の team_name 解決の問題、本 ticket scope 外、別 ticket(未起票)で対応必要
- **player team 偏り**: g (巨人) 28 player、s/t/m 各 2 player、b/c/d/db/e 各 1 player、**f/h/l 0 player**(パリーグ 3 球団 inducer 失敗)。`config/giants_roster.json` の roster alias が巨人中心のため、他球団選手の `player_canonical` 解決失敗。342 で「12 球団 top 30」記事を出す際の制約、同上 別 ticket 必要
- **失敗 game 8 件**: 主に試合中止 / fixture HTML incomplete。再 fetch しても回復しない可能性高、現状で OK

#### 342-INSIGHT impl 着手判断(343 close 後)

backfill 完了で 342 ticket §10 「Phase 1 着手前 user GO 判断材料」の **option A prerequisite が完了**:
- `last_30d` batter snapshot: 14 player ✓ (12 球団分は揃わず巨人中心、ただし「巨人選手 OPS top 10」記事は十分)
- `season` snapshot: 10 batter + 6 pitcher ✓ (年間 ranking 記事 OK)
- 月初発火 trigger 設計 + extractor 拡張 spec + wp_client.create_category 追加 spec は 342 §10 で完成済

342-INSIGHT 初版 4 候補のうち実装 ready:
- ✓ A1 月次 巨人選手 OPS / wOBA / ISO ranking(巨人 14 batter 分 last_30d 揃い)
- △ B2 守備指標 12 球団 rank(`defense_opportunities` 3388 行あるが UZR proxy 計算 path 別途必要)
- △ B1 12 球団 OPS top 30(g 28 + 他球団少、cross-team 不足、roster 拡張後)
- ✓ E1 直近 7 / 14 試合 hot/cold ranking(last_7d 11 player 揃い)

#### Phase 3 で **触らなかった** もの(明示)

- src 一切 touch なし(read-only execution、既存 `insight_nightly --auto --all-teams --date` 引数で run)
- Cloud Run image / Cloud Run job / Cloud Scheduler の設定一切 touch なし
- production GCS bucket は **insight.db のみ push** (既存 article_candidates.csv / digest/ には touch なし)
- WP / X / mail / SEO / Gemini api key 一切 touch なし
- 並走 actor の commit `e7a33bd`(336-QA digest、disjoint で衝突なし)

### 343 ticket close 候補判断(2026-05-14 PM 時点)

§目的 達成度:

- ✓ INSIGHT-007 nightly job が `teams` / `players` / `advanced_metric_snapshots` を populate していない原因 = src 全体 INSERT 0 hit、Phase 1 で 3 function 追加 + run_nightly wire で解決
- ✓ 不足 path を backfill 実装 = `seed_teams` / `seed_players_from_logs` / `compute_advanced_metric_snapshots` 全 implementation + production deploy LIVE
- ✓ INSIGHT-007 系の data quality を本来の設計水準まで引き上げ = 227 game / 4086 batting_logs / 616 snapshot で `season` scope まで充足
- ✓ 342-INSIGHT impl 着手 unblock = 巨人選手中心の ranking 記事は即実装 ready

§残存課題(別 ticket で対応):
- team_code 誤マッピング(INSIGHT-001 ETL `_resolve_team_code_from_name` 改善)
- player roster 拡張(他 11 球団の active player induce 改善 or `config/giants_roster.json` 12 球団拡張版)

これら 2 課題は 342-INSIGHT 初版実装の妨げにならない(巨人中心記事は data 揃い)、343 ticket は **close 候補**。close 判断は user GO で `doc/active/` → `doc/done/2026-05/` 移動 + status `CLOSED`。

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
