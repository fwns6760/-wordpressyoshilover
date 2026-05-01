# 288-INGEST source add READY pack

Date: 2026-05-01 JST  
Mode: Codex Lane A round 16 / doc-only / read-only  
Decision owner: user  
Execution owner: Claude -> Codex impl  
Risk class: `SOURCE_ADD + COST_INCREASE`

## Conclusion

- **Today**: `HOLD`
- **Reason**: 5 preconditions are not all `YES` yet. Source addition must stay blocked until `289 / 290 / 295 / 291 / 282` chain is complete.
- **GO recommendation rule**: recommend `GO` only after all 5 preconditions are `YES`.

## Scope

- Add new RSS endpoints to `config/rss_sources.json`
  - `NNN web`
  - `スポニチ web`
  - `サンスポ web`
- Rebuild fetcher image
- Update `yoshilover-fetcher` service
- Observe `24h` after deploy:
  - article count
  - mail emit
  - Gemini call delta

## Non-Scope

- `scanner`
- `persistence`
- `ledger`
- `publish-notice`
- `guarded-publish`
- `Scheduler`
- `SEO`
- `Team Shiny`
- `WP` write policy changes
- new `src/` logic or runtime-flag expansion outside source add

## Current Evidence

- Pack bundle is complete as a decision artifact: draft `26ede3a` + supplement `5f8b966` + consistency review v2 `0ae5505` + unknown resolution `ade62fb`
- Current source set is `13` entries; `NNN web / スポニチ web / サンスポ web` are not in `config/rss_sources.json`
- `OPS_BOARD future_user_go.288-INGEST` blocked-by items are now documented, but operational GO is still blocked by the 5 preconditions below
- **Current precondition state today**: `0/5 YES`, `5/5 NO`

## Implementation Order

1. Confirm source candidate list: `NNN web / スポニチ web / サンスポ web`
2. Edit `config/rss_sources.json`
3. Rebuild image and update `yoshilover-fetcher`
4. Observe `24h` for article count, mail emit, and Gemini call delta

## 18-field matrix

| field | value | note |
|---|---|---|
| 1. Conclusion | `HOLD` | 5 preconditions all `YES` are required before `GO` |
| 2. Scope fixed | `YES` | source endpoints add + image rebuild + service update only |
| 3. Non-Scope fixed | `YES` | scanner/persistence/ledger/publish-notice/guarded-publish/Scheduler/SEO/Team Shiny stay untouched |
| 4. Implementation order fixed | `YES` | 4-step order is locked |
| 5. Current evidence sufficient for HOLD | `YES` | pack bundle complete; preconditions still `NO` |
| 6. User-visible impact exists | `YES` | publish/review/hold/skip opportunities may increase |
| 7. Mail volume impact | `YES` | quantified estimate is required; `UNKNOWN` would force `HOLD` |
| 8. Gemini call increase | `YES` | new source articles multiply existing call sites |
| 9. Token increase | `YES` | follows call increase |
| 10. Candidate disappearance risk | `NO` | forbidden by contract; any detection is an immediate stop |
| 11. Cache impact | `YES` | new `source_url_hash` buckets create cold misses; exact delta is a 24h observe item |
| 12. Silent skip allowed | `NO` | `POLICY §8` forbids internal-log-only outcomes |
| 13. Test plan fixed | `YES` | precondition/dedup/delta/visibility checks are defined |
| 14. Rollback plan fixed | `YES` | Phase A/B/C rollback is defined |
| 15. Stop conditions fixed | `YES` | cost/visibility/mail/cache path stop set is defined |
| 16. Preconditions all YES today | `NO` | today is `0/5 YES` |
| 17. GO recommended today | `NO` | current recommendation remains `HOLD` |
| 18. User reply format fixed | `YES` | one-line reply is `GO` / `HOLD` / `REJECT` |

## Impact Estimates

- **Mail**: `+3/day` typical, `+6/day` conservative upper; still inside `MAIL_BUDGET 30/h, 100/d` if sources are activated one at a time with `24h` observe
- **Gemini**: modeled raw increase is about `+5% to +10%`; precondition 5 still requires observed `24h` delta `< +20%`
- **Cache**: impact is `YES`; exact cache-hit delta stays unknown until the post-add `24h` compare window

## Preconditions (all 5 must be YES before GO)

| # | precondition | today | GO threshold |
|---|---|---|---|
| 1 | `289` stable for `24h` | `NO` | `silent skip = 0` stays stable for `24h` |
| 2 | `290-QA` deploy + `24h` stable | `NO` | weak-title rescue live and stable for `24h` |
| 3 | `295-QA` implementation complete | `NO` | subtype misclassify fix implemented, deployed, and observed |
| 4 | candidate visibility contract | `NO` | new and existing sources both end in `publish / review / hold / skip` visibility |
| 5 | cost suppression chain | `NO` | `282-COST` flag ON after `293`, then `24h` Gemini delta `< +20%` |

## Test Plan

- Precondition test: confirm all 5 preconditions are `YES`
- Measure per-article fetch effect and Gemini call delta for each newly added source
- Verify dedup behavior with `source_url_hash` and normalized title collision checks
- Verify candidate-visibility contract: existing-source publish opportunities do not disappear
- Compare `MAIL_BUDGET 30/h, 100/d` against the `24h` post-add window

## Rollback Plan

- **Phase A**: revert source-add commit with `git revert <commit>`, then rebuild image and update service
- **Phase B**: rollback `yoshilover-fetcher` to the exact pre-288 image
  - safe baseline family today: `:4be818d`
  - exact pre-288 digest must be locked immediately before GO
- **Phase C**: archive and quarantine new-source artifacts by `source_url` or `source_url_hash`
  - cache buckets
  - ledger samples
  - mail samples

## Stop Conditions

- Gemini call delta `> +30%`
- candidate disappearance detected
- silent skip increases
- `Team Shiny` / `289` / error-notification path changes
- cache-hit ratio shifts sharply from baseline
- `MAIL_BUDGET 30/h` or `100/d` is breached
- publish count shifts by `±50%` or more without a clear source-attribution explanation

## User Reply

`GO` / `HOLD` / `REJECT`

Claude note: present `GO` only after all 5 preconditions turn `YES`. Until then, this pack is user-ready in format but the recommendation stays `HOLD`.
