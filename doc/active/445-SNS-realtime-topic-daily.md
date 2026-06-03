# 445 SNS リアルタイム話題 (巨人 一軍/二軍三軍) daily aggregation

## 1. ticket header

- **ticket id**: 445
- **status**: LIVE_DEPLOYED_VERIFIED (2026-06-03 13:18 JST、 SEO 編集要約 follow-up deploy + verify 済)
- **owner**: Claude Code
- **lane**: ingest / sns-realtime
- **created**: 2026-05-28
- **priority**: P1
- **github_issue**: #114 (<https://github.com/fwns6760/etc/-wordpressyoshilover/issues/114>)
- **spec doc**: `mkdocs_docs/spec/sns-realtime-topic.md`

## 2. 目的 (1 line)

Yahoo リアルタイム検索の **巨人専門 一軍 / 二軍・三軍 版** を、 既存 RSSHub + 既存 Scheduler + 既存 fetcher pipeline 相乗りで実装 (==追加コスト ¥0==)。

## 3. LIVE URL

- 一軍: <https://yoshilover.com/giants-sns-realtime-1gun/> (page_id=73959)
- 二軍・三軍: <https://yoshilover.com/giants-sns-realtime-farm/> (page_id=73960)

## 4. scope 達成項目

- source = 巨人専門 / 球団公式 X account 4 件 (`yomiuri_giants` / `TokyoGiants` / `hochi_giants` / `Sanspo_Giants`)
- RSSHub `https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/{handle}` 経由
- 発火 = 既存 fetcher Scheduler 相乗り + 内部 time gate (`hour in {10,13,17,21} and minute < 5`)、 1 日 4 回
- 出力 = **post type = page**、 永続 2 URL (`giants-sns-realtime-1gun` / `giants-sns-realtime-farm`)
- 4 fire/日 × 365 日 全部同 URL upsert (Yahoo リアルタイム検索式)
- 一軍 page = 上位 15 投稿 / farm page = 二軍 5 + 三軍 5 最大 10
- 分類 = 三軍 (`role=='ikusei'` or `育成/三軍/3軍`) / 二軍 (`ファーム/二軍/イースタン` or roster position `二軍/ファーム`) / 一軍 (default)
- トレンド = `config/giants_roster.json` 全 136 名 aliases で言及回数 count、 各 page 独立 count、 上位 15 名 (2 回以上のみ)
- render = oEmbed `https://publish.twitter.com/oembed` (X 公式、 著作権安全)

## 5. SEO 強化 (本 ticket 内)

### (a) 急上昇 marker
- 新 module: `src/sns_realtime_topic_state.py` (GCS-backed save_counts / load_previous_counts)
- path: `gs://yoshilover-history/sns_realtime_topic/counts_{date}.json` (nested per-page)
- 毎 fire で counts save、 翌日 fire で delta 表示
- ↑+5 以上 = 赤太字 / ↑+1〜4 = orange / ↓N = 灰色 / 同値 badge なし
- 初日 (前日 counts なし) は badge 抑制

### (b) tag chip → 内部リンク enrichment
- data-site page (`/data/{slug}/`、 ticket 444) 該当 player → `/data/{slug}/`
- 該当なし player → `/tag/{quote(name)}/` fallback
- WP REST `/pages?parent={data_id}` で 1 fire 1 回 fetch + cache (process-local)

