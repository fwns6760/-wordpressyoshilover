# :material-trending-up: 巨人 SNS リアルタイム話題 (sns-realtime-topic)

!!! info "これは何のページ"

    Yahoo リアルタイム検索の **巨人専門 一軍 / 二軍・三軍 版**。 巨人専門の X 公式アカウント (球団 + 報知 / サンスポ 巨人担当) を **RSSHub 経由** で 24h 集約し、 「==今 X で何が話題か==」 を 2 ページ (一軍 / ファーム) として WordPress に毎日 4 回 update する。

    **追加コスト ¥0** (新 Scheduler なし / X API なし / LLM なし / RSSHub 既稼働 / WP は既支払 hosting)。

!!! tip "LIVE URL"

    - 一軍: <https://yoshilover.com/giants-sns-realtime-1gun/>
    - 二軍・三軍: <https://yoshilover.com/giants-sns-realtime-farm/>

## :material-clock-outline: 発火タイミング (JST)

新 Scheduler は **作らない**。 既存 fetcher trigger の中で内部 time gate で本 subtype を実行する。

| 既存 Scheduler | 該当時刻 (10-23 JST) | 本 subtype 発火スロット |
| --- | --- | --- |
| `giants-weekday-daytime` (`0 6-16 * * *`) | 10:00, 11:00, 12:00, 13:00, 14:00, 15:00, 16:00 | **10:00 / 13:00** |
| `giants-realtime-trigger` (`0,30 17-21 * * *`) | 17:00, 17:30, ... 21:00 | **17:00 / 21:00** |

実行場所: Cloud Run service `yoshilover-fetcher` の hourly run の中、 `JST.hour in {10,13,17,21} and minute < 5` の time gate で `sns_realtime_topic.run()` を呼ぶ (env `ENABLE_SNS_REALTIME_TOPIC=1` で有効化)。

== 1 日 4 回 (10:00 / 13:00 / 17:00 / 21:00) ==、 過去 24h の X 投稿を集約する。

## :material-source-branch: source = 巨人専門 X アカウント

`src/sns_realtime_topic.py:SOURCE_HANDLES` で定義する 巨人専門 / 球団公式 のみ。 野球全般の `SponichiYakyu` / `nikkansports` / `npb` は本 subtype では使わない。

| handle | 種別 |
| --- | --- |
| `yomiuri_giants` | 球団公式 |
| `TokyoGiants` | 球団公式 (英語) |
| `hochi_giants` | 報知 巨人担当 |
| `Sanspo_Giants` | サンスポ 巨人担当 |

取得は **RSSHub Cloud Run** 経由:

```
https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/{handle}?limit=30
```

- env `TWITTER_AUTH_TOKEN` で認証済 (既稼働、 追加コストなし)
- 1 fire = 4 handle × 1 request = ==4 outbound HTTP only==

## :material-pencil-box-multiple-outline: page split (2 URL)

==Yahoo リアルタイム検索式 1 URL / level== を 2 page で運用 (user 「一軍と2軍3軍はページ分けて」「一日のSNSは見える量にしたい」 反映)。

| ページ | slug | URL | levels | max 表示件数 |
| --- | --- | --- | --- | --- |
| 一軍 | `giants-sns-realtime-1gun` | `/giants-sns-realtime-1gun/` | 一軍 | 15 |
| 二軍・三軍 | `giants-sns-realtime-farm` | `/giants-sns-realtime-farm/` | 二軍 + 三軍 | 各 5 (合計 最大 10) |

- post type = **`page`** (post type=post ではない、 後述 § indexability)
- 各 page は **永続 1 URL**、 4 fire/日 × 365 日 全部同 URL を upsert
- SEO: authority concentration、 thin content URL の量産防止、 freshness signal 累積

## :material-card-bulleted-outline: 記事構造

```
<hero banner>
  ⚾ 巨人  SNS リアルタイム (一軍)
  ●LIVE  最終更新 YYYY-MM-DD HH:MM JST (10/13/17/21 JST 更新)
  [投稿/24h: 51]  [話題の選手: 27]

<トレンド section>
  🔥 今日のトレンド
  [① #戸郷翔征 17 ↑+5] [② #橋上秀樹 11 ↑+3] [③ #坂本勇人 5 →] ...

<feed section>
  📱 最新の投稿 (一軍 page)
  二軍 / 三軍 (farm page、 各 section に分割)
  - oEmbed (X 公式 blockquote)

<出典 footer>
  📡 出典 X アカウント
  @yomiuri_giants / @TokyoGiants / @hochi_giants / @Sanspo_Giants
```

