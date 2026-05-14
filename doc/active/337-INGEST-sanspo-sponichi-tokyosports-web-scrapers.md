# 337-INGEST サンスポ / スポニチ / 東スポ web 記事 scraper 拡張

## meta

- ticket: 337-INGEST-sanspo-sponichi-tokyosports-web-scrapers
- owner: Claude Code
- status: DESIGN_DRAFT / INVESTIGATION_PHASE_ONLY
- priority: P2(C / D / B 完了後の媒体拡張)
- created: 2026-05-14
- numbering reserved: 337(README に追加予定、本 doc とは別タイミング)
- depends_on: なし(独立、ただし C / D の進捗とは並走可)
- 関連 ticket: 288-INGEST-source-coverage-expansion(planning 状態の親、本 ticket は実装側)
- 関連 memory: `project_multi_source_digest_subtype` / `feedback_hochi_priority_no_imitate` / `feedback_title_no_ai`

## 背景

2026-05-14 audit で直近 50 WP post の URL ホスト分布を計測:

| 媒体 | recent 50 件中 web 記事数 |
|---|---|
| hochi.news | 80(scraper 動作中) |
| daily.co.jp | 5(scraper 動作中、絶対数少ない) |
| sanspo.com | 0 |
| sponichi.co.jp | 0 |
| nikkansports.com | 0(RSS atom 登録あるのに 0、別軸) |
| tokyo-sports.co.jp | 0(scraper 未接続) |

つまり「報知・デイリー以外の web 記事は yoshilover に流入していない」が確定。本 ticket はサンスポ・スポニチ・東スポの 3 媒体の web 記事 ingestion を新規 / 拡張する。日刊スポーツは別 ticket(RSS atom debug、本 ticket scope 外)。

## scope(本 ticket がやる事)

1. **調査 phase**(本 ticket Phase 1):
   - 各媒体の巨人記事の article URL pattern を実 URL で確認
   - 各媒体の HTML 構造を `src/source_article_body_extractor.py` 既存 extractor で extract 可能か local verify
   - bot block / rate limit / robots.txt の挙動確認
   - 著作権 / 引用要件(主従関係 / 出所明示 / literal のみ)の境界確認
2. **実装 phase**(別 commit 単位、調査完了後):
   - サンスポ: `tag_page_scraper.py` の既存 `sanspo_giants_search` を `config/rss_sources.json` に登録(narrow、+10 行)
   - 東スポ: 新規 scraper(URL pattern `/articles/-/{記事ID}` 既知、+80 行)
   - スポニチ: URL pattern 調査後、新規 scraper(+100 行程度の見積、上振れ可能性)
3. **canary**(別 commit):
   - 各媒体 1 媒体ずつ単独 enable、24-48h 観察 → 次媒体
   - publish 影響なし(default で draft 化 + noindex 維持)

## 3. 今回触らない範囲

- **報知**(hochi.news / hochi.co.jp / sports.hochi.co.jp)の既存 scraper(`tag_page_scraper.hochi_giants_tag`)
- **デイリー**(daily.co.jp)の既存 scraper(`tag_page_scraper.daily_giants_tag`)
- **巨人公式**(giants.jp)/ **NPB 公式**(npb.jp)の登録(`source_trust.py` の primary family)
- **日刊スポーツ**(nikkansports.com)の RSS atom 流入経路(別 ticket、本 ticket では touch しない)
- 既存 `publish` flow(`guarded_publish_runner.py` / `publish_notice_scanner.py` 等)
- mail 通知(`mail_delivery_bridge.py` / `morning_analyst_email_sender.py`)
- scheduler(`giants-weekday-daytime` / `giants-realtime-trigger` / `giants-postgame-catchup-am` 等)
- env 変数 (`ENABLE_*` 一切 touch しない、本 ticket はデフォルトで OFF gate を入れる場合のみ env 追加 1 件まで)
- Cloud Run service 設定(memory / CPU / concurrency 等)
- 334-QA digest path(`player_voice_digest_clusterer.py` / `player_voice_digest_body_renderer.py`)
- 335-QA title path(`title_template_assembler.py` の `_assemble_pattern_A` / `_R` / `_X`)
- C fix(`_fetch_url_html` 修復、別 work)
- D 336-QA(digest 報知引用、別 work)
- 既存 published 記事(forward-only、遡及変更なし)
- AI / LLM call(literal extraction のみ、`feedback_title_no_ai` 継承)
- X 投稿 path(`x_post_*.py` 一切 touch しない)
- WP REST mutation(本 ticket は draft 生成までで、publish flip は既存 gate 経由)

