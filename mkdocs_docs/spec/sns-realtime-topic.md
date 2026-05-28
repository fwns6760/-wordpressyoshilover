# :material-trending-up: 巨人 SNS リアルタイム話題 (sns-realtime-topic)

!!! info "これは何のページ"

    Yahoo リアルタイム検索の **巨人専門 1軍 / 2軍 / 3軍 版**。 巨人専門の X 公式アカウント (球団 + 報知 / サンスポ 巨人担当) を **RSSHub 経由** で 24h 集約し、 「==今 X で何が話題か==」 を 1 記事 (3 section) として WordPress に毎日数回 publish する。

    **追加コスト ¥0** (新 Scheduler なし / X API なし / LLM なし)。 既存の RSSHub Cloud Run service + 既存の fetcher Scheduler 発火に相乗りする。

## :material-clock-outline: 発火タイミング (JST)

新 Scheduler は **作らない**。 既存 fetcher trigger の中で内部 time gate で本 subtype を実行する。

| 既存 Scheduler | 該当時刻 (10-23 JST) | 本 subtype 発火スロット |
| --- | --- | --- |
| `giants-weekday-daytime` (`0 6-16 * * *`) | 10:00, 11:00, 12:00, 13:00, 14:00, 15:00, 16:00 | **10:00 / 13:00** |
| `giants-realtime-trigger` (`0,30 17-21 * * *`) | 17:00, 17:30, ... 21:00 | **17:00 / 21:00** |
| `giants-realtime-2230` / `2300` | 22:30 / 23:00 | (なし) |

実行場所: Cloud Run service `yoshilover-fetcher` の既存 entry。 内部で `JST.hour in {10,13,17,21} and minute < 5` のとき本 subtype 生成。

== 1 日 4 回 (10:00 / 13:00 / 17:00 / 21:00) ==、 過去 24h の X 投稿を集約する。

## :material-source-branch: source = 巨人専門 X アカウント

`src/tools/manual_intake.py:3437-3441` で既に登録済の **巨人専門 / 球団公式 のみ** を本 subtype の source とする (野球全般の `SponichiYakyu` / `nikkansports` / `npb` は本 subtype では使わない)。

| handle | 種別 |
| --- | --- |
| `yomiuri_giants` | 球団公式 |
| `TokyoGiants` | 球団公式 (英語) |
| `hochi_giants` | 報知 巨人担当 |
| `Sanspo_Giants` | サンスポ 巨人担当 |

取得は **RSSHub 経由**:

```
https://rsshub-n5hunzkyna-an.a.run.app/twitter/user/{handle}?limit=30
```

- RSSHub Cloud Run は `TWITTER_AUTH_TOKEN` env で認証済 (既稼働、 追加コストなし)
- 1 fire = 4 handle × 1 request = ==4 outbound HTTP only==
- 取得失敗 handle は section から除外、 fire 自体は継続

## :material-card-bulleted-outline: 記事構造

1 記事 = 1 H1 + **トレンド section** + **3 軍別 section**。

```
H1: 巨人 SNS リアルタイム (YYYY-MM-DD HH:MM JST 更新)

## 今日のトレンド
[ #岡本和真 12 ][ #坂本勇人 8 ][ #阿部慎之助 7 ][ #吉川尚輝 5 ][ #丸佳浩 4 ] ...

## 一軍
oEmbed (X post URL)
oEmbed (X post URL)
...

## 二軍
oEmbed (X post URL)
...

## 三軍
oEmbed (X post URL)
...

## 出典 / 更新
- @yomiuri_giants / @TokyoGiants / @hochi_giants / @Sanspo_Giants
- 過去 24h の投稿を集約、 4 時刻 (10/13/17/21 JST) で更新
```

### トレンド section (==最上部==)

過去 24h に集約した X 投稿の text を `config/giants_roster.json` の **全 136 名 (player 84 + coach 27 + manager 1 + shihaikako 1 + ikusei 23) の aliases** で照合し、 言及回数で sort。

- 表示: 上位 ==15 名==、 言及 ==2 回以上== のみ (1 回はノイズ除去)
- format: clickable tag chip `[ #{name} {count} ]` (各 chip は WP の player tag page にリンク)
- 言及 0 のときは section ごと非表示 (試合なし日 + ニュースなし日)

### 一軍 / 二軍 / 三軍 分類ルール

各 X 投稿を以下の優先順で分類:

