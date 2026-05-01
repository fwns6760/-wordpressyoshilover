# 293-COST deploy-phase Pack v3

Supersedes `2026-05-01_293_COST_ready_pack.md` (impl-start phase artifact).

Date: 2026-05-01 JST  
Mode: Lane A round 24 / doc-only / deploy-phase Pack refresh  
Pack status: impl-complete sync / user-decision-required / production unchanged

## Decision Header

```yaml
ticket: 293-COST
recommendation: HOLD
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: medium
classification: USER_DECISION_REQUIRED
user_go_reason: FLAG_ENV+IMAGE_REBUILD
expires_at: 2026-05-02 09:00 JST after Phase 6 verify pass + 24h stability
```

## 1. Conclusion

- **HOLD**: deploy-phase Pack is implementation-complete and decision-ready, but Claude recommendation stays `HOLD` until `298-v4` Phase 6 verify passes and 24h stability is confirmed.

## 2. Scope

- image rebuild to `yoshilover-fetcher:<new SHA>` including the 293-COST preflight-skip notification path
- env apply:
  - `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1`
  - `PREFLIGHT_SKIP_LEDGER_PATH`
  - `PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS`
- post-deploy verify for revision, env, startup, mail path, silent-skip visibility, and rollback readiness

## 3. Non-Scope

- Cloud Run service traffic split
- Scheduler change
- SEO / noindex / canonical / source expansion
- Gemini call increase
- mail routing / From change

## 4. Current Evidence

- implementation commits `6932b25`, `afdf140`, `7c2b0cc`, and `10022c0` are reflected on `origin/master`
- test baseline moved from `pytest 2008/0` to `pytest 2018/0`
- delta is `+10` passing tests: `7` new + `3` existing coverage
- `299-QA` transient issue is absent in a fresh environment pass
- production state is `298-v4 deploy complete / OBSERVED_OK`
- Lane A and Lane B are idle relative to this deploy decision

## 5. User-Visible Impact

- preflight skip becomes visible by email notification instead of remaining indistinguishable from silent skip
- normal review mail, `289` path, and Team Shiny From remain unchanged
- publish / review / hold / skip routing stays intact if deploy verify passes

## 6. Mail Volume Impact

- expected preflight-skip notification volume is about `5 mails/hour` from the last `6h` observation pattern
- expected first-day burst upper bound is about `10`
- this remains inside `MAIL_BUDGET 30/hour`
- decision should remain `HOLD` if post-deploy verify suggests mail behavior above those bounds

## 7. Gemini / Cost Impact

- preflight-skip notification adds no Gemini call
- implementation is scanner / ledger touch only
- source count and candidate count are unchanged
- expected Gemini delta tolerance remains within `±5%`

## 8. Silent Skip Impact

- preflight skip is routed into publish-notice visibility instead of silent loss
- `silent skip = 0` must remain true after deploy
- this aligns with `POLICY §8` so long as visible skip mail emits and existing review paths remain intact

## 9. Preconditions

- `298-v4` Phase 6 verify must pass
- `298-v4` must remain stable for `24h`
- image build must succeed
- rollback target previous image SHA must be recorded before env apply

## 10. Tests

- unit, smoke, regression, mail-path, and rollback-related coverage are represented in `pytest 2018/0`
- no additional runtime-only test debt is introduced by this Pack refresh

## 10a. Post-Deploy Verify Plan (POLICY §3.5 7-point)

- confirm deployed image and active revision match `<new SHA>`
- confirm env includes `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1`
- confirm service/job startup is healthy
- record previous image SHA as the runtime rollback target
- confirm GitHub/source rollback path remains `git revert 6932b25 afdf140 7c2b0cc 10022c0`
- confirm error trend stays at `0`
- confirm mail volume remains under `rolling 1h < 30` and `24h < 100`
- confirm Gemini delta stays within `±5%`
- confirm silent skip remains `0`
- confirm Team Shiny From remains `y.sebata@shiny-lab.org`
- confirm publish / review / hold / skip paths remain intact
- confirm no stop condition is hit

## 10b. Production-Safe Regression Scope

- allowed:
  - read-only inspection
  - log / health / mail-count review
  - env check
  - revision check
  - Scheduler observation
  - sample candidate review
  - dry-run
  - existing notification route verification
- forbidden:
  - bulk mail
  - source addition
  - Gemini increase
  - publish-criteria change
  - cleanup mutation
  - SEO change
  - rollback-impossible mutation
  - flag ON without user `GO`
  - mail experiment with `UNKNOWN` volume

## 11. Rollback (POLICY §3.6 / §16.4 3 dimensions)

- Tier 1 runtime:
  - env rollback: `gcloud run jobs update <job> --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION,PREFLIGHT_SKIP_LEDGER_PATH,PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS` (`~30 sec`)
  - image rollback: `gcloud run jobs update <job> --image=<prev_SHA>` (`~2-3 min`)
- Tier 2 source:
  - `git revert 6932b25 afdf140 7c2b0cc 10022c0` + push `origin master`
- last known good:
  - previous image SHA
  - commit `dab9b8e` (`298-v4` robustness supplement)

## 12. Stop Conditions

- rolling `1h sent > 30`
- `silent skip > 0`
- errors `> 0`
- `289` volume decreases unexpectedly
- Team Shiny From changes
- publish / review / hold / skip routing breaks
- Gemini call delta exceeds `+5%`
- cache-hit ratio moves by more than `±15pt`

## 13. User Reply

`OK` / `HOLD` / `REJECT`