## 4. 影響範囲

新規追加 / 変更が想定される箇所:

| ファイル | 想定変更 | 行数見積 |
|---|---|---|
| `src/tag_page_scraper.py` | 東スポ scraper 関数 / スポニチ scraper 関数 新規追加(サンスポは既存利用) | +180 行 |
| `config/rss_sources.json` | 3 媒体の web 記事 source entry 追加 | +30 行 |
| `src/source_article_body_extractor.py` | 各媒体の HTML pattern 追加(extractor が既存 path で fall through できなければ) | +50 行(条件依存) |
| `src/source_trust.py` | サンスポ・スポニチ・東スポ の family 登録(東スポは既存、サンスポ・スポニチも既存) | 0 行(既存維持) |
| `src/nomotoke_card_renderer.py` | `_PRIMARY_HOST_LABELS` 拡張(東スポは既存、サンスポ・スポニチも既存) | 0 行(既存維持) |
| `tests/test_tag_page_scraper.py` 等 | 各媒体 fixture-based unit test | +200 行 |

合計 推定 +460 行、ただし調査結果次第で上下動する。

## 5. 実行予定テスト

- **調査 phase(本 ticket 開始時)**:
  1. 各媒体の巨人記事の URL pattern を実 URL で確認(2-3 件、local fetch)
  2. `extract_article_body_excerpt` を各 URL に対して実行、>0 字を返すか確認
  3. 各媒体の tag/index page を fetch、article 一覧抽出 regex の draft を作る
  4. 著作権 / robots.txt 確認
  5. 結果を本 doc の「9. 作業ログ欄」に記録、code 変更 0
- **実装 phase(別 commit)**:
  1. 各媒体 scraper 関数の fixture-based test(2-3 件、tag page + article page)
  2. `extract_article_body_excerpt` の媒体別 fixture test
  3. 既存 pytest baseline(現状 333 passed + α)維持、増減 0
  4. AST / py_compile pass
  5. 既存 hochi / daily scraper の回帰 test 不変
- **canary phase(別 commit)**:
  1. local docker / Cloud Run で実 fire を 1 回、各媒体の article URL が candidate 化されるか確認
  2. WP draft 化、publish せず観察
  3. 1 媒体 24-48h 観察後、次媒体

## 6. STOP 条件

以下のいずれかが起きたら **即 stop、user 報告 + 巻き戻し検討**:

1. 既存 publish flow の挙動が変わった(hochi / daily で異常)
2. pytest baseline が減少した(増減 0 を維持できない)
3. AI / LLM call が新 path に紛れ込んだ
4. 各媒体の web 記事が bot block / rate limit / 403 / 404 で安定 fetch できないことが判明
5. 著作権 / 法務に触れる挙動(literal 引用境界違反、出所明示欠落、長文 copy 等)
6. duplicate detection が壊れて 1 article が複数 publish される
7. Cloud Run timeout / OOM 等の resource pressure
8. mail / scheduler / env / publish gate に副作用が出た
9. `git status` の余分な dirty が出た(scope 拡大)
10. user から「stop」「rollback」指示

STOP 時の手順:
- 該当 commit を revert
- 本 doc「9. 作業ログ欄」に STOP 理由を記録
- 影響範囲を user に報告

## 7. 禁止事項

