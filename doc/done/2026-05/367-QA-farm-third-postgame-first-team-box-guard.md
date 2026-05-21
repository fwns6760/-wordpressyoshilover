# 367-QA 三軍/二軍の試合結果に一軍 boxscore を混入させない恒久対応

## meta

- status: LIVE_DEPLOYED_OBSERVE
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/36
- triggers: published post `68610`

## 問題

`68610` は三軍の `巨人 4-2 信濃グランセローズ` 記事だが、本文に当日の一軍 `DeNA 3 - 巨人 4` の NPB boxscore が混入した。
二軍記事でも、相手が DeNA / ロッテなど NPB 球団の場合に同じ事故が起きうる。

## 原因

`src/source_postgame_extractor.py` の `league_level` 判定は `二軍` / `2軍` / `ファーム` を farm とするが、`三軍` / `3軍` を見ていなかった。
そのため三軍の試合結果が `first` と誤判定され、`src/rss_fetcher.py` が一軍専用の `fetch_today_giants_npb_box_facts()` / `fetch_today_giants_postgame_facts_from_yahoo()` を呼んだ。
これらの fetcher は「今日の一軍巨人戦」を取りに行くため、三軍記事に一軍 boxscore が混ざった。

## 方針

- 記憶から再構成しない。
- silent skip にしない。
- 自己評価 OK で終わらせない。
- `三軍` / `3軍` / `３軍` を first ではなく third として扱う。
- `二軍` / `2軍` / `ファーム` は従来通り farm として扱う。
- rss_fetcher 側にも防御層を置き、parser が first と誤返却しても farm / third 文脈では一軍 boxscore fetch に進まない。
- skip 理由は構造化 log `postgame_first_team_box_fetch_skipped` に残す。

## 実装スコープ

触ってよい:

- `src/source_postgame_extractor.py`
- `src/rss_fetcher.py`
- `tests/test_source_postgame_extractor.py`
- `tests/test_rss_fetcher_postgame_table.py`
- 本 ticket
- `doc/README.md`
- `doc/active/assignments.md`

触らない:

- Scheduler
- Cloud Run env
- Secrets
- X / SNS投稿
- mail 条件
- source 追加
- published WP post `68610` の本文更新

## 受け入れ条件

- 三軍 postgame は `league_level=third` になり、一軍 NPB / Yahoo boxscore fetch を呼ばない。
- 二軍 postgame は相手が DeNA など一軍にも存在する球団でも、一軍 NPB / Yahoo boxscore fetch を呼ばない。
- parser が誤って `league_level=first` を返しても、title / summary / category / subtype の farm / third 文脈で fetch を止める。
- fallback の試合結果 block は三軍なら `巨人3軍`、二軍なら `巨人2軍` と表示する。
- `py_compile` / targeted pytest が PASS する。
- Scheduler / env / Secret / X / SNS / mail 条件は変更しない。

## 実装結果

- `src/source_postgame_extractor.py` で三軍 marker を `league_level=third` に分類。
- `src/rss_fetcher.py` に `_should_fetch_first_team_postgame_boxscore` と context guard を追加。
- parser が first と誤返却しても、三軍 / 二軍 / ファーム marker、farm subtype、ドラフト・育成カテゴリでは一軍 boxscore fetch を止める。
- fallback 表示で `league_level=third` は `巨人3軍` と表示。
- 回帰テストで三軍 fixture と、parser 誤分類時の三軍 / 二軍DeNA混線防止を固定。

## 検証

実行済み:

- `python3 -m py_compile src/source_postgame_extractor.py src/rss_fetcher.py tests/test_source_postgame_extractor.py tests/test_rss_fetcher_postgame_table.py`
- `pytest tests/test_source_postgame_extractor.py tests/test_rss_fetcher_postgame_table.py -q` -> 33 passed / 4 warnings / 12 subtests passed
- `python3 -m compileall -q src/source_postgame_extractor.py src/rss_fetcher.py tests/test_source_postgame_extractor.py tests/test_rss_fetcher_postgame_table.py tests/test_build_news_block.py`
- AST parse -> `AST_OK src/source_postgame_extractor.py,src/rss_fetcher.py,tests/test_source_postgame_extractor.py,tests/test_rss_fetcher_postgame_table.py`
- `python3 -m pytest tests/test_source_postgame_extractor.py tests/test_rss_fetcher_postgame_table.py tests/test_build_news_block.py -q` -> 92 passed / 4 warnings / 12 subtests passed
- commit `6664e16` (`367: guard farm postgame boxscore routing`)
- `gcloud builds submit --project baseballsite --region asia-northeast1 --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:367-farm-box-6664e16 .` -> Cloud Build `f321dc67-1491-49a3-87b3-077abf922a20` SUCCESS
- image digest `sha256:9c6dcd9294d5f36fc745d4d4e9311a6d8156e710fce2366c8c6188cbe56f1618`
- `gcloud run deploy yoshilover-fetcher --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:367-farm-box-6664e16 --project baseballsite --region asia-northeast1 --quiet` -> revision `yoshilover-fetcher-00404-kds`, traffic 100%
- `curl -sS https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/health` -> OK
- Cloud Run log: revision `yoshilover-fetcher-00404-kds` startup TCP probe succeeded; Ready condition true
- published post `68610` は status=publish のため未更新
- GitHub Issue evidence comment: https://github.com/fwns6760/-wordpressyoshilover/issues/36#issuecomment-4466612943
- GitHub Issue log-event補足: https://github.com/fwns6760/-wordpressyoshilover/issues/36#issuecomment-4466613417

## 未完了

- natural fire / log evidence
- GitHub Issue #36 close
