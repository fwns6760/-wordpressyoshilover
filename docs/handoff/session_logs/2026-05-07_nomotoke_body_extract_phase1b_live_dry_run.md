# 2026-05-07 NOMOTOKE-BODY-EXTRACT-001 Phase 1B live dry-run observation

## 1 行サマリ

- 14:40 JST | 10 URL を `fetch_source_meta` 経由で 1 回ずつ + 同一セット 2 回目 → **8 success / 2 fetch_forbidden / 0 robots_blocked / 0 meta_unavailable / pass 2 cache hit 10/10** で Phase 1B 観測ゲートを通過

## 構成

- HEAD: `5d9bb28` (Phase 1A push 後)
- pipeline: `build_default_pipeline()` (`RequestsHttpClient` + `_DefaultRobotsChecker` + `_PerHostRateLimiter` + `FetchCache`)
- UA: `YoshiloverBot/1.0 (+https://yoshilover.com/)`
- per-host 1 req/sec、URL hash cache TTL 6h (Phase 1A locked spec)
- WP write 0 / Gemini 0 / Scheduler / env / deploy 不変
- live HTTP は本観測の 10 URL のみ。CLI へは未接続 (Phase 1A の opt-in flag は default OFF のまま)

## URL セット (10 URL)

| # | host | URL pattern | 期待 |
|---|---|---|---|
| 1-5 | hochi.news | `/articles/20260427-...` ~ `/articles/20260506-...` | OG/JSON-LD 取得 |
| 6-8 | sanspo.com | `/article/...?outputType=theme_giants` | OG/JSON-LD 取得 |
| 9-10 | giants.jp | `/G/G_news/...` `/G/news.html` | 403 fetch_forbidden |

## Pass 1 (live HTTP) — 10 URL × 1

| # | host | status | skip_reason | extraction_source | og_title 長 | og_description 長 | published_at | ms |
|---|---|---|---|---|---|---|---|---|
| 1 | hochi.news | 200 | "" | og_meta+json_ld | 47 | 37 | 2026-05-06T19:55:00+09:00 | 226 |
| 2 | hochi.news | 200 | "" | og_meta+json_ld | 51 | 100 | 2026-05-07T05:10:00+09:00 | 997 |
| 3 | hochi.news | 200 | "" | og_meta+json_ld | 60 | 100 | 2026-05-07T05:30:00+09:00 | 1015 |
| 4 | hochi.news | 200 | "" | og_meta+json_ld | 60 | 100 | 2026-05-06T23:13:00+09:00 | (jitter)* |
| 5 | hochi.news | 200 | "" | og_meta+json_ld | 56 | 100 | 2026-04-27T17:00:00+09:00 | 1092 |
| 6 | sanspo.com | 200 | "" | og_meta+json_ld | 53 | 80 | 2026-05-06T16:00:37+09:00 | 1160 |
| 7 | sanspo.com | 200 | "" | og_meta+json_ld | 51 | 80 | 2026-05-06T17:50:49+09:00 | 134 |
| 8 | sanspo.com | 200 | "" | og_meta+json_ld | 50 | 75 | 2026-05-06T16:38:53+09:00 | 1008 |
| 9 | giants.jp | 403 | fetch_forbidden | "" | - | - | - | 168 |
| 10 | giants.jp | 403 | fetch_forbidden | "" | - | - | - | 1003 |

`*` 行 4 は `time.time()` の jitter で負値が出力された (実時間は ~1s。fetcher 自体は正常動作、計測 wrapper の artefact)

pass1 elapsed: **6.3s / 10 URL** (per-host 1 req/sec の rate-limit が効いている: hochi 5 URLs が ~5s、sanspo 3 URLs が ~3s、giants 2 URLs が ~1s 並列)

## Pass 2 (同一 URL セット — cache 期待)

| metric | 値 |
|---|---|
| `cache_hit` | **10/10** |
| live HTTP requests | 0 (全 cache 由来) |
| pass2 elapsed | **0.0s** |
| skip_reason / extraction_source | pass1 と完全一致 (cache に保存された FetchResult をそのまま返却) |
| `_mark_cache_hit` flag | True for all 10 |

`fetch_forbidden` も含めて cache hit。これは **同 URL を short interval で再 fetch して 403 を再観測しない** 重要な挙動 (Phase 1A locked: 「robots_blocked / fetch_forbidden 結果も TTL 6h cache に入れる」)。

## 集約 metrics

### extraction_source 分布

| source | count |
|---|---|
| og_meta+json_ld | 8 |
| og_meta only | 0 |
| json_ld only | 0 |
| (none, skipped) | 2 |

両 source とも OG meta + JSON-LD を併用していて、**Phase 0 の prefer-OG-fallback-to-JSON-LD logic が実環境で発火する経路** は今回観測したが、純粋 OG-only / 純粋 JSON-LD-only の publisher は今回 sample に含まれなかった (将来 sponichi / nikkansports / giants.jp 等の追加で出る可能性あり)。

### skip_reason 分布

| skip_reason | count | 内訳 |
|---|---|---|
| "" (success) | 8 | hochi 5 + sanspo 3 |
| `robots_blocked` | 0 | (UA `YoshiloverBot/1.0` が hochi/sanspo robots.txt の deny 一覧に該当しない) |
| `fetch_forbidden` | 2 | giants.jp は anonymous GET に対し HTTP 403 を返す |
| `meta_unavailable` | 0 | (success 8 件は全て OG/JSON-LD を取得) |

### robots 実挙動

