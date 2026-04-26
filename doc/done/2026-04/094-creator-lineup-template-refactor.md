# 094 Creator lineup template surgical fact-first refactor

## why

- 091 audit で lineup subtype は 49 件中 15 件 fail(23%)、主因は `src/rss_fetcher.py:9881-9883` の lineup template にある speculative 末尾句と body leak
- 旧 template は `巨人スタメン {body}でどこを動かしたか` で、長い原題断片がそのまま流入し、`でどこを動かしたか` が 086 validator の speculative 判定に当たる

## what

- lineup branch の f-string 1 個だけを fact-first 化
- `body` の replace 3 段は維持しつつ、`body[:25].rstrip()` で cap
- speculative 末尾句 `でどこを動かしたか` を撤去
- `body` が空なら `"巨人スタメン"` に fallback

## non-goals

- lineup body extraction logic の改善
- 092 で触った template 群や他 subtype の変更
- editor lane / front lane / validator module 本体の変更

## acceptance

1. lineup title から speculative 末尾句が消えている
2. lineup body は 25 文字 cap
3. body 空時は `"巨人スタメン"` を返す
4. 長めの lineup title は 086 validator で pass する
5. full suite が green
6. 不可触リストの diff は 0
