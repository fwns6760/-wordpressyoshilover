# 342-INSIGHT-data-driven-ranking-auto-publish

| field | value |
|---|---|
| ticket_id | 342-INSIGHT-data-driven-ranking-auto-publish |
| priority | P1(ヨシラバー独自 enrichment、INSIGHT 基盤の活用第一弾) |
| status | PHASE_0_AUDIT_DONE_PHASE_1_SPEC_PENDING(2026-05-14 user GO 後 Claude Phase 0 完了) |
| owner | Claude Code |
| lane | INSIGHT |
| created | 2026-05-14 |
| doc_path | doc/active/342-INSIGHT-data-driven-ranking-auto-publish.md |
| ready_for | Phase 1 spec 精度上げ(本 doc §10 Phase 0 audit 結果反映)+ user GO → impl 着手 |
| blocked_by | (Phase 0 完了で unblock)、Phase 1 着手は Phase 0 結果を踏まえた spec 精度上げ + user GO |
| numbering_reserved | doc/README.md に追記予定 |

## 目的(B 案: 設計 + 初版 + 拡張可能 framework)

INSIGHT-001〜009 で構築済 data 基盤(12 球団 batting/pitching、20+ advanced
metrics、UZR proxy、rank → article draft generator)を活用し、**大手スポーツ
メディアがやらない sabermetric / cross-team data-driven 定期 publish 記事** を
ヨシラバー独自の差別化コンテンツとして自動配信する。

- 拡張可能な framework として設計(後で記事種を追加できる shape)
- 初版 1-2 種類を Phase 1-2 で実装(候補は §影響範囲 §初版候補)
- pure rule-based(LLM 不使用)で **コスト 0 維持**
- 過去 publish 不変、forward-only

## scope

### 含む

- INSIGHT data 取得 → ranking 計算 → article draft → WP publish の自動 pipeline
- 「定期 re-publish(Type B)」と「snapshot 1 回(Type A)」両対応の framework
- Cloud Scheduler 新規 job 1-2 個(週次 / 月次 発火)
- 新 subtype / category タグの WP 側登録(noindex 既定維持)
- mail 通知 / X intent との連携(既存 path 流用、設定変更なし)
- 全 12 球団 metrics + 巨人選手 rank 計算
- 既存 player_eyecatch_resolver からの eyecatch 選定
- 拡張可能性: 新 ranking 記事種を low-cost で増やせる design

### 含まない

- 過去 publish の遡及 update / mutation
- LLM 文章生成(rule-based template のみ)
- 新規 data source の追加(既存 INSIGHT data に限定)
- noindex 解放 / SEO 設定変更
- live 更新型(Type C、同 URL を時間で書き換え)記事
- ファン投票 / interactive 要素
- 新規 Cloud Run service 立ち上げ(既存 fetcher / insight-nightly 流用)

### 初版候補(Phase 1-2 で実装)

優先順:
1. **A1 月次 巨人選手 OPS / wOBA / ISO ranking**(月 1 回、月末発火)
2. **B2 守備指標(UZR 代理)で 12 球団 rank**(月 1 回、月末発火)
3. **B1 12 球団 OPS top 30 + 巨人選手の位置**(月 1 回)
4. **E1 直近 7 / 14 試合 hot/cold ranking**(週 1 回、月曜発火)

Phase 1 で 1-2 種、Phase 2 で残り or 別系統。

## 3. 今回触らない範囲

- 既存 publish flow(postgame / manager / lineup / pregame / farm / broadcast /
  notice / player_voice_digest 等)の title / body 生成ロジック
- `src/rss_fetcher.py` 既存 entry point(`_main`、entry 走査、record 整形)
- `src/wp_client.py` 既存 publish chokepoint
- `src/title_template_assembler.py` 既存 pattern 関数(`_assemble_pattern_A..O`)
- `src/guarded_publish_runner.py` の dedup ledger / publish gate logic
- `src/analysis/insight_*.py` 既存 module の signature(追加 OK、改名 / 削除 NG)
- master ブランチ / 既存 Cloud Run image build pipeline
- Cloud Run **既存** service / job の env / secret / SA permission(追加 OK、既存削除 NG)
- Cloud Scheduler **既存** job の enable / pause / schedule(新規 job 追加のみ可、既存触らない)
- WordPress 本文 / publish status / noindex / canonical / 301 / SEO
- WP custom table / `wp_postmeta` schema
- Gemini call / GEMINI_API_KEY 経路 / X API / X 自動投稿
- 既存 publish 済 post の body / title / status / meta(retroactive 一切なし)
- 既存 mail 通知の format(per-post mail、burst summary)
- player_eyecatch_map / giants_roster.json の構造(read 専用、追加 OK)

