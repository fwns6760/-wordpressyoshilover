# 384-INGEST source expansion with publish-time fallback

## meta

- status: DESIGN_LOCKED / READY_FOR_IMPL
- priority: P1
- owner: Claude
- created: 2026-05-19
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/59
- scope: 産経 / 日刊SPA / 中日新聞 / 中日スポーツ / THE ANSWER 等の source 追加 + meta なし媒体の publish-time 抽出 fallback

## user intent (2026-05-19 chat lock)

- 「要はソースをふやしたい、ガードに引っかからないが私の希望」
- 古い記事を出すのは引き続き避ける (5/19 朝 chat: 「古いものは出さないようにしてる」)
- 「記憶から再構成 / silent skip / 自己評価 OK」は禁止、証拠ベースで進める

## root cause (2026-05-19 chat verify)

381 で追加した 16 family のうち、`article:published_time` meta を持たない媒体は guarded-publish で `source_time_missing_review` に review 落ちしている (9 時 cycle で 52 件 evidence)。

新規追加候補も同様の問題:

| 媒体 | URL | meta 有無 | guard 通過 | 追加可否 (現状の scraper) |
|---|---|---|---|---|
| 産経 (sankei) | `https://www.sankei.com/?s=巨人` | ✓ `<meta name="article:published_time" content="2026-05-19T05:30:00+09:00"/>` | ✓ | **追加可** |
| 日刊SPA | `https://nikkan-spa.jp/?s=巨人` | ✓ `<meta property="article:published_time">` | ✓ | **追加可** (search の sort 順は要 verify) |
| 中日新聞 / 中日スポーツ | `https://www.chunichi.co.jp/?s=巨人&genre=chuspo` | ✗ meta なし (og:type/url/image のみ) | ✗ source_time_missing_review | **scraper fallback 必要** |
| THE ANSWER | `https://the-ans.jp/?s=巨人` | ✓ feed あり | ✗ search page が SPA で article href 抽出不能 | **scraper SPA 対応必要 (別 phase)** |

既存 381 内の meta なし系 (要個別記事再 verify): 朝日 / 毎日 / FRIDAY / NEWSポストセブン / デイリー新潮 / 現代ビジネス / アサ芸 / Smart FLASH / ベースボールチャンネル — これらも root では meta 取れず、9 時 52 件 review 落ちの一因の可能性。

## implementation scope

### Phase 1: meta あり 2 媒体を追加 (確度高、scope 小)

1. **`config/rss_sources.json`**: 産経 + 日刊SPA を tag_scrape として追加
   ```json
   {
     "name": "産経新聞 巨人 search",
     "url": "https://www.sankei.com/?s=%E5%B7%A8%E4%BA%BA",
     "type": "tag_scrape",
     "role": ["article_source", "media_quote_pool"],
     "tag_scrape_max_age_days": 7,
     "tag_scrape_article_limit": 10,
     "enabled": true
   },
   {
     "name": "日刊SPA! 巨人 search",
     "url": "https://nikkan-spa.jp/?s=%E5%B7%A8%E4%BA%BA",
     "type": "tag_scrape",
     "role": ["article_source", "media_quote_pool"],
     "tag_scrape_max_age_days": 30,
     "tag_scrape_article_limit": 10,
     "enabled": true
   }
   ```
   - 日刊SPA は search が日付 sort でない可能性あり → `tag_scrape_max_age_days=30` で freshness window 制限 + `_is_ymd_within_window` で古い記事を scraper 段階で弾く

2. **`src/source_trust.py`**: `SourceFamily` に `"sankei"` と `"nikkan_spa"` 追加、`TRUSTED_SOURCE_PROFILES` に entry 追加
   ```python
   SourceProfile(family="sankei", trust="secondary", family_trust="mid",
                 domains=("sankei.com", "www.sankei.com"))
   SourceProfile(family="nikkan_spa", trust="secondary", family_trust="mid",
                 domains=("nikkan-spa.jp",))
   ```

3. **`src/rss_fetcher.py:1915`**: `_POST_GEN_VALIDATE_TOPIC_SOURCE_FAMILIES` に `"sankei"`, `"nikkan_spa"` 追加 (limited bypass)

4. **`src/tag_page_scraper.py`**: 産経 / 日刊SPA の HTML selector verify (既存 pattern で取れるか PoC)
   - 産経: `<a href="/article/YYYYMMDD-HASH/">` → article page で `<meta name="article:published_time">` 取得
   - 日刊SPA: `<a href="https://nikkan-spa.jp/<id>">` → article page で `<meta property="article:published_time">` 取得

### Phase 2: meta なし媒体向け publish-time fallback

