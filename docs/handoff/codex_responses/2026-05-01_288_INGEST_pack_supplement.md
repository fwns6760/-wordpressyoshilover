# 288-INGEST source-add judgment Pack supplement

Date: 2026-05-01 JST  
Lane: Codex B round 8 (doc-only / read-only)  
Parent draft: `docs/handoff/codex_responses/2026-05-01_288_INGEST_pack_draft.md` (`26ede3a`)  
UNKNOWN resolution: `docs/handoff/codex_responses/2026-05-01_unknown_flags_resolution.md` (`ade62fb`)  
Purpose: fill the remaining 13-field Pack gaps for rollback, stop condition, mail-volume impact, five-precondition order lock, candidate-disappearance contract detail, and final completeness only

This supplement does not replace the parent draft. Read it together with:

- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
- `docs/ops/POLICY.md`
- `docs/ops/OPS_BOARD.yaml`
- `doc/active/288-INGEST-source-coverage-expansion.md`
- `doc/active/289-OBSERVE-post-gen-validate-mail-notification.md`
- `doc/active/291-OBSERVE-candidate-terminal-outcome-contract.md`
- `doc/active/295-QA-subtype-evaluator-misclassify-fix.md`
- `doc/active/282-COST-gemini-preflight-article-gate.md`

Current recommendation remains `HOLD`.

## 1. rollback 3-tier fixed