## 4. 影響範囲

### 新規追加

- `src/analysis/ranking_publisher.py`(仮称、新規 module):
  - INSIGHT DB から ranking query → article draft 組み立て → WP publish に飛ばす
  - rule-based template, no LLM
  - 記事種を拡張可能にする dispatcher 構造(`ranking_type` enum + handler map)
- `src/analysis/ranking_templates/`(仮称、新規 dir):
  - 各 ranking 種類ごとの template 関数(`monthly_ops_ranking.py`、
    `defense_ranking.py`、`cross_team_ranking.py` etc.)
  - title pattern + body section 構造を pure Python で定義
- 新規 Cloud Scheduler job(1-2 個):
  - 週次 / 月次発火、`insight-nightly` 系 job の trigger と区別
  - URL = 既存 fetcher / insight 系 service の新 endpoint(または既存 job 拡張)
- 新規 WP category / tag(必要に応じて):
  - 「データで見る巨人」「巨人ランキング」等のカテゴリ(noindex 既定維持)
- 既存 `src/wp_client.py` を経由(変更なし、利用のみ)
- 新規 tests: `tests/test_ranking_publisher.py` + `tests/test_ranking_templates_*.py`
- 本 ticket doc 自身: `doc/active/342-INSIGHT-data-driven-ranking-auto-publish.md`
- `doc/README.md` 内 ticket index 追加

### 既存への影響(read-only / additive)

- `src/analysis/insight_article_generator.py`(INSIGHT-008): read 利用、内部 helper
  関数を再利用する可能性あり(変更なし、import のみ)
- `src/player_eyecatch_resolver.py`: 選手 eyecatch 解決に利用(read のみ)
- WP REST API の `posts` endpoint: 新規 publish 経路として利用(既存挙動不変)
- mail 通知 path: 新 post も既存 publish-notice scanner で拾われる(既存路線、
  format 変更なし)

### 影響しない(verify した上で記載)

- 既存 publish post の表示 / SEO / canonical / 出力 HTML
- 既存 X 自動投稿(本 ranking 系は X OFF 維持)
- 既存 fetcher / publish-notice / guarded-publish / broadcast-auto / lineup-auto /
  postgame-auto / publish-notice / draft-body-editor の image / env / scheduler
- 既存 insight-nightly job の動作

## 5. 実行予定テスト

### Phase 0(audit)

- `src/analysis/insight_*` の public API 一覧化、ranking publisher が利用できる
  helper 関数の特定
- INSIGHT DB の schema 確認(advanced_metrics の field 一覧、defense proxy の
  field 一覧)
- 既存 WP category / tag 一覧 verify(衝突しない category 名選定)
- duplicate_guard / publish gate の挙動 verify(新 post type を skip しないこと)

### Phase 1-2(narrow impl)

- **module 単体テスト**(fixture-based):
  - 固定 sample data から expected ranking output(top N 選手 + score)
  - title pattern が template と一致
  - body HTML が期待 section 構造(banner / fact card / ranking table /
    fan voice section / 出典)を含む
  - eyecatch resolver が呼ばれる
- **ranking 計算ロジック**:
  - 同点処理 / 欠損データ処理 / 選手非 active 除外
  - 全 12 球団分の data shape 不整合に対する graceful fallback
- **WP REST publish dry-run**:
  - draft 作成までを mock で確認(実 publish しない unit test)
- **regression**:
  - 既存 pytest baseline 維持(pass 数 増減 0)
  - 既存 publish path に touch していないことを `git diff --stat` で確認
- **integration**(Phase 2 末尾):
  - canary 1-2 本 publish(noindex / X OFF / mail OFF で局所確認)
  - WP REST で content_html を fetch、構造 + ranking 数値を audit

### Phase 3(live canary、user GO 必要)

