# 210e YouTube / 公式動画 source coverage audit

## meta

- number: 210e
- type: audit
- status: REVIEW_NEEDED
- priority: P1
- lane: Codex-M / Codex B
- created: 2026-04-27
- parent: 210-primary-source-expansion-plan

## background

YOSHILOVER の main ingress は `config/rss_sources.json` 上で **X(RSSHub) 9 source + news RSS 4 source** に寄っており、球団公式 YouTube / GIANTS TV / 番組系の「動画由来の準一次情報」は main ingress にまだ入っていない。`080 social_video_notice` と `081 x_source_notice` により **記事 contract 自体** は一部整っているが、live fetch / source registry / dedup policy は未配線である。

本便は **read-only audit only** とし、repo 内の既存実装 / config / doc を根拠に、YouTube / 公式動画の source coverage を監査する。live web fetch、YouTube API 利用、GCP / WP / X / mail 変更は行わない。

## 既存実装カバレッジ

### 080 social-video-notice-lane

- `doc/done/2026-04/080-social-video-notice-lane.md` は `instagram` / `youtube` 向けの `social_video_notice` lane を定義済み。
- 実装 artifact も存在する:
  - `src/social_video_notice_contract.py`
  - `src/social_video_notice_builder.py`
  - `src/social_video_notice_validator.py`
  - `src/tools/run_social_video_notice_dry_run.py`
- ただし 080 の non-goal どおり、**automation wiring / live fetch / publish route / API fetch は未実装**。
- したがって 080 は「parked」ではなく **closed artifact + live 未配線** の状態であり、main ingress source coverage をまだ増やしていない。

### 081 x-source-notice-lane

- `doc/done/2026-04/081-x-source-notice-lane.md` は `x_source_notice` lane を定義済み。
- 実装 artifact も存在する:
  - `src/x_source_notice_contract.py`
  - `src/x_source_notice_builder.py`
  - `src/x_source_notice_validator.py`
  - `src/tools/run_x_source_notice_dry_run.py`
- 081 は **公式 X 告知から動画 URL を含む告知を候補化するための近接 artifact** として再利用余地がある。
- ただし 081 も **live fetch / official-video intake lane** そのものではない。

### source_trust coverage

- `src/source_trust.py` の family registry は以下まで:
  - `giants_official`
  - `npb_official`
  - `hochi`
  - `nikkansports`
  - `sponichi`
  - `sanspo`
  - `daily`
  - `yomiuri_online`
  - `yahoo_news_aggregator`
- **`youtube` / `giants_tv` / `official_video` 専用 family は存在しない。**
- handle 判定も X 前提で、YouTube channel / video URL の family 正規化は未整備。

### RSS source coverage

- `config/rss_sources.json` の現行 source は 13 件:
  - `social_news` 9 件 = すべて RSSHub 経由 X
  - `news` 4 件 = 日刊 / 報知 / Full-Count / BaseballKing
- **YouTube feed、GIANTS TV feed、番組 feed は 0 件**。
- したがって現行 main ingress は、動画告知を取るとしても **X 告知の二次経路に依存**している。

### subtype / filter coverage

- `src/social_video_notice_contract.py` の subtype は `social_video_notice`。
- `src/guarded_publish_evaluator.py` には fallback subtype として `program` が存在する。
- `src/tools/run_notice_fixed_lane.py` には `program_notice` family が存在する。
- 一方で repo 全体では **`video_notice` という実 subtype / family は未定義**。
- `src/rss_fetcher.py` は `_is_promotional_video_entry(...)` で `GIANTS TV` / `配信中` / `アーカイブ` を streaming hint として検知し、`video_promo` skip を掛ける。
- 現状は「動画を積極 intake する」よりも **main RSS ingress から promotional video を落とす** 実装寄りである。

### dedup / source-url coverage

- `src/rss_fetcher.py` の `_is_history_duplicate(...)` は **exact `post_url`** と `title_norm` の両方で重複を見ている。
- `src/rss_fetcher.py` の same-fire guard は、同一 fire 内の distinct `source_url` を検知する。
- `src/wp_client.py` は `_yoshilover_source_url` meta を使って source URL reuse を判定する。
- `src/source_id.py` は **X URL の canonicalization は持つが、YouTube 専用 canonicalization は持たない**。
- `src/draft_audit.py` は `youtube.com` / `youtu.be` を supported source URL から除外しており、**現行 audit / editor 観点でも YouTube を一次 source として数えていない**。

## 取得元候補一覧

### A. YouTube 公式 channel

