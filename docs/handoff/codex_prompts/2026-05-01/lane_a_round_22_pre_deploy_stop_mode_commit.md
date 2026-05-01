# Lane A round 22 — POLICY §17 Pre-Deploy Stop Mode 永続化 + 関連 ops doc 同期

## 目的

本日(2026-05-01)user 明示の方針 = 298-Phase3 v4 以外の全 ticket は **デプロイ直前まで** 進める = の永続化。POLICY §17 追加 + CURRENT_STATE / OPS_BOARD / NEXT_SESSION_RUNBOOK 同期 + round 21 receipt + round 22 prompt 永続化。

doc-only。code / deploy / env / Scheduler / SEO / source / Gemini / mail 一切触らない。

## 不可触リスト

- src / tests / scripts / config / .codex/automations 触らない
- env / Scheduler / secret / image / WP / Gemini call / mail routing 触らない
- `git add -A` 禁止
- 下記 scope 外 untracked / modified 一切触らない

## scope (明示的に stage する path のみ、6 path)

modified (M):
- `docs/ops/POLICY.md`(§17 Pre-Deploy Stop Mode 追加 + §16.5 末尾整合)
- `docs/ops/CURRENT_STATE.md`(ticket board を「デプロイ直前まで」表現に切替 + §17 reference)
- `docs/ops/OPS_BOARD.yaml`(`pre_deploy_stop_mode_2026_05_01:` block 追加)
- `docs/ops/NEXT_SESSION_RUNBOOK.md`(§7a 追加)

added (A):
- `docs/handoff/codex_receipts/2026-05-01/lane_a_round_21.md`(round 21 close 永続化)
- `docs/handoff/codex_prompts/2026-05-01/lane_a_round_22_pre_deploy_stop_mode_commit.md`(self-include)

## 実施

1. `git status --short` で 6 path のみ確認、想定外 file 混入なし
2. 6 path 明示 stage:
   ```
   git add docs/ops/POLICY.md docs/ops/CURRENT_STATE.md docs/ops/OPS_BOARD.yaml docs/ops/NEXT_SESSION_RUNBOOK.md
   git add docs/handoff/codex_receipts/2026-05-01/lane_a_round_21.md
   git add docs/handoff/codex_prompts/2026-05-01/lane_a_round_22_pre_deploy_stop_mode_commit.md
   ```
3. `git diff --cached --name-status` で M 4 + A 2 確認
4. commit message:

```
docs(ops): POLICY §17 Pre-Deploy Stop Mode 永続化(298-v4 以外 全 ticket 直前停止)

本日 user 明示方針:
- 298-Phase3 v4 以外の全 ticket は「デプロイ直前まで」進める
- 本番反映 (Cloud Run deploy / env / flag / Scheduler / SEO / source / Gemini / mail) は user GO まで停止
- impl / test / pytest / regression / commit / push(auto-deploy なし)/ Pack / rollback plan / verify plan / UNKNOWN 潰し は Claude 自律 GO
- user 向け表現:「READY_FOR_DEPLOY」より「デプロイ直前まで」を使う

ticket 別:
- 293-COST: デプロイ直前まで
- 282-COST: flag ON 直前まで
- 290-QA: デプロイ直前まで
- 300-COST: 実装直前または実装準備まで
- 288-INGEST: source 追加直前まで

POLICY §17 (17.1-17.6) 追加 + CURRENT_STATE / OPS_BOARD / NEXT_SESSION_RUNBOOK 同期 + Lane A round 21 receipt 永続化。
```

5. `git commit -m "<message>"`(plumbing 3 段 fallback)
6. `git log -1 --stat` で 6 file changed 確認

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "docs/ops/POLICY.md",
    "docs/ops/CURRENT_STATE.md",
    "docs/ops/OPS_BOARD.yaml",
    "docs/ops/NEXT_SESSION_RUNBOOK.md",
    "docs/handoff/codex_receipts/2026-05-01/lane_a_round_21.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_a_round_22_pre_deploy_stop_mode_commit.md"
  ],
  "diff_stat": "6 files changed",
  "commit_hash": "<hash>",
  "test": "n/a (doc-only)",
  "remaining_risk": "none",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff 6 file scope 内
- POLICY §17 + 関連 ops doc 同期 + round 21 永続化のみ
- pytest +0(doc-only)
- scope 内
- rollback 不要(可逆 doc commit)
