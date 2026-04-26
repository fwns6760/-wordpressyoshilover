# 111 long-body-compression-or-exclusion

## meta

- number: 111
- alias: PUB-002-D
- owner: Claude Code(設計)/ Codex B(実装)
- type: ops / publish blocker reduction / prose length policy
- status: READY(B 補充候補)
- priority: P1
- lane: CodexB
- created: 2026-04-26(102 board 採番、本体仕様は alias `doc/PUB-002-D-...md` を参照)

## 仕様詳細

→ **`doc/PUB-002-D-long-body-draft-compression-or-exclusion-policy.md`** を参照

## write_scope

- 新規 module: `src/long_body_compression_audit.py`(read-only audit + subtype 別 prose 上限判定)
- 新規 CLI: `src/tools/run_long_body_audit.py`
- 新規 tests: `tests/test_long_body_compression_audit.py`
- 既存 PUB-004-B detector(`heading_sentence_as_h3` / `dev_log_contamination` / `weird_heading_label`)流用、改変禁止
- WP write は本 ticket scope 外(後続 ticket、113 以降)

## acceptance

1. 72h draft の prose 長分布表
2. 長い body の構造要因 5 軸の集計(AI tone / 関連記事 / Twitter / 二重化 / 一般論)
3. subtype 別 policy 表(上限 + 圧縮可否 + 除外条件)
4. Yellow 修正方針(`HALLUC-LANE-001-A` 案 = AI tone 決定論検出)
5. Green に戻せる条件 / Red 除外条件
6. WP write ゼロ
7. tests pass

## test_command

```
python3 -m pytest tests/test_long_body_compression_audit.py -v
python3 -m unittest discover -s tests 2>&1 | tail -3
```

## next_prompt_path

`/tmp/codex_111_impl_prompt.txt`(本 ticket fire 時に Claude が用意)

## 不可触

- WP REST POST/PUT/DELETE(read-only audit のみ)
- 大量自動 rewrite
- published 記事の書換(本 ticket scope 外)
- `RUN_DRAFT_ONLY` flip
- creator 主線 `src/rss_fetcher.py` 大改修
- automation / scheduler / .env / secrets / Cloud Run env
- front / plugin / build
- baseballwordpress repo
- `git add -A` / `git push`