| candidate | 想定 URL / family | 取得経路候補 | coverage value | repo-only status |
|---|---|---|---|---|
| 巨人公式 YouTube | `https://www.youtube.com/@yomiuri_giants` | YouTube RSS、X 告知補助 | 球団公式動画、選手出演、告知系 | repo に channel_id mapping なし |
| GIANTS TV | `https://giants.jp/giants_tv/` または公式 YouTube mirror | YouTube RSS、公式 Web 告知、X 告知 | 番組 / アーカイブ / インタビュー | repo に RSS/feed 定義なし |
| ジャイアンツ球場 / ファーム公式動画 | official farm / youth video account 想定 | YouTube RSS、X 告知補助 | 二軍・育成・練習場面 | repo に source 定義なし |

監査メモ:

- YouTube RSS は `https://www.youtube.com/feeds/videos.xml?channel_id=<channel_id>` 形式が本命。
- ただし **`channel_id` 自体は repo-only audit では未確定**。実装便で handle -> channel_id の固定化が必要。

### B. 報道動画(報道機関の YouTube)

| candidate family | 取得経路候補 | coverage value | duplicate risk |
|---|---|---|---|
| スポーツ報知 YouTube | YouTube RSS | コメント動画、番組切り出し、試合後映像 | 報知 RSS / 報知 X と高め |
| 日刊スポーツ動画 | YouTube RSS | 速報動画、番組 clip | 日刊 RSS / X と高め |
| スポニチ動画 | YouTube RSS | 取材動画、特集 clip | Sponichi web / X と中程度 |

監査メモ:

- 報道動画は「動画そのもの」は新規でも、**同テーマの記事 RSS と高確率で衝突**する。
- したがって official channel より後順位でよい。

### C. テレビ番組情報 / EPG / 番組 Web

| candidate | 取得経路候補 | coverage value | 本便判断 |
|---|---|---|---|
| 日テレ G+ / NHK BS などの番組表 | EPG / 番組 Web / 番組公式 X | 放送予定、出演、再放送 | audit reference のみ |
| GIANTS TV 番組表 | 公式 Web / X | 番組名、放送時刻、出演 | A の補完として有用 |

監査メモ:

- EPG / 番組表は **動画 upload feed ではなく schedule source** で、別 lane として考えた方が安全。
- 本便では **YouTube / 公式動画 source coverage** を主眼とし、EPG 実装は範囲外とする。

## 安全 / コスト評価

| route | safety | quota / cost | repo fit | verdict |
|---|---|---|---|---|
| YouTube RSS feed | high | なし | 既存 RSS ingest と親和 | 推奨 |
| YouTube Data API v3 | mid | quota 必要、将来課金 / auth 管理 risk | 現 repo に未導入 | 保留 |
| 公式 X 告知経由 | mid-high | 既存 RSSHub/X 枠内 | 081 / social_news と接続しやすい | 補助経路 |
| EPG / 番組 Web | mid | quota なしでも scraping/規約確認が要る | 現行 main ingress と別性質 | 別 ticket |

判断理由:

- **YouTube RSS feed** は upload notification だけを扱うシンプルな pull source であり、API key / quota が不要で、今回の「タイトル・公開日時・出演者・テーマで扱う」方針に最も合う。
- **YouTube Data API** は動画メタデータ取得の幅は広いが、現時点では overkill であり、quota 判断を本便で持ち込むべきではない。
- **X 公式告知経由** は既存資産を活かせるが、X 告知が無い動画は取れず、source coverage の本線にはならない。
- **EPG / 番組表** は有用だが、番組 schedule lane と動画 upload lane を混ぜると subtype drift が起きやすい。

## 推奨経路(YouTube RSS feed)

### 推奨方針

1. **公式 channel 限定で YouTube RSS feed を追加候補にする。**
2. 入口は `channel_id` ベースの RSS のみを使い、API quota は使わない。
3. 最初の 1 本は **巨人公式 YouTube 1 source** に絞り、dry-run / candidate list だけを見る。
4. `GIANTS TV` と farm 系は 2 本目以降で広げる。

### 理由

- 現行 ingest は RSS を主経路として持っているため、追加実装が最も狭い。
- 動画内容の全文処理ではなく、**feed title / published_at / channel title / canonical video URL** だけで candidate 化できる。
- 公式 source に限定すれば、報道 clip や個人切り抜きより trust / dedup の設計が単純になる。

### 実装前提として残る未確定点

- `@handle` から `channel_id` への固定 mapping は repo に無い。
- GIANTS TV が独立 YouTube channel か、公式 Web 内導線中心かは repo-only では未確定。
- YouTube Shorts / `youtu.be` / `live` URL を **`watch?v=` へ canonicalize する補助**が将来必要。

