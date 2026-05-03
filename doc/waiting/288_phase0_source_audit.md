# 288 Phase 0 source/topic coverage read-only audit

| field | value |
|---|---|
| ticket | 288-INGEST-source-coverage-expansion |
| phase | Phase 0 |
| mode | read-only / dry-run only |
| created | 2026-05-03 |
| scope | 6 candidate source の URL/endpoint・volume 推定・repo overlap・接続技術・利用上注意・YOSHILOVER fit・Phase 1 最小 risk の棚卸し |
| hard constraints kept | no source add / no fetcher mainline wiring / no Gemini / no mail / no Scheduler / no deploy / no WP REST |

## 1. Scope lock

- 本票は **棚卸しのみ**。`config/rss_sources.json` / `src/rss_fetcher.py` / automation / env / Scheduler / Cloud Run は変更しない。
- 「new source」とは **現行 main ingress (`config/rss_sources.json`) に未登録** を意味する。
- 「repo overlap」は 3 段階で記す。
  - `none`: main ingress / helper / downstream artifact いずれも見当たらない
  - `artifact_only`: helper / validator / dry-run / audit host 認識のみあり、本線 source ではない
  - `legacy_seed`: artifact に加えて旧 lane / 旧 query / source type など接続の種がある

## 2. Current baseline

- 現行 main ingress は `config/rss_sources.json` の **13 source**:
  - `social_news` 9件 = RSSHub 経由 X
  - `news` 4件 = 日刊 / 報知 / Full-Count / BaseballKing
- 今回の 6 candidate は **全て main ingress 未登録**。
- ただし 6件中 5件は repo 内に何らかの helper / validator / dry-run seed がある。**東スポWEB巨人ラベル**は 6候補の中で repo overlap が最も薄い。

## 3. Matrix

