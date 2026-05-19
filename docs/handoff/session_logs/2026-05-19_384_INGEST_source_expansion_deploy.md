# 2026-05-19 session log — 384-INGEST source expansion deploy

## sequence (JST)

| time | event | ticket | hash / id | next |
|---|---|---|---|---|
| 10:00 | chat session 開始: 9 時 publish 0 件調査 | – | – | freshness gate 確認 |
| 10:15 | spec verify: `STRICT_BREAKING_NEWS_THRESHOLDS` で `source_time_missing_review` review 落ち = 仕様通り、9 時 52 件 evidence | – | – | – |
| 10:25 | user 「ソースをふやしたい、ガードに引っかからない」 chat lock | – | – | ticket 384 起票判断 |
| 10:30 | ticket 384 起票 + GitHub Issue #59 作成 | 384 | – | implementation |
| 10:45 | Phase 1 + 2 実装 commit | 384 | `620121c` | Cloud Build |
| 10:48 | Cloud Build fire (sankei-spa) | 384 | – | – |
| 10:51 | Cloud Build SUCCESS (fetcher + xpm) `384-sankei-spa-620121c` | 384 | `edd62387` / `39326f49` | deploy |
| 10:53 | fetcher rev `00437-qh7` 100% + xpm gen `24` Ready=True | 384 | – | Phase 3 検討 |
| 10:58 | Phase 3 (chunichi-chuspo) 実装 fire | 384 | – | – |
| 10:56 | 並走 commit `c289704` (author yoshihiro) が 384 Phase 3 src + 385 doc を着地 | 384/385 mixed | `c289704` | – |
| 11:00 | Cloud Build fire (chunichi) | 384 | – | – |
| 11:02 | Cloud Build SUCCESS (fetcher + xpm) `384-chunichi-c289704` | 384 | `334164e8` / `45ae8a25` | deploy |
| 11:05 | fetcher rev `00439-ksd` 100% + xpm gen `25` Ready=True | 384 | – | observation |

## c289704 attribution trace (要重要)

commit `c289704` (author `yoshihiro <yoshihiro@example.com>`, message `"385: record youtube caption deploy evidence"`) は実は **2 ticket の変更が同 commit に含まれる**:

| ファイル | 内容 | 帰属 ticket |
|---|---|---|
| `src/rss_fetcher.py` | `_POST_GEN_VALIDATE_TOPIC_SOURCE_FAMILIES` に `chunichi` 追加 | **384 Phase 3** |
| `src/source_trust.py` | `chunichi` family + SourceProfile | **384 Phase 3** |
| `src/tag_page_scraper.py` | `fetch_chunichi_chuspo_giants_entries` + suffix regex + registry | **384 Phase 3** |
| `tests/test_source_trust.py` | chunichi family 認識 +1 test | **384 Phase 3** |
| `tests/test_tag_page_scraper.py` | chunichi scraper +2 test | **384 Phase 3** |
| `config/rss_sources.json` | 中日スポ entry 追加 | **384 Phase 3** |
| `doc/active/385-INGEST-youtube-caption-short-quote-summary.md` | 385 ticket 14 行追記 | 385 |
| `doc/active/assignments.md` | 385 status 更新 | 385 |
| `doc/README.md` | 385 entry 更新 | 385 |

**git log で 384 を追う時、`c289704` は "385:" prefix で見落としやすい**。本 session log で帰属を明示する。

実装は技術的に問題なく、pytest 5306 passed (baseline 5303 + 3 chunichi 新規)、deploy 完了 (fetcher rev `00439-ksd` / xpm gen `25`)。

## 384 deploy state (final)

- fetcher service: `yoshilover-fetcher-00439-ksd` 100% / image `384-chunichi-c289704` (digest `sha256:03e3ccf555a52dab7aa06f5a44cbc61bd93c6b2afd2a6890354646068dfe4691`)
- x-post-mail-lane job: generation `25` Ready=True / image `384-chunichi-c289704` (digest `sha256:f3e75438d89d76035659c53b767d89f2fdf4f06a6a36b763dff033755b3a5892`)
- Cloud Build 4 SUCCESS: `edd62387` / `39326f49` (sankei-spa) + `334164e8` / `45ae8a25` (chunichi)
- pytest: 5306 passed, 1 xfailed, 3 xpassed, baseline regression 0

