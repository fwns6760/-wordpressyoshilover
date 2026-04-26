# 096 Creator postgame speculative template refactor

## Why

- 091 audit で残っていた `OUT_OF_LENGTH` / `SPECULATIVE` / `GENERIC` の主因が、`src/rss_fetcher.py` の postgame branch と numeric pregame branch に残っていた hardcoded fallback title だった。
- 092 は `9935-9970` 側の template だけを fact-first 化しており、`9900-9940` 周辺の postgame / numeric pregame template は未解消だった。

## What

- `src/rss_fetcher.py` の `9900-9940` 周辺にある約 17 個の f-string を、11 個の template_key を維持したまま fact-first / topic-only wording に置換した。
- `tests/test_rss_fetcher_title_style_alignment.py` を拡張し、対象 11 template_key の新 title が `validate_title_style` を通る case を追加した。
- 既存の直比較 expectation と collision fixture を、新 title に合わせて最小更新した。

## Non-goals

- 関数構造、signature、branch 順序、template_key の変更
- 092 で触った `9935-9970` 範囲の再編集
- 094 で触った lineup branch の再編集
- editor lane / front lane / API cost / scheduler / env の変更

## Acceptance

- 対象約 17 個の f-string が fact-first 化されている
- 対象関数の signature は不変
- template_key 11 種は不変
- 関連 tests が pass する
- 新 wording が 086 validator を pass する
- `python3 -m unittest discover -s tests` が green
- 不可触 list の diff は 0