| candidate | 公開 URL / endpoint | volume 推定 | repo overlap | post type / subtype 推定 | 重複コスト推定 | 接続技術 | 利用上注意 / license 概要 | YOSHILOVER fit | Phase 1 最小 risk 推定 |
|---|---|---|---|---|---|---|---|---|---|
| 東スポ巨人担当 (X) | X profile: `https://x.com/tospo_giants`。mainline 候補にするなら RSSHub mirror は `.../twitter/user/tospo_giants` 形式 | **中〜高**。専任 beat account なので平常時でも複数 post/day、試合日・補強日は増える想定。根拠: repo 旧 collect query + 公開検索 snippet で直近継続投稿を確認 | `legacy_seed`。`src/x_api_client.py` に `from:tospo_giants -is:retweet` の旧 collect query あり。`config/rss_sources.json` には未登録 | `player` / `manager` / `postgame` / `notice` / `injury` / 練習写真 / 記事告知 | **高**。同一 event が 東スポWEB / Yahoo再配信 / 他紙X と重なる | X page / RSSHub mirror / 既存 social_news と同系 | X ToS は公開 interface 以外の access / scrape に厳格。使うなら embed / 公式 interface 前提で、本文全文コピーや thread 大量再利用は避ける | **中〜高**。巨人専任で coverage は濃いが、一次 source ではなく topic trigger / article pointer 寄り | **高**。policy risk + duplicate 増 + social noise。Phase 1 でやるなら dry-run / topic trigger 限定が安全 |
| 東スポWEB 巨人ラベル | label page: `https://www.tokyo-sports.co.jp/list/label/巨人`。記事 URL は `https://www.tokyo-sports.co.jp/articles/-/...` | **中**。シーズン中は 1〜5本/日程度のレンジが妥当。根拠: 公開検索で巨人 tag article が朝・昼・夜に散在 | `artifact_only`。`config/rss_sources.json` 未登録。`src/draft_audit.py` は `tokyo-sports.co.jp` を source host として認識するが、`src/source_trust.py` family 未登録 | `postgame` / `manager` / `player` / `notice` / `補強` / opinion 混在 | **高**。東スポX、Yahoo配信、他紙同話題と重なる。加えて煽り title 混入の恐れ | RSS 未確認。実装するなら HTML label scrape が本命 | site-specific scraping 許容範囲は未確認。安全側では **headline / URL / 公開時刻のみ**、本文取得なしで扱うべき | **中**。巨人 coverage はあるが rumor / opinion 混入に注意 | **中〜高**。trust family 追加、dup 抑止、sensational title filter が必要 |
| 巨人公式 YouTube | official handle: `https://www.youtube.com/@YOMIURI_GIANTS`。official site からの導線で channel id `UCXxg0igSYUp0tqdd6luPEnQ` を確認。RSS候補: `https://www.youtube.com/feeds/videos.xml?channel_id=UCXxg0igSYUp0tqdd6luPEnQ` | **中〜高**。公開 analytics(第三者集計)では total videos 約2.3k / since 2016 で長期平均 4〜5本/週。シーズン・イベント期は増加想定 | `artifact_only`。`210e` 監査済み、`social_video_notice_*` artifact あり。ただし `config/rss_sources.json` 未登録、`draft_audit.py` は YouTube URL を supported source から除外 | `social_video_notice` / `program` / `notice` / player interview / behind-the-scenes / event video | **中**。GIANTS TV・公式X・報道動画とテーマ重複あり | **YouTube RSS** が最有力。API 不要 | YouTube content は copyright 管理下。動画本体 / transcript / 長尺引用は避け、metadata + canonical URL + embed 前提で扱う | **高**。公式 source で信頼度が高い | **中**。channel mapping と URL canonicalization が必要だが、6候補中では比較的安全 |
| GIANTS TV | service root: `https://tv.giants.jp/`。live: `/lives/...`、video: `/videos/...`、search/archive: `/search/archive?...` | **高**。公開検索で `見逃し配信 (99件)`、live game pages、多数の interview / documentary を確認。シーズン中は daily 更新前提 | `artifact_only`。`rss_fetcher` は `GIANTS TV` を streaming/program hint として扱い、一部 promo skip あり。`social_video_notice_*` tests でも GIANTS TV payload 使用。ただし main ingress source は 0 | `program` / `social_video_notice` / 練習配信 / live game / archive / documentary | **非常に高い**。公式YouTube、公式X、試合結果記事、番組告知が相互に重なる。現行 fetcher も promo/streaming を抑制寄り | RSS 未確認。現実的には HTML page scrape か X/YouTube 補助 | 公式有料/地域制限サービス。少なくとも metadata を超える再利用は保守的に扱い、動画内容の転載・文字起こしは避けるべき | **中**。公式ではあるが volume / promo 量が多く、全部入れると media ではなく番組表 lane になる | **高**。noise / duplicate / region gate が大きい。Phase 1 は live/practice 全量ではなく interview/program の narrow subset 前提 |
| Yahoo リアルタイム検索 | query endpoint: `https://search.yahoo.co.jp/realtime/search?p=巨人`。既存 helper は keyword query 形式 | **raw は高ノイズ / run は低め**。ページ自体は trend/popular post の塊だが、detector は 1 query + 上位 rows only。運用上は 0〜10 candidate/run 程度に抑えられる | `legacy_seed`。`src/viral_topic_detector.py` と `src/tools/run_viral_topic_dry_run.py` あり。`src/rss_fetcher.py` にも Yahoo realtime helper / fan reaction helper がある。`config/rss_sources.json` 未登録 | topic trigger only。推定 subtype は `postgame` / `lineup` / `notice` / `program` 等だが、**fact source ではない** | **中〜高**。同一話題を既存 RSS / 公式X がすでに取っている可能性が高い | HTML scrape、timeout 5s、retry なし、API なし | LINEヤフー規約は service 想定外の複製・転載を制限。使うなら keyword / rank 程度の signal に留め、post本文の再利用は避ける | **中**。話題検知としては有用だが、巨人特化 media の一次ソースにはならない | **中**。dry-run 継続なら低リスク。本線接続すると noise と review volume が先に増える |
| Yahoo ニュースランキング | code/246 想定 endpoint: `https://news.yahoo.co.jp/ranking/access/news/baseball`。公開 sports page `https://news.yahoo.co.jp/categories/sports` に ranking section あり | **中**。ranking list は bounded で、1 fetch あたりの候補数は少ない。実運用では top 5〜20 headline 観察向き | `artifact_only`。`src/viral_topic_detector.py` に helper あり。`src/source_trust.py` は `yahoo_news_aggregator` family を持つ。`sns_topic_publish_bridge.py` も yahoo domains を認識 | topic trigger / ranking watch。`postgame` / `補強` / `injury` / `comment` など大きめ話題に寄るが、Giants specificity は弱い | **高**。Yahoo配信元と元記事 source が重複する。fact source にすると dup だらけ | HTML scrape / aggregator page | LINEヤフー規約上、ranking page を main fact source にせず、配信元 URL を優先すべき | **低〜中**。巨人専用ではなく、discoverability 用途に限れば有用 | **中**。topic trigger に限定すれば manageable。fact source として繋ぐのは非推奨 |

