# 282-COST Pack v3 template refresh

Supersedes `2026-05-01_282_COST_ready_pack.md` (pre-293-impl phase artifact).

Date: 2026-05-01 JST  
Mode: Lane A round 26 / doc-only / template refresh  
Pack status: 293 impl-complete sync / user-decision-required / production unchanged

## Decision Header

```yaml
ticket: 282-COST
recommendation: HOLD
decision_owner: user
execution_owner: Codex (env apply via Cloud Run job update) + Claude (push, post-deploy verify)
risk_class: medium
classification: USER_DECISION_REQUIRED
user_go_reason: FLAG_ENV+COST_INCREASE
expires_at: 293 image rebuild + flag ON OBSERVED_OK + 24h 安定後
```

## 1. Conclusion

- **HOLD**: `ENABLE_GEMINI_PREFLIGHT=1` の有効化は `293-COST` image rebuild + flag ON deploy 完了と `24h` `OBSERVED_OK` が前提。
- 293 が `READY_FOR_DEPLOY` に進んだため、282 の HOLD 理由は「impl 未完」ではなく「deploy + observe precondition 未達」に更新された。

## 2. Scope

- env apply `ENABLE_GEMINI_PREFLIGHT=1`
- 282-COST preflight gate の live 有効化
- 293 で既に push 済みの visible preflight-skip path を前提にした flag ON judgment

## 3. Non-Scope

- image 変更
- Scheduler 変更
- SEO / noindex / canonical / 301
- source 追加
- mail routing 変更
- 293-COST 実装差分の再編集

## 4. Current Evidence

- `293-COST` implementation commits `6932b25`, `afdf140`, `7c2b0cc`, `10022c0` are on `origin/master`
- `293` test baseline is `pytest 2018/0`
- `293` current state is `READY_FOR_DEPLOY`; remaining step is image rebuild + flag ON deploy + `24h` observe
- current production state is `298-v4 deploy OBSERVED_OK`
- `282` supplement `925003d` and unknown-resolution `ade62fb` already fixed:
  - `Candidate disappearance risk = NO`
  - `Cache impact = YES`
- remaining open metric is not a Pack-field UNKNOWN:
  - exact post-enable Gemini call delta is confirmed only after live deploy + `24h` observe

## 5. User-Visible Impact

- preflight gate 有効化により、Gemini に進む前の source-side cost を削減する。
- `293` visible path が live であれば、preflight skip は internal-log-only ではなく既存 notification route で見える。
- 想定 user-visible outcome は publish 量の急変ではなく、`silent skip 0` を保ったままの cost suppression。

## 6. Mail Volume Impact

- 新しい mail routing は追加しない。
- 期待される net increase は **none**。許容 outcome は `flat to slight down` で、`MAIL_BUDGET 30/h・100/d` の範囲内を維持する。
- `293` code path は既に push 済みのため、282 flag ON 自体は env apply のみで mail flow contract を変えない。

## 7. Gemini / Cost Impact

- primary goal is **Gemini call reduction**
- expected direction is down; reverse-direction anomaly(`> +5%`) is an immediate stop condition
- source count / candidate count の追加はない
- exact delta remains a post-deploy metric:
  - rough direction = reduction
  - exact rate = confirm after `293` deploy + `282` flag ON + `24h` observe

## 8. Silent Skip Impact

- `293` により preflight skip は publish-notice 経由の visible mail path を持つ
- `282` flag ON 後も `silent skip = 0` 維持が acceptance
- internal log only は不可。publish / review / hold / skip 導線の user-visible contract を壊さないこと

## 9. Preconditions

- `293` image rebuild deploy 完了
- `293` flag ON 後の post-deploy verify が `OBSERVED_OK`
- `293` `24h` stability confirm 完了
- rollback path(`--remove-env-vars=ENABLE_GEMINI_PREFLIGHT`) を authenticated executor が即実行可能
- exact Gemini call delta が post-deploy observe で確定可能な状態になっている

## 10. Tests

- `293` coverage is already `pytest 2018/0`, including `test_preflight_skip_notification.py` and `7` new tests
- `282` 自体に追加の unit / integration test は不要。今回の live mutation は env apply のみ
- smoke / regression / mail / rollback 検証は post-deploy observe で確認する

## 10a. Post-Deploy Verify Plan (POLICY §3.5 7-point)

- image / revision: `293` deploy 後の intended image / revision を維持する
- env / flag: `ENABLE_GEMINI_PREFLIGHT=1` 反映確認
- mail volume: rolling `1h < 30`, `24h < 100`, storm pattern 不在
- Gemini delta: expected reduction direction。abnormal は `> +5%`
- silent skip: `0` 維持
- Team Shiny From: `MAIL_BRIDGE_FROM` 維持
- rollback target: env remove `~30 sec` + GitHub/source rollback path 記録済み

## 10b. Production-Safe Regression Scope

- allowed:
  - read-only
  - log / health
  - mail count
  - env / revision
  - Scheduler observation
  - sample candidate review
  - dry-run-equivalent checks
  - existing notification route verification
- forbidden:
  - bulk mail
  - source addition
  - Gemini increase
  - publish criteria change
  - cleanup mutation
  - SEO change
  - rollback-impossible mutation
  - flag ON without user `OK`
  - mail experiment while impact is unknown

## 11. Rollback (POLICY §3.6 / §16.4 3 dimensions)

- Tier 1 runtime env:
  - `gcloud run jobs update <job> --remove-env-vars=ENABLE_GEMINI_PREFLIGHT`
  - expected time: `~30 sec`
  - owner: Claude / authenticated executor
- Tier 1 runtime image:
  - not applicable for this Pack because the 282 live step is env-only
- Tier 2 source:
  - no source revert is required for the 282 flag flip itself
  - if a future preflight code change is bundled, use `git revert <commit>`
- last known good:
  - `293` deploy 直後 image SHA
  - `293` commit family `6932b25..10022c0`

## 12. Stop Conditions

- rolling `1h sent > 30`
- `silent skip > 0`
- `errors > 0`
- `289` volume decreases unexpectedly
- Team Shiny From changes
- publish / review / hold / skip routing breaks
- Gemini call delta exceeds `+5%`

## 13. User Reply

`OK` / `HOLD` / `REJECT`