| tier | action | exact command / action | expected time | owner | use when |
|---|---|---|---|---|---|
| 1 | config revert | `git revert <288-source-add-commit>` and remove only the newly added endpoints from `config/rss_sources.json` | repo revert `~1-2 min`, rebuild/deploy follows normal fetcher path | Codex prepares revert commit, authenticated executor deploys | First stop condition hit and the problem is clearly tied to the newly added source list |
| 2 | image rollback | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --image=<pre-288 fetcher image digest/SHA>` | `~2-3 min` | user-confirmed authenticated executor recommended | Tier 1 is insufficient, or runtime behavior still degrades after the config revert; example safe family today is `yoshilover-fetcher:4be818d`, but the exact pre-288 digest/SHA must be locked immediately before GO |
| 3 | state cleanup / quarantine | Archive the 288 window artifacts first, then quarantine only rows/objects attributable to the added domains (`news.ntv.co.jp` / `nnn.co.jp`, `sponichi.co.jp`, `sanspo.com`) using `source_url` or `source_url_hash`; include `guarded_publish_history.jsonl`, `publish_notice_history.json`, `publish_notice_queue.jsonl`, and any new-source cache buckets before any delete | anomaly-only | Claude directs; authenticated executor performs any live cleanup | Use only when Tier 1/2 are not enough because dedup/cursor/cache state itself is contaminated |

Notes:

- Tier 1 is the canonical first rollback because 288 is a source-list change first, not a logic rewrite.
- Tier 2 target must be the exact fetcher image running immediately before 288 GO. `:4be818d` is a valid example baseline family today, but 288 is sequenced after 290/295/282 evidence work, so the real pre-288 image may be newer.
- Tier 3 is not a normal rollback step. It exists only for proven state pollution such as cache poisoning, title-collision mismerge, or cursor contamination tied to the added domains.

## 2. stop conditions and immediate action

### 2.1 fixed stop-condition list

The following stop conditions align with `docs/ops/POLICY.md` §7 and §8.

| stop condition | why it matters | immediate action |
|---|---|---|
| Gemini call delta `> +30%` in the 24h compare window | 288 is explicitly `SOURCE_ADD+COST_INCREASE`; this exceeds the allowed drift envelope from the parent Pack | Tier 1 rollback immediately; move to Tier 2 if the next run still shows elevated behavior |
| candidate disappearance increase | new-source dedup or merge behavior must never make an existing visible candidate vanish | Tier 1 rollback immediately; use Tier 3 if state cleanup is needed to restore visibility |
| silent skip increase | `POLICY.md` §8 forbids internal-log-only outcomes | Tier 1 rollback immediately |
| Team Shiny From / `289` / error notification path changes | 288 must not disturb protected existing mail identity or protected visible routes | Tier 1 rollback; move to Tier 2 if the route stays degraded |
| cache-hit ratio swings sharply vs the locked `229/282` baseline | 288 introduces new `source_url_hash` buckets, but a sharp drop implies unexpected cold-miss or duplicate behavior | Tier 1 rollback and compare before/after cache metrics |
| `MAIL_BUDGET` breach (`>30/h` or `>100/d`) | policy-defined P1 boundary | Tier 1 rollback immediately |
| publish drops sharply | source add must not trade coverage for fewer visible publish opportunities | Tier 1 rollback immediately |
| publish spikes sharply beyond the modeled `+3 to +6/day` band | likely duplicate/admission regression rather than legitimate new coverage | Tier 1 rollback and inspect source-family attribution before any re-ON |

### 2.2 practical interpretation

- `candidate disappearance` here is narrower than “fewer total candidates.” It means a candidate that was previously visible through publish/review/hold/skip is now absent or silently merged away after the source add.
- `publish increase` by itself is not a stop. It becomes a stop when the rise is materially above the modeled envelope and cannot be explained by clearly attributable new-source wins.
- `cache-hit ratio` is expected to move somewhat because 288 adds fresh URL families. The stop condition is not “any movement,” but a sharp swing that breaks attribution or indicates collision/duplication anomalies.

## 3. mail volume impact: quantified estimate

### 3.1 locked planning baseline

Use these two references together:

| baseline | locked value | why it matters |
|---|---|---|
| current source-set audit | current config is `13` sources, and the 2026-04-30 audit concluded the true coverage gap in that sample was only `2` missed items, both tied to `報知 RSS error + NNN 未登録` | proves 288 is a narrow incremental source-add ticket, not the main cause of candidate loss |
| current post-rollback mail mix proxy | `docs/handoff/codex_responses/2026-05-01_282_COST_pack_supplement.md` locked a `95m33s` live slice with visible mails `7`, composition `post_gen_validate=3`, `review=3`, `old_candidate=1` | gives the most recent review-heavy visible-route mix for per-article mail modeling |
| future-pack planning envelope | `docs/handoff/codex_responses/2026-05-01_290_QA_pack_supplement.md` already uses a post-rollback planning envelope of about `~86 mails/day` after 290 | provides the envelope 288 must fit inside once 290 and the other preconditions are satisfied |

### 3.2 expected incremental source articles per day

This is an incremental estimate, not total feed volume. It counts only new giant-related articles likely to survive existing X-feed overlap and current source coverage.

| source candidate | current overlap state | expected incremental unique candidates / day | rationale |
|---|---|---|---|
| NNN web | no current web source in config | `+1 to +2/day` | 288 audit identified NNN as the only clearly missing web family; the missed `堀田賢慎 / 東京ドーム` item demonstrates real incremental value |
| スポニチ web | `@SponichiYakyu` X feed already present | `+1/day` typical, `0-2/day` upper | most sport news is already partially covered through the X feed, so web RSS is mainly an overlap-plus-gap filler |
| サンスポ web | `@Sanspo_Giants` X feed already present | `+1/day` typical, `0-2/day` upper | same logic as スポニチ web; incremental value comes from website-only or differently timed headlines |
| all 3 together | mixed | `+3/day` typical, `+6/day` conservative upper | matches the “coverage gap is real but minority” conclusion from the 2026-04-30 audit |

### 3.3 per-article review mail model

The mail model must follow `POLICY.md` §8 and the 291 terminal-outcome contract:

1. one article may create at most one new visible terminal outcome per 24h family
2. internal-log-only outcomes are forbidden
3. 24h dedup and the shared cap remain active

Therefore the conservative budgeting model is:

- visible terminal mails per new article: `1.0` worst-case upper bound
- review-family mail share per visible article: `0.86` proxy
  - basis: current post-rollback live proxy has `6` review-family mails (`post_gen_validate=3` + `review=3`) out of `7` visible mails

Projected increment:

| scenario | added articles / day | visible mails / day | review-family mails / day |
|---|---|---|---|
| typical | `+3/day` | about `+3/day` | about `+2.6/day` |
| conservative upper | `+6/day` | about `+6/day` | about `+5.1/day` |

Important interpretation:

- These are conservative planning numbers. If 290 rescue and 295 subtype repair are working as intended before 288, some of these candidates should resolve to publish instead of review, so real review-mail increment should be equal or lower.
- The model assumes source-by-source activation, not a blind multi-source batch without 24h observation.

### 3.4 MAIL_BUDGET read

Hourly:

- current stable band used in the 290 supplement is `rolling 1h = 5-6 mails`
- 288 average increment at `+3 to +6/day` is only `+0.1 to +0.25/h`
- even if all upper-band new candidates land inside the same hour, burst addition is only about `+6/h`
- resulting burst band is therefore about `11-12/h`, still below `30/h`

Daily:

- the locked 290 planning envelope is `~86/day`
- 288 typical increment `+3/day` yields about `~89/day`
- 288 conservative upper increment `+6/day` yields about `~92/day`
- this stays below `MAIL_BUDGET 100/d`

Judgment:

- `Mail volume impact = YES`
- quantified estimate: `+3/day` typical, `+6/day` conservative upper
- budget verdict: within `30/h` and `100/d` **if and only if** the post-290 planning envelope remains valid and 288 is activated one source at a time with 24h observe gates

## 4. five-precondition order lock

### 4.1 canonical blockers vs operational preconditions

`docs/ops/OPS_BOARD.yaml` fixes the current `future_user_go.288-INGEST.blocked_by` set as:

- `candidate visibility contract`
- `mail impact estimate`
- `Gemini cost estimate`

This supplement closes those three Pack-level blockers at the document/evidence level:

- candidate visibility contract: §5
- mail impact estimate: §3
- Gemini cost estimate: parent draft §2.3 / §5 plus §4.3 below

That does **not** mean 288 is ready. The five operational preconditions remain the real order lock.

### 4.2 fixed five-precondition table

| # | precondition | current state | why not yet YES | evidence path to close |
|---|---|---|---|---|
| 1 | `289` 24h stable | **NO** | 289 is `REVIEW_NEEDED`; 24h stable visible-route proof is not yet locked as done | deploy + 24h observe showing `silent skip=0`, Team Shiny unchanged, protected paths alive |
| 2 | `290` deploy + 24h stable | **NO** | 290 is still `FUTURE_USER_GO`; deploy has not happened | deploy evidence + 24h observe with rescue candidates visible and Gemini delta `0` |
| 3 | `295` implementation complete | **NO** | 295 remains `DESIGN_DRAFTED + HOLD` | implementation, tests, deploy, and 24h observe for live-update misclassify rescue |
| 4 | candidate visibility contract (`291`) | **NO** | 291 is still design-only; all candidate families are not yet proven to end in publish/review/hold/skip visibility | 291 complete or equivalent evidence that new-source candidates and existing-source candidates both reach visible terminal outcomes |
| 5 | cost suppression chain closed (`282` flag ON after `293`, then 24h Gemini delta observe) | **NO** | 282 is still OFF and blocked behind 293; exact post-enable delta is future observe-only evidence | 293 complete + 24h stable -> 282 flag ON -> 24h compare showing Gemini delta `< +20%` |

### 4.3 Gemini cost estimate tied to precondition 5

The parent draft already fixed the control limits:

- precondition-to-pass threshold: 24h Gemini delta `< +20%`
- stop threshold after GO: 24h Gemini delta `> +30%`

Use the current live proxy from the 282 supplement to budget the 288 increment:

- current actual Gemini calls in the locked live proxy: `4` calls / `95m33s`
- rough day-rate proxy: about `60 calls/day`
- 288 incremental article estimate: `+3 to +6/day`
- raw call delta before any 282 suppression: about `+5%` to `+10%`

Interpretation:

- 288 is structurally a cost-increase ticket, so `Gemini / Cost impact = YES`
- the modeled increase still fits inside the parent Pack’s `< +20%` pass threshold
- the precondition remains `NO` because 282/293 are not yet live and the exact observed delta does not exist yet

## 5. candidate disappearance contract detail

### 5.1 user-visible contract

288 is allowed only if adding a source can do one of the following:

- increase visible publish opportunities
- increase visible review / hold / skip opportunities
- leave existing visible opportunity count unchanged

288 is forbidden if adding a source can do this:

- make an existing source candidate disappear
- convert a visible candidate into an internal-log-only outcome
- merge a source-distinct candidate away without leaving a visible terminal trace

### 5.2 dedup rules that must hold

| mechanism | allowed use | forbidden use |
|---|---|---|
| `source_url_hash` | exact same URL dedup only | cross-domain article collapse just because headlines are similar |
| title hash / normalized title collision | observability and explicit merge review only | silent drop of the losing candidate |
| shared terminal-outcome dedup | suppress duplicate notifications within the same 24h family | suppress the only visible outcome for a candidate |

### 5.3 evidence already locked pre-add

- `docs/handoff/codex_responses/2026-05-01_unknown_flags_resolution.md` fixed `288 Cache impact = YES` and `collision sub-judgment = NO`
- same note also records that pre-add `gcloud logging read` returned:
  - `title_collision_detected = 0 rows`
  - `same_fire_distinct_source_detected = 0 rows`
- current cache key is `source_url_hash + content_hash + prompt_template_id`, so accidental title-only cache collision is not the primary risk

### 5.4 operational rule after GO

For the first 24h after each source add:

1. compare existing-source visible outcomes before/after
2. compare new-source visible outcomes by terminal family
3. if an article from a pre-existing source loses visibility without a corresponding visible terminal outcome, stop immediately
4. if a new-source article merges into an existing candidate, the merge must still leave a durable, user-visible reason trail

This is the exact meaning of “WP 側 publish 機会増加方向のみ”:

- 288 may add opportunities
- 288 may expose additional review/skip work
- 288 may not reduce the already-visible opportunity surface

## 6. 13-field completeness re-evaluation

This section evaluates the 288 Pack as:

- parent draft `26ede3a`
- UNKNOWN resolution `ade62fb`
- this supplement

against `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`.

| # | required field | status | evidence path |
|---|---|---|---|
| 1 | Conclusion | **YES** | parent draft §1 / §5 |
| 2 | Scope | **YES** | parent draft §2 / §5 |
| 3 | Non-Scope | **YES** | parent draft §5 |
| 4 | Current Evidence | **YES** | parent draft §1-4 + `doc/active/288-INGEST-source-coverage-expansion.md` + this supplement §3-5 |
| 5 | User-Visible Impact | **YES** | parent draft §4-5 + this supplement §5 |
| 6 | Mail Volume Impact | **YES** | this supplement §3 |
| 7 | Gemini / Cost Impact | **YES** | parent draft §2.3 / §5 + this supplement §4.3 |
| 8 | Silent Skip Impact | **YES** | parent draft §4 + this supplement §2 / §5 |
| 9 | Preconditions | **YES** | parent draft §3 + this supplement §4 |
| 10 | Tests | **YES** | `doc/active/288-INGEST-source-coverage-expansion.md` §5 + parent draft §5 |
| 11 | Rollback | **YES** | this supplement §1 |
| 12 | Stop Conditions | **YES** | this supplement §2 |
| 13 | User Reply | **YES** | parent draft §5 |

### 13-field result

- Pack completeness with supplement: `13/13`
- Pack-field residual `UNKNOWN`: `0`

Still future observe metrics, but not Pack-field unknowns:

- exact post-add cache-hit delta
- exact post-add Gemini call delta
- exact per-source title-collision rate after live source add

Those remain 24h observe items after GO, not blockers to Pack completeness.

## 7. Claude handoff note

When Claude compresses this for the user, the key additions from this supplement are:

- rollback is explicitly `Tier 1 config revert -> Tier 2 image rollback -> Tier 3 new-source state quarantine`
- stop conditions now include the full `POLICY §7 / §8` set plus the 288-specific `publish too low / too high` guard
- mail impact is now quantified:
  - `NNN +1 to +2/day`
  - `スポニチ web +1/day typical`
  - `サンスポ web +1/day typical`
  - total `+3/day` typical, `+6/day` conservative upper
  - review-family increment about `+2.6/day` typical, `+5.1/day` upper
- cost impact is now quantified against the current live proxy:
  - raw Gemini delta about `+5%` to `+10%`
  - still inside the Pack’s `< +20%` pass envelope, but only after `282/293` are live and measured
- the OPS_BOARD `blocked_by` trio is now documented, but the five operational preconditions remain all `NO`
- the Pack is now `13/13 complete`, while the correct recommendation remains `HOLD`
