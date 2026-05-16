# 363-QA 同じ話題の連続重複記事を止める

## meta

- status: CLOSED
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16
- updated: 2026-05-16
- trigger: user report that WP drafts `68478` and `68480` appeared as duplicate consecutive articles
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/32

## 何が起きたか

WP REST と Cloud Logging で確認したところ、`68478` と `68480` は同じ URL の二重取り込みではなかった。
東京巨人公式 X の別ポスト 2 本だったが、タイトル生成が両方を同じ見出しに潰していた。

`巨人スタメン 巨人 vs DeNA 東京ドーム🏟 14時試合開始`

ログでは `title_collision_detected` と `same_fire_distinct_source_detected` が出ていた。
つまり、システムは「同じ見出しになった別 URL」を検知していたが、止めずに 2 本目も下書き作成していた。

同じ構造で、報知 / スポニチ / デイリーなどが同じ巨人ニュースを出した場合も、別 URL 扱いで似た下書きが増える可能性がある。

## 直す内容

同じ実行内で「別 URL だが生成タイトルが同じ」になった場合、重複と見なして 2 本目を作らない。
ただし、全部の同じタイトルを雑に潰すと別ニュースまで消す危険があるため、対象は重複確度が高い型に限定する。

- lineup / farm lineup
- pregame
- postgame
- rainout slide
- player status
- player quote
- manager quote

一般的な「巨人ニュース」のようなタイトル衝突は、今まで通りログだけ残して止めない。

## 実装

- `src/rss_fetcher.py`
  - Add `_should_skip_same_fire_cross_source_title_duplicate`.
  - 同じ fire 内で別 `source_url` が同じ normalized generated title になった場合、高確度 family だけ `wp.create_post` 前に `0` を返して skip。
  - JSON log event `same_fire_cross_source_title_duplicate_skip` を出す。
  - generic title collision は observe-only のまま維持。
- `tests/test_duplicate_prevention_golden.py`
  - `68478` / `68480` 型のスタメン title collision を再現。
  - 報知 / スポニチ型の player quote duplicate を再現。
  - generic title は従来通り observe-only であることを確認。

## 完了条件

- Same fire, same generated title, different source URL, `game_lineup` -> second draft is skipped (`post_id=0`).
- Same fire, same generated title, different source URL, `player_quote` -> second draft is skipped (`post_id=0`).
- Generic same-title collision remains observe-only and still creates both drafts.
- Existing exact source URL same-fire dedup still returns `0`.
- No Scheduler / env / Secret / WP existing post / X / SNS changes in this code change.

## 検証

- `python3 -m py_compile src/rss_fetcher.py tests/test_duplicate_prevention_golden.py` PASS
- First targeted pytest run failed once because the new generic collision test expected exactly one `logger.info` call, while existing `auto_rss_excerpt_skip` also logs through `logger.info`; assertion was narrowed to check the expected call is present.
- `python3 -m pytest tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_reliability_2026_05_08.py -q` PASS: 36 passed, 3 xfailed, 3 warnings, 3 subtests passed
- `python3 -m pytest tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_reliability_2026_05_08.py tests/test_rss_fetcher.py tests/test_lineup_source_priority.py tests/test_title_prefix_lineup_misuse_fixtures.py -q` PASS: 79 passed, 3 xfailed, 3 warnings, 3 subtests passed
- Cloud Build: `7a9f0bc1-439f-43ee-9a84-63a0df766fd1` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:363-cross-source-10ae4ef`
- digest: `sha256:53dd60aa908d483c61cf2b5756706b70d8ea67b0a29335a7a3ba7d051152d40a`

## deploy status

- Cloud Run service `yoshilover-fetcher` deployed.
- revision: `yoshilover-fetcher-00400-f29`
- traffic: 100%
- service generation: `542`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:363-cross-source-10ae4ef`
- `/health`: `OK`
- Scheduler / env / Secret / existing WP post / X / SNS: unchanged.
