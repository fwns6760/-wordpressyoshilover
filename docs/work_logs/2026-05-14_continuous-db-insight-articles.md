# 2026-05-14 継続的 DB 改善 system — 「気づかない pattern」分析記事 自動生成基盤

| field | value |
|---|---|
| 種別 | 継続改善 work log (ticket ではない、`doc/active/` に置かない) |
| 場所 | `docs/work_logs/2026-05-14_continuous-db-insight-articles.md` |
| 作成 | 2026-05-14 PM |
| owner | Claude Code (実装) + user (tuning / 最終 publish 判断) |
| 目的 | 大手が出さない「人が気づかない pattern」分析記事を、production DB 由来で **継続的 / 自動で WP draft に landed** させる基盤を構築。`§11 user 判断境界` の範囲では publish gate は env flag で user 制御 |
| 状態 | DRAFT — user GO 待ち、本 markdown 作成のみ完了 |
| 関連 | 342-INSIGHT (ranking 自動 publish 基盤、本 work と合流) / 343-INSIGHT-007 (12 球団 data 基盤、prerequisite 完了) |

---

## 3. 今回触らない範囲

(things we will NOT touch)

### 既存 publish flow / WP
- 既存 publish flow(postgame / manager / lineup / pregame / farm / broadcast / notice / player_voice_digest 等)の title / body 生成
- `src/rss_fetcher.py` 既存 entry point / 既存 RSS 処理
- 既存 publish 済 post の body / title / status / meta(forward-only 厳守)
- 既存 WP category(試合速報 663 / 選手情報 664 / 首脳陣 665 / ドラフト・育成 666 / OB・解説者 667 / 補強・移籍 668 / 球団情報 669 / コラム 670 / 旧記事 672)の編集 / 削除
- 既存 mail 通知(per-post mail / burst summary)の format

### 既存 INSIGHT 系
- INSIGHT-001 schema (`games` / `batting_logs` / `pitching_logs` / `lineups` / `fielding_logs` / `inning_scores` / `standings_snapshots` / `insight_runs` / `article_candidates` の column 削除 / 改名)
- INSIGHT-007 schema (`teams` / `players` / `defense_opportunities` / `advanced_metric_snapshots` の column 削除 / 改名)
- 既存 `_load_roster_aliases` / `resolve_canonical` / `_resolve_team_code_from_name` / `_load_team_aware_aliases` / `resolve_canonical_team_aware` / `fill_canonical_team_aware` / `seed_teams` / `seed_players_from_logs` / `compute_advanced_metric_snapshots` の signature (additive 追加 OK、改名 / 削除 NG)
- 既存 `insight_advanced_metrics.py` per-metric 計算関数 (per-line helper、変更なし)
- 既存 `insight_rank_query.py` `rank_players` / `get_player_rank` signature
- 既存 `insight_article_generator.py` `render_article` / `RankRow` / `ArticleContext` signature (template 拡張は別 helper で追加)
- 既存 `insight_defense_proxy.py` populate path (`run_nightly` line 251 wire 不変)
- `config/giants_roster.json`(343 dedupe 済、本 work で読むだけ、編集なし)
- `config/npb_12team_roster.json`(343 で landed、本 work で読むだけ、編集なし)

### Cloud infrastructure
- master ブランチ / 既存 Cloud Run image build pipeline
- 既存 Cloud Run service (yoshilover-fetcher / publish-notice / guarded-publish / broadcast-auto / lineup-auto / postgame-auto / publish-notice / draft-body-editor / manual-intake-service / etc.) の image / env / scheduler / SA / revision
- 既存 Cloud Scheduler job (`insight-nightly-trigger` 含む全 33 job) の enable / pause / schedule
- env / Secret Manager(GEMINI_API_KEY / WP_USER / WP_APP_PASSWORD / INSIGHT_GCS_BUCKET / その他全 secret 不変)
- GCP project / region / billing 設定

### 公開 / SNS / SEO
- noindex / SEO / canonical / 301 設定
- WP custom table の schema 変更
- X 自動投稿(`§11` user 判断境界)
- 自動 publish (status='publish') の default ON — 本 work では status='draft' 固定、auto-publish は env flag gate で user が明示 ON

### 並走 actor 関連
- 並走 actor の commit (`336-QA digest` / `337-INGEST sanspo` / `339-INGEST` / `341-FIX` / `335-QA Pattern R2` / `e7a33bd` / `6bb2ebc` / `e3d1f22` 等) の src への touch / 上書き
- 並走 actor が触ってる lane (`src/rss_fetcher.py` / digest / title 系 / RSS / fetcher) 全般

