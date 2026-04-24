# 092 Creator speculative title template surgical fact-first refactor

## why

- 091 audit で creator 側 hardcoded speculative templates が新規 draft title の違反主因と確認された
- 根は `src/rss_fetcher.py` の pregame / reinforcement / farm_lineup fallback title に固定 phrase が残っていたこと
- 086 validator は既に land 済みだが、本 ticket では creator 出力自体を contract に寄せて違反を減らす

## what

- `src/rss_fetcher.py` の対象 11 template group の返却文言だけを speculative なしの fact-first / topic-only へ置換
- 既存 fixture / expected assertion は新タイトルへ最小更新
- 新規 alignment test で対象 template が同じ template key を維持しつつ `validate_title_style` を通ることを確認

## non_goals

- function 構造変更
- 対象外 template の修正
- `src/title_style_validator.py` の import / wiring 追加
- LLM call / API call / 外部依存追加
- editor lane / front lane / automation / scheduler / env / WP write の変更

## acceptance

1. 対象 11 template group が fact-first 化されている
2. 対象関数の signature は不変
3. template key は不変
4. 更新済みタイトルが 086 validator を通る
5. unittest suite が green
6. 不可触 list の file は diff 0 のまま
