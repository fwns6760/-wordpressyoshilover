# 381-INGEST Giants general source expansion

status: LIVE_DEPLOYED_OBSERVE
owner: Codex
created: 2026-05-18 JST
github_issue: #55
scope: source expansion + X post mail news/opinion fallback coverage

## User problem

- 2026-05-18 07:00 / 12:01 / 13:07 の X 投稿候補 mail で同じ選手が繰り返し出た。
- user 要望: データだけでなく、ニュース記事への意見でもよい。巨人だけ総合で拾う。
- user 要望: Full-Count / 日テレ / 一般誌 / 週刊誌 / 読売新聞 / 朝日新聞 / 毎日新聞 / 週刊ベースボールも対象にする。
- hard rule: 記憶から再構成しない、silent skip しない、自己評価で OK にしない。証拠だけ出す。

## Root cause found

1. `src/tools/run_x_post_mail.py` の news/opinion fallback は `tag_scrape` source を読んでいなかった。
2. 同 fallback の既定 source limit は 4 だったため、config に source を追加しても新聞・週刊誌・一般誌まで到達しなかった。
3. `Full-Count 巨人` の旧 feed `https://full-count.jp/tag/yomiuri-giants/feed/` は HTTP 200 だが 0 items だった。

## Implementation scope

- `config/rss_sources.json`
- `src/tag_page_scraper.py`
- `src/source_trust.py`
- `src/rss_fetcher.py`
- `src/tools/run_x_post_mail.py`
- targeted tests under `tests/`

Out of scope:

- X / SNS live post
- WP existing article mutation
- Scheduler / Secret / env change
- production manual mail execute
- deploy until review / decision

## Sources added or fixed

| source | mechanism | guard | live evidence on 2026-05-18 JST |
|---|---|---|---|
| Full-Count 巨人 | RSS | feed URL fixed to Giants category | new feed returned 10 items in live check; old tag feed returned 0 |
| ベースボールチャンネル 巨人 | RSS | Giants category feed | live feed returned 30 items |
| 朝日新聞スポーツRSS | RSS | downstream Giants/player filter | live feed 10 items, Giants hit 1 |
| 毎日新聞スポーツRSS | RSS | downstream Giants/player filter | live feed 20 items, Giants hit 0 at check time |
| 週刊ベースボールONLINE RSS | RSS | downstream Giants/player filter | live feed 49 items, Giants hits 6 |
| 読売新聞オンライン プロ野球 | tag_scrape | article title/summary must include 巨人 / 読売ジャイアンツ / ジャイアンツ | scraper returned 3 Giants entries |
| 日テレNEWS NNN 巨人 tag | tag_scrape | same Giants topic filter | scraper returned 5 Giants entries |
| FRIDAY ジャイアンツ tag | tag_scrape | same Giants topic filter, 120-day freshness | scraper returned 0 under current freshness window; sample page has Giants tag but old |
| Smart FLASH 巨人 tag | tag_scrape | same Giants topic filter, 120-day freshness | scraper returned 5 Giants entries |
| 週刊女性PRIME 巨人 tag | tag_scrape | same Giants topic filter, 180-day freshness | scraper returned 5 Giants entries |
| 文春オンライン 読売ジャイアンツ | tag_scrape | same Giants topic filter, 365-day freshness | scraper returned 0 at check time |
| NEWSポストセブン 巨人 search | tag_scrape | same Giants topic filter, 180-day freshness | scraper returned 2 Giants entries |
| デイリー新潮 巨人 search | tag_scrape | same Giants topic filter, 180-day freshness | scraper returned 0 at check time |
| 現代ビジネス 巨人 search | tag_scrape | same Giants topic filter, 180-day freshness | search returned 9 article URLs; scraper returned 0 after Giants topic filter at check time |
| アサ芸プラス 巨人 search | tag_scrape | same Giants topic filter, 180-day freshness | search returned 39 article URLs; scraper returned 3 Giants entries |

## Guard lowering

Lowered:

