# 290-QA deploy judgment Pack supplement

Date: 2026-05-01 JST  
Lane: Codex A round 8 (doc-only / read-only)  
Parent draft: `docs/handoff/codex_responses/2026-05-01_290_QA_pack_draft.md` (`65c09c1`)  
Purpose: fill the remaining 13-field Pack gaps for rollback, stop condition, mail-volume impact, silent-skip visibility, and `2026-05-01 17:00 JST` `production_health_observe` baseline only

This supplement does not replace the parent draft. Read it together with the draft and the current policy set:

- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
- `docs/ops/POLICY.md`
- `docs/ops/OPS_BOARD.yaml`

Current recommendation remains `HOLD`. This supplement only makes the Pack complete and more explicit.

## 1. rollback 3-tier fixed

| tier | action | exact command / action | expected time | owner | use when |
|---|---|---|---|---|---|
| 1 | env rollback | `gcloud run services update yoshilover-fetcher --remove-env-vars=ENABLE_WEAK_TITLE_RESCUE` | `~30 sec` | Claude autonomous hotfix boundary if an authenticated executor is available; otherwise user-confirmed executor | First stop condition hit, and the fastest way to return 290 to live-inert |
| 2 | image rollback | `gcloud run services update yoshilover-fetcher --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d` | `~2-3 min` | user-confirmed executor recommended | Tier 1 is insufficient, or runtime behavior still degrades after flag removal |
| 3 | commit revert | `git revert c14e269` + rebuild + redeploy the new rollback image | image rebuild/deploy dependent | Codex prepares; authenticated executor runs live steps | Repo-level rollback only if code itself must be removed, not just disabled |

Notes:

- Tier 1 is the canonical first rollback because `c14e269` is already in `master` but is still **live-inert while `ENABLE_WEAK_TITLE_RESCUE` is absent**.
- Tier 2 returns the fetcher to the same safe image family already used as the post-289 / pre-298 fetcher baseline: `yoshilover-fetcher:4be818d`.
- Tier 3 is intentionally the slowest path. It is not required for first response because the feature is flag-gated.
- For authenticated shell use, the executor may add the usual `--project=baseballsite --region=asia-northeast1` flags around Tier 1 and Tier 2.

## 2. stop conditions and immediate action

### 2.1 stop condition list

The following are fixed stop conditions for `290-QA` after deploy + flag ON. They align with `docs/ops/POLICY.md` §7 and §8.

| stop condition | why it matters | immediate action |
|---|---|---|
| silent skip increase | `290` must not reintroduce invisible candidate loss; every candidate still needs publish/review/hold/skip visibility | Tier 1 rollback immediately |
| Gemini call delta `> 0` | `290` is regex/metadata-only; any extra Gemini activity is out-of-scope behavior | Tier 1 rollback immediately |
| Team Shiny From changes | mail sender invariants are no-touch by policy | Tier 1 rollback immediately |
| errors `> 0` | fetcher/runtime regression is a hard stop even if rescue candidates appear | Tier 1; move to Tier 2 if errors persist through the next trigger |
| mail rolling 1h `> 30` | `MAIL_BUDGET` breach is P1 | Tier 1 rollback immediately |
| mail since `2026-05-01 09:00 JST` cumulative `> 100` | daily budget breach is P1 | Tier 1 rollback immediately |
| real review / `289` / X-candidate visible path decreases | `290` must not starve existing visible routes while rescuing titles | Tier 1 rollback and compare pre/post logs |
| publish drops sharply | rescue logic must not trade publish volume for new hidden losses | Tier 1 rollback and compare pre/post logs |

### 2.2 evidence path for each stop condition