- AI / LLM call を新 path に追加する(literal extraction 一択、`feedback_title_no_ai` / `feedback_hochi_priority_no_imitate` 継承)
- 既存 published 記事の遡及修正
- publish / mail / scheduler / env(`ENABLE_*` の既存値変更)を touch する
- Gemini call の増加(本 ticket は extractor 拡張のみ、LLM コスト増 0)
- 著作権境界の緩和(literal 引用以外、長文 copy、出所明示省略 等)
- 報知・デイリー の既存 scraper(`hochi_giants_tag` / `daily_giants_tag`)の挙動変更
- Phase 4 canary を同 commit に含める(必ず別 commit)
- C fix / D 336-QA / 334-QA / 335-QA の path に touch する
- `git add -A`(memory: `feedback_doc_folder_policy_permanent` / `feedback_git_diff_cached_verify_strict`)
- 並走 commit(memory: `feedback_codex_supervision_rules` の commit 直列 lock)
- 1 commit に複数媒体の scraper を混ぜる(媒体ごとに narrow PR)

## 8. 想定されるデグレ

| デグレ | 発生条件 | mitigation |
|---|---|---|
| 既存 hochi / daily scraper が壊れる | scraper helper 共通化で副作用 | hochi / daily 関数を touch しない、新規関数を分離 |
| extractor が新 HTML pattern で empty を返す | media 側 HTML 構造が想定外 | local fixture で先に verify、unmatch 時は silent skip(既存 behavior) |
| bot block / 403 / rate limit | media 側の対 bot 措置 | User-Agent / Accept-Language / robots 確認、fetch 失敗時は silent skip(既存 behavior) |
| duplicate post(同一記事を別 url で複数取得) | tag page と RSS atom の URL 形式違い | 既存 `_normalize_history_title` / `same_fire_source_urls` で吸収、新規 normalize 不要 |
| candidate 数増加で fire 時間延長 | 4 媒体 × 30 article/fire → 上限超え | 既存 `article_limit` / `max_age_days` を保守的に設定(7 days / 30 article 上限) |
| 既存 candidate selection で slot 圧迫 | publish slot は 1 fire 10 件、追加分で他 candidate 流出 | `RUN_DRAFT_ONLY=0` 影響なし、draft 化のみで publish gate は既存 |
| 著作権 / 引用要件違反 | extractor が長文 copy / 出所欠落 | `_insert_body_excerpt_block` の既存 `nomotoke-source-excerpt__attr` 出所明示を再利用 |
| 各媒体 scraper の HTML 変更時に silent 落ち | media 側 HTML rewrite | extractor が empty を返した時の log が既に C fix で追加されている(再利用) |

## 9. 作業ログ欄

(本 ticket 開始時点で空。調査 phase / 実装 phase / canary phase で時系列に追記する)

```
YYYY-MM-DD HH:MM JST | event | 内容 | commit/log ref
```

### 2026-05-14 調査 phase 結果(code 変更 0、local fetch + extractor reproduce)

#### 各媒体の article URL pattern 確定

| 媒体 | tag/index page | article URL pattern | http_status |
|---|---|---|---|
| sanspo | `https://www.sanspo.com/?s=巨人`(検索) | `https://www.sanspo.com/article/{YYYYMMDD}-{code}/` | 200(593K bytes) |
| sponichi | `https://www.sponichi.co.jp/baseball/`(top page、巨人専用 tag は無さそう) | `https://www.sponichi.co.jp/baseball/news/{YYYY}/{MM}/{DD}/kiji/{ID}.html` | 200(non-tag) |
| tokyo-sports | `https://www.tokyo-sports.co.jp/list/label/%E5%B7%A8%E4%BA%BA` | `https://www.tokyo-sports.co.jp/articles/-/{記事ID}` | 200(258K bytes) |

#### extractor 動作 verify(local fetch、`extract_article_body_excerpt`)

| 媒体 | fetch | extractor | 抽出例 |
|---|---|---|---|
| sanspo `/article/20260514-37LTR6XPVROZNINMRJGCEA376M/` | ✓ 402,986 bytes(redirect follow 後) | **✗ EMPTY**(原因: 非貪欲 regex の早期切断) | regex `\barticle-body\b` は **match している(1468 字)**、しかし sanspo HTML は `<div class="article-body"><figure><div>...</div></figure><p>本文</p>...</div>` の nested 構造で **非貪欲 `.+?` が最初の内側 `</div>` で停止 → 中身は figure/image element だけ → HTML strip 後 EMPTY** |
| sponichi `/baseball/news/2026/05/14/kiji/20260514s00001173060000c.html` | ✓ 115,254 bytes | ✓ 587 字 | `「巨人・坂本 延長12回に逆転サヨナラ通算300号！...」` 含む坂本本人 quote 抽出成功 |
| tokyo-sports `/articles/-/388121` | ✓ 247,925 bytes | ✓ 506 字 | `「巨人は１３日の広島戦（福井）で延長１２回の末...坂本勇人内野手（３７）のＮＰＢ通算３００号となる逆転３ラン...」` 試合詳細抽出成功 |