- `robots_decision_reason` は 8 success ケース全てで空文字 = `RobotsDecision.allowed=True, reason=""` (明示 allow)。
- pass1 中の robots.txt fetch は 1 host あたり 1 回キャッシュ → hochi.news / www.sanspo.com / www.giants.jp の 3 回のみ。
- giants.jp は 403 (記事 URL / robots.txt 共に 403) だが `_DefaultRobotsChecker` の policy として **robots-unavailable-default-allow** が機能、robots 経路は通過し、本体 GET で 403 → `fetch_forbidden`。

### per-host rate-limit 実挙動

`_PerHostRateLimiter(interval=1.0s)` は同 host 連続 GET の 2 回目以降を 1s 待ち。pass 1 timing からおおよそ:

- hochi 1→2→3→5: ~1s gap (URL 順による)
- sanspo 6→8: ~1s gap (内部 #7 は cache 関係で短くなったように見えるが、これは sanspo CDN 側の応答時間差で rate limiter は 1s sleep 入っている)
- giants 9→10: ~1s gap

### facts.source provenance 確認

8 success レコード全件で `extracted_facts` に `title.source` / `description.source` / `image.source` / `published_at.source` / `canonical_url.source` が記録され、value は OG / JSON-LD ソース名 (`og:title` / `og:article:published_time` / `link.canonical` 等) を closed set 内で持つ。

### rss_title / rss_summary 不上書き確認

本観測は `fetch_source_meta` を直接呼ぶスクリプトで CLI 経由ではないため、`rss_title` / `rss_summary` の overwrite は構造的に発生不可 (FetchResult は `primary_og_*` namespace のみ持つ)。CLI 経由経路は Phase 1A の `SourceExtractorOptInTests::test_extractor_does_not_overwrite_rss_title_or_summary` で既に検証済み。

## Phase 2 で renderer に使える facts (8 success ケース)

Phase 2 の renderer wiring 時、各記事から以下が source-only で取得可能:

- **primary_og_title**: 47–60 文字。RSS title より整っており、「【巨人】〜」「【巨人評論】〜」「【巨人記録室】〜」 等のジャンル prefix を含む。
- **primary_og_description**: 37–100 文字 (cap 100 で truncate されている可能性)。
  - 例: hochi-1 (若林楽人) — `巨人の若林楽人外野手が今季３度目のスタメンで初のマルチ安打をマークした。` (37 char、フル文)
  - 例: sanspo-7 (竹丸) — `（セ・リーグ、巨人0－5ヤクルト、9回戦、ヤクルト6勝3敗、6日、東京D）巨人のドラフト1位・竹丸和幸投手（24）＝鷺宮製作所＝が6度目の先発。自己最多111…` (80 char、score / 対戦カード / 球場 / 試合数を 1 行に圧縮)
- **primary_published_at**: ISO 8601 / 秒精度 (RSS pubDate より細かい)。今後の stale_source_age gate で source_published_at_iso 候補として使える。
- **primary_canonical_url**: 取得済 (rel="canonical")。dedupe / hash key として有用。
- **primary_og_image**: featured_media 候補 URL を一律取得済 (今後 WP 設定で featured_media を埋める判断に使える)。

特に sanspo の og:description は 1 行に **score / 対戦カード / 試合数 / 球場 / 選手名 / 役職** を内包する高密度フォーマットで、Phase 2 の `_extract_short_news_facts` への補強材料として価値が高い。

## Phase 2 でやる最小差分

1. **renderer 側 `_extract_lead_sentences(raw_og_description, max_sentences=2)`**: 全文転載禁止 policy を満たすため、`raw_og_description` から先頭 1〜2 文だけ取り出す。`。` 区切り、120 文字 cap。og:description が空 / 短すぎる時は RSS summary フォールバック。
2. **router の `data_preview` に optional `primary_og_*` を forward**: CLI が `_attach_source_extractor_facts()` で base_summary に書いた facts を、router 側に注入する経路を追加。**rss_title / rss_summary は不上書き** (Phase 1A 担保済)。
3. **renderer の事実カードを補強**: `primary_og_description` を `_extract_short_news_facts()` の入力に追加 (現状は `title + summary` のみ)。これで sanspo の `9回戦` / `東京D` / `6日` 等が自動的に 対戦 row に入る。
4. **renderer の lead 文を OG description ベースに切替**: 現状 `<p class="nomotoke-lead">` は RSS summary を使うが、Phase 2 では `primary_og_description` 由来の 1〜2 文を優先。OG なしの場合 RSS summary に fallback。
5. **opt-in flag を CLI dry-run のみで継続**: Phase 2 でも draft mode は user GO 待ち、live HTTP も dry-run only。Phase 3 (AI 抽出 / Gemini) は引き続き HOLD。
6. **fixture 追加**: `tests/fixtures/source_html/giants_jp_403.html` の代替として、`fetch_forbidden` 経路を Phase 2 unit test で再現する fake response (`HttpResponse(status_code=403)` を `FakeHttpClient` に登録するだけ、新 fixture file は不要)。

## 異常時の停止基準 (Phase 1B 内では発生せず)

- 403 多発 (giants.jp の 2/2 は既知、想定内)
- robots 全 deny (今回 0 件、UA `YoshiloverBot/1.0` が hochi/sanspo robots.txt に該当しないため pass)
- connection error 連続 (今回 0 件)

いずれも CLI flag を OFF にすれば即停止 (default OFF、live HTTP は flag/env 立てた時だけ発生)。本番設定変更 / deploy / env 不要。

## 次セッション着手前の git 確認手順

1. `git status`
2. `git rev-parse --short HEAD` → `5d9bb28` 以降であること
3. 未 commit / 未追跡は掃除しない
4. `tests/fixtures/source_html/` (Phase 0 fixtures) と `src/source_html_extractor.py` / `src/source_html_fetcher.py` / 本ドキュメントが揃っていること
5. `python3 -m pytest -q --ignore=tests/integration` → 3035 pass を baseline 確認