### トレンド section (==最上部==)

過去 24h に集約した X 投稿の text を `config/giants_roster.json` の **全 136 名 (player 84 + coach 27 + manager 1 + shihaikako 1 + ikusei 23) の aliases** で照合し、 言及回数で sort。

- 表示: 上位 ==15 名==、 言及 ==2 回以上== のみ (1 回はノイズ除去)
- format: ranking chip `[ ① #{name} {count} ↑+{delta} ]`
  - top 1-3 は gold / silver / bronze 色
- **(a) 急上昇 marker**: 昨日の言及回数 (GCS snapshot) と diff を chip に表示
  - `↑+5 以上` = 赤太字 (急上昇) / `↑+1〜4` = orange / `↓N` = 灰色 / 同値 badge なし
  - 初日 (前日 counts なし) は badge 抑制 (全 chip ↑+N で見栄え悪化を防ぐ)
- **(b) tag chip → 内部リンク** (==C 内部リンク enrichment==):
  - data-site page (`/data/{slug}/`、 ticket 444) が **ある player** → `/data/{slug}/` リンク
  - **ない player** → `/tag/{quote(name)}/` fallback
  - data-site page slug は 1 fire 1 回 WP REST `/pages?parent={data_id}` で fetch + process-local cache

#### GCS state (a 用)

- path: `gs://{GCS_BUCKET}/sns_realtime_topic/counts_{YYYY-MM-DD}.json` (`GCS_BUCKET=yoshilover-history` 既設定済)
- format: nested per-page dict `{1gun: {name: count, ...}, farm: {name: count, ...}}`
- 毎 fire で当日の最新 counts を upload (4 fire × 30 日 = 120 file × 数 KB = 数 MB、 free tier 内)
- 翌日の fire で前日 file を load して delta 計算 (初日は空 dict、 badge 抑制)

### 一軍 / 二軍 / 三軍 分類ルール

各 X 投稿を以下の優先順で分類:

1. **三軍** = 投稿 text に `育成 / 三軍 / 3軍` 含む、 または text 内の選手名が `roster.json` で `role == "ikusei"`
2. **二軍** = 投稿 text に `二軍 / 2軍 / ファーム / イースタン` 含む、 または text 内の選手名が roster で position に `二軍 / ファーム`
3. **一軍** = 上記以外 (default)

監督 / コーチ言及は **一軍配置を仮定** (Phase 1)。 将来 lineup data で 1軍 / 2軍 コーチ split は別 ticket。

### oEmbed 埋め込み (card frame)

`https://publish.twitter.com/oembed?url={x_post_url}` を fetch して `<blockquote class="twitter-tweet">` を本文に貼る。 X 公式 oEmbed なので **著作権安全** (CLAUDE.md §18 マスコミ X 引用 oEmbed only に準拠)。

各 embed は CSS class `ysn-card` の orange border-left frame で包む。

## :material-shield-search: indexability

yoshilover は site-wide noindex policy (`yoshilover-post-noindex` plugin + SEO SIMPLE PACK)。 ただし **post type=page** は両 plugin の noindex 対象外。

| 検証対象 | 結果 |
| --- | --- |
| 既存 `/data/` (page) | `<meta name='robots' content='max-image-preview:large' />` (noindex なし) |
| 既存 `/about-yoshilover/` (page) | 同上 |
| 既存 通常 post (`/73533`) | `<meta ... content='max-image-preview:large, noindex, follow' />` |
| 本 page (`/giants-sns-realtime-1gun/`) | `max-image-preview:large` のみ (noindex なし) ✓ |

== post type=page にするだけで noindex 自動回避==、 plugin / SEO 設定 / 個別 checkbox 一切操作不要。

## :material-share-variant-outline: 構造化 markup (JSON-LD)

3 つの `<script type="application/ld+json">` を inject。

### (a) CollectionPage

| 項目 | 値 |
| --- | --- |
| `@type` | `CollectionPage` |
| `name` | `巨人 SNS リアルタイム (一軍)` 等 |
| `url` | 該当 page URL |
| `datePublished` / `dateModified` | 該当 fire の ISO 8601 +09:00 |
| `about` | `SportsTeam` 読売ジャイアンツ |
| `publisher` | `Organization` ヨシラバー |
| `mainEntity` | `ItemList` (SocialMediaPosting × max 20) |