### (c) 巨人ブランド design
- hero banner (黒 → オレンジ gradient + LIVE pulse + stats card)
- ranking chip (top 3 = gold / silver / bronze、 rank# 表示)
- card feed (oEmbed を border-left オレンジ frame で包む)
- 巨人カラー (黒 #000 / オレンジ #FF6F00 / クリーム #fff4e6)
- mobile responsive (@media max-width:540px)
- inline `<style>` + class prefix `ysn-` で theme conflict 回避

### (d) JSON-LD 構造化 markup (3 schema)
- **CollectionPage**: name / about=SportsTeam 読売ジャイアンツ / publisher / mainEntity=ItemList(SocialMediaPosting × 20)
- **LiveBlogPosting** (==Google SERP LIVE バッジ狙い==): coverageStart/End、 liveBlogUpdate × 20 (BlogPosting + author)
- **BreadcrumbList**: ヨシラバー → 該当 page

### (e) OGP / Twitter Card
- WP page `excerpt` に top3 トレンド + 投稿数 + 更新 schedule
- SEO SIMPLE PACK が自動で og:title / og:description / twitter:card 生成

### (f) indexability
- yoshilover は site-wide noindex (post type=post 限定で `yoshilover-post-noindex` plugin + SEO SIMPLE PACK)
- **post type=page** にすることで両 plugin の noindex 対象外、 自動 index 許可
- 既存 `/data/` `/about-yoshilover/` で検証済 (noindex なし)、 本 page も同様

## 6. 実装 file

| file | 内容 | 状態 |
| --- | --- | --- |
| `src/sns_realtime_topic.py` | main module、 fetch + 分類 + render + WP upsert + state + data-site slug | 新規 |
| `src/sns_realtime_topic_classifier.py` | 一軍 / 二軍 / 三軍 分類 + roster alias match | 新規 |
| `src/sns_realtime_topic_template.py` | template (hero / chip / data link / card / JSON-LD 3 種) | 新規 |
| `src/sns_realtime_topic_state.py` | GCS state IO (nested per-page) | 新規 |
| `tests/test_sns_realtime_topic.py` | 18 tests | 新規 |
| `tests/test_sns_realtime_topic_classifier.py` | 11 tests | 新規 |
| `src/rss_fetcher.py` | hourly run 末尾に hook (env flag) | 変更 1 箇所 |
| `mkdocs_docs/spec/sns-realtime-topic.md` | 仕様書 | 新規 |
| `mkdocs.yml` | nav 追加 | 変更 |

新規 Cloud Run Job / Dockerfile / cloudbuild は **作らない**。

## 7. deploy 経緯

| commit | image | revision | 内容 |
| --- | --- | --- | --- |
| `3811c4c` | — | — | doc + spec + ticket + GH Issue #114 |
| `da588c8` | `sns-realtime-da588c8` | `00498-547` | impl + tests + fetcher hook |
| `7ba307d` | `sns-realtime-7ba307d` | — | permanent slug + (a) 急上昇 + (b) tag link |
| `7bed2dc` | `sns-realtime-7bed2dc` | `00500-b2b` | page split + 初日 badge 抑制 + auto-post category |
| `37f1c70` | `sns-realtime-37f1c70` | `00501-ksv` | post → page 切替 (noindex 自動回避) |
| `0d09e60` | `sns-realtime-0d09e60` | `00502-qdx` | Giants design + JSON-LD (CollectionPage + Breadcrumb) |
| `3cbe211` | `sns-realtime-3cbe211` | `00503-bxc` | A LiveBlogPosting + B OGP excerpt + C /data/ 内部リンク |
| `6609bae` | `disable-social-news-6609bae` | `00504-9hw` (LIVE) | DISABLE_SOCIAL_NEWS_ARTICLES kill switch follow-up |
| `b4c8d61` | `sns-seo-b4c8d61` | `00509-wrl` (LIVE) | SEO 編集要約 + 固定 title + 人間向け excerpt + RSSHub 重複除去 |

env: `ENABLE_SNS_REALTIME_TOPIC=1` + `DISABLE_SOCIAL_NEWS_ARTICLES=1` 設定済。

## 8. tests (38/38 PASS)

- `test_sns_realtime_topic_classifier.py`: 11 tests
  - 育成 / 三軍 / 3軍 keyword → 三軍
  - ファーム / 二軍 / 2軍 / イースタン keyword → 二軍
  - roster `role=='ikusei'` match → 三軍
  - keyword + match なし → 一軍 default
  - count_mentions: alias dedup per post / empty / no match
- `test_sns_realtime_topic.py`: 18 tests
  - should_run_now: slot 内 / 外
  - filter_recent_24h: 24h window / no published
  - split_by_level
  - section_oembeds: limit / empty url skip
  - collect_all_posts: URL dedup
  - wp_tag_url_for: 日本語 URL encode
  - wp_upsert: page endpoint / status draft / no categories / no meta / update no status change
  - build_pages: 2 page / slugs / title suffix / level 分離
  - 急上昇 badge: 初日抑制 / 2 日目表示
  - run: outside_slot / 両 page upsert / load/save nested

2026-06-03 SEO follow-up:

- `python3 -m pytest tests/test_sns_realtime_topic.py tests/test_sns_realtime_topic_classifier.py` → 38 passed
- `python3 -m compileall src/sns_realtime_topic.py src/sns_realtime_topic_template.py tests/test_sns_realtime_topic.py tests/test_sns_realtime_topic_classifier.py` → OK
- AST parse (`sns_realtime_topic.py` / `sns_realtime_topic_template.py` / `tests/test_sns_realtime_topic.py`) → OK
- `git diff --check -- src/sns_realtime_topic.py src/sns_realtime_topic_template.py tests/test_sns_realtime_topic.py` → OK

## 9. 受け入れ条件 (全達成)

- [x] 4 fire/日 で WP の 2 page を upsert (1 page = 1 URL fix)
- [x] トレンド section 上位 15 名以下 (count desc、 ranking color)
- [x] 三軍 / 二軍 / 一軍 分類 rule 通り
- [x] oEmbed 正しく render (Giants frame card)
- [x] page type で noindex 自動回避 (Google index 許可)
- [x] CollectionPage + LiveBlogPosting + BreadcrumbList の 3 JSON-LD
- [x] OGP / Twitter Card meta set
- [x] /data/ 内部リンク enrichment (該当 player)
- [x] sitemap (`page-sitemap.xml`) 自動登録
- [x] 追加コスト ¥0 verify (Cloud Build / deploy 計 7 回、 全て成功、 cost 増分なし)

## 10. follow-up 完了 (2026-05-28 20:23 JST)

### DISABLE_SOCIAL_NEWS_ARTICLES kill switch
user 「SNS のポストは作りたいが、 SNS の記事はいらない」 反映。

- commit `6609bae` / image `disable-social-news-6609bae` / revision `yoshilover-fetcher-00504-9hw` (LIVE)
- env `DISABLE_SOCIAL_NEWS_ARTICLES=1` 設定済
- `src/rss_fetcher.py:main` の source load 直後で `type=social_news` 15 件 skip
- 残り 32 件 (news / tag_scrape / fan_voice_pool) は継続
- 445 SNS aggregation / X live posting (auto-tweet) は完全別経路、 影響 0
- 21:00 JST 初回 fire で `event=social_news_sources_disabled` log で動作確認予定
- 仕様書 `mkdocs_docs/spec/sns-realtime-topic.md` § DISABLE_SOCIAL_NEWS_ARTICLES に明記

## 10-B. follow-up 完了 (2026-06-03 13:18 JST)

### SEO 編集要約 + meta 安定化

user 「SNSのリアルタイムについて」「このサイトSEO強くならないのは？」への対応。

- commit `b4c8d61` / image `sns-seo-b4c8d61` / revision `yoshilover-fetcher-00509-wrl` (LIVE)
- build `031e1390-bda4-466b-9bf4-78425b788c6c` SUCCESS、 digest `sha256:4acc271e...`
- Cloud Run service `yoshilover-fetcher` 100% traffic、 Ready / Active / ContainerHealthy = True
- deploy 後 15 分 ERROR log = 0
- title を日付入りから固定型 `巨人 SNSリアルタイム速報 (一軍) | 今日のX話題まとめ` へ変更
- WP excerpt を `投稿/24h` 型の計測文から、ヨシラバーが整理する人間向け要約へ変更
- 本文 top に `ヨシラバー注目ポイント` セクションを追加し、X 埋め込み一覧だけに見えない構成へ変更
- RSSHub の title / summary 重複を除去し、JSON-LD / editor summary の重複文を軽減
- local `/health` curl は sandbox DNS 制約で未確認。Cloud Run revision health は `ContainerHealthy=True` で確認済み。

## 11. 残課題 (本 ticket scope 外、 別 ticket 候補)

- **(E) embed lazy load** (Core Web Vitals LCP 改善) — IntersectionObserver で scroll で初めて load。 工事 1h。
- **1軍 / 2軍 コーチ split** — 監督 / コーチ言及は現在 一軍 仮定。 lineup data で per-team split は別 ticket。
- **2軍3軍 source 追加** — `TokyoGiantsFarm` 等が公式に存在すれば source list 追加検討。
- **Google Search Console URL inspection** — 2 URL の「インデックス登録をリクエスト」 で初回 crawl 加速 (user 手動推奨)。

## 11. 関連 ticket

- 関連: 392 (X branding MCP)、 411 (X voice persona)、 414 (X voice quality framework) — 本 ticket は X 出力ではなく **WP 上の集約記事**
- 関連: 444 (data-site per-player) — daily upsert / 1 URL fix 方針共通、 (C) /data/ 内部リンク enrichment で連動
- 関連: 251 (SEO noindex release strategy、 waiting) — 本 ticket は noindex を post type=page で回避する narrow path、 251 とは独立
