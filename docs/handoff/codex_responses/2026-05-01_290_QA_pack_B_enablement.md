# 290-QA Pack B: enablement

supersedes `2026-05-01_290_QA_ready_pack.md` (monolithic phase artifact)

Date: 2026-05-01 JST  
Mode: Lane A round 25 / doc-only / split decision pack  
Pack class: enablement / USER_DECISION_REQUIRED

## Decision Header

```yaml
ticket: 290-QA-enablement
recommendation: HOLD  # Pack A live-inert deploy 完了 + 1 週間 OBSERVED_OK 後に GO 化検討
decision_owner: user
execution_owner: Codex + Claude
risk_class: medium
classification: USER_DECISION_REQUIRED  # flag ON で挙動変化
user_go_reason: FLAG_ENV+WEAK_TITLE_RESCUE_ENABLEMENT
expires_at: Pack A live-inert OBSERVED_OK + 1 週間後
```

## 1. Conclusion

- 推奨 `HOLD`
- Pack A live-inert deploy 完了後、user `GO` で `GO` 化する前提
- 本 pack は挙動変化を伴う enablement を user decision 領域へ分離する

## 2. Scope

- env apply `ENABLE_WEAK_TITLE_RESCUE=1`
- weak title rescue path 有効化

## 3. Non-Scope

- image 変更
- Scheduler
- SEO
- source 追加
- Gemini call 増加
- rescue 経路は内部 fallback、新規 Gemini call なし想定だが要確認

## 4. Current Evidence

- Pack A live-inert deploy 完了 evidence が precondition
- 必要 evidence: commit + image SHA + post-deploy verify pass

## 5. User-Visible Impact

- weak title 検出時は review mail / `post_gen_validate` notification 経路へ送る
- normal review wall は維持

## 6. Mail Volume Impact

- expected `+1〜3 mail/h` (weak title rescue 検出時)
- `MAIL_BUDGET 30/h` 内

## 7. Gemini / Cost Impact

- 確認必須
- rescue path で Gemini call が増えるかは `UNKNOWN` 解消必須

## 8. Silent Skip Impact

- weak title rescue は review 経由の visible mail へ送る
- silent skip `0` 維持

## 9. Preconditions

- Pack A live-inert deploy `OBSERVED_OK` + `1` 週間安定
- Gemini call delta 数値確定
- mail volume burst 数値確定
- rollback path 確認 (`env remove`)

## 10. Tests

- weak title rescue unit test
- integration
- mail flow
- rollback test

## 10a. Post-Deploy Verify Plan (POLICY §3.5 7-point)

- image / revision: Pack A と同一
- env / flag: `ENABLE_WEAK_TITLE_RESCUE=1` 反映確認
- mail volume: rolling `1h < 30`, `24h < 100`
- Gemini delta: `±5%` (`UNKNOWN` 解消後の数値で判定)
- silent skip: `0`
- `MAIL_BRIDGE_FROM` 維持
- rollback target: env remove `30 sec`

## 10b. Production-Safe Regression Scope

- Pack A と同等

## 11. Rollback (POLICY §3.6 / §16.4 3 dimensions)

- Tier 1 runtime env: `gcloud run jobs update <job> --remove-env-vars=ENABLE_WEAK_TITLE_RESCUE` (`30 sec`)
- Tier 1 runtime image: 該当なし (`env-only change`)
- Tier 2 source: 該当なし (`env-only`)、ただし将来 weak title rescue narrow code change を含むなら `git revert <commit>`

## 12. Stop Conditions

- rolling `1h sent > 30`
- Gemini call `> +5%`
- silent skip `> 0`
- errors `> 0`
- publish/review/hold/skip 導線破損

## 13. User Reply

- 一言 `OK` / `HOLD` / `REJECT`
