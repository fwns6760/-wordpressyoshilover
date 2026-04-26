# 098 Creator notice/quote/rainout/live speculative refactor

## Why

092 / 094 / 096 で creator side の主要 speculative title template は fact-first 化したが、`src/rss_fetcher.py` の player_status / player_quote / manager_quote_lineup / game_rainout_slide / game_live_tie に推測的 phrasing が残っていた。

## What

- `src/rss_fetcher.py` の対象 12 f-string を fact-first / topic-only wording に置換
- 対象 template_key は 11 種のまま維持
- `tests/test_rss_fetcher_title_style_alignment.py` に 12 case を追加
- 関連 fixture / expected assertion を新 wording に更新

## Non-goals

- function structure / signature の変更
- 092 / 094 / 096 で touch した範囲の再編集
- editor lane / front lane / validator 実装の変更
- API cost / scheduler / env / deploy 挙動の変更

## Acceptance

1. 対象 12 f-string が fact-first 化されている
2. 対象関数の signature は不変
3. template_key 11 種は不変
4. 関連 tests が pass する
5. 086 validator に対して 12 新文字列が pass する
6. full unittest suite が green
7. 不可触 list と front lane への diff 混入が 0