## 4. Detailed notes

### 4-1. 東スポ巨人担当 (X)

- main ingress には **未登録**。
- 旧 X API collect lane の query にだけ残っており、現在の RSSHub mainline には未接続。
- 6候補の中では coverage 密度は高いが、**X access policy と duplicate** が最も問題になりやすい。
- 使うなら **topic trigger / media quote pool 補助** が先で、main fact source にしない方が安全。

### 4-2. 東スポWEB 巨人ラベル

- 現時点で RSS endpoint は repo / 公開検索の範囲では確認できず、**HTML label scrape 前提**。
- `draft_audit.py` の host allowlist には入っているが、`source_trust.py` family は未整備。
- 追加するなら「trust family → dup guard → label scrape」の順でないと downstream drift が大きい。

### 4-3. 巨人公式 YouTube

- official giants.jp page の `公式YouTubeチャンネルはこちら` から **handle と channel id が確認できた**。
- 6候補の中では **最も official / API-free / feed 化しやすい**。
- ただし repo 現状では:
  - YouTube URL は `draft_audit.py` supported source から除外
  - `source_trust.py` に youtube family なし
  - `social_video_notice` artifact はあるが intake 未配線
- Phase 1 候補としては **最有力**。

### 4-4. GIANTS TV

- source coverage の意味では魅力が大きいが、**volume と duplicate が最大**。
- `rss_fetcher.py` 自体が現状 `GIANTS TV` / `配信中` / `アーカイブ` を streaming hint と見て一部 skip するため、現行思想は「入れる」より「抑える」に寄っている。
- もし後でやるなら:
  - live game / practice archive は外す
  - `program` / interview / documentary only
  - `practice/live/archive` title を hard filter
  が必要。

### 4-5. Yahoo リアルタイム検索

- すでに `viral_topic_detector` と `rss_fetcher` 内 helper があり、**topic trigger seed としては最も進んでいる**。
- ただし source 性質は「話題の入口」であり、本文の事実確認は別 source に依存する。
- したがって 288 の文脈でも、**source add** というより **trigger lane** として扱うのが正しい。

### 4-6. Yahoo ニュースランキング

- `viral_topic_detector.py` の ranking helper がそのまま evidence。
- `source_trust.py` に aggregator family があるため downstream 認識は一部済んでいる。
- ただし 210 plan どおり、**Yahoo 本体を first-class fact source にせず、配信元 family 優先** が妥当。

## 5. Phase 1 suitability ranking (implementation ではなく判断材料)

| rank | candidate | 理由 |
|---|---|---|
| 1 | 巨人公式 YouTube | official / feed 化容易 / API不要 / 6候補中で最も trust が明確 |
| 2 | Yahoo リアルタイム検索 | 既に dry-run artifact があり、topic trigger 限定なら risk が狭い |
| 3 | Yahoo ニュースランキング | bounded list で topic trigger 向き。ただし aggregator dup に注意 |
| 4 | 東スポWEB 巨人ラベル | coverage は増えるが trust/dup/scrape の同時整備が必要 |
| 5 | 東スポ巨人担当 (X) | coverage は濃いが X access policy と duplicate が重い |
| 6 | GIANTS TV | volume 爆発・promo 混入・region gate の三重リスク |

## 6. Recommended interpretation for USER_DECISION_REQUIRED pack

- **main source add 候補**
  - 第一候補: 巨人公式 YouTube (RSS only)
  - 第二候補: 東スポWEB巨人ラベル (ただし scrape 設計と trust family が先)
- **topic trigger only 候補**
  - Yahoo リアルタイム検索
  - Yahoo ニュースランキング
  - 東スポ巨人担当 X
- **narrow subset でのみ検討**
  - GIANTS TV (`program` / interview / documentary 限定)

## 7. Open issues kept for later phase