### (b) LiveBlogPosting (==SEO 強化 A==)

| 項目 | 値 |
| --- | --- |
| `@type` | `LiveBlogPosting` |
| `coverageStartTime` | 24h 前 ISO 8601 |
| `coverageEndTime` | 該当 fire ISO 8601 |
| `liveBlogUpdate` | `BlogPosting` × max 20 (headline=投稿 text preview、 datePublished、 author=@handle) |

Google SERP で「LIVE」 rich snippet 表示の可能性。

### (c) BreadcrumbList

| position | name | item |
| --- | --- | --- |
| 1 | ヨシラバー | `https://yoshilover.com/` |
| 2 | 巨人 SNS リアルタイム (一軍) 等 | 該当 page URL |

## :material-share-circle: OGP / Twitter Card (==SEO 強化 B==)

WP page の `excerpt` field に top3 トレンド + 投稿数 + 更新 schedule を要約 set。 WP / SEO SIMPLE PACK が以下を自動生成:

| meta | source |
| --- | --- |
| `og:title` | page title (`巨人 SNS リアルタイム (一軍) (最終更新: ...)`) |
| `og:description` | hero text + excerpt から自動抽出 |
| `og:image` | site default OG image |
| `twitter:card` | `summary_large_image` (theme default) |

excerpt 例: 「巨人 SNS リアルタイム (一軍) - 過去 24h で 49 件の X 投稿。 話題: #増田大輝 (8) / #中山礼都 (8) / #浅野翔吾 (6)。 1 日 4 回 (10/13/17/21 JST) 自動更新。」

## :material-database-outline: WP upsert

- 各 page は **slug** で固定検索 → 存在 = update / 不在 = create (status=`draft` で作成、 publish は user 判断)
- update payload: `title` / `content` / `excerpt` のみ (`status` 不変)
- create payload: + `slug` + `status=draft`
- category 不要 (page は categories field なし)
- meta override も不要 (page は noindex 対象外なので `_yoshilover_index` 不要)

## :material-cog-outline: 実装 file

| file | 内容 |
| --- | --- |
| `src/sns_realtime_topic.py` | main module、 fetch + 分類 + render + WP upsert + state IO + data-site slug fetch |
| `src/sns_realtime_topic_classifier.py` | 一軍 / 二軍 / 三軍 分類 + roster alias match + count_mentions |
| `src/sns_realtime_topic_template.py` | template (hero / 急上昇 chip / data link / card feed / 出典 + JSON-LD 3 種) |
| `src/sns_realtime_topic_state.py` | GCS state IO (save_counts / load_previous_counts、 nested per-page) |
| `tests/test_sns_realtime_topic.py` | fetch mock / 分類 / page split / 急上昇 badge / wp_upsert page endpoint |
| `tests/test_sns_realtime_topic_classifier.py` | 育成 / ファーム keyword + roster alias match の boundary tests |
| `src/rss_fetcher.py` | hourly run の末尾に `sns_realtime_topic.run()` hook (env flag gate) |

依存 (本 ticket では新規 file を 作らず参照):

- `config/giants_roster.json` — トレンド count 用 (player + coach + manager + ikusei 全 136 名)
- `config/data_site_phase1_players.json` — data-site 該当 player list (Phase 1.5)
- `src/data_site_slug.py` — `player_slug(name)` で /data/ slug 生成
- `src/wp_draft_creator.py:build_oembed_block` — X 公式 oEmbed wrapper
- `src/wp_client.py:WPClient` — REST 認証

== 新規 Cloud Run Job / Dockerfile / cloudbuild は 作らない==。 既存 `yoshilover-fetcher` service の hourly run に組み込む。

## :material-currency-jpy: コスト

| 項目 | 月コスト |
| --- | --- |
| Cloud Scheduler 追加 | **¥0** (既存 trigger 相乗り) |
| X API | **¥0** (RSSHub `TWITTER_AUTH_TOKEN` 経由) |
| LLM (Gemini / Grok) | **¥0** (oEmbed 埋め込み、 AI rewrite なし) |
| RSSHub Cloud Run | **¥0** (既稼働、 outbound 4 req × 4 fire × 30 日 = 480 req/月、 free tier 内) |
| WP REST | **¥0** (既支払 hosting) |
| GCS state | **¥0** (1 file/日 × 365 日 = 数 MB、 free tier) |
| **合計** | **¥0** |