#### 媒体ごとの必要作業(調査確定)

| 媒体 | 必要作業 | 想定 |
|---|---|---|
| sanspo | (1) extractor pattern 拡張(sanspo HTML 構造に対応、`source_article_body_extractor.py` に sanspo-specific selector 追加)+ (2) scraper 有効化(`config/rss_sources.json` に search-based source entry 追加、code は `tag_page_scraper.sanspo_giants_search` 既存) | 中(extractor 拡張要)、+30-50 行 |
| sponichi | scraper 新規作成(`tag_page_scraper.py` に `sponichi_giants_filter` 関数追加、top page から記事抽出 → 巨人記事 filter)、extractor は既存利用 | 中(filter 必要、tag page が無く top page から巨人記事を識別)、+80-100 行 |
| tokyo-sports | scraper 新規作成(`tag_page_scraper.py` に `tokyo_sports_giants_label` 関数、`/list/label/巨人` から articles 抽出)、extractor は既存利用 | 軽(URL pattern 明快、tag page 構造単純)、+60-80 行 |

#### 共通注意点(調査で判明)

- bot block / 403 / rate limit: 3 媒体とも UA `Mozilla/5.0 (...) Chrome/120.0.0.0 Safari/537.36` で 200 取得成功、production の Cloud Run でも同じ UA で動くか別途 verify 必要(本 ticket scope 外、C fix の知見利用)
- sponichi tag page: `/baseball/giants/` 404、`/baseball/teams/giants/` 404、`/baseball/team/giants/` 404、`/baseball/team_news/` 404 → **巨人専用 tag が無い**、top page から filter する方式が必要(sanspo 検索ベースと類似だが、sanspo は検索 query で巨人指定可能、sponichi は top page 全体から hits=20+ の article を識別)
- 著作権 / 引用境界: 既存 `_insert_body_excerpt_block` の literal 600 字 抜粋 + `nomotoke-source-excerpt__attr` 出所明示で各媒体とも遵守可能、新規緩和不要
- robots.txt 確認: 本 phase では行っていない(本 ticket Phase 1 着手前に各媒体 robots.txt を確認、実装着手 gate)

#### Phase 1 実装着手前の追加 verify(本 ticket 完了)

| 項目 | 結果 | 影響 |
|---|---|---|
| **1. robots.txt** | sanspo / sponichi / tokyo-sports 全て `User-agent: *` Allow。AI bot 専用 blocklist (ClaudeBot / GPTBot 等) は別系統、現 yoshilover UA = browser-like Chrome → block 該当せず | 3 媒体すべて scraping 適法、UA 変更不要 |
| **2. 既存 extractor selector 読み込み** | `_SITE_SELECTORS` の sanspo entry が `\barticle-body\b` regex 非貪欲 `.+?` で nested div で早期切断、`<article>` fallback も 5 字、JSON-LD `articleBody` field 不在(0 字)。balanced div counter で本物 body 1754 字抽出可 検証済 | sanspo は extractor 拡張必須(balanced helper 追加 or 既存 regex 書き換え) |
| **3. sponichi 巨人 filter** | sponichi HTML には `article-body` class 不在(`class="text"` のみ)、しかし `<article>` tag fallback で 6121 字 stripped text 取得成功。/baseball/ top page には「巨人」hits を持つ article URL が複数件混在、scraper で巨人 keyword count filter(threshold 検討中)で識別必要 | extractor 変更 0、scraper のみ新規。filter は本文中「巨人」hits >= 5 で巨人記事と判定する draft 案 |
| **4. tokyo-sports URL 抽出 regex** | `/list/label/巨人` page に `href="/articles/-/{ID}"` 形式の 5 件 URL 確認。既存 `tag_page_scraper.py` の hochi / daily と同じ `<a href=...>` + regex 抽出パターンに整合 | 整合可、新規実装は既存パターン踏襲(`tokyo_sports_giants_label_tag` 関数) |
| **5. candidate 数上限 / max_age_days 保守値** | 既存 hochi: `max_age_days=7, article_limit=30`、daily: 同じ。新 3 媒体も同 default(7 days / 30 article)を採用提案。fire 時間影響は実装後の local fire test で再評価 | 既存 default に揃える → 設定一貫性、Cloud Run timeout risk は実装後 verify |

