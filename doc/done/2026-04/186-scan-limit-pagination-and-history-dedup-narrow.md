# 186 scan-limit pagination and history dedup narrow

- priority: P0.5
- status: CLOSED
- owner: Codex A
- lane: A
- parent: 105 / 145 / guarded-publish history

## Purpose

`guarded-publish` の対象取りこぼしを減らすため、`max_pool` が 100 を超えても pagination で最後まで走査できるようにしつつ、history dedup の `refused` 扱いを 24 時間 window に narrow する。

## Landed In

- commit: `26c6ae2`
- scope:
  - `src/guarded_publish_evaluator.py`
  - `src/guarded_publish_runner.py`
  - `tests/test_guarded_publish_evaluator.py`
  - `tests/test_guarded_publish_runner.py`

## Implemented

- evaluator 側に `_list_posts_upto_limit(...)` を追加し、`max_pool` を 100 cap せず page 送りで回収するよう変更
- `scan_wp_drafts()` の draft / publish 取得を pagination 対応へ変更
- runner 側の history dedup を `sent` は恒久、`refused` は直近 24 時間だけ skip に変更
- unparseable timestamp の `refused` は安全側で skip 維持
- pagination 300 件 / later page fail partial result / refused 24h window / sent 永久 skip などの test を追加

## Verification

- pytest: `1431 -> 1438` (`+7`)
- effect: image deploy 後、`guarded-publish-tskdt` で 8 件 publish 成功

## Notes

- 旧 `refused` が永続 dedup されて再挑戦不能になる問題を narrow fix
- code は `26c6ae2` で着地済み。ここでは doc 補完のみ