- 月次 scheduler 1 回発火、production publish 観察
- mail 通知が正常に出るか
- duplicate_guard が新 post を弾かないか
- 既存 publish 数 / publish 失敗 数の regression が無いか

## 6. STOP条件

- 既存 publish flow(postgame / manager 等)に regression(本文崩れ / publish
  失敗 / mail 二重送信 等)が出たら STOP
- LLM call(Gemini / GPT / 他)が ranking publish path に混入したら STOP
- 過去 post の mutation を観測したら STOP(forward-only 違反)
- pytest baseline が 1 件でも新規 fail を出したら STOP
- Cloud Scheduler の **既存** job の enable / pause / schedule を変更したら STOP
- X 自動投稿に影響(新 post が X intent 経由で投稿される等)が出たら STOP
- 新 post の publish に **既存 WP category(試合速報 / 選手情報 / 等)** が誤って
  付与され、既存記事と category 上で混在したら STOP
- Cost が想定外に増加(Cloud Run 実行時間 / Gemini call / Cloud Scheduler
  料金)したら STOP
- noindex / SEO 設定が変更されたら STOP

## 7. 禁止事項

- env / secret(GCP Secret Manager / Cloud Run env)変更
- master 以外への force push / master の history rewrite
- 既存 publish history / dedup ledger の削除 / mutation
- LLM(Gemini / GPT / 他)への新規 call 追加(rule-based 限定)
- noindex / SEO / canonical / 301 設定変更
- WP custom table の schema 変更
- 既存 publish 済 article の body / title / status / meta 変更
- X 自動投稿の enable / 新カテゴリの X 投稿対象化
- 既存 Cloud Scheduler job の enable / pause / schedule 変更
- 既存 INSIGHT-* module の signature 変更(rename / 削除 NG、追加 OK)
- `git add -A` 使用(明示 path のみ stage)
- `--no-verify` / hook skip
- 既存 publish 経路への hook 挿入(pre-publish filter 等)
- 新規 data source の追加(別 ticket、本 ticket scope 外)

## 8. 想定されるデグレ

- **duplicate_guard 誤判定**: 新 post type を既存 guard が認識せず、毎回 dup と
  判定 → publish 0 件
- **mail 通知量増加**: 新 post も既存 publish-notice scanner が拾うため、user に
  「ranking 記事公開」mail が増える(意図通りだが noise になる可能性)
- **fan voice section の fallback 表示**: 新 post type に fan voice X embed が
  なく、毎回「関連ポストなし」になる(設計上問題ないが見た目気になるかも)
- **eyecatch 不在**: 12 球団 ranking 等で複数選手が登場する記事の eyecatch を
  どう選ぶか未確定 → 既存 fallback(team logo)に落ちる可能性
- **WP category 衝突**: 新規 category 名が既存と被ると分類が乱れる
- **publish freshness check**: 既存 stale guard が「同じ data の月次 ranking」を
  古い data と誤判定して skip する可能性
- **front front-page 混入**: 新 post が front-page 上位に出て postgame 記事を
  押し下げる(category 分離 + sorting で予防予定)
- **mobile レイアウト崩れ**: ranking table が mobile で table 横スクロールに
  なる可能性
- **Cloud Scheduler 無料枠超過**: 月 1-2 ジョブ追加で月 ¥15-30 程度の課金発生
  (実質ゼロだが厳密には 0 ではない)
- **historical compare の欠損**: 「前月比」「前年同月比」を出したいが過去 season
  data の蓄積期間によっては比較できない

## 9. 作業ログ欄

| 日時 (JST) | 内容 | 結果 |
| --- | --- | --- |
| 2026-05-14 | 本 ticket doc 作成(B 案: 設計 + 初版 + 拡張 framework) | user GO 待ち |
| 2026-05-14 PM | user GO 受領後 Claude が Phase 0 audit 完了(7 項目、read-only、§10 audit 結果に追記) | 4 項目 ✓ / 1 項目 △ / 2 項目 ✗、Phase 1 着手前に spec 精度上げ必要 |

## 10. Regression Memo欄

### current observation(本 ticket 着手前)

- INSIGHT-001〜009 着地済、`insight-nightly` job 稼働、`manual-intake-service`
  の 2 タブ GUI 配信中
