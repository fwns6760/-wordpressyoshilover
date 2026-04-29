---
ticket: 243
title: emit observability narrow fix (llm_cost / no_op_skip 観測経路の見える化)
status: CLOSED
owner: Claude (起票) / Codex A (実装)
priority: P1
lane: A
ready_for: codex_a_fire
created: 2026-04-28
related: 229-A (llm_cost emit), 232 (no_op_skip), 235 (duplicate_news_pre_gemini_skip), 236-A (rule_based_subtype_skip_gemini), 229-B (cooldown / refused_cooldown)
---

## 背景

229-A / 232 / 235 / 236-A / 229-B の Gemini cost 削減は **logic としては動いている**(集計で 184 entries → 1 draft = 99% filter 確認済)。
しかし **per-tick の skip event log が Cloud Logging に出ていない**ため、削減量が ticket 単位で不可視。

具体的観測:
- **N-1**: `src/rss_fetcher.py` の `emit_llm_cost()` 呼び出し(line 4314 / 4342 / 7758 / 7780 / 8249 / 8270 の 6 箇所)、12:15 fetcher tick で `Gemini strict fact mode 生成成功` 3 件確認済だが、textPayload に `"event":"llm_cost"` JSON 行が **0 件**
- **N-2**: `src/tools/run_draft_body_editor_lane.py:1076` の `_emit_no_op_skip_log()`、`if not candidates` (line 1441) から呼ばれる想定だが、4 tick (12:02 / 12:12 / 12:22 / 12:32) 全て `Container called exit(0)` のみで stdout 空

仮説:
1. emit code path は到達しているが、`try/except` で例外が swallow されて print されず終わっている
2. emit より前の早期 return / 早期 exit で emit に到達していない
3. stdout flush は走っているが Cloud Logging 側で出ていない(可能性低、他 print は出ている)

## ゴール

**「削減する処理」は触らない**。「削減が見えるようにする処理」だけ narrow 追加。

具体的に:
- emit_llm_cost / `_emit_no_op_skip_log` 周辺の **swallow されている例外を log に出す**(error log 追加のみ、logic 不変)
- 「emit に到達したか」「到達せずに早期 return したか」が log で識別できる状態にする
- 既存 unit test に **emit 到達 assertion** を追加(emit が呼ばれることを test で担保、test logic 変更ではなく既存 test の verify 強化)

## scope (narrow)

### 対象 file (3 file 想定):

1. **`src/rss_fetcher.py`** — emit_llm_cost call sites 6 箇所(line 4314 / 4342 / 7758 / 7780 / 8249 / 8270)周辺
   - call site の `try/except` に `except Exception as e: log.warning(...)` を追加(silent pass を debug log 化)
   - emit 直前/直後の到達識別 log を debug レベルで追加(本数最小、INFO は増やさない)

2. **`src/tools/run_draft_body_editor_lane.py`** — `_emit_no_op_skip_log` (line 1076) / 呼び出し元 (line 1441 周辺) / main() entrypoint (line 1218)
   - main() の早期 return path(`if args.max_posts <= 0` / edit_window error / candidates 取得時の例外)に「なぜ早期 return したか」の 1 行 log
   - `_emit_no_op_skip_log` の try/except に warning 追加

3. **`src/llm_cost_emitter.py`** — `emit_llm_cost()` 内部
   - JSON dump / stdout.write / stdout.flush の各段階で例外が swallow されないように warning 追加
   - 出力した payload の hash / size を debug log で残す(payload 重複や空 payload 検出用)

### test 拡張 (既存 test の assertion 強化のみ、新 test 追加は最小):

- `tests/` 配下の既存 emit_llm_cost / _emit_no_op_skip_log 関連 test に `assert emit が呼ばれた` の確認追加
- 新規 fixture / 新規 logic test は **追加しない**(narrow scope 維持)

### 完了報告で必須:

- changed files (path + 行数)
- swallow されていた例外の有無(あれば原因と log 出力例 1 行)
- emit 到達/早期 return の識別が log で可能になったか(yes/no + 確認方法)
- pytest collect 数 / pass 数 / fail 数 (baseline 比)

## 不可触 (絶対に触らない)

- `src/guarded_publish_evaluator.py` (242-A/D/D2/E live、評価 logic 変更禁止)
- `src/draft_body_editor.py` 本体 (品質 logic 不変)
- 235 の `duplicate_news_pre_gemini_skip` 判定 logic (line 10396 / 10438 周辺、event 名や条件式は変えない)
- 236-A の `rule_based_subtype_skip_gemini` 判定 logic (line 6795 周辺)
- 229-A / 229-B の cooldown / refused_cooldown logic
- Gemini call の追加 / 削除
- WP REST 呼び出し / WP publish/draft 変更
- env / Secret / Scheduler / Cloud Run 設定
- automation.toml / cron / RUN_DRAFT_ONLY
- 新規 LLM 呼び出し / 新規 API call / 新規外部依存
- Web 検索 / browser / 外部 fetch
- evaluator / publish gate / fact_check / quality 系全般

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 3 file (+ tests) の最小 diff のみ stage、git add -A 禁止、明示 path のみ
2. **挙動**: 既存 emit 経路の logic は完全に同じ、追加されたのは error log と debug log のみ。pytest baseline (現行 collect/pass/fail) を維持(fail 増えない)
3. **境界**: 評価 logic / publish gate / Gemini call / Cloud Run / Scheduler / Secret / WP すべて不変

## commit 規約

- git add -A 禁止、明示 path のみ stage
- commit message: `243: emit observability narrow fix (llm_cost / no_op_skip path 可視化)`
- push は Claude が後から実行(Codex は commit までで止まる)
- `.git/index.lock` 拒否時は plumbing 3 段 fallback(write-tree / commit-tree / update-ref)

## 完了後の Claude 判断事項

- pytest baseline 確認 + commit accept
- git push (Claude 実行)
- live 反映は次便(rss_fetcher / draft_body_editor 両 image rebuild、本 ticket scope 外)
- 観測 log 出方を 1-2 tick 確認して、bug 確定 or 追加 narrow ticket 起票判断

## non-goals

- 削減 logic の追加 / 強化(229-C 等)
- 新規 skip event 追加(本 ticket は既存 event の **見える化**のみ)
- emit failure の自動 retry(複雑度上昇、scope 外)
- Cloud Logging 側の log filter 追加(GCP infra 変更、scope 外)
- README / assignments の大幅編集(本 commit は src + tests のみ)
