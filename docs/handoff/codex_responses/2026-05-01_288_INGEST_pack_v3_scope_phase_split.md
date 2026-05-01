# 288-INGEST Pack v3 scope normalization + 4-phase split

Supersedes `2026-05-01_288_INGEST_ready_pack.md` (narrow source-add phase artifact).

Date: 2026-05-01 JST  
Mode: Lane A round 27 / doc-only / scope normalization  
Pack status: active-ticket scope sync / production unchanged

## Decision Header

```yaml
ticket: 288-INGEST
recommendation: HOLD
decision_owner: user
execution_owner: Codex (impl) + Claude (push, source-add deploy verify)
risk_class: medium-high
classification: USER_DECISION_REQUIRED
user_go_reason: SOURCE_ADD+COST_INCREASE+MAIL_VOLUME_IMPACT
expires_at: 298-v4 24h 安定 + 293/282 完了 + phase-3 exact mail/Gemini/rollback fields 確定後
```

## Scope normalization summary

- active ticket `doc/active/288-INGEST-source-coverage-expansion.md` is a **multi-phase scope**:
  - Phase 1: candidate visibility contract
  - Phase 2: fallback + trust-score implementation
  - Phase 3: source addition
  - Phase 4: post-add stabilization + cost trend audit
- previous ready pack `2026-05-01_288_INGEST_ready_pack.md` was a **narrow Phase 3 artifact** centered on adding `NNN web / スポニチ web / サンスポ web`
- this v3 Pack restores the **active ticket as the canonical scope** and keeps execution phase-split; no all-in-one GO is allowed

## Phase split(active ticket sync)

| phase | scope | mutation level | decision class | note |
|---|---|---|---|---|
| 1 | candidate visibility contract | read-only verify | HOLD until pack/evidence close | source add 前に silent skip `0` / visible terminal outcome 契約を固定 |
| 2 | fallback + trust score impl | narrow impl / possible live-inert deploy | `CLAUDE_AUTO_GO` candidate only if behavior-preserving; else re-pack | 報知 RSS error fallback、NNN family / source trust 整備 |
| 3 | source add(3 source) | `config/rss_sources.json` + deploy + observe | `USER_DECISION_REQUIRED` | live mail / Gemini / candidate volume 影響が出る本体 phase |
| 4 | post-add stabilization + cost trend audit | observe / audit | post-add Pack v4 | `24h` trend と rollback 必要性の監視 |

## 1. Conclusion

- **HOLD**: 288-INGEST は source-add 単相ではなく fallback / trust / source add / post-add audit を含む 4-phase ticket として扱う。
- **Reason**: source 追加前に phase split と前提条件を固定し、Phase 3 の exact mail / Gemini / rollback 数値が確定するまで user `OK` を求めない。

## 2. Scope

- **Phase 1**: candidate visibility contract 確認(read-only)
  - `publish / review / hold / skip` visible terminal outcome 契約
  - `silent skip 0` の evidence 固定
- **Phase 2**: fallback + trust score narrow impl
  - 報知 RSS error retry / fallback
  - `NNN` family などの trust / source-family 整理
  - live-inert deploy で済む場合のみ `CLAUDE_AUTO_GO` 候補
- **Phase 3**: 3 source 追加
  - `config/rss_sources.json` に `NNN web / スポニチ web / サンスポ web`
  - fetcher rebuild / deploy
  - live mail / Gemini / candidate count impact を伴う
- **Phase 4**: `24h` post-add observe + cost audit
  - source 別 publish / review / hold / skip 集計
  - mail / Gemini / cache / candidate disappearance trend audit

## 3. Non-Scope

- 本 round での code / deploy / production 変更
- 本 round での `config/rss_sources.json` 編集(source 追加しない)
- Scheduler 変更
- SEO / noindex / canonical / 301
- publish criteria / review criteria の変更
- Team Shiny From / mail routing major redesign
- 全 4 phase を一括で `OK` にすること
- 広域 scanner / persistence / ledger rewrite

Note:
- Phase 2 は将来 narrow code change と image/revision reflection を伴いうるが、本 round では実施しない。

## 4. Current Evidence

- active ticket: `doc/active/288-INGEST-source-coverage-expansion.md`
  - fallback / trust / source-add / post-add audit の 4 phase を already defined
- existing 288 bundle:
  - draft `26ede3a`
  - supplement `5f8b966`
  - unknown resolution `ade62fb`
  - ready pack `7fd760f`
- pack consistency review v2 `0ae5505` already closed bundle completeness; remaining issue is **scope mismatch**, not field completeness
- current production state is recorded as `298-v4 OBSERVED_OK`
- existing supplement already fixed planning envelopes relevant to phase split:
  - mail impact planning band: `+3/day` typical, `+6/day` conservative upper
  - raw Gemini delta planning band: about `+5% to +10%`
  - final exact phase-3 acceptance values remain a pre-GO requirement

## 5. User-Visible Impact

- **Phase 1**: none(read-only)
- **Phase 2**: none if live-inert / behavior-preserving; otherwise Phase 2 must be re-packed before any live reflection
- **Phase 3**:
  - new-source candidates may increase
  - review / hold / skip visibility may increase
  - publish opportunities may increase
- **Phase 4**: none as a product change; observe-only

Guardrail:
- 288 may increase visible opportunity surface, but it may not reduce existing visible opportunities or create internal-log-only outcomes.

## 6. Mail Volume Impact