- 12 球団 advanced metrics + UZR 代理 + atbats parse landed(INSIGHT-007)
- rank → article draft generator(INSIGHT-008)+ NL question → draft
  (INSIGHT-009)は landed、ただし **publish path に wire されていない**
  (現状は GUI から手動で draft を見るのみ)
- 本 ticket は INSIGHT-008/009 の draft を **自動 publish に橋渡しする**位置付け

### guard hypothesis

- guard A: 新 post の category / tag は既存と完全 disjoint な命名(例: 「データ
  分析」「巨人ランキング」)で分離、既存 front sorting / SEO に影響しない
- guard B: 新 publish path は既存 guarded_publish runner の **dedupe_key** に
  ranking-specific prefix(例: `ranking:monthly:2026-05`)を持たせ、既存
  dedup ledger と物理的に分離
- guard C: 新 publish の `meta.notice_kind` / `meta.subtype` は新規値で発行、
  既存 publish-notice scanner が format 拡張に対応する形(または scanner 側で
  skip するように分岐追加)
- guard D: fan voice section は本 ranking 系では「関連ポストなし」fallback で
  OK(2026-05-14 PM の `_ensure_fan_voice_section` 設計と整合)
- guard E: eyecatch は player ranking 系は top 1 選手の eyecatch、12 球団系は
  team logo(将来追加)、未解決時は既存 fallback

### feasibility 確認事項(Phase 0 で audit)

- INSIGHT DB の monthly aggregation query が現在の schema で可能か
- 「月末」発火を Cloud Scheduler で表現できるか(cron `0 23 28-31 * *` 等で末日判定)
- 12 球団 batting/pitching の月次 sample 数(N=最小 50 PA / 30 IP 等)を満たす
  選手数
- WP REST で新 category 作成 + 新 post publish の権限が既存 `WP_USER` で足りるか

### Phase 0 audit 結果(2026-05-14、Claude、user GO 後)

全項目 1 次 source verify(`feedback_ai_top_failure_modes_meta_rule` 準拠、handoff
2 次 source 推論禁止)。

| # | 項目 | 結果 | 詳細 |
|---|---|---|---|
| 1 | INSIGHT DB schema の `advanced_metric_snapshots` 定義 | ✓ | `data/insight/schema.sql:201-216` に既存定義あり、`scope` ('season' / 'last_7d' / 'last_30d' / 'last_5_games')、`metric_name` (free-form: 'OPS' / 'wOBA' / 'FIP' / 'RF_proxy')、`sample_size`、`league_rank`、`position_rank` 揃う。月次は `last_30d` 流用 or 新 scope 値追加 |
| 2 | `src/analysis/insight_*.py` 公開 API | ✓ | `insight_rank_query.rank_players()` / `get_player_rank()` / `_aggregate_batting/pitching()` (内部) / `RankedRow` class、`insight_article_generator.render_article(ctx, *, top_n=10) -> dict` / `RankRow` / `ArticleContext` class、`insight_defense_proxy.uzr_proxy_for_player()` / `position_summary_for_player()` / `league_position_baseline()` / `rebuild_defense_for_game()` 利用可、改名 / 削除しない |
| 3 | 既存 WP category 一覧 + 衝突 check | ✓ | `config/categories.json` に 9 件: 試合速報(663) / 選手情報(664) / 首脳陣(665) / ドラフト・育成(666) / OB・解説者(667) / 補強・移籍(668) / 球団情報(669) / コラム(670) / 旧記事(672)。671 空き。提案命名「データで見る巨人」「巨人ランキング」は衝突なし、disjoint |
| 4 | duplicate_guard / publish gate 挙動(新 subtype 対応) | ✓ partial | `src/guarded_publish_runner.py` に subtype-aware guard 完備(`extractor.infer_subtype(title)` / `publish_evaluator.resolve_guarded_publish_subtype()` / `_resolve_subtype_cleanup()`)。新 subtype は両 module への追記必須、未追記時は `CandidateRefusedError("cleanup_ambiguous", "subtype_unresolved_no_resolution")` で publish が拒否される。dedupe_key は `nomotoke_rss_router._dedupe_key(template_key, canonical)` で sha1[:12] |
| 5 | Cloud Scheduler 月末 cron 表現可否 | △ | `gcloud scheduler jobs list` で 33 既存 job 確認、月末発火 job は **存在しない**(全部 daily / hourly / weekly / cron-fixed)。標準 cron で「月末」は直接表現不可。**推奨**: (a)`0 23 28-31 * *` 毎日発火 + script 側で末日判定 or (b)月初発火(`0 0 1 * *`)で「先月分 monthly ranking」を出す方が clean。`insight-nightly-trigger`(`0 2 * * *` ENABLED)が既に存在、関連 job として並走 OK |
| 6 | 12 球団 monthly sample 数 (実 data) | ✗ | local DB(`data/insight/insight.db`、110KB、2026-05-13 更新)が **INSIGHT-007 additive table 全部 missing**(`teams` / `players` / `defense_opportunities` / `advanced_metric_snapshots` 4 table 不在)。INSIGHT-001 base のみ(games:1 / batting_logs:18 / pitching_logs:11)。production DB は GCS bucket `baseballsite-yoshilover-insight` 上(`INSIGHT_GCS_BUCKET` env、`insight_gcs_sync.py` で download / upload)。**Phase 1 前に GCS 経由で本番 DB pull → sample 数 verify 必須**(local では絶対 verify 不能) |
| 7 | WP REST 新 category 作成 + WP_USER 権限 | ✗ | `src/wp_client.py` には `get_categories()` (line 1283) と `resolve_category_id(name)` (line 1299) のみ、**`create_category` / `add_category` method は不在**。新 category 作成 path は (a)Phase 1 で `wp_client.create_category()` 新 method 実装 or (b)WP admin GUI で手動作成 → `config/categories.json` に手動追記。`WP_USER` + `WP_APP_PASSWORD` (application password) は admin 権限相当、API 側の権限不足は無し(method 実装の問題) |

