# 200 publish-notice scanner subtype fallback 推論

## meta

- number: 200
- owner: Claude Code(起票) / Codex B(実装)
- type: dev / publish-notice / subtype inference
- status: **CLOSED**
- priority: P0.5
- lane: B
- created: 2026-04-27
- closed: 2026-04-27
- commit: `e78f088`

## 背景

- `src/publish_notice_scanner.py` は REST payload の `meta.article_subtype` / `meta.subtype` / top-level `article_subtype` / `subtype` に依存していた。
- 欠落時は `unknown` 扱いになり、manual X candidate の subtype が `default` に寄りすぎて、lineup / postgame / farm / notice / program の分類が弱かった。
- scope は scanner 本体と専用 test の 2 file に限定した。

## 実装

- `_extract_subtype()` の優先順を `meta.article_subtype` -> `meta.subtype` -> top-level `article_subtype` -> top-level `subtype` -> fallback inference に整理。
- title / excerpt / content から lineup / postgame / farm / notice / program を推論する helper を追加。
- シグナルが薄い短い title は `unknown` ではなく `default` に倒し、manual X candidate 側の `default` 偏りを解消しつつ、拾える subtype を増やした。

## Verify

- scanner 限定 pytest rerun: `python3 -m pytest tests/test_publish_notice_scanner.py -q`
  - result: 22 passed, 5 subtests passed
- full pytest baseline after 200: 1453 pass / 1 fail
- residual fail:
  - `tests/test_guarded_publish_readiness_guard.py::test_human_format_renders_summary`
  - scanner 変更と write scope が完全に disjoint のため、ticket 201 に分離

## Guardrails Held

- touched files: `src/publish_notice_scanner.py`, `tests/test_publish_notice_scanner.py`
- `src/publish_notice_email_sender.py`: NO
- WP write: NO
- Cloud Run / Scheduler / Secret: NO
- git push: NO