- **Phase 1-2**: none expected
- **Phase 3**:
  - planning envelope inherited from the current 288 supplement is `+3/day` typical, `+6/day` conservative upper
  - exact acceptance value must be locked as `expected +N/h, +N/day` in the dedicated Phase 3 Pack before user `OK`
  - `MAIL_BUDGET 30/h・100/d` compliance is mandatory
- **Phase 4**: observe trend only

Result:
- current recommendation stays `HOLD` until Phase 3 mail numbers are exact, not just modeled.

## 7. Gemini / Cost Impact

- **Phase 1**: none
- **Phase 2**: none expected if the phase is truly live-inert
- **Phase 3**:
  - cost direction is **increase**
  - current modeled raw delta from the existing 288 bundle is about `+5% to +10%`
  - exact phase-3 acceptance delta must be locked before GO
  - `282/293` cost-suppression chain must already be complete and stable first
- **Phase 4**: observe exact post-add cost trend

Rule:
- If the exact delta is still UNKNOWN at Phase 3 user-decision time, recommendation remains `HOLD`.

## 8. Silent Skip Impact

- **Phase 1-3 全て**: `silent skip = 0` must remain true
- all candidates, including new-source candidates, must end in visible:
  - `publish`
  - `review`
  - `hold`
  - `skip`
- internal-log-only outcomes are forbidden
- title collision / source merge / dedup may not silently erase an existing visible candidate

## 9. Preconditions

- `298-v4` post-deploy verify pass + `24h` 安定
- `293-COST` image rebuild + deploy reflect 完了
- `282-COST` flag ON 完了 + `24h` 安定
- `291 / 295 / 293→282` dependency chain confirmed and not regressing
- before Phase 3 user Pack:
  - exact `expected mail/h` and `mail/day`
  - exact Gemini delta acceptance band
  - exact rollback anchors(runtime env / runtime image / source revert)
  - source-add storm stop condition

Operational reading:
- this v3 Pack is the scope sync artifact; it does not authorize any live phase by itself.

## 10. Tests

- **Phase 1**: read-only verify only
- **Phase 2**:
  - unit tests
  - integration tests
  - mail flow preservation
  - rollback rehearsal path written
- **Phase 3**:
  - source-add smoke
  - `24h` regression checks
  - mail volume verification
  - Gemini delta verification
  - candidate visibility verification
- **Phase 4**:
  - observe trend audit
  - stop-condition audit
  - rollback necessity review

## 10a. Post-Deploy Verify Plan (POLICY §3.5 7-point, Phase 3)

1. **image / revision**: deployed image SHA / revision matches intended Phase 3 target
2. **env / flag**: any source knob or related env state matches intended target, with no extra diff
3. **mail volume**: rolling `1h < 30`, `24h < 100`, storm pattern absent
4. **Gemini delta**: observed delta stays inside the exact band locked in the Phase 3 Pack
5. **silent skip**: `0` maintained
6. **Team Shiny From**: `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` maintained
7. **rollback target**: runtime rollback(image/revision or env) and source rollback(`git revert`) are both recorded before GO

## 10b. Production-Safe Regression Scope

- **allowed**
  - read-only checks
  - log / health / error trend
  - mail count
  - env / revision
  - Scheduler / job observation
  - sample candidate review
  - dry-run-equivalent checks
  - existing notification route preservation checks
- **forbidden**
  - bulk mail
  - unknown source addition
  - Gemini increase experiment outside the accepted Phase 3 window
  - publish criteria change
  - cleanup mutation
  - SEO/noindex/canonical/301 change
  - rollback-impossible operation
  - flag ON without user `OK`
  - mail-UNKNOWN experiment

## 11. Rollback (POLICY §3.6 / §16.4 3 dimensions)

- **Runtime env rollback**
  - use when a source-specific env knob exists
  - command shape: `gcloud run jobs/services update <name> --remove-env-vars=<flag>`
  - expected time: `~30 sec`
- **Runtime image / revision rollback**
  - Cloud Run job: `gcloud run jobs update <name> --image=<prev_image_sha>`
  - Cloud Run service: `gcloud run services update-traffic --to-revisions=<prev_rev>=100`
  - expected time: `~2-3 min`
- **Source rollback**
  - `git revert <bad_commit>`
  - revert only the Phase 3 source-add diff in `config/rss_sources.json`
  - Claude performs push after Codex prepares revert commit
- **Last known good**
  - `298-v4` deploy-complete commit family
  - `293/282` deploy-complete image SHA / revision family once fixed

Rule:
- placeholders are acceptable only because this Pack remains `HOLD`; exact rollback anchors must be closed in the dedicated Phase 3 Pack before user `OK`.

## 12. Stop Conditions

- rolling `1h sent > 30`
- rolling `24h sent > 100`
- `silent skip > 0`
- consecutive `errors > 0`
- `289` visible-route volume degrades unexpectedly
- Team Shiny From changes
- observed Gemini call delta exceeds the locked Phase 3 band
- publish / review / hold / skip route breaks
- candidate disappearance or silent merge is detected
- source-add-origin storm pattern is detected

## 13. User Reply

`OK` / `HOLD` / `REJECT`

Phase rule:
- user reply is one line only
- each live phase(Phase 1 / 2 / 3 / 4) must be presented as its own compact Pack before execution
- this v3 Pack is the parent scope-normalization artifact, not the final execution approval for any live phase