5. **`src/tag_page_scraper.py` に fallback chain 追加**:
   - 優先順 (1) `<meta property="article:published_time">` (現状)
   - (2) `<meta name="article:published_time">` (産経が name attribute) ← Phase 1 で必要
   - (3) `<meta property="article:modified_time">` (modified を published として代用、保守的)
   - (4) URL path の `/YYYY/MM/DD/` または `/YYYYMMDD-` pattern (full-count や産経の URL から日付抽出)
   - (5) article body 内の `(2026年M月D日|2026-MM-DD|2026/MM/DD)` regex 抽出 (本文末尾の掲載日表記)
   - 全部失敗 → 現状通り source_time_missing_review 維持

6. **`src/guarded_publish_evaluator.py:_strict_source_time_review_required`**: 変更なし
   - fallback で source_time が得られた場合は scraper 側で `freshness_basis="source_time"` set されるので、guard logic は変えない
   - 「meta 無し family を guard 緩和」ではなく「fallback で source_time を立てる」設計、品質 gate 維持

### Phase 3: 中日 / 中日スポーツ追加 (Phase 2 完了後)

7. **`config/rss_sources.json`**: 中日新聞 / 中日スポーツ追加
   ```json
   { "name": "中日新聞 巨人 search", "url": "https://www.chunichi.co.jp/?s=%E5%B7%A8%E4%BA%BA", "type": "tag_scrape", ... }
   { "name": "中日スポーツ 巨人 search", "url": "https://www.chunichi.co.jp/?s=%E5%B7%A8%E4%BA%BA&genre=chuspo", "type": "tag_scrape", ... }
   ```
8. **`src/source_trust.py`**: `chunichi` family 追加
9. **chunichi 個別 verify**: Phase 2 fallback で article body 日付表記が取れるか実 verify (取れなければこの phase は HOLD)

### Phase 4: THE ANSWER (SPA、独立 ticket 化検討)

10. THE ANSWER は search page が JavaScript 動的描画。`tag_page_scraper.py` を Playwright 等で SPA 対応するか、別経路 (RSS feed の wp.the-ans.cloud-partner.site/feed/ を直接読む) を試す。本 ticket では HOLD、別 ticket で扱う。

## 不可触

- 既存 publish 済記事 (forward-only)
- env / Secret / Scheduler は最小変更 (今 ticket では変更しない)
- WP plugin / wp-admin / WP existing draft / X / SNS は touch しない
- `_POST_GEN_VALIDATE_TRUSTED_FAMILIES` (full bypass) は変えない、limited topic_source bypass のみ拡張
- numeric/fact validator / close_marker / placeholder_body / hard-stop は変えない
- 既存 16 family の挙動は変えない (Phase 1 では新規 family 追加のみ)

## 成功条件

1. 産経 / 日刊SPA から fetcher が記事を取得し、5/19 以降の自然 fire で WP draft created に成功する evidence (fetcher log で `[SOURCE] url=sankei.com/article/...`)
2. 産経 / 日刊SPA 由来の記事が guarded-publish で `source_time` を正常取得し、`source_time_missing_review` review 落ちしない (新規 family の log で `freshness_basis="source_time"`)
3. 古い記事 (`tag_scrape_max_age_days` を超えるもの) は scraper 段階で URL date check で弾かれる evidence
4. Phase 2 fallback chain により、既存 381 既追加の meta なし系 source からも source_time が立つ記事の数が増える (production log で `source_time_missing_review` count が減少する観察)
5. 既存 16 family の挙動 (Full-Count / 週刊女性PRIME / 読売新聞 等) が regression 0 = 既存 test 全 PASS
6. unit test + integration test 全 PASS、production deploy 後 ERROR 0

## デグレ試験 (regression test)

### unit test 新規追加

| test ファイル | test 内容 |
|---|---|
| `tests/test_source_trust.py` | `sankei` / `nikkan_spa` family が `_source_trust_classify_url_family("https://www.sankei.com/article/...")` で正しく classify される。既存 16 family の分類は変わらない (sankei / nikkan-spa 以外の入力は元の family を返す) |
| `tests/test_tag_page_scraper.py` | 産経 article URL fixture (`/article/20260519-HASH/` HTML) から `article:published_time` (name attribute) を抽出できる。日刊SPA fixture から `article:published_time` (property attribute) を抽出できる。古い URL (8 日前) は `_is_ymd_within_window` で skip される |
| `tests/test_tag_page_scraper_fallback.py` (新規) | Phase 2 fallback chain test: (1) property 優先 (2) name fallback (3) modified_time fallback (4) URL date fallback (5) body 内日付表記 fallback (6) 全失敗時は None (現状動作) |
| `tests/test_guarded_publish_freshness_source_time.py` | 産経 / 日刊SPA URL fixture で `freshness_basis="source_time"` が立つ regression。既存 16 family の挙動が変わらない regression (既存 fixture で `freshness_basis="source_time"` または `created_at_fallback` が同じ結果) |
| `tests/test_rss_fetcher_reliability_2026_05_08.py` | 既存 stale_source_age / source_time_missing_review の挙動が変わらない regression (`STRICT_BREAKING_NEWS_THRESHOLDS=ON` で従来の閾値判定が動く) |