1. **三軍** = 投稿 text に `育成 / 三軍 / 3軍` 含む、 または text 内の選手名が `roster.json` で `role == "ikusei"`
2. **二軍** = 投稿 text に `二軍 / 2軍 / ファーム / イースタン` 含む、 または text 内の選手名が roster で position に `二軍 / ファーム` 含む
3. **一軍** = 上記以外 (default)

監督 / コーチ言及は **一軍配置を仮定** (Phase 1)。 将来 lineup data で 1軍 / 2軍 コーチ split は別 ticket。

各 section は ==上位 5 件== を oEmbed 埋め込み (1 記事に最大 15 投稿)。 該当 0 件の section は H2 ごと非表示。

### oEmbed 埋め込み

`https://publish.twitter.com/oembed?url={x_post_url}` を fetch して `<blockquote class="twitter-tweet">` を本文に貼る。 X 公式 oEmbed なので **著作権安全** (AGENTS.md / CLAUDE.md §18 のマスコミ X 引用 oEmbed only に準拠)。

## :material-database-outline: 重複防止

同一日 4 fire = 同一記事の **upsert**。 新 X 投稿が出るたびに section が更新される。

- WP post の slug = `giants-sns-realtime-{YYYY-MM-DD}` で fix
- 存在チェック: `GET /wp-json/wp/v2/posts?slug=giants-sns-realtime-{date}`
- 存在すれば `PUT /posts/{id}` で content / title 上書き、 なければ `POST /posts`
- ==1 日 1 URL==、 4 回 update で 4 URL 増えない

## :material-cog-outline: 実装 file (新規)

| file | 内容 |
| --- | --- |
| `src/sns_realtime_topic.py` | main module、 RSSHub fetch + 分類 + render + WP upsert |
| `src/sns_realtime_topic_classifier.py` | 一軍 / 二軍 / 三軍 分類 + roster alias match |
| `src/sns_realtime_topic_template.py` | jinja template (トレンド + 3 section + 出典) |
| `tests/test_sns_realtime_topic.py` | unit tests (fetch mock / 分類 / render / upsert mock) |
| `tests/test_sns_realtime_topic_classifier.py` | 育成 / ファーム keyword + roster alias match の boundary tests |

既存 fetcher pipeline (`src/rss_fetcher.py`) の hourly run の中で時刻 gate を見て `sns_realtime_topic.run()` を呼ぶ。 別 Cloud Run Job は作らない。

## :material-currency-jpy: コスト

| 項目 | 月コスト |
| --- | --- |
| Cloud Scheduler 追加 | **¥0** (既存 trigger 相乗り) |
| X API | **¥0** (RSSHub `TWITTER_AUTH_TOKEN` 経由) |
| LLM (Gemini / Grok) | **¥0** (投稿は oEmbed 埋め込み、 AI rewrite なし) |
| RSSHub Cloud Run | **¥0** (既稼働、 outbound 4 req × 4 fire × 30 日 = 480 req/月、 free tier 内) |
| WP REST | **¥0** (既存) |
| **合計** | **¥0** |

## :material-hand-pointing-up: 触らない範囲

- 既存 article / 既存 subtype の生成 path
- 既存 Scheduler の cron 式 / enable 状態
- WP frontend display CSS
- X live posting / X API key
- featured_media rule
- 個人 X アカウント (球団 / 専門メディア以外は対象外)

## :material-test-tube: tests

- `test_sns_realtime_topic_classifier.py`
  - 育成 keyword → 三軍
  - ファーム / 二軍 / イースタン keyword → 二軍
  - 選手名 alias で role match → 該当軍
  - keyword なし + roster match なし → 一軍 default
- `test_sns_realtime_topic.py`
  - RSSHub fetch mock (1 handle 取得失敗で他 3 handle 継続)
  - トレンド count 2 回未満は除外
  - WP slug 存在チェック → PUT で update (1 日 1 URL fix)
  - section 0 件は H2 ごと非表示

## :material-source-pull: 受け入れ条件

- [ ] 4 fire 後の 1 日 (例: 10/13/17/21) で WP に **1 URL のみ** 作成され、 4 回 update されている (revision 履歴で確認)
- [ ] トレンド section に上位 15 名以下が表示 (count desc)
- [ ] 三軍 section に 育成選手 (`role=='ikusei'`) または `育成 / 三軍 / 3軍` keyword 投稿のみ
- [ ] 二軍 section に `ファーム / 二軍 / イースタン` keyword または farm position 選手のみ
- [ ] 一軍 section に上記以外 (default)
- [ ] oEmbed が正しく render され、 X 投稿が embed 表示される
- [ ] Cloud Run / Scheduler / RSSHub の追加課金が **¥0** (24h 観察)
