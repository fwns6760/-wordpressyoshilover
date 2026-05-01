# Lane A round 23 — Pre-Deploy Stop Mode Pack readiness audit(5 ticket、read-only)

## 目的

POLICY §17 Pre-Deploy Stop Mode 適用下、298-Phase3 v4 以外 5 ticket(293-COST / 282-COST / 290-QA / 300-COST / 288-INGEST)の **「直前まで」 Pack readiness** を audit。各 ticket の現状 + 不足項目 + 次 Codex subtask 候補を doc 化。read-only、impl / commit 一切なし。

## 不可触リスト

- src / tests / scripts / config / .codex / quality-* / draft-body-editor 触らない
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- git mutation 一切なし(commit / add / push 全部 NO)、純粋 read-only
- audit 結果 doc は本 round では書き込まない(次 round で integrate)

## 出力(stdout 経由、commit なし)

ticket 別、以下 form で output:

```
### <ticket-id>

- 直前 stop point: (POLICY §17.3 該当 cell)
- 既 Pack 由来:
  - <commit hash 1> <ticket round> <要約>
  - <commit hash 2> ...
- 既 Pack file path:(該当 file が repo 内にあれば)
- 13 fields 充足確認(POLICY §9 / ACCEPTANCE_PACK_TEMPLATE):
  - 1 Conclusion: ✓ / 不足 / partial
  - 2 Scope: ✓ / 不足
  - 3 Non-Scope: ✓ / 不足
  - 4 Current Evidence: ✓ / 不足
  - 5 User-Visible Impact: ✓ / 不足
  - 6 Mail Volume Impact: ✓ / 不足
  - 7 Gemini / Cost Impact: ✓ / 不足
  - 8 Silent Skip Impact: ✓ / 不足
  - 9 Preconditions: ✓ / 不足
  - 10 Tests: ✓ / 不足
  - 10a Post-Deploy Verify Plan(POLICY §3.5 7 項目): ✓ / 不足
  - 10b Production-Safe Regression Scope: ✓ / 不足
  - 11 Rollback(POLICY §3.6 / §16.4 3 dimensions): ✓ / 不足
  - 12 Stop Conditions: ✓ / 不足
  - 13 User Reply 1 行: ✓ / 不足
- 「直前まで」 gap(残作業):
  - <bullet 1>
  - <bullet 2>
- 次 Codex subtask 推奨(Lane A or B):
  - 内容:
  - scope:
  - estimated rounds:
- UNKNOWN 残:
  - <UNKNOWN 1>
  - <UNKNOWN 2>
- 自律 GO 該当か(POLICY §17.1 進めてよい範囲のみで closeable か):
  - YES / PARTIAL / NO
  - 理由:
```

最後に summary:

```
### Summary

- 完全に「直前まで」到達済 ticket: <list>
- 残 Pack work あり ticket(優先順): <list>
- UNKNOWN 解消必須 ticket: <list>
- 次に fire すべき Codex round: <ticket-id> <内容> <Lane>
- §17 適用後 Codex 連続 dispatch 計画(優先順、最大 5 連): <list>
```

## audit 範囲

read-only:
- `git log --oneline` 既 commit 確認
- 各 ticket の Pack 由来 commit `git show --stat <hash>` 確認
- repo 内 ticket doc(`doc/active/*.md`、`docs/handoff/codex_responses/2026-05-01_*.md`、`docs/handoff/codex_prompts/2026-05-01/*.md`)の grep
- POLICY §17.3 stop point cell との整合チェック
- POLICY §9 / ACCEPTANCE_PACK_TEMPLATE 13 fields 充足チェック
- POLICY §3.5 7-point post-deploy verify plan 文中存在チェック
- POLICY §3.6 / §16.4 3 dimension rollback plan 文中存在チェック

src / tests / scripts は読まない(audit は doc level のみ、実装詳細は Pack に書かれているはずの内容を確認)。

## 完了報告(stdout、commit なし)

5 ticket audit + summary を full output で stdout に出すだけ。Final report JSON は audit summary を含めて以下形式:

```json
{
  "status": "audit_completed",
  "tickets_audited": ["293-COST", "282-COST", "290-QA", "300-COST", "288-INGEST"],
  "fully_at_stop_point": [],
  "remaining_work_tickets": [],
  "unknown_blocked_tickets": [],
  "next_recommended_round": {
    "ticket": "<ticket-id>",
    "content": "<subtask>",
    "lane": "A or B",
    "estimated_rounds": <int>
  },
  "test": "n/a (read-only audit)",
  "open_questions_for_claude": [],
  "next_for_claude": "Read audit output, dispatch next Codex round per recommendation"
}
```

## 5 step 一次受け契約

- read-only(commit / git mutation 一切なし)
- doc 読み込みのみ
- pytest 不要
- scope 内
- rollback 不要(read-only audit)
