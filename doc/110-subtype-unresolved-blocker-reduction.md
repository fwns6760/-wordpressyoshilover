# 110 subtype-unresolved-blocker-reduction

## meta

- number: 110
- alias: PUB-002-C
- owner: Claude Code(設計)/ Codex B(実装)
- type: ops / publish blocker reduction / subtype routing
- status: READY(B 補充候補)
- priority: P1
- lane: CodexB
- created: 2026-04-26(102 board 採番、本体仕様は alias `doc/PUB-002-C-...md` を参照)

## 仕様詳細

→ **`doc/PUB-002-C-subtype-unresolved-publish-blocker-reduction.md`** を参照

## write_scope

- 既存 `src/pre_publish_fact_check/extractor.py` の `infer_subtype` heuristic 拡張(narrow 改修)
- 新規 tests: `tests/test_subtype_unresolved_recovery.py`(or 既存 `tests/test_pre_publish_fact_check_extractor.py` 拡張)
- subtype branch 拡張: `coach_comment` / `pitcher_focus` / `roster_move` / `promotional_event` / `batter_focus` / `farm_postgame` / `farm_player_note` 等

## acceptance

1. 72h draft の subtype 別件数表
2. `other` 落ち pattern 代表サンプル(各 5-10 件)
3. 安全マッピング新 branch 案 3-5 件 + 実装 prompt 草案
4. tests 方針(branch カバレッジ + order test)
5. 既存 tests pass(branch order 互換性維持)

## test_command

```
python3 -m pytest tests/test_pre_publish_fact_check_extractor.py -v
python3 -m pytest tests/test_subtype_unresolved_recovery.py -v
python3 -m unittest discover -s tests 2>&1 | tail -3
```

## next_prompt_path

`/tmp/codex_110_impl_prompt.txt`(本 ticket fire 時に Claude が用意)

## 不可触

- creator 主線 `src/rss_fetcher.py` の大改修(narrow 修正のみ可)
- 全 draft 一括 re-classify
- WP write
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY` / front / plugin
- baseballwordpress repo
- `git add -A` / `git push`