| metric | baseline compare source | stop detection source |
|---|---|---|
| silent skip | `docs/handoff/session_logs/2026-05-01_ops_reset.md` §8 rules + `289` 24h baseline | same `production_health_observe` query family; any candidate that vanishes without a visible route is P0 |
| Gemini delta | `docs/handoff/codex_responses/2026-05-01_298_Phase3_stability_evidence_pre.md` Q5/Q6 | same Q5/Q6 after 290 live; delta must stay `0` attributable to 290 |
| Team Shiny From | `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` baseline | `gcloud run jobs/services describe` mail env check |
| errors | partial-slice baseline `errors=0`; `14:15 JST` observe `errors=0` | fetcher / publish-notice summary rows and Cloud Run error lines |
| rolling 1h mail | `14:15 JST` baseline `5-6/h`; partial-slice extrapolation `~9.9/h` | `publish-notice` summary/result rows |
| since 09:00 cumulative | `13:24 JST 125` and `13:35 JST ~142/h` are the known breach patterns to avoid repeating | daily cumulative mail count in the same incident-observe workbook |
| visible-path decrease | `14:15 JST` observe showed `【要review｜post_gen_validate】1 / 【要確認】3 / 【要確認・X見送り】1 / 【巨人】1` | same path mix after 290 live; a drop without an alternate visible terminal route is a stop |

### 2.3 silent-skip visibility contract

This closes Required Field 8 in the 13-field template.

| candidate outcome after 290 | required visibility |
|---|---|
| rescue succeeds and article becomes publishable | existing publish path stays visible |
| rescue succeeds but article still needs review | existing review path stays visible |
| rescue fails and existing skip reason remains valid | existing `289` visible skip/review path stays visible |
| hold / X-skip outcome | existing hold or X-candidate path stays visible |

`290` is not allowed to create an internal-log-only outcome. If rescue fails, the candidate must remain visible through the same already-user-visible route, not disappear.

## 3. mail volume impact: quantified estimate

### 3.1 rescue candidate set

The known first-wave rescue pool remains the same `A/B` group of 7:

1. 泉口友汰
2. 山崎伊織 + 西舘勇陽
3. 阿部監督 → 竹丸
4. 平山功太 `左手おとり`
5. 竹丸和幸 + 内海投手コーチ
6. 平山功太 `スイム`
7. 平山功太 + 片岡氏

The parent ticket already fixes the scope as `7` known candidate families plus future candidates only when they match the same narrow regex/metadata patterns.

### 3.2 incremental mail model

Assumptions:

- `290` adds **no new mail class**, **no new scanner loop**, and **no new Scheduler trigger**.
- A rescued candidate adds at most **one newly visible terminal mail event in 24h** because the existing visibility path still dedups by terminal outcome family.
- The relevant budget baseline for a future `290` GO is the **post-rollback stable band on 2026-05-01**, not the earlier storm window.

Observed baseline inputs:

- `2026-05-01 14:00:00-14:18:12 JST` partial stable slice from `aa6a8eb`: `sent=3`, `suppressed=0`, `errors=0`
- Extrapolated from that slice: `3 / 18.2 min = ~9.9 mails/hour`
- Day-rate inference from that same slice: `~79 mails/day`
- `2026-05-01 14:15 JST` post-rollback observe: rolling `1h = 5-6 mails`

Projected 290 increment:

- known rescue pool upper bound: `+7 mails/day`
- projected total day volume: `~79 + 7 = ~86/day`
- projected same-hour burst upper bound using the higher slice-rate baseline: `~9.9/h + 7 = ~16.9/h`
- projected same-hour burst upper bound using the direct `14:15 JST` rolling baseline: `5-6/h + 7 = 12-13/h`

MAIL_BUDGET judgment:

- hourly budget `30/h`: projected `12-16.9/h`, so **within budget**
- daily budget `100/d`: projected `~86/d`, so **within budget**
- classification: `Mail volume impact = YES (minor increase), not UNKNOWN`

Important interpretation note:

- `289-OBSERVE` historical evidence `24h sent=172 errors=0 silent=0` remains valid as a **path-alive / visibility continuity** record.
- It is **not** the right budget baseline for a `290` GO after the `2026-05-01 13:55 JST` Phase3 rollback, because the relevant decision point for `290` is the stabilized post-rollback band on `2026-05-01`.

## 4. baseline to carry into `2026-05-01 17:00 JST production_health_observe`