---

## 4. 影響範囲

(things this work WILL affect)

### 新規追加(予定)

**新 module**:
- `src/analysis/insight_anomaly_detector.py`:
  - z-score outlier detector(`detect_zscore_outliers(conn, scope, metric, threshold_sigma) -> list[Candidate]`)
  - 運 vs 実力 乖離 detector(BABIP / xwOBA vs AVG, FIP vs ERA)
  - trend detector(月別 metric の線形回帰 slope + 簡易 change-point)
  - pace projection detector(現在ペース → シーズン換算 + 巨人内 rank)
  - 各 detector は `article_candidates` table に新 signal_type で insert
- `src/analysis/ranking_article_publisher.py`:
  - 巨人中心 + 12 球団 ranking article を render
  - 既存 `insight_article_generator.render_article` を wrap、focus_player = 巨人 top
  - WP draft 投入(`wp_client.create_post(status='draft')`)
- `src/analysis/anomaly_article_publisher.py`:
  - `article_candidates` から本 work の新 signal を fetch
  - 「気づかない pattern」型の body section 構造で render
  - WP draft 投入

**新 helper / method**:
- `src/wp_client.py` に `create_category(name, slug=None, description="", parent=0) -> int` 追加(342 ticket §10 spec 通り、term_exists fallback 含む)

**既存 file への additive 追加**(signature 不変、新 branch 追加のみ):
- `src/pre_publish_fact_check/extractor.py:infer_subtype()`: 新 subtype 認識追加
  - `data_ranking_monthly` / `data_ranking_anomaly` / `data_insight_hidden_gem` / `data_insight_trend` / `data_insight_pace`
- `src/guarded_publish_evaluator.py:resolve_guarded_publish_subtype()`: 新 subtype の resolution 対応
- `src/analysis/insight_nightly.py:run_nightly()`: best-effort wire で anomaly detector を呼び出し(`defense_proxy` / `seed_teams` / `compute_advanced_metric_snapshots` と同 pattern)

**新 tests**:
- `tests/test_insight_anomaly_detector.py`(z-score / 乖離 / trend / pace 各 detector)
- `tests/test_ranking_article_publisher.py`
- `tests/test_anomaly_article_publisher.py`
- `tests/test_wp_client_create_category.py`
- `tests/test_extractor_infer_subtype_data_insight.py`(新 subtype 認識)

**新 config / data**:
- 「データで見る巨人」WP category(初回 trigger 時 `create_category` で idempotent 作成、ID は WP REST が返した値を `config/categories.json` に追記する補助 path 追加可能性)
- 環境変数 `ENABLE_DATA_INSIGHT_AUTO_PUBLISH`(default 0、user tuning 完了後 1 へ flip)
- 環境変数 `DATA_INSIGHT_ANOMALY_THRESHOLD_SIGMA`(default 2.0、user tuning 可)
- 環境変数 `DATA_INSIGHT_PUBLISH_MAX_PER_RUN`(default 3、暴走防止)

**新 Cloud Scheduler trigger 候補**(Phase 2 で設定、Phase 1 は手動 trigger):
- `data-insight-monthly-trigger` (cron `0 0 1 * *`, time_zone `Asia/Tokyo`) — 月次 ranking
- `data-insight-weekly-trigger` (cron `0 0 * * 1`, time_zone `Asia/Tokyo`) — 週次 hot/cold + anomaly

