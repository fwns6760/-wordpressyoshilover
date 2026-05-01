# YOSHILOVER ACCEPTANCE_PACK_TEMPLATE

Last updated: 2026-05-01 JST

Use this when a change is `USER_DECISION_REQUIRED`. Do not use a Pack to offload UNKNOWN technical judgment to the user; UNKNOWN means HOLD until Claude resolves it. `CLAUDE_AUTO_GO` changes need evidence and Decision Batch reporting, not user approval.

## Decision Header

```yaml
ticket:
recommendation: GO | HOLD | REJECT
decision_owner: user
execution_owner: Claude | Codex
risk_class:
classification: CLAUDE_AUTO_GO | USER_DECISION_REQUIRED | HOLD
user_go_reason:
expires_at:
```

## Required Fields

1. Conclusion
   - GO / HOLD / REJECT
   - one-sentence reason

2. Scope
   - exactly what will change

3. Non-Scope
   - what will not change
   - explicitly mention Cloud Run, Scheduler, SEO, source, Gemini, mail routing if relevant

4. Current Evidence
   - commits
   - tests
   - logs
   - current prod state

5. User-Visible Impact
   - publish
   - review mail
   - hold mail
   - skip mail
   - X candidate

6. Mail Volume Impact
   - expected mails/hour
   - expected mails/day
   - MAIL_BUDGET compliance
   - UNKNOWN means HOLD

7. Gemini / Cost Impact
   - expected Gemini call delta
   - source/candidate count impact
   - UNKNOWN means HOLD

8. Silent Skip Impact
   - how every candidate reaches publish/review/hold/skip visibility
   - internal log only is not enough

9. Preconditions
   - all must be true before GO

10. Tests
   - unit tests
   - smoke checks
   - regression checks
   - mail checks
   - rollback checks

11. Rollback
   - exact command or exact action
   - expected rollback time
   - rollback owner

12. Stop Conditions
   - errors
   - mail burst
   - silent skip
   - Gemini increase
   - user-visible degradation

13. User Reply
   - one line only:
     - `OK`
     - `HOLD`
     - `REJECT`

## 298-Phase3 Additional Required Fields

For any Phase3 re-ON Pack, include:

- old candidate pool cardinality estimate
- expected first-send mail count
- max mails/hour
- max mails/day
- stop condition
- rollback command
- confirmation that `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` is currently OFF/absent
- confirmation that persistent ledger behavior is currently disabled
- confirmation that normal review, 289, and error mail remain active

If any value is UNKNOWN, recommendation must be HOLD.

## Forbidden Pack Patterns

- "進めてよいですか?" without the required fields
- multiple unrelated choices
- raw Codex output
- "probably safe" without evidence
- "mail volume unknown but GO"
- "Gemini impact unknown but GO"
- "rollback unclear but GO"

## Minimal User-Facing Format

```text
結論: GO / HOLD / REJECT
分類: CLAUDE_AUTO_GO / USER_DECISION_REQUIRED / HOLD
理由:
変更範囲:
変えないもの:
mail影響:
Gemini/cost影響:
silent skip:
rollback:
stop condition:
userが返すべき1行:
```