#### Phase 1 前に必要な spec 精度上げ(audit から導出)

a. **GCS から production DB を pull して 12 球団 monthly sample 数を実 measure** (audit #6 の follow-up)
   - 最小 PA / IP 閾値(N=50 PA / 30 IP)を満たす選手数を球団別に計測
   - `last_30d` scope の既存 snapshot 件数 + period coverage(現在 INSIGHT-007 が production で何ヶ月分蓄積されているか)
   - sample 不足な球団 / position があれば、初版 4 候補のうち実装可能順を再優先順位付け

b. **新 subtype 命名 + extractor / publish_evaluator への追加 spec** (audit #4 の follow-up)
   - 候補命名: `monthly_ops_ranking` / `defense_uzr_ranking` / `cross_team_ops_top30` / `recent_hot_cold_ranking`
   - `extractor.infer_subtype(title)` の title 判定 rule(title 中の「月次」「ranking」「top 30」「hot/cold」等)
   - `publish_evaluator.resolve_guarded_publish_subtype()` の resolution path

c. **`wp_client.create_category()` 新 method の spec** (audit #7 の follow-up)
   - WP REST POST `/wp/v2/categories` を call、name + slug + parent + description を受ける
   - 既存 method `get_categories()` (line 1283) と対称、application password で auth 通る
   - エラーハンドリング: 既存 category 名と衝突したら何を返すか(WP REST は 400 + `term_exists`)

d. **Cloud Scheduler 月末発火戦略の最終決定** (audit #5 の follow-up)
   - 推奨案 (b)月初発火 `0 0 1 * *` で「先月分 ranking」を出す方が cron 純粋で操作可逆性高い
   - script 側 ranking 計算 query は「前月 1 日〜末日」を `snapshot_date` で filter、week 系は「直近 7 日」「直近 14 日」で filter

#### Phase 0 audit で **触らなかった** もの(明示)

- `src/analysis/insight_*.py` (全 14 file、read のみ、edit 0)
- `data/insight/insight.db` (read のみ、edit 0)
- `src/guarded_publish_runner.py` / `src/wp_client.py` (read のみ、edit 0)
- `config/categories.json` (read のみ、edit 0)
- Cloud Scheduler / Cloud Run / GCS (gcloud list のみ、mutate 0)
- `data/insight/schema.sql` (read のみ、edit 0)
- production DB / GCS bucket(read もしてない、env 変数の存在確認のみ)

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