## 加えた source

| family | URL pattern | scraper kind | max_age_days | publish-time 取得方法 |
|---|---|---|---|---|
| sankei | `https://www.sankei.com/article/YYYYMMDD-HASH/` | `sankei_giants_search` | 7 | `<meta name="article:published_time">` (name attribute) |
| nikkan_spa | `https://nikkan-spa.jp/<id>` | `nikkan_spa_giants_search` | 30 | `<meta property="article:published_time">` |
| chunichi | `https://www.chunichi.co.jp/article/<id>` | `chunichi_chuspo_giants_search` | 14 | JSON-LD `"datePublished"` 経由 (`_extract_embedded_published_date`) |

## Phase 2 (publish-time fallback chain) 追加内容

`src/tag_page_scraper.py:_build_entry_from_article_meta` の published_time 取得 chain:

1. `meta.get("article:published_time", "")` — property / name 両方 (`_extract_og_meta` の既存設計)
2. **`meta.get("article:modified_time", "")` ← Phase 2 で追加** (保守的 fallback)
3. `meta.get("date", "")`
4. `_extract_embedded_published_date(article_html)` — JSON-LD `datePublished` 等 (既存)
5. `_extract_datetime_attr(article_html)` — `<time datetime>` (既存)
6. `_fallback_struct_from_yyyymmdd(fallback_yyyymmdd)` — URL date pattern (既存)

guard logic (`_strict_source_time_review_required`) は変えず scraper 側で source_time を立てる設計 = 品質 gate 維持。

## 並走 session 由来の混乱 (5/19 11:10-11:15 JST)

session 進行中、別 session (author `yoshihiro`) が同時 commit を着地。私の local 編集と origin が乖離し、以下が起きた:

- 私が打った doc commit `bb7ff10` (LIVE_DEPLOYED_OBSERVE 更新) は local-only で push 失敗 (remote が前進していた)
- 並走 session が `c289704` を rewrite (`abadce2` / `92cfd44` 連鎖) して chunichi 含む全 src + 385 doc を 1 commit に詰めた
- 私が `git reset --hard origin/...` で同期 → bb7ff10 doc 変更が消失
- 本 session log は私の固有 file、並走 conflict なし → 単独 commit で着地

production image (`384-chunichi-c289704`) は abandoned commit `c289704` を base に build = blob hash 経由で持っているので動作には影響なし。ただし git log で `c289704` を grep すると見つからない可能性 (force-push で history rewrite された場合)。

## 観察項目 (5/20 朝集計)

1. fetcher log で `[SOURCE] url=https://www.sankei.com/article/` / `https://nikkan-spa.jp/` / `https://www.chunichi.co.jp/article/` の出現件数
2. guarded-publish log で sankei / nikkan_spa / chunichi URL の `freshness_basis=source_time` 取得件数
3. tag_scrape log で `_is_ymd_within_window` false (古い記事 skip) の件数
4. 24h baseline 比較: 既存 16 family の `source_time_missing_review` 件数 (deploy 前 vs deploy 後 24h)
5. WP draft 数増 evidence: deploy 後 24h で新規 draft 数増 (sankei + nikkan_spa + chunichi 由来分)

## 次セッション 引継ぎ

- 5/20 朝、上記 5 項目を Cloud Logging で集計
- 全 acceptance ✓ なら ticket 384 を `doc/done/2026-05/` へ move + GH Issue #59 CLOSE
- Phase 4 (THE ANSWER) は別 ticket 化判断
- もし sankei / nikkan_spa / chunichi のいずれかから 0 件 fetch なら、HTML 構造変化 / selector 不一致 の可能性、narrow fix 起票

## 不可触 (本 session 中)

- env / Secret / Scheduler / RUN_DRAFT_ONLY
- WP既存記事 / X / SNS / publish 動線
- 既存 16 family の挙動 (regression 0 で verify 済)
- `_POST_GEN_VALIDATE_TRUSTED_FAMILIES` (full bypass)
- numeric fact validator / close_marker / placeholder_body / hard-stop
- `STRICT_BREAKING_NEWS_THRESHOLDS` 閾値判定