- `src/rss_fetcher.py` now treats the above newspapers / general magazines / weekly magazines as `topic_source` for a limited publish-validation bypass.
- This limited bypass only covers weak-title / routing-review / generic-title-repair style blockers where the article itself is still Giants-topic verified.
- `src/tools/run_x_post_mail.py` now reads `tag_scrape` sources and raises default fallback source limit from 4 to 32, so all 32 article sources are reachable.

Not lowered:

- No full trusted bypass for general magazines / newspapers.
- No numeric fact bypass.
- No hard-stop bypass.
- No WP publish / X post / mail send side effect in this implementation.
- `tag_scrape` candidates still require title or summary to contain `巨人` / `読売ジャイアンツ` / `ジャイアンツ`.
- X post mail fallback caps tag scraper article fetches to `DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT` (=5) even if source config has `article_limit=30`, to avoid excessive mail-job latency.

## Acceptance

- [x] 読売新聞オンライン / 朝日新聞 / 毎日新聞 / 週刊ベースボールを source config に入れる。
- [x] FRIDAY 以外の一般誌も巨人限定で source config に入れる。
- [x] source が追加されても mail fallback が実際にそこまで届くことを証拠で確認する。
- [x] ガードの下げ方を「何を下げた / 何を下げていない」で明文化する。
- [x] 同じ選手だけになる時、DB候補だけでなく news/opinion fallback が別選手・別話題を補える。
- [x] GitHub Issue を作成して本 ticket と同期する。#55
- [x] commit。
- [x] deploy decision。
- [ ] 次回自然 mail で user-visible acceptance を確認する。

## Verification

- `python3 -m json.tool config/rss_sources.json` PASS
- `python3 -m unittest tests.test_tag_page_scraper tests.test_source_trust tests.test_rss_fetcher_reliability_2026_05_08 tests.test_x_post_mail`
  Result: `Ran 170 tests in 1.935s OK`
- `python3 -m pytest tests/test_source_trust.py tests/test_tag_page_scraper.py tests/test_x_post_mail.py tests/test_rss_fetcher_reliability_2026_05_08.py -q`
  Result: `203 passed, 4 warnings in 2.77s`
- X mail fallback source reachability:
  - default limit: `32`
  - total loaded article sources: `32`
  - positions 23-32 include 読売新聞オンライン / 日テレ / FRIDAY / Smart FLASH / 週刊女性PRIME / 文春 / NEWSポストセブン / デイリー新潮 / 現代ビジネス / アサ芸プラス

## Deploy evidence

Deployed on 2026-05-18 JST. No env / Secret / Scheduler changes.

### x-post-mail-lane

- build: `a8a5ea80-db47-4eec-9582-86a195bdba8b` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:381-general-sources-c791f52`
- digest: `sha256:a39a7415ed59bf75218dd82778735d1723a8d58bb65b5200c47ecdbd8af0145e`
- Cloud Run Job: `x-post-mail-lane`
- generation: `22`
- observedGeneration: `22`
- Ready: `True`
- latest execution after update: none. Latest listed execution remains `x-post-mail-lane-l9652`, created `2026-05-18T06:00:04Z`, before generation 22 update. Manual execute avoided to prevent extra real mail.

### yoshilover-fetcher

- build: `2b60df25-25b7-4ab1-bf9e-8ca9504c0f3e` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:381-general-sources-c791f52`
- digest: `sha256:ad8fd151885a15fb8e24c1672bb8cab5bca4756fd7662e0e085b39c96bf1ed1e`
- revision: `yoshilover-fetcher-00431-vl9`
- traffic: `100%`
- startup probe: succeeded
- `GET /health`: `OK`
- post-health-check ERROR logs after `2026-05-18T07:53:30Z`: `0`

Note: `curl -I /health` produced one `HEAD /health` 501 request at `2026-05-18T07:52:58Z`. Follow-up `GET /health` returned `OK`; the HEAD 501 is excluded from acceptance because the service does not implement HEAD for that endpoint.
