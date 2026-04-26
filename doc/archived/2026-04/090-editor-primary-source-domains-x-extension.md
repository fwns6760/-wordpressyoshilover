# 090 Editor primary-source whitelist extension for X official sources

## meta

- owner: Codex
- type: impl ticket
- status: done
- created_at: 2026-04-24 JST
- target_repo: `/home/fwns6/code/wordpressyoshilover`

## why

- editor の `PRIMARY_SOURCE_DOMAINS` は news 媒体 domain 中心で、`twitter.com` / `x.com` を通していなかった
- creator pipeline は球団公式 X / 媒体公式 X ベースへ寄っており、body footer fallback だけでは `_is_primary_source_url()` 入口判定を越えられない draft が残っていた
- 22:00 / 23:25 smoke の `missing_primary_source: 45-46 件` の主要因がこの whitelist 不整合だった

## what

- `src/tools/run_draft_body_editor_lane.py` の `PRIMARY_SOURCE_DOMAINS` に `twitter.com` と `x.com` を追加
- editor では source URL が primary source whitelist を通るかだけを判定し、tier 判定や真贋判定は既存 layer に委ねる
- `tests/test_run_draft_body_editor_lane.py` に X official / news domain / non-whitelisted の primary 判定テストを追加

## non_goals

- 064 tier 判定や `source_trust` の拡張
- creator 側 (`src/rss_fetcher.py` / `src/wp_client.py`) の変更
- 089 body footer fallback の改修
- X account allowlist の新設
- scheduler / env / secret / WP 書込 / publish 動線の変更

## acceptance

1. `https://twitter.com/TokyoGiants/status/...` が primary source として通る
2. `https://twitter.com/hochi_giants/status/...` と `https://twitter.com/sanspo_giants/status/...` が通る
3. `https://x.com/TokyoGiants/status/...` も通る
4. 既存 news 媒体 7 domain の primary 判定は維持される
5. `https://example.com/article` は引き続き reject される
6. `python3 -m unittest discover -s tests` が green
7. smoke で `missing_primary_source` が 30+ 件以上減ることを観測対象にする