### デグレ無し確認 (既存 test 維持)

- `python3 -m unittest tests.test_tag_page_scraper tests.test_source_trust tests.test_rss_fetcher_reliability_2026_05_08 tests.test_x_post_mail tests.test_guarded_publish_freshness_source_time tests.test_guarded_publish_evaluator tests.test_guarded_publish_runner` 全 PASS
- `python3 -m pytest tests/ -q` 全 PASS (collect 数と pass 数を fire 前 baseline と比較、増減 0 を確認)

### live verify (deploy 後)

| verify 項目 | 方法 |
|---|---|
| 産経 article fetch | fetcher Cloud Run log で `[SOURCE] url=https://www.sankei.com/article/` 出現 |
| 産経 freshness pass | guarded-publish log で sankei URL の `freshness_basis="source_time"` |
| 古い記事 skip | tag_scrape log で `_is_ymd_within_window` false で skip evidence |
| 既存 family 不変 | 既存 16 family の `source_time_missing_review` 比率が deploy 前と同じ (24h baseline 比較) |
| WP draft 増 | yoshilover.com 内の status=draft 新規記事数が deploy 前比で増加 (sankei + nikkan_spa 由来分) |

## verification (commit 前)

1. `python3 -m json.tool config/rss_sources.json` PASS
2. `python3 -c "import ast; ast.parse(open('src/tag_page_scraper.py').read())"` PASS
3. `python3 -m py_compile src/tag_page_scraper.py src/source_trust.py src/rss_fetcher.py` PASS
4. unit test (上記 5 ファイル) 全 PASS、collect 数 baseline 比 +N (新規 test 数)、fail 数 0
5. full pytest `tests/` 全 PASS、baseline 比 fail 数 0

## deploy plan

| step | action | rollback |
|---|---|---|
| 1 | commit Phase 1 (sankei + nikkan_spa 追加、scraper Phase 2 fallback) | git revert |
| 2 | Cloud Build `yoshilover-fetcher` + `x-post-mail-lane` image rebuild | 前 image (rev `00436-7zq`) で revert |
| 3 | Cloud Run service / job update | 前 generation で revert |
| 4 | 自然 fire 観察 (10:00 fetcher、12:00 / 15:00 x-post-mail) | env で `ENABLE_POST_GEN_VALIDATE_TOPIC_SOURCE_BYPASS=False` で limited bypass off |
| 5 | 24h evidence 集計 (sankei article 取得数 / freshness pass 率 / WP draft 数 / 既存 family regression 0) | – |
| 6 | Phase 3 (chunichi / 中日スポ) 着手判断 (Phase 2 fallback の効果 evidence ベース) | – |

## risk + 対処

| risk | 対処 |
|---|---|
| 産経 / 日刊SPA の HTML 構造変更で selector 死亡 | scraper test で fixture 化、変更検知時 narrow fix |
| Phase 2 fallback の URL date 抽出が誤動作 (古い記事を新しいと誤判定) | URL date が抽出できても `_is_ymd_within_window` で freshness window check 維持。fallback chain で source_time set した場合も freshness_check が threshold で stale 判定する |
| 既存 family の挙動変化 (Phase 2 fallback が思わぬ影響) | regression test で既存 16 family fixture を全部 check、deploy 後 24h baseline 比較 |
| 古い記事流入 (user の「古いものは出さない」原則違反) | scraper 側で `tag_scrape_max_age_days` 設定、article URL の YYYY/MM/DD path check、最終的に guarded-publish の stale_source_age gate で止まる (2 重 guard) |
| THE ANSWER の SPA 対応で依存追加 (Playwright 等) → コスト増 | Phase 4 は独立 ticket 化、SPA 対応の必要性を後で判断 |

## cost

- 全部 ¥0 (既存 Cloud Run free tier 内、新規依存なし、LLM 不使用)
- 産経 / 日刊SPA fetch frequency は既存 schedule 流用 (新規 Scheduler 追加なし)

## related

- 381 (giants general source expansion) = parent ticket、本 ticket は extend
- 377-OPS = draft-first flow、本 ticket とは独立 (377-OPS が完遂すれば本 ticket 由来の draft も mail に乗る)
- 363/364/365/366/367/368/369/370/371/372 = QA chain、本 ticket とは scope 独立

## next action

1. 本 ticket commit (doc-only)
2. GitHub Issue 起票 (日本語)
3. README.md / assignments.md 更新
4. Phase 1 実装着手 (Claude 直接、user 受け入れは Phase 1 deploy 後)
