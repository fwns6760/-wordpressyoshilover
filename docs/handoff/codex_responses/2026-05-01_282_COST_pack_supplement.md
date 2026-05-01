# 282-COST flag ON judgment Pack supplement

Date: 2026-05-01 JST  
Lane: Codex A round 9 (doc-only / read-only)  
Parent draft: `docs/handoff/codex_responses/2026-05-01_282_COST_pack_draft.md` (`1fd2755`)  
UNKNOWN resolution: `docs/handoff/codex_responses/2026-05-01_unknown_flags_resolution.md` (`ade62fb`)  
Purpose: fill the remaining 13-field Pack gaps for rollback, stop condition, mail-volume impact, 293-order preconditions, and final completeness only

This supplement does not replace the parent draft. Read it together with:

- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
- `docs/ops/POLICY.md`
- `docs/ops/OPS_BOARD.yaml`
- `docs/handoff/codex_responses/2026-05-01_unknown_flags_resolution.md`

Current recommendation remains `HOLD`.

## 1. rollback 3-tier fixed

| tier | action | exact command / action | expected time | owner | use when |
|---|---|---|---|---|---|
| 1 | env rollback | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_GEMINI_PREFLIGHT` | `~30 sec` | Claude autonomous hotfix boundary if an authenticated executor is available; otherwise user-confirmed executor | First stop condition hit; narrowest rollback for 282 itself |
| 2 | image rollback | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d` | `~2-3 min` | user-confirmed executor recommended | Tier 1 is insufficient, or fetcher behavior still regresses after flag removal |
| 3 | coordinated rollback with 293 path | 1. `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_GEMINI_PREFLIGHT` 2. `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION` | `~1-2 min` | Claude/user-confirmed executor | If `282` and `293` are both live and visibility symmetry must be restored immediately |

Notes:

- Tier 1 is the canonical first rollback because `282` is an env-only activation.
- Tier 2 is a safety fallback only. The locked safe baseline remains fetcher image family `:4be818d` / revision `yoshilover-fetcher-00175-c8c`.
- Tier 3 exists to preserve the `POLICY.md` §8 visibility contract. If fetcher preflight remains ON while `293` visible notification is OFF, silent preflight skip can reappear.
- Current live state is still `282 OFF` and `293 impl HOLD`, so Tier 3 is a future both-live rollback plan, not an immediate mutation.

## 2. stop conditions and immediate action

### 2.1 fixed stop-condition list

The following stop conditions align with `docs/ops/POLICY.md` §7 mail-storm rules and §8 silent-skip policy.

| stop condition | why it matters | immediate action |
|---|---|---|
| Gemini call delta `> +5%` | `282` is a cost-reduction gate; any increase is reverse-direction anomaly | Tier 1 rollback immediately |
| silent skip increase | `293` visible path failed, or preflight skip is no longer user-visible | Tier 1 rollback immediately; use Tier 3 if `293` is also live |
| candidate disappearance increase | preflight skip is changing user-visible candidate outcomes instead of only moving them to visible fallback/review/skip | Tier 1 rollback immediately |
| Team Shiny From / `289` / error notification path changes | `282` must not disturb existing mail identity or protected visible paths | Tier 1 rollback; move to Tier 3 if the both-live stack is active |
| cache-hit ratio swings sharply vs the locked observe baseline | `ade62fb` fixed `Cache impact = YES`; a large swing can break `229` attribution and hide a regression | Tier 1 rollback and re-measure before any re-ON |
| MAIL_BUDGET breach (`30/h` or `100/d`) | policy-defined P1 boundary | Tier 1 rollback immediately |

### 2.2 practical interpretation

- `Candidate disappearance risk = NO` from `ade62fb` remains true at the article-generation layer.
- The stop condition above is narrower: it watches for **user-visible outcome loss or route starvation**, not for total candidate deletion.
- If mail composition changes from `publish/review` toward `preflight_skip`, that alone is not a stop. It becomes a stop only when total visibility degrades, the shared cap starves higher-priority routes, or cost moves in the wrong direction.

## 3. mail volume impact: quantified estimate

### 3.1 baseline sources to lock

Use two baselines together, not one:

| baseline type | locked value | why it matters |
|---|---|---|
| 24h continuity baseline | `289-OBSERVE` stable reference: `sent=172`, `errors=0`, `silent skip=0`, Gmail sample reached, Team Shiny unchanged | This is the last full-day visible-route continuity proof already locked in docs |
| current post-rollback live slice | `2026-05-01T04:40:00Z` to `2026-05-01T06:15:33Z` (`95m33s`): publish-notice summaries `20` rows, `sent=7`, `errors=0`; result mix = `post_gen_validate=3`, `review=3`, `old_candidate=1`; fetcher `gemini_call_made=true = 4` | This is the latest low-volume live proxy after the rollback, and it shows the current per-run pressure before `282` is ON |

Interpretation:

- The `172/24h` number is the continuity reference, not the correct budget floor for a future `282` GO.
- The current slice is the better **directional** baseline for `282` because it reflects the present post-rollback state.

### 3.2 expected raw delta when `282` turns ON

Parent draft expectation remains:

- Gemini call reduction target: `-10%` to `-30%`

Applying that range to the current live proxy:

- current proxy actual Gemini calls: `4` in `95m33s`
- expected raw preflight skips in the same window: `0.4` to `1.2`
- hourly proxy: `+0.25` to `+0.76` raw preflight-skip opportunities per hour
- rough 24h proxy if the same traffic mix holds: `+6` to `+18` raw preflight-skip events per day

This is only a proxy, not the final 24h observe result. Exact 24h `gemini_call_skipped` counts remain a post-`293`, post-`282` measurement item.