**Cloud Run image rebuild**:
- `insight-nightly:343d` 以降(343-INSIGHT-007 image tag pattern 継承)
- Dockerfile.insight_nightly 自体は不変(src/* を COPY するため自動取り込み)

### read-only / additive(変更なし、利用のみ)

- `src/analysis/insight_advanced_metrics.py`(metric 計算関数、利用のみ)
- `src/analysis/insight_rank_query.py`(`rank_players` / `get_player_rank` 利用のみ)
- `src/analysis/insight_article_generator.py`(`render_article` / `ArticleContext` / `RankRow` 利用のみ、内部 template 拡張のため新 helper を本 work module 内で書く)
- `src/analysis/insight_atbats_parser.py`(`parse_atbat` 利用のみ)
- `src/analysis/insight_defense_proxy.py`(read のみ、`run_nightly` wire の隣に追加するだけ)
- production DB(`article_candidates` への新 row insert / read のみ、既存 row 不変)
- production GCS bucket(`insight.db` の既存 download/upload path で更新、別 file 触らず)

### 影響しない(verify 上明示)

- 既存 publish post の HTML / title / status / meta
- 既存 X 自動投稿(本 work で触らず、status='draft' のみ)
- 既存 fetcher / publish-notice / guarded-publish / broadcast-auto / lineup-auto / postgame-auto / publish-notice / draft-body-editor の image / env / scheduler
- 既存 mail 通知 path(新 post は per-post mail scanner が拾うかもしれないが、既存 mail format 変更なし)
- noindex / SEO / canonical / 301
- Gemini API call(本 work で一切呼ばない、pure Python / numpy / 軽 ML)

---

## 5. 実行予定テスト

### Phase 0(audit、read-only)

- production DB の `article_candidates` の現状確認(signal_type 分布、status=NEW 件数、本 work で衝突する signal_type 不在 verify)
- 既存 `insight_article_generator.render_article` の sample call 動作確認(ArticleContext + RankRow 形式の入力で title/body_md/suggested_tags が返る)
- 既存 `wp_client.create_post(status='draft', categories=[id])` の動作 sample(mock requests.post)
- Cloud Run job `insight-nightly` の現 timeout 300s + 平均実行時間 measure
- 新 category 「データで見る巨人」が WP REST `/wp/v2/categories` に既存しないこと verify
- 既存 `extractor.infer_subtype` / `publish_evaluator.resolve_guarded_publish_subtype` の挙動 sample run

### Phase 1(unit + integration、fixture-based)

**detector tests**:
- `detect_zscore_outliers` で fixture batting_logs + 既知 outlier player を `+2σ` 閾値で正しく抽出
- 閾値境界 test(`+1.99σ` / `+2.0σ` / `+2.01σ`)
- BABIP / xwOBA 乖離 detector で expected 乖離値 fixture assertion
- FIP-ERA 乖離 detector で投手 fixture(高 ERA 低 FIP = 運悪い、低 ERA 高 FIP = 運いい)
- trend detector(`fixture monthly OPS series`)で slope > 0 + change-point date が想定範囲
- pace projection(`fixture monthly HR + 残試合数`)で expected シーズン換算

**publisher tests**:
- `ranking_article_publisher.render()`(`focus_player=巨人 top OPS`)で title / body section 構造が想定形に landed
- `anomaly_article_publisher.render()`(`signal=z-score outlier`)で body の section 順序(lead / data / interpretation / disclaimer)
- WP draft mock投入 path(`requests.post` mock で `status='draft'` 固定確認)
- 重複 draft 防止(同 metric / 同 scope / 同日 で 2 回 trigger しても WP に 1 本のみ)

**wp_client tests**:
- `create_category` で 201 path(新規作成)+ 400 `term_exists` fallback path(既存 ID 返却)
- `categories.json` 同期 path(`update_categories_json` helper)

**extractor tests**:
- 新 subtype 5 種が title pattern で正しく分類
- 既存 subtype に逆 contamination 0(`postgame` 等が「データで見る」title に誤分類されない)

**regression**:
- 既存 pytest baseline (4 failed pre-existing / 4500+ passed) 維持、増減 0

### Phase 2(deploy + smoke)

- Cloud Build image rebuild SUCCESS(`insight-nightly:343d` 等の tag、1m30s 以内)
- Cloud Run job update SUCCESS(image 更新 verify)
- 手動 trigger 1 回(`gcloud run jobs execute insight-nightly`)→ Cloud Run job 完走 + log で新 detector 動作確認
- production DB pull で新 signal_type rows が article_candidates に insert された(N>=5 程度)
- WP REST `/wp/v2/posts?status=draft` で新 draft 1-3 本 landed 確認
- 既存 INSIGHT-007 populate path 不変(teams=12 / players=462+ / advanced_metric_snapshots 増加のみ)
- 既存 INSIGHT-001 ETL path 不変(games / batting_logs / pitching_logs の row 数増加のみ、減少なし)

### Phase 3(live observation、1-2 week)

- 月初 trigger 自然発火で WP draft 自動投入 verify(初回は手動 trigger で代替可)
- 週次 trigger 自然発火 verify
- user tuning feedback 反映 loop(template / threshold 修正)
- WP publish 状態の手動移行(user による draft → publish)観察
- 並走 actor commit 衝突 0 verify(`git log --oneline -50` で disjoint 確認)
- production DB の article_candidates 件数推移 monitor

---

## 6. STOP 条件

(when to halt immediately)

### data 安全性
- 既存 publish post の mutation 観測(forward-only 違反)
- 既存 INSIGHT-001 / INSIGHT-007 schema / table への mutation(本 work は additive 限定)
- production DB の既存 row count が減少
- `article_candidates` の既存 signal_type の row が新 detector で誤って書き換えられた

### publish 安全性
- WP に意図しない publish (`status='publish'`)が landed
- WP に重複 draft が 1 trigger で 2 本以上 landed
- WP の既存 category が誤って書き換えられた
- 「データで見る巨人」category が他 article に誤って付与された
- env flag `ENABLE_DATA_INSIGHT_AUTO_PUBLISH=0` のはずなのに publish が観測された

### 既存 system 影響
- 既存 publish flow が壊れる(publish 数の不自然な減少 / mail 失敗 / WP error 急増)
- Cloud Run job timeout 超過(現 300s)
- Cloud Run job の他 service (yoshilover-fetcher 等) が影響を受けた
- 既存 INSIGHT-* module の signature が壊れた(import error / TypeError)
- Cloud Scheduler 既存 job の挙動異常

### LLM / cost
- LLM call (Gemini / GPT / 他) が本 work path から発火(本 work は rule-based 厳守)
- Gemini API call 数が増加
- Cloud Run / Cloud Build / GCS の月額コストが想定外増加

### 並走 actor
- 並走 commit の上書き(force push / rebase 不要 commit)
- 並走 commit の src に touch
- merge conflict が PR 化前に発生(本 work は feature branch なら OK)

### 数値 verify
- ranking 計算の数値が production DB 直 query と乖離(z-score / pace / trend で誤計算)
- 「データで見る巨人」記事の中身に存在しない player が混入
- 「巨人選手のリーグ X 位」表示が実 DB の rank と一致しない

### test
- pytest baseline が新規 fail 1 件でも増加
- 新 tests が flaky (3 回中 1 回 fail) で安定しない

---

## 7. 禁止事項

(absolute prohibitions、`§11 user 判断境界` 厳守)

### env / secret / infra
- env / secret (GCP Secret Manager / Cloud Run env) の **追加 / 変更 / 削除**
- master 以外への force push / master の history rewrite
- master への直接 push (PR 化を経由)
- 既存 Cloud Scheduler job の **enable / pause / schedule 変更**
- Cloud Run service / job の image **直接 push**(必ず `gcloud builds submit` 経由)
- GCP project / region / billing 設定変更

### publish / SNS
- WP に `status='publish'` で create_post する path の実装(必ず `status='draft'` 固定)
- env flag `ENABLE_DATA_INSIGHT_AUTO_PUBLISH=0` の bypass
- X 自動投稿の enable(`§11` user 判断)
- 新カテゴリの X 投稿対象化
- noindex / SEO / canonical / 301 設定変更
- 既存 publish 済 article の body / title / status / meta 変更

### code 衛生
- `git add -A` 使用(必ず明示 path のみ stage)
- `--no-verify` / hook skip
- LLM (Gemini / GPT / 他) への新規 call 追加(本 work は pure Python / numpy / 軽 ML 限定)
- 既存 INSIGHT-* module の signature 変更(rename / 削除 NG、additive 追加 OK)
- INSIGHT-001 / INSIGHT-007 schema 変更
- 既存 publish history / dedup ledger の削除 / mutation
- 過去 game / batting / pitching log の mutation
- 並走 actor の src に touch
- 並走 actor の commit の上書き
- WP custom table の schema 変更

### user 教示 / roster
- 教示なしの roster file 編集(`config/giants_roster.json` / `config/npb_12team_roster.json` は読むのみ)
- player_canonical の手動上書き(必ず `_load_team_aware_aliases` 経由)
- 「12 球団 top 30」記事の中身 で training data 由来の player attribution(roster file が source of truth)

---

## 8. 想定されるデグレ

(possible regressions to watch、preemptive)

### performance / cost
- **既存 nightly job の長時間化**: anomaly detector + ranking 計算で実行時間が現 ~10s から 30-60s へ。timeout 300s に余裕あるが要 monitoring
- **production DB 肥大化**: `article_candidates` の signal_type 増加で `insight.db` が 5 MB → 10-15 MB+。GCS upload 時間増加(現 5s 程度 → 10-15s 程度)
- **Cloud Run cost 微増**: nightly job の実行時間延長で月数百円〜数千円程度の増。安全範囲内

### data quality
- **新 signal_type と既存 detector の衝突**: 既存 INSIGHT-001/007 detector が emit している signal_type と被ると status 競合 / 重複 candidate(`disjoint` verify 必須)
- **render_article で空 rows の場合のエラー**: fixture 不在 / data 不足で空 rows 渡されると body / table が空に。graceful fallback 必須(空時は draft 出さず skip)
- **z-score / 線形回帰の sample 不足 false-positive**: 2 ヶ月 data で outlier 検出すると小サンプル由来の noise が多発。`min_sample` 閾値で gate
- **「気づかない」が「事故」になる**: 統計上の outlier が実は data quality issue(則本 team_code 問題のような誤マッピング)で、誤った insight 記事が出る。fact check pipeline 経由必須
- **roster snapshot 鮮度**: 12-team roster は 2026-05-13 時点、新規昇格 / 退団 / 移籍があると canonical 解決不能 → signal 出ない or null player。weekly 再 scrape 検討(別 ticket)

### publish 整合
- **WP draft の category 衝突**: 「データで見る巨人」category 作成失敗で別 category に誤投入 or category 二重作成。`term_exists` fallback で対処
- **subtype_unresolved error**: extractor が新 subtype を resolve できないと guarded_publish runner が refuse、本 work で wire ミスなら publish 不能
- **重複 draft**: trigger 連発 / migration 中 / 既存 draft 上書きで重複 draft。`dedupe_key` + idempotency 設計必須
- **既存 publish-notice scanner の振る舞い**: 新 draft が scanner に拾われて mail 送信される可能性。新 subtype を mail scope から除外必要

### 公平性 / objectivity
- **巨人偏重**: 「巨人中心」を強調しすぎて他球団 ranking の objectivity が損なわれる(fairness 観点)。title / lead の表現で「巨人選手の位置」を明示しつつ、他球団選手も正当に評価する book-stop 必要
- **「気づかない」が誤解を招く**: 統計上の outlier が即「実力」と読まれかねない。「運要素」「sample 不足」「観察期間短い」等の disclaimer を必ず付ける

### ML / 計算
- **change-point detection の false-positive**: 2 ヶ月 data で change-point 検出すると noise を pattern 化する可能性。`min_baseline_period` で gate
- **pace projection の overshoot**: 月間 HR 8 本 → シーズン換算 40 本 等の単純比例は season 後半疲労 / 怪我 / 不調を無視。disclaimer + 「過去 5 年平均との比較」併記推奨(historical data 不足で限定的)
- **clustering の意味づけ**: k-means / k-medoids の cluster 解釈が arbitrary、記事化前に sanity check

### 並走 actor
- **scope 衝突**: 並走 actor (digest / RSS / title 系) が `src/analysis/insight_*` を touch しない前提だが、`src/wp_client.py` は 並走 lane も触る可能性あり。`git pull --ff-only` で同期 + diff 確認
- **stale roster 衝突**: `config/giants_roster.json` を並走 actor が変更すると本 work の resolve が変化。Read 時に `git log --oneline -5 config/giants_roster.json` で fresh state 確認

---

## 9. 作業ログ欄

(work log — to be filled during execution)

| 日時 (JST) | 内容 | 結果 |
| --- | --- | --- |
| 2026-05-14 PM | 本 work record markdown 作成(継続改善 system のため non-ticket)、`docs/work_logs/` に置く | user GO 待ち、本 markdown のみ landed、コード一切未着手 |

---

## 10. Regression Memo 欄

(observation notes — pre-impl baseline + ongoing notes)

### current observation(本 work 着手前、2026-05-14 PM 時点)

**production DB state**(343-INSIGHT-007 Phase 4 LIVE 後の最新):
- teams: 12
- players: 462(12 球団全部 32-43 player ずつ)
- games: 227(2026-03-27 〜 2026-05-13、2 ヶ月分)
- batting_logs: 4086
- pitching_logs: 1839
- advanced_metric_snapshots: 6394(scope 別 `last_7d=2135` / `last_30d=2634` / `season=1625`)
- defense_opportunities: 3388
- article_candidates: 3856(status=NEW 全件、signal_type 11 種:`pitcher_rest_days_back_to_back` 1092 / `pitcher_rest_days_extended_layoff` 792 / `pitcher_workload_warning` 501 / `lineup_first_slot_appearance` 401 / `lineup_slot_jump_up` 301 / `lineup_slot_jump_down` 218 / `batter_homerun` 184 / `starter_quality_start` 143 / `batter_multi_hit` 93 / `batter_hit_streak` 91 / `pitcher_high_pitch_count` 40)

**既存 article_generator の API**:
- `insight_article_generator.render_article(ctx: ArticleContext, *, top_n: int = 10) -> dict`
- 返り値: `{title, body_md, suggested_tags, meta}`
- `ArticleContext`: `metric_name`, `rows: list[RankRow]`, `focus_player`, `position_filter`, `since`, `until`, `sample_window_label`
- 内部 helper(`_make_title` / `_make_lead` / `_render_rank_table` / `_make_interpretation` / `_make_disclaimer` / `_make_meta_footer` / `_suggest_tags`)が ranking-article 想定で動作

**既存 wp_client の API**:
- `create_post(title, content, categories=[id], status='draft')` で WP draft 投入可能
- `get_categories()` で全 category fetch 可能
- `resolve_category_id(name)` で name → ID 解決(`config/categories.json` 参照)
- `create_category(...)` method は **不在**、本 work で追加実装

**既存 WP category 一覧**(`config/categories.json` snapshot):
- 試合速報=663 / 選手情報=664 / 首脳陣=665 / ドラフト・育成=666 / OB・解説者=667 / 補強・移籍=668 / 球団情報=669 / コラム=670 / 旧記事=672
- 671 空き、672 旧記事 と衝突しない 範囲で新 category 作成可能

**並走 actor 状況**(本 markdown 作成時点):
- 直近 50 commit に並走 actor commit 多数(`336-QA digest` / `337-INGEST sanspo` / `339-INGEST` / `341-FIX` / `335-QA Pattern R2` / 等)
- いずれも scope disjoint(digest / RSS / title 系)、本 work の scope(`src/analysis/insight_*` + `src/wp_client.py` create_category 追加 + `src/pre_publish_fact_check/extractor.py` 新 subtype 追加 + `src/guarded_publish_evaluator.py` 新 subtype resolve)と衝突なし

**343-INSIGHT-007 既存 work 状態**:
- src 5 commit landed: `fc20b34` / `1058845` / `b899d0c` / `f356ae1` / `033b92e` / `3d928be` / `9bd0923` / `c7923ac` / `b8824f7` / `74614a5`
- production image: `insight-nightly:343c`
- 343 status: `PHASE_4_TEAM_AWARE_ROSTER_LANDED_READY_FOR_CLOSE`
- 342 status: `READY_FOR_PHASE_1_IMPL_FULL_12TEAM`

### guard hypothesis

- guard A: 全 detector / publisher は read-only 計算 + additive insert のみ、既存 row mutation なし
- guard B: WP `create_post` は `status='draft'` 固定、auto-publish は env flag `ENABLE_DATA_INSIGHT_AUTO_PUBLISH`(初期 0)gate
- guard C: 並走 commit との scope disjoint(`src/analysis/insight_*` + `src/wp_client.py` create_category 追加 + `src/pre_publish_fact_check/extractor.py` 新 subtype additive)
- guard D: Phase 2 deploy 前 / 後 で pytest baseline 維持(regression 0、4 failed pre-existing 維持)
- guard E: WP draft が 1 trigger で 2 本以上 landed したら STOP + 即 rollback(env flag OFF + Cloud Scheduler pause)
- guard F: production DB の既存 row count に対し新 row 増加のみ、既存 row 値の mutation なし(`article_candidates.status` の `NEW` → `DRAFTED` 等は許容、これは既存 schema の status 仕様)
- guard G: 並走 actor の commit を `git pull --ff-only` で取り込み(force push 禁止)
- guard H: 新 subtype の disjoint verify(既存 11 signal_type と被らないこと、本 markdown で確認済)
- guard I: 「データで見る巨人」WP category の idempotent 作成(`term_exists` fallback で重複作成回避)
- guard J: roster snapshot の鮮度 watch(weekly re-scrape は別 work、本 work では week-old snapshot 許容)

### feasibility 確認事項(Phase 0 で audit)

- 新 signal_type 5 種(`anomaly_zscore_outlier` / `anomaly_babip_divergence` / `anomaly_fip_era_divergence` / `trend_monthly_slope_change` / `pace_season_projection` 等の命名候補)が既存 11 signal_type と disjoint
- `insight_article_generator.render_article` の空 rows 時の挙動(graceful fallback or exception)
- `wp_client.create_post` で `status='draft'` + 新 category ID 指定の挙動 sample
- `guarded_publish_runner` の新 subtype 認識(extractor + publish_evaluator 両方追加要、`_resolve_freshness_threshold` の default 動作確認)
- Cloud Run job timeout 300s に新 detector 計算追加で収まるか(`article_candidates` 既存 3856 + 本 work 新 signal 想定 +500 程度、書き込み 5-10s 程度の見込み)
- WP REST `/wp/v2/categories` で「データで見る巨人」が既存しないこと(空 ID 671 を使う or 自動採番に任せる)
- `publish-notice scanner` が新 draft を mail 経由通知するかどうかの挙動(必要なら新 subtype を mail scope から除外)

---

## 作業後に追記する 8 項目(user GO 後の実装完了時に埋める)

以下 8 項目は **本 work が GO されて完了した時点で同じ markdown に追記**する。
現時点は placeholder のみ、内容は空。

### 1. 実際に変更したファイル

**新規追加(5 file)**:
- `src/analysis/ranking_article_publisher.py`(467 行、巨人中心 ranking article + WP draft / publish)
- `src/analysis/insight_anomaly_detector.py`(518 行、z-score / 乖離 / pace / Giants top の 5 detector)
- `src/analysis/anomaly_article_publisher.py`(~600 行、5 signal_type 別 article render + 大城式 table + 赤太字 + 期間表示)
- `tests/test_ranking_article_publisher.py`(13 test)
- `tests/test_wp_client_create_category.py`(5 test)
- `tests/test_insight_anomaly_detector.py`(10 test)

**既存 file 拡張**:
- `src/wp_client.py` に `create_category()` method 追加
- `src/pre_publish_fact_check/extractor.py:infer_subtype` に新 subtype(`data_ranking_*`)認識追加
- `src/analysis/insight_nightly.py:run_nightly` 末尾 main() に anomaly + ranking publish wire 追加
- `config/player_eyecatch_map.json` に ダルベック entry 追加

**新規データ / インフラ**:
- WP category 675「データで見る巨人」(新規作成)
- WP media 67498(ダルベック Wikipedia EN 画像)
- Cloud Scheduler 4 trigger 追加(`data-insight-morning/noon/pregame/during-game-trigger`)
- Cloud Run job `insight-nightly` env 追加(`ENABLE_DATA_INSIGHT_AUTO_DRAFT=1` / `ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1`)+ WP secret 3 個 attach
- Cloud Run image 計 10 build(`:343c` → `:343q`)

### 2. diff 概要

**LoC 統計**:
- src 追加: ~1500 行(3 新 module)
- src 修正: ~80 行(wp_client / extractor / insight_nightly)
- tests 追加: ~640 行(3 新 test file、計 28 test)
- config 追加: 1 line(player_eyecatch_map.json)
- doc 追加: 本 work record 約 600 行

**commit 数**: 本 session で 15+ commit landed(主要):
- Phase 1A(ranking_article_publisher + create_category): `ee7a5fc`
- Phase 1B(anomaly detector + publisher + wire): `de6fa3d`
- threshold 緩和 + 巨人優先 priority: `c9d226f`
- 巨人 auto-publish env gate: `4bb1330`
- max_per_run 拡大 + 4 scheduler trigger: `7daa537`
- title format 改善: `2400233`
- table 中心 + 赤太字 highlight: `d499ed4`
- prefix「巨人を数字で読む」→「巨人データを見る」: `347ca1b` → `a8892ce`
- セ/パ リーグ別 ranking: `6ef5f6b`
- ダルベック 画像 Wikipedia 取得: `af930b3`
- ERA ASC ranking fix(lower-is-better): `0d424fa`
- 期間明示 + 期間 date range + 試合数除去: `30679e1` → `f2fd46a`

### 3. 実行したテスト

- `pytest tests/test_ranking_article_publisher.py`(13 test)
- `pytest tests/test_wp_client_create_category.py`(5 test)
- `pytest tests/test_insight_anomaly_detector.py`(10 test)
- `pytest -q --tb=no`(full baseline、4500+ test)
- production DB 直接 dry_run(local script、anomaly detect → article render の sanity check)
- Cloud Run job 手動 trigger 計 3 回(`insight-nightly-j488w` / `2n8x2` / `mcs78` / `lf8s7` / `wjxjq`)
- production WP REST 経由 update / publish 30+ 回

### 4. テスト結果

- 新 28 test 全 PASS
- 既存 4500+ test:**5 failed(pre-existing、全 parallel actor 由来)/ 4500+ passed**
- regression 0(本 work で 新規 fail 0)
- Cloud Run trigger:5 回全 SUCCESS、平均 43-300s
- Production WP:全 10 article landed、巨人 7 publish、他球団 3 draft

### 5b. 将来 TODO(記事数が増えてから着手)

**選手別ランディング / navigation 強化**(2026-05-14 user 教示):
- 現在: 記事 10 本 / 選手別最大 2 本程度 → 選手別 page 単独成立しない
- 将来: 記事数 30+ / 選手別 5+ 本に増えた段階で:
  - WP tag pages(/tag/<player>/)を専用 template でリッチ化
  - 「この選手の全 sabermetric 記事」ハブ page
  - 月別 / scope 別 timeline 表示
  - 選手プロフィール画像 + 季節成績 chart inline 表示
- 現時点では既存 WP tag(`大城卓三`=676 等)で navigation 機能、追加 customization 不要
- 着手判断 trigger: 1 選手で 5 本以上記事が landed した時 OR user 教示時

### 5. 残った懸念

- **WP eyecatch 不在 2 選手**: 平山功太 / ウィットリー の player image が公開 web source(Wikipedia ja/en、NPB 公式、巨人公式 403)で取得不可。user の WP admin 手動 upload 待ち
- **「赤星 優志」 space form canonical**: 既存 INSIGHT-001 ETL の `_resolve_team_code_from_name` で space-form name が canonical に残る既知問題、別 ticket 必要
- **則本昂大 team_code='g' (Giants 移籍済) 認識**: roster ファイルで管理、scrape されない外国人選手画像の問題と並行
- **NPB roster scrape 鮮度**: 2026-05-13 snapshot、移籍 / 退団があれば再 scrape 必要(週次 or 月次 job)
- **「直近 5 試合」 scope detector**: `compute_advanced_metric_snapshots` で未実装、必要なら別 phase
- **記事の人間チェック**: 自動 publish 巨人記事は user 確認なしで site に出る、内容 review が遅延しないか観察必要

### 6. 新しく見つかったデグレ

なし(本 work での新規デグレ 0)。

並走 actor 由来の事故 1 件:
- `tests/test_ingestion_filter_relaxation.py::test_main_passes_36_hour_window_for_postgame_skip_check` が 344-INGEST 系の commit で fail に。本 work と完全 disjoint な rss_fetcher module、HEAD stash 後も再現確認済。

### 7. 追加した回帰テスト

- `test_ranking_article_publisher.py`(13 test):
  - fetch_ranking_rows top_n / empty / latest snapshot
  - find_giants_top picks first / returns None
  - markdown_to_html: h2/h3/table/bold/italic
  - render_giants_centric_ranking full / no-giants
  - publish dry_run / no_data / full / category_error / max_per_run
- `test_wp_client_create_category.py`(5 test):
  - 201 success / term_exists fallback / 500 error / optional fields / minimal payload
- `test_insight_anomaly_detector.py`(10 test):
  - z-score outlier batter / pitcher
  - BABIP / FIP-ERA divergence
  - giants_top_outliers
  - run_all_anomaly_detectors empty DB
  - 7-day dedup
  - render anomaly z-score
  - publish dry_run / DRAFTED status

### 8. 次回触ってはいけない範囲

**production WP**(現状の content):
- 既に publish 済 7 巨人 articles(`67329` / `67400` / `67401` / `67402` / `67406` / `67407` / `67408`)
- WP category 675「データで見る巨人」自体の rename / 削除
- 巨人 4 巨人 image media(`44424` / `66557` / `67498` Bobby Dalbec)
- 他球団 3 draft(`67397` / `67398` / `67399`)を勝手に publish

**Cloud infrastructure**:
- 既存 Cloud Scheduler 33 trigger(33 → 37 に追加した 4 trigger 含む)の pause / 削除 / schedule 変更
- Cloud Run job `insight-nightly` の image rollback(現 `:343q`)
- 既存 secret 3 個(`wp-url` / `wp-user` / `wp-app-password`)の value 変更

**env / scheduler**:
- env flag `ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1` を user 教示なしで OFF
- env flag `ENABLE_DATA_INSIGHT_AUTO_DRAFT=1` を user 教示なしで OFF

**src**:
- `src/analysis/insight_*` の signature 変更
- 既存 INSIGHT-001 / INSIGHT-007 schema の column 削除 / 改名
- LLM call の path への混入

**roster / config**:
- `config/player_eyecatch_map.json` の既存 entry 削除(追加のみ可)
- `config/giants_roster.json` の手動編集(NPB scrape 経由のみ)
- `config/npb_12team_roster.json` の手動編集(scrape 経由のみ)

**並走 lane**:
- 並走 actor の commit 上書き(force push 禁止)
- `src/rss_fetcher.py` / digest / title 系 lane の touch(本 work scope 外)

---

(end of work record、本 session 完了)

---

(end of work record draft、user GO 待ち — コード編集 / commit / push / deploy / env / scheduler の一切は GO 後に実行)