## 既存重複判定整合

### 現行でそのまま使えるもの

- `rss_history.json` の **URL ベース重複**。
- `_is_history_duplicate(...)` の `title_norm` ベース重複。
- `WPClient` の `_yoshilover_source_url` reuse。
- same-fire 中の title collision / distinct source 検知。

### 追加で注意すべきもの

- 現行 `source_id.py` は X 専用 canonicalization しか持たないため、YouTube URL は **generic normalize のまま**。
- `https://www.youtube.com/watch?v=<id>` なら URL dedup は効きやすいが、`youtu.be/<id>` / `/shorts/<id>` / `/live/<id>` が混ざると exact URL dedup は弱くなる。
- 報道機関 YouTube と既存 news RSS は **URL が違っても title / game nucleus が近い**ため、`title_key` / `game_key` 相当の束ねが必要になる。

### 実装時の安全策

- intake 直後に canonical video URL を `watch?v=<id>` へ寄せる。
- 初手は **official channel only** に絞って、cross-source duplicate を増やしすぎない。
- press YouTube 拡張は、210d 系の recheck / dedup 実測後に後追いする。

## 分類方針(program / video_notice / notice)

### policy bucket

| bucket | 使う場面 | 推奨 nucleus |
|---|---|---|
| `program` | 番組名、放送時刻、出演者、再放送など schedule/episode が主語 | 「GIANTS TV『阿部監督インタビュー』を4月27日20:00配信」 |
| `video_notice` | 新規動画公開そのものが主語で、番組表より upload notice に近い | 「巨人公式 YouTube が坂本勇人の練習映像を公開」 |
| `notice` | 動画 URL は付くが、主語は roster / event / ticket / campaign など別の公式告知 | 「球団がファンイベント詳細を告知、説明動画を添付」 |

### repo 語彙との整合

- repo 既存語彙として明示実装があるのは `program`, `program_notice`, `social_video_notice`, `x_source_notice`, `notice`。
- **`video_notice` は policy 上の便宜語であり、現 repo の subtype としては未実装**。
- そのため最初の実装では:
  - schedule/episode nucleus が強いもの -> `program`
  - upload notice nucleus が強いもの -> 既存 `social_video_notice` へ寄せる
  - video link 付き一般告知 -> `notice` または `x_source_notice`
- 新しい live subtype を増やすより、まず **既存 subtype へ安全に写像**した方が drift が少ない。

## 記事化候補 / 保留候補

### 記事化候補

- 公式 channel 由来である。
- title / channel / published_at だけで事実核が立つ。
- 出演者 / 主題 / 発言者 / 番組名のいずれかが title に明示される。
- 報道 RSS / 公式 X / 既存公式 Web のいずれかで再確認しやすい。
- 本文が「出典 + 事実要約 1 文 + 補足 1 文」程度で完結できる。

### 保留候補

- `ハイライト`, `練習`, `アーカイブ配信中`, `配信開始` のように **事実核が薄い generic title**。
- 出演者 / 発言主体が title に無い。
- 個人投稿 / 切り抜き / unofficial mirror。
- 動画を見ないと fact が立たないもの。
- コメント欄や文字起こしに依存しないと記事化できないもの。

## 不可触 / 安全方針

- 動画内容の**全文文字起こしは禁止**。
- コメント欄転載は禁止。
- 個人投稿 / 切り抜き / 非公式 mirror を source にしない。
- 5ch / まとめ風の補強は禁止。
- 自動 publish しない。最初は candidate list / dry-run のみ。
- 自動 X 投稿しない。
- YouTube Data API quota / 課金導入は、本便では判断しない。
- 動画が準一次情報であることを前提に、重要 fact は **公式 / 報道 / RSS と照合**する。

## 次に実装する最小 1 本

### 210e-impl-1

`巨人公式 YouTube RSS feed 1 source 追加 dry-run`

最小 scope:

- `channel_id` を 1 本だけ固定
- YouTube RSS feed を 1 source として dry-run ingest
- canonical video URL を `watch?v=` に寄せる方針を先に決める
- output は candidate summary / duplicate summary のみ
- publish / X / API quota / multi-channel 拡張は持ち込まない

## non-goals

- 動画本文 / 音声の全文転載
- コメント欄利用
- 個人投稿 / 切り抜き / mirror 取り込み
- 自動 publish
- 自動 X 投稿
- YouTube Data API quota 利用判断
- EPG / 番組表 lane の本実装
- 既存 `src/` / `tests/` / `config/` 変更
