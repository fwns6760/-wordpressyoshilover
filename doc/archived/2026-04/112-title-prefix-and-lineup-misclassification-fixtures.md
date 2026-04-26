# 112 title-prefix-and-lineup-misclassification-fixtures

## meta

- number: 112
- alias: -
- owner: Claude Code(設計)/ Codex B(実装、test-first)
- type: ops / fixture-based test / regression prevention
- status: READY(B 補充候補)
- priority: P0.5
- lane: CodexB
- created: 2026-04-26
- 関連: 104(PUB-002-E、commit `78f965d` で land)、本 ticket は 104 本体実装と衝突しないよう **fixture / test-first**

## 目的

`subtype=lineup` 以外に `巨人スタメン` prefix が付く問題を **fixture 化して止める**。
104 で `lineup_prefix_misuse` 判定は実装されたが、本 ticket は **regression test 強化** + **edge case fixture** の追加。

## 問題例

- title: `巨人スタメン 主将・岸田行倫が初回に先制の適時二塁打！` → 実は **postgame** 記事(63497 で観測)
- title: `巨人スタメン 巨人・石塚裕惺の激動２デイズ` → 実は **postgame** narrative(63307)
- title: `巨人スタメン NPB通算安打 ① （東映）3085` → 実は **数値ランキング**(63499)

これらが PUB-004-A evaluator で正しく `lineup_prefix_misuse` Red 判定されることを fixture で保証。

## 重要制約

- **104 本体実装(`src/lineup_source_priority.py` / `src/guarded_publish_evaluator.py`)を改変しない**(衝突防止、本 ticket は fixture/test 追加のみ)
- WP write 一切なし
- live publish / mail / X 一切なし
- `.env` / secret / Cloud Run env / front 全部不可触
- `git add -A` 禁止 / `git push` 禁止

## write_scope

- 新規 file: `tests/test_title_prefix_lineup_misuse_fixtures.py`(本 ticket 主体、fixture-based regression test)
- 既存 `src/lineup_source_priority.py`(改変禁止、import 流用のみ)
- 既存 `src/guarded_publish_evaluator.py`(改変禁止、import 流用のみ)
- 既存 `tests/test_guarded_publish_evaluator.py` / `tests/test_lineup_source_priority.py`(既存 tests を破壊しない、本 ticket は **追加のみ**)

## acceptance

1. fixture(>= 8 件):
   - `巨人スタメン` prefix + lineup body(正しい) → Green or Yellow OK
   - `巨人スタメン` prefix + postgame body → `lineup_prefix_misuse` Red
   - `巨人スタメン` prefix + 数値ランキング body → `lineup_prefix_misuse` Red + R7
   - `巨人スタメン` prefix + injury body → R5 + `lineup_prefix_misuse` Red
   - 短いラベル H3 のみ(`スタメン` 単体)許容 fixture
   - speculative `巨人スタメン どう見る` → R5 speculative
   - 同 game 重複 lineup_notice (game_id 同じ + 報知/非報知両方) → 報知 1 本残り、他 absorbed
   - 報知なし lineup_notice → deferred
2. 各 fixture が PUB-004-A evaluator + `compute_lineup_dedup` で期待 Red 判定
3. 既存 tests(`test_guarded_publish_evaluator.py` 既存 17+9 件、`test_lineup_source_priority.py`)pass
4. 本 ticket 追加 fixture test がすべて pass
5. 104 本体 src 改変なし(verify: `git diff` で src/ 改変ゼロ)

## test_command

```
python3 -m pytest tests/test_title_prefix_lineup_misuse_fixtures.py -v
python3 -m pytest tests/test_lineup_source_priority.py tests/test_guarded_publish_evaluator.py -v  # regression
python3 -m unittest discover -s tests 2>&1 | tail -3
```

## next_prompt_path

`/tmp/codex_112_impl_prompt.txt`(本 ticket fire 時に Claude が用意)

## 不可触

- src/ 配下の既存 file 改変(本 ticket = test 追加のみ)
- 104 本体 src(`src/lineup_source_priority.py` / `src/guarded_publish_evaluator.py` の lineup hook)
- WP write
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY` / front / plugin
- baseballwordpress repo
- `git add -A` / `git push`

## 関連 file

- `doc/104` 相当 = `doc/PUB-002-E` 内容(本 chat 内既起票、commit `78f965d`)
- `doc/PUB-004-guarded-auto-publish-runner.md`(評価 contract)
- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(R 判定)
- `src/lineup_source_priority.py`(104 本体、流用のみ)
- `src/guarded_publish_evaluator.py`(PUB-004-A、流用のみ)