`aa6a8eb` is an `18m12s` partial slice, not a full 24h record. For the `17:00 JST` observe gate, use it together with the existing 24h continuity baseline.

### 4.1 partial stable slice baseline from `aa6a8eb`

Source: `docs/handoff/codex_responses/2026-05-01_298_Phase3_stability_evidence_pre.md`

| metric | locked value |
|---|---|
| capture window | `2026-05-01 14:00:00-14:18:12 JST` |
| publish-notice sent | `3` |
| suppressed | `0` |
| errors | `0` |
| `sent=10` burst runs | `0` |
| `【要確認(古い候補)】` | `0` |
| `【要review｜post_gen_validate】` | `1` |
| yellow `【要確認】` | `2` |
| `【要確認・X見送り】` | `0` |
| silent text hit | `0` |
| actual `gemini_call_made:true` | `1` |
| Team Shiny From | `y.sebata@shiny-lab.org` |
| fetcher image | `yoshilover-fetcher:4be818d` |
| fetcher revision | `yoshilover-fetcher-00175-c8c` |

### 4.2 same-day post-rollback stability marker

Source: `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md`

| timestamp | locked value |
|---|---|
| `2026-05-01 14:15 JST` | `16 triggers` aggregate `sent=8`, rolling `1h=5-6`, `【要確認(古い候補)】=0`, normal visible paths all present, `errors=0`, `silent skip=0`, Team Shiny unchanged |

### 4.3 24h continuity baseline

Source: `docs/handoff/session_logs/2026-04-30_next_action_queue.md`

| metric | locked value |
|---|---|
| `289-OBSERVE` 24h sent | `172` |
| errors | `0` |
| silent skip | `0` |
| Gmail sample | `10+ thread` sample reached |
| Team Shiny From | unchanged |

Use of the 24h baseline:

- This proves that the visibility routes were alive over a longer window.
- It should not be used as the forecast budget floor for `290`.
- For `290` stop-condition comparison, prefer the post-rollback stable band in `4.1` and `4.2`.

## 5. 13-field completeness re-evaluation

This section evaluates the Pack as **parent draft + this supplement** against `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`.

| # | required field | status | evidence path |
|---|---|---|---|
| 1 | Conclusion | YES | parent draft §4 |
| 2 | Scope | YES | parent draft §4 |
| 3 | Non-Scope | YES | parent draft §4 |
| 4 | Current Evidence | YES | parent draft §1-3 + this supplement §4 |
| 5 | User-Visible Impact | YES | parent draft §4 + this supplement §2.3 |
| 6 | Mail Volume Impact | YES | this supplement §3 |
| 7 | Gemini / Cost Impact | YES | parent draft §4 + this supplement §2.1-2.2 |
| 8 | Silent Skip Impact | YES | this supplement §2.1-2.3 |
| 9 | Preconditions | YES | parent draft §3-4 |
| 10 | Tests | YES | parent draft §2-3 + `doc/active/290-QA-weak-title-rescue-backfill.md` §4 |
| 11 | Rollback | YES | this supplement §1 |
| 12 | Stop Conditions | YES | this supplement §2 |
| 13 | User Reply | YES | parent draft §4 |

Result:

- Pack completeness with supplement: `13/13`
- UNKNOWN residual fields: `0`
- Remaining pending items are **operational preconditions**, not Pack-field unknowns:
  - `2026-05-01 17:00 JST production_health_observe` must pass
  - `299-QA` must settle at that checkpoint
  - `298-Phase3` still needs its post-regression stability window

## 6. Claude handoff note

When Claude compresses this for the user, the key additions from this supplement are:

- rollback is explicitly **Tier 1 env / Tier 2 image / Tier 3 revert**
- mail impact is **small but non-zero**, with a quantified forecast still inside `30/h` and `100/d`
- stop conditions are explicit and tied to the same baseline/evidence set used by `production_health_observe`
- the Pack is now **13/13 complete**, even though the correct recommendation remains `HOLD`
