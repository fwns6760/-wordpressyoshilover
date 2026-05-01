# Lane B round 19 — 300-COST read-only test plan + Pack supplement

## 目的

POLICY §17.3 = 300-COST「実装直前または実装準備まで進める」整合。read-only test plan 整備 + 既 narrow spec(commit `e14c944`)補強。impl は user GO 後の別 round。

## 不可触リスト

- src / tests / scripts / config 一切編集しない、read-only grep / cat / 設計のみ
- production 不触
- `git add -A` 禁止

## scope

added (A):
- `docs/handoff/codex_responses/2026-05-01_300_COST_test_plan_v1.md`(read-only test plan、impl 便 fire 用 contract 補強)
- `docs/handoff/codex_prompts/2026-05-01/lane_b_round_19_300_test_plan.md`(self-include)

## 内容

read-only 調査 + test plan doc:

1. existing source-side dedupe path 把握(`src/guarded_publish_runner.py`、`src/cron_eval.py`)
2. 同一 post_id 連続 evaluate 時の挙動分析(現状 vs impl 後)
3. test cases 7+ 設計(narrow spec で要求済 7 件 + 追加 edge case)
4. test fixture 設計(JSONL ledger / mock cron_eval.json)
5. baseline pytest 現在 2018/0(本日 main)→ +N/0 想定
6. 300 関連 既存 test の grep + 影響範囲確認
7. impl 直前 capture 必須項目(pre-300 image SHA / source rollback commit)を明示

POLICY §3.5 7-point + §16.4 3-dim rollback test も含める(impl 便 fire 時 reuse)。

## 完了後 commit + push

通常 flow。本 round は production 不触、Codex sandbox commit 通常成功想定。