## :material-cancel: 旧 per-X-post 記事化の停止 (`DISABLE_SOCIAL_NEWS_ARTICLES`)

ticket 445 で SNS aggregation page に集約済 → **旧 個別 X-post を 1 WP article 化する path は停止**。

user 「SNS のポストは作りたいが、 SNS の記事はいらない」 (2026-05-28 PM) 反映。

### 停止する path

`config/rss_sources.json` の `type: "social_news"` source 15 件 (全 X feed)。 `rss_fetcher.py:main` の source load 直後で skip。

| 停止する処理 | 例 |
| --- | --- |
| X 投稿 1 件 → WP article 1 件 化 | 旧 `source_type=social_news` post 量産 |
| `x_tweet_article_unfurler` 経由の outbound article discovery | t.co → hochi.news の unfurl 経路 |

### 停止しない機能 (全部継続)

| 機能 | 経路 |
| --- | --- |
| ==445 SNS aggregation page== (一軍 / ファーム) | `src/sns_realtime_topic.py:SOURCE_HANDLES` の hardcoded list + RSSHub 直 URL、 `rss_sources.json` 参照しない |
| ==X live posting== (auto-tweet) | `AUTO_TWEET_ENABLED` 等 完全別 path、 本 flag の影響 0 |
| ==報知 / サンスポ / スポニチ等の直 RSS== 由来 article | `type: "news"` source 32 件、 同じ媒体の article は別経路で discover 継続 |
| fan reaction 収集 | `type: "fan_voice_pool"` source、 別経路 |
| tag scrape | `type: "tag_scrape"` source、 別経路 |

### env flag

| key | value | 効果 |
| --- | --- | --- |
| `DISABLE_SOCIAL_NEWS_ARTICLES` | `1` / `true` / `yes` / `on` | 全 X feed source を main loop で skip |
| `DISABLE_SOCIAL_NEWS_ARTICLES` | unset / `0` / 他 | 旧挙動 (全 47 source 処理) |

log signature: `event: social_news_sources_disabled, skipped_sources: 15, remaining: 32`

flag 反転は env update 1 発で即時復帰可能 (`gcloud run services update yoshilover-fetcher --update-env-vars=DISABLE_SOCIAL_NEWS_ARTICLES=0`)。

## :material-hand-pointing-up: 触らない範囲

- 既存 article / 既存 subtype の生成 path
- 既存 Cloud Scheduler の cron 式 / enable 状態
- WP frontend display CSS (本 page は inline `<style>` で完結、 theme 不干渉)
- X live posting / X API key
- featured_media rule
- 個人 X アカウント (球団 / 専門メディア以外は対象外)
- 野球全般アカウント (`SponichiYakyu` / `nikkansports` / `npb`) は本 subtype では使わない
- yoshilover-post-noindex plugin / SEO SIMPLE PACK 設定 (post type=page 切替で回避)

## :material-test-tube: tests

29 tests PASS (本 module + classifier):

- 分類器: 育成/ファーム/イースタン keyword、 roster alias match、 mention count dedup
- main: fire slot gate (10/13/17/21 :00-:04)、 24h filter、 URL dedup、 oembed limit
- page split: 2 page 返却 / slug / title suffix / level 分離
- 急上昇 badge: 初日抑制 / 2 日目表示
- wp_upsert: page endpoint (/wp/v2/pages)、 status=draft、 excerpt 含む
- run: outside_slot skip、 両 page upsert、 load_previous_counts / save_counts 呼び出し

## :material-source-pull: 受け入れ条件 (達成)

- [x] 4 fire 後の 1 日で WP に **1 URL / page** で update (revision 履歴で確認)
- [x] トレンド section に上位 15 名以下 (count desc、 1-3 位は色つき)
- [x] 三軍 / 二軍 / 一軍 分類が rule 通り
- [x] oEmbed が正しく render
- [x] page type 採用で noindex なし → Google index 許可
- [x] CollectionPage + LiveBlogPosting + BreadcrumbList の 3 JSON-LD inject
- [x] OGP / Twitter Card meta set
- [x] /data/ 内部リンク enrichment (該当 player のみ)
- [x] sitemap (`page-sitemap.xml`) 自動登録
- [x] Cloud Run / Scheduler / RSSHub の追加課金 **¥0**