- 東スポWEB の RSS endpoint 有無は未確定。Phase 1 着手前に再確認が必要。
- 巨人公式 YouTube は channel id まで確認できたが、repo 内の `youtube` trust family / canonicalization は未整備。
- GIANTS TV は公式サービスだが、RSS/公開 feed の有無は未確定。現状は scrape 前提。
- Yahoo 系 2 source は **fact source 化しない** 前提のまま扱うべき。

## 8. Public evidence used

- 読売ジャイアンツ公式 special page からの公式 YouTube 導線: `https://www.giants.jp/sp/re5pec7/`
- YouTube official channel link: `https://www.youtube.com/@YOMIURI_GIANTS`
- GIANTS TV main / search examples:
  - `https://tv.giants.jp/`
  - `https://tv.giants.jp/search/archive?q=%E7%B7%B4%E7%BF%92`
  - `https://tv.giants.jp/search/video?tag=%E3%83%89%E3%82%AD%E3%83%A5%E3%83%A1%E3%83%B3%E3%83%88`
- Yahoo pages:
  - `https://search.yahoo.co.jp/realtime/search?p=巨人`
  - `https://news.yahoo.co.jp/categories/sports`
  - `https://news.yahoo.co.jp/ranking/access/news/baseball` (repo / dry-run code evidence)
- Terms / usage references:
  - X Terms: `https://x.com/en/tos`
  - X embed help: `https://help.x.com/en/using-x/how-to-embed-a-post`
  - LINEヤフー共通利用規約: `https://www.lycorp.co.jp/ja/company/terms/`
  - YouTube copyright help: `https://support.google.com/youtube/answer/143459`
  - GIANTS site rights / transmission rules PDF: `https://www.giants.jp/files/Rules_governing_the_taking_and_delivery_or_transmission_of_photographs_video_footage_etc.pdf`

## 9. Phase 0 extension (2026-05-03 PM, repo-only deeper read-only)

### 9-1. repo-only facts locked in this extension

- 外部 HTTP / Gemini / mail / deploy / WP REST は **0**。repo 内の config / src / tests / docs のみ再確認した。
- `automation/` directory はこの workspace に存在せず、source 別 wiring を repo 側 TOML で制御している痕跡は今回確認できなかった。
- scheduler 可視契約は引き続き `giants-realtime-trigger -> yoshilover-fetcher POST /run` が mainline。candidate source が本線化する条件は、実質 `config/rss_sources.json` 追加か、別 dry-run runner の新規接続である。
- 現時点の 6 candidate は **すべて mainline active wiring = NO**。したがってこの extension 自体の `Gemini delta` / `mail delta` は **0**。

### 9-2. repo evidence matrix (current state + activation planning band)

