# 099 Creator Generic Fallback Speculative Refactor

## Why

- 092 / 094 / 096 / 098 で fact-first 化した範囲の外に、creator generic fallback templates が 4 件だけ残っていた。
- 対象は `player_mechanics_generic`、`player_generic`、`manager_quote_generic`、`manager_generic`。
- ここを閉じることで `rss_fetcher` の hardcoded speculative title fallback を完全消去する。

## What

- `src/rss_fetcher.py` の対象 4 f-string を fact-first 表現へ置換した。
- `tests/test_rss_fetcher_title_style_alignment.py` に 4 template_key の alignment case を追加した。
- 既存期待値を保持していたテストと fixture を新文字列へ更新した。

## Non-goals

- 関数構造、branch、signature、template_key の変更
- 092 / 094 / 096 / 098 で touch した範囲の再編集
- editor / front lane / API cost の変更

## Acceptance

1. 4 f-string が fact-first 化されている
2. 対象関数の signature は不変
3. template_key 4 種は不変
4. tests が pass する
5. 086 validator で新文字列が pass する
6. full suite が green
7. 不可触 list の diff は 0

本 ticket close で `rss_fetcher` の hardcoded speculative title fallback 完全消去を達成する。
