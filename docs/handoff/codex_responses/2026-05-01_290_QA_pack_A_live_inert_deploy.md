# 290-QA Pack A: live-inert deploy

supersedes `2026-05-01_290_QA_ready_pack.md` (monolithic phase artifact)

Date: 2026-05-01 JST  
Mode: Lane A round 25 / doc-only / split decision pack  
Pack class: live-inert deploy / CLAUDE_AUTO_GO candidate

## Decision Header

```yaml
ticket: 290-QA
recommendation: GO  # 298-v4 24h 安定後、CLAUDE_AUTO_GO で進行可
decision_owner: Claude  # CLAUDE_AUTO_GO 該当時
execution_owner: Codex (build) + Claude (push, deploy verify)
risk_class: low
classification: CLAUDE_AUTO_GO  # POLICY §3.1 全条件確認
user_go_reason: n/a (live-inert deploy)
expires_at: 5/2 09:00 JST Phase 6 verify pass + 24h 安定後
```

## 1. Conclusion

- 推奨 `GO`。
- 本 pack は live-inert deploy 専用で、挙動変化を伴う Pack B enablement と切り離して扱う。
- `ENABLE_WEAK_TITLE_RESCUE` を未設定のまま維持するため、deploy 後も production behavior は不変。

## 2. Scope

- image rebuild `<weak-title-rescue 含む新 SHA>`
- env 変更なし
- `ENABLE_WEAK_TITLE_RESCUE` 未設定維持 = default `OFF`

## 3. Non-Scope

- env 変更
- flag `ON`
- Scheduler
- SEO
- source
- Gemini
- mail routing

## 4. Current Evidence

- existing impl commit は `c14e269` で既 push 済み
- tests は pytest baseline 維持予定
- production state は `298-v4 OBSERVED_OK`

## 5. User-Visible Impact

- なし
- flag `OFF` default のため code path は到達しない

## 6. Mail Volume Impact

- なし
- 挙動不変

## 7. Gemini / Cost Impact

- なし
- code unreachable のため Gemini delta `0`

## 8. Silent Skip Impact

- 不変
- silent skip `0` 維持、`POLICY §8` 前提

## 9. Preconditions

- `298-v4` Phase 6 verify pass
- `298-v4` 24h 安定
- image build success
- rollback target SHA 確認

## 10. Tests

- pytest `+0` regression
- 挙動不変確認
- `290` 関連 unit test pass

## 10a. Post-Deploy Verify Plan (POLICY §3.5 7-point)

- image / revision matches `<new SHA>`
- env / flag: 変更なし確認
- mail volume: 不変
- Gemini delta: `0`
- silent skip: `0` 維持
- `MAIL_BRIDGE_FROM` 維持
- rollback target: prev image SHA 記録

## 10b. Production-Safe Regression Scope

- allowed: read-only / log / health / mail count / env / revision / Scheduler obs / sample candidate / dry-run / existing notification route
- forbidden: bulk mail / source addition / Gemini / publish criteria / cleanup mutation / SEO / rollback-impossible / flag `ON` without `GO` / mail `UNKNOWN`

## 11. Rollback (POLICY §3.6 / §16.4 3 dimensions)

- Tier 1 runtime: image rollback `gcloud run jobs update <job> --image=<prev_SHA>` (`2-3 min`)
- Tier 2 source: `git revert c14e269` + push (必要時)
- last known good: prev image SHA + 直近安定 commit

## 12. Stop Conditions

- rolling `1h sent > 30`
- silent skip `> 0`
- errors `> 0`
- `289` 減
- Team Shiny 変
- publish/review/hold/skip 導線破損

## 13. User Reply

- 一言 `OK`
- `CLAUDE_AUTO_GO` 該当時は user 通知のみ