| candidate | config / naming read | 実装の種(read-only) | mainline wiring | repo-safe dry-run | trust family 整備度 | activation planning volume/day | activation planning Gemini/day | activation planning visible mail/day | duplicate / silent-skip read |
|---|---|---|---|---|---|---:|---:|---:|---|
| 東スポ巨人担当 (X) | `config/rss_sources.json` 未登録。現行 social source の命名規則は「媒体名 + X」、type=`social_news` | `src/x_api_client.py` に `from:tospo_giants -is:retweet` 旧 collect query。現 mainline RSSHub source には未反映 | **NO**。scheduler は `/run` のみ、config に source entry なし | **partial only**。`x_api_client.py collect --dry-run` はあるが live X API 依存で fixture 不在 | **未整備**。`source_trust.py` handle registry に `tospo_giants` 不在、`source_attribution_validator.py` も東スポ marker 非対応 | `0-2` | `0` if trigger-only, `+1 to +4` if article source | `0` if trigger-only, `+0 to +2` if article source | **high / medium-high**。unknown handle のまま `social_news` 化すると `ambiguous_x` 寄りになり、dup も増えやすい |
| 東スポWEB 巨人ラベル | 未登録。現行 config の web source は RSS URL + type=`news` | `draft_audit.py` host allowlist に `tokyo-sports.co.jp`。それ以外は fetch/helper 不在 | **NO** | **none**。fixture / runner / RSS helper 不在 | **未整備**。`source_trust.py` family 不在、`source_attribution_validator.py` marker 不在 | `+1 to +3` | `+1 to +6` | `+1 to +3` | **high / medium-high**。URL family 未登録のまま入れると attribution / dup / sensational title review burden が増える |
| 巨人公式 YouTube | 未登録。現行 config に YouTube / video feed entry 0 | `social_video_notice_*` contract/builder/validator、`run_social_video_notice_dry_run.py`、`210e` audit | **NO** | **YES (fixture)**。builder/validator dry-run は fixture / stdin で完結 | **部分整備**。`youtube` family 自体は不在、`draft_audit.py` は `youtube.com` / `youtu.be` を除外 | `+0.5 to +2` | `0` if `social_video_notice` / `program` path、`+0.5 to +2` if generic fetcher | `+0.5 to +2` | **medium / medium**。canonical URL と trust family が無いので drift はあるが、volume は narrow |
| GIANTS TV | 未登録。現行 config に `tv.giants.jp` / video source 0 | `rss_fetcher.py` の `GIANTS TV` streaming/program hint、`social_video_notice_*` tests、rule-based `program` tests | **NO** | **YES (fixture)**。`run_social_video_notice_dry_run.py` と `tests/test_rss_fetcher_rule_based_subtypes.py` で repo-safe dry-run seed あり | **web domain は既認識**。`tv.giants.jp` は `source_trust.py` の `giants.jp` domain match で `giants_official` 扱い。ただし video-specific family は不在 | `+1 to +4` narrow subset / full ingest はさらに上振れ | `0` if deterministic program/video lane、`+1 to +4` if generic fetcher | `+1 to +4` | **high / low-medium**。volume/dup は重いが、web domain trust 自体は 6候補中でかなり良い |
| Yahoo realtime | config 未登録。`rss_fetcher.py` には `source_type == "yahoo_realtime"` branch あり | `src/viral_topic_detector.py`、`src/tools/run_viral_topic_dry_run.py`、`rss_fetcher.py` 内 Yahoo realtime helper / fan reaction path | **NO** | **YES (fixture)**。`tests/test_viral_topic_detector.py` で HTML fixture、runner は JSONL 出力のみ | **source family としては未整備**。`search.yahoo.co.jp` は `source_trust.py` / `draft_audit.py` 両方の一次 source allowlist 外 | `0-2` confirmed trigger/day | `0` current dry-run, `+0 to +2` only after bridge | `0` current dry-run, `+0 to +2` only after bridge | **medium-high / low** if trigger-only。history cross-reference があるため silent skip より review 増の方が主 risk |
| Yahoo ranking | config 未登録 | `src/viral_topic_detector.py` ranking helper、`run_viral_topic_dry_run.py`、Yahoo family downstream consumers | **NO** | **YES (fixture)**。ranking rows も `tests/test_viral_topic_detector.py` で fixture 済 | **整備済み(aggregator 限定)**。`news.yahoo.co.jp -> yahoo_news_aggregator`、`draft_audit.py` allowlist あり | `0-1` | `0` current dry-run, `+0 to +1` only after bridge | `0` current dry-run, `+0 to +1` only after bridge | **high / low-medium**。配信元重複は強いが family 認識は既にある |

### 9-3. evidence-backed interpretation updates

- **dry-run capability が repo-safe なのは 4/6**。
  - `巨人公式 YouTube`, `GIANTS TV`, `Yahoo realtime`, `Yahoo ranking` は fixture or stdin runner がある。
  - `東スポ X` は networked dry-run しかなく、`東スポWEB` は runner 自体が無い。
- **trust family readiness が最も高いのは GIANTS TV(web URL) と Yahoo ranking**。
  - `GIANTS TV` は prior audit では「family 不在」寄りに見えていたが、repo code 上は `tv.giants.jp -> giants_official` に入る。
  - 一方で **巨人公式 YouTube** は actual source URL が `youtube.com` なので、official candidate でも registry readiness は未整備のまま。
- **mail/Gemini planning burden が低い順**は、current repo path だけ見ると:
  1. Yahoo realtime / Yahoo ranking (trigger-only なら current delta 0)
  2. 巨人公式 YouTube (deterministic `social_video_notice` / `program` 活用余地)
  3. GIANTS TV narrow subset
  4. 東スポ X / 東スポWEB
- **Phase 1 ranking 自体は据え置き**でよい。
  - `巨人公式 YouTube` を first official candidate、
  - `Yahoo realtime / ranking` を trigger-only candidate、
  - `東スポ X / 東スポWEB / GIANTS TV full ingest` を higher-planning-burden group
 という整理は、repo-only facts でも崩れなかった。