#### 実装方針 lock

| 媒体 | 実装内容 | 行数見積 |
|---|---|---|
| **tokyo-sports**(最軽量、Phase 1) | (a) `tag_page_scraper.py` に `tokyo_sports_giants_label_tag` 関数追加 (b) `config/rss_sources.json` 登録 (c) tests | +80 行 |
| **sponichi**(Phase 2) | (a) `tag_page_scraper.py` に `sponichi_giants_filter_tag` 関数追加(top page → 「巨人」hits 5 以上 filter)(b) `config/rss_sources.json` 登録 (c) tests | +100 行 |
| **sanspo**(Phase 3、要 extractor 拡張) | (a) `source_article_body_extractor.py` に sanspo 用 balanced div helper 追加 + 呼び出し integration (b) `config/rss_sources.json` 登録(scraper code 既存) (c) tests | +120 行 |

各 phase 完了 → AST + py_compile + pytest baseline 維持 verify → narrow commit。媒体ごと別 commit、まとめ commit しない。

### Phase 1 実装ログ(tokyo-sports、2026-05-14)

```
2026-05-14 11:xx JST | impl | src/tag_page_scraper.py に fetch_tokyo_sports_giants_entries 関数追加(+90 行)
2026-05-14 11:xx JST | impl | _SCRAPER_REGISTRY に "tokyo_sports_giants_label" 登録
2026-05-14 11:xx JST | impl | config/rss_sources.json に「東スポWEB 巨人 label」 entry 追加(max_age_days=7, article_limit=30)
2026-05-14 11:xx JST | test | tests/test_tag_page_scraper.py に FetchTokyoSportsGiantsEntriesTests 4 件追加
                              - test_extracts_articles_and_strips_tospo_web_suffix
                              - test_filters_articles_older_than_max_age_days
                              - test_drops_articles_without_published_time
                              - test_registered_in_scraper_kinds
2026-05-14 11:xx JST | verify | AST OK, py_compile OK
2026-05-14 11:xx JST | verify | pytest test_tag_page_scraper.py: 27 → 31 passed (+4 新規)
2026-05-14 11:xx JST | verify | 広め smoke (7 file): 337 passed / 0 failed / 30 subtests
2026-05-14 11:xx JST | verify | local fire test (実 fetch、東スポ label page): 5 entries 取得成功
                                  - 「【巨人】坂本勇人３００号は逆転サヨナラ弾」等 巨人記事のみ
                                  - title "| 東スポWEB" suffix strip 確認
                                  - published_time 正常 parse(2026-05-13)
                                  - age_filtered_out=0(全件 1 日以内)
```

## 10. Regression Memo 欄

(本 ticket で新たに見つかった既存挙動の不審点 / 既存テスト不在の領域 / 次回触る時の注意点を時系列に記録)

```
YYYY-MM-DD | finding | 内容 | 推奨対応
```

---

## 作業後追記欄(完了後に user 指示で本欄に追記する)

### 1. 実際に変更したファイル

(空、commit 完了後に追記)

### 2. diff 概要

(空、commit 完了後に追記)

### 3. 実行したテスト

(空、commit 完了後に追記)

### 4. テスト結果

(空、commit 完了後に追記)

### 5. 残った懸念

(空、commit 完了後に追記)

### 6. 新しく見つかったデグレ

(空、commit 完了後に追記)

### 7. 追加した回帰テスト

(空、commit 完了後に追記)

### 8. 次回触ってはいけない範囲

(空、commit 完了後に追記)