### 3.3 emitted mail impact after `293` visible path exists

`293` changes the raw skip events into visible `【要review｜preflight_skip】` mail, but two guards keep that from behaving like a new unbounded mail class:

1. `293` runs **after** existing guarded / `289 post_gen_validate` review paths.
2. `293` shares the same review cap `10/run`, so `preflight_skip` competes for remaining slots instead of bypassing them.

Expected direction:

- `282 ON` alone pushes the system toward **fewer publish-ready candidates** and therefore fewer `publish/review` notices.
- `293` gives part of that back as visible `preflight_skip` notices.
- net effect should be **flat to slightly down**, not up, if substitution works correctly.

Practical estimate from the current proxy:

| metric | current proxy | expected 282+293 shift |
|---|---|---|
| visible mails per `95m33s` | `7` | raw composition shift of about `0.4-1.2` candidates from `publish/review` toward `preflight_skip` |
| `post_gen_validate` pressure | `3` visible mails in the same slice | `293` must not starve these because preflight sits behind `289` in the shared-cap order |
| raw preflight-skip emit opportunity | `0` now because `282 OFF` | `+0.4-1.2` per same-size slice; visible emitted count can be lower because of cap competition and 24h dedup |

### 3.4 budget reading

- Hourly burst risk from `282` itself looks low on the current slice. Adding `0.25-0.76/h` to a slice that currently emits `7` mails across `95m33s` does not approach `30/h`.
- Daily budget is the tighter risk. Because the last locked 24h continuity baseline is already high, `282` is only acceptable as a **composition shift**, not as a net-new mail generator.
- Therefore the Pack assumption should be:
  - `Mail volume impact = YES`
  - expected direction = `publish/review down`, `preflight_skip up`
  - acceptable net outcome = `flat to slight down`
  - unacceptable net outcome = total visible-mail increase large enough to worsen `MAIL_BUDGET`

## 4. 293 completion preconditions and order lock

### 4.1 canonical blockers

`docs/ops/OPS_BOARD.yaml` already fixes:

- `future_user_go.282-COST.blocked_by = 293-COST visible skip readiness`

That is the authoritative order lock for `282`.

### 4.2 current state

| condition | current state | judgment |
|---|---|---|
| `293-COST` implementation | design/final-review only, not completed live | **NO** |
| `293` 24h stable observe | impossible until `293` is implemented and deployed | **NO** |
| `282` cost-reduction evidence after a live preflight window | not measurable while `ENABLE_GEMINI_PREFLIGHT` is absent | **NO** |
| current `282` recommendation | `HOLD` in parent draft | **YES** |

### 4.3 resulting rule

`282` must stay in this order:

1. `293` complete
2. `293` stable for 24h
3. `282` Pack rechecked with cost / mail evidence
4. user GO for `ENABLE_GEMINI_PREFLIGHT=1`

That order is stricter than the parent draft alone because it is now consistent across:

- `docs/ops/OPS_BOARD.yaml`
- `docs/ops/POLICY.md` §7 / §8
- `docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md`

## 5. 13-field completeness re-evaluation

This section evaluates the `282` Pack as:

- parent draft `1fd2755`
- UNKNOWN resolution `ade62fb`
- this supplement

against `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`.

| # | required field | status | evidence path |
|---|---|---|---|
| 1 | Conclusion | YES | parent draft §1 |
| 2 | Scope | YES | parent draft §5 |
| 3 | Non-Scope | YES | parent draft §5 |
| 4 | Current Evidence | YES | parent draft §2-4 + `ade62fb` + this supplement §3-4 |
| 5 | User-Visible Impact | YES | parent draft §5 + this supplement §2.2 / §3.3 |
| 6 | Mail Volume Impact | YES | this supplement §3 |
| 7 | Gemini / Cost Impact | YES | parent draft §5 + `ade62fb` + this supplement §2.1 |
| 8 | Silent Skip Impact | YES | parent draft §4-5 + this supplement §2 |
| 9 | Preconditions | YES | parent draft §4 + this supplement §4 |
| 10 | Tests | YES | parent draft §2-4 + `doc/active/282-COST-gemini-preflight-article-gate.md` §6 / §9 |
| 11 | Rollback | YES | this supplement §1 |
| 12 | Stop Conditions | YES | this supplement §2 |
| 13 | User Reply | YES | parent draft §5 |

### 13-field result

- Pack completeness with supplement: `13/13`
- Pack-field residual `UNKNOWN`: `0`

Resolved values from `ade62fb` that are now fixed:

- `Candidate disappearance risk = NO`
- `Cache impact = YES`

Still not a Pack-field unknown:

- exact post-enable `Gemini call delta`
- exact post-enable `cache-hit delta`

Those remain **post-`293`, post-`282` observe metrics**, not blockers to Pack completeness.

## 6. Claude handoff note

When Claude compresses this for the user, the key additions from this supplement are:

- rollback is now explicitly `Tier 1 env -> Tier 2 image -> Tier 3 coordinated 293 rollback`
- stop conditions now include the missing reverse-direction anomaly (`Gemini +5%`), `MAIL_BUDGET`, `Team Shiny / 289 / error-path` protection, and `cache impact = YES`
- mail impact is no longer just `+N/d`; it is a **composition-shift forecast**
  - rough raw `preflight_skip` opportunity = `+6 to +18/day` from the current proxy
  - acceptable net effect = `flat to slight down`
  - unacceptable effect = total visible-mail increase or route starvation
- `282` stays blocked behind `293 complete + 24h stable`
- the Pack is now `13/13 complete` even though the correct recommendation remains `HOLD`
