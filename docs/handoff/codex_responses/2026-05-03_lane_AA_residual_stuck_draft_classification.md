# 2026-05-03 Lane AA residual stuck draft classification

作成: 2026-05-03 22:43 JST  
mode: read-only / doc-only / live-inert

## scope

- primary latest-state source:
  - `/tmp/lane_W2_backup_20260503T221315/guarded_publish_history.before.jsonl`
- support:
  - `/tmp/publish_notice_queue_20260503_live.jsonl`
  - `/tmp/lane_z_publish_notice_queue.jsonl`
  - `docs/handoff/codex_responses/2026-05-03_lane_Z_mass_publish.md`
  - `docs/handoff/codex_responses/2026-05-03_lane_N_h_regression_fix.md`
  - `docs/handoff/codex_responses/2026-05-03_lane_R_injury_return_7_publish.md`
  - `docs/handoff/codex_responses/2026-05-03_lane_Q_bug003_14_audit.md`
  - `docs/handoff/codex_responses/2026-05-03_lane_U_placeholder_50_sample.md`
  - `docs/handoff/codex_responses/2026-05-03_lane_P_backlog_16_reeval_publish.md`
- stale local mirror note:
  - repo-local `logs/guarded_publish_history.jsonl` is stale through `2026-04-26`
  - for `2026-05-03` residual classification, the `/tmp` live mirror is authoritative in this sandbox

Out-of-scope in this memo:

- Lane W2 in-flight 7 ids:
  - `63175`, `63385`, `63517`, `63661`, `64321`, `64324`, `64332`
- live mutation, WP write, mail send, env / Scheduler / history rewrite

## Step 1. latest stuck draft population

Latest-entry-per-post scan from the authoritative local mirror:

- latest `refused` / `skipped` within last `48h`: `416`
- latest `refused` / `skipped` with latest row on `2026-05-03 JST`: `409`
- residual scope after excluding Lane W2 7 in-flight ids:
  - `48h residual = 409`
  - `same-day residual = 402`

Residual hold_reason distribution:

| hold_reason | residual count |
|---|---:|
| `hard_stop_lineup_duplicate_excessive` | `141` |
| `backlog_only` | `136` |
| `hard_stop_farm_result_placeholder_body` | `48` |
| `hard_stop_death_or_grave_incident` | `24` |
| `review_date_fact_mismatch_review` | `20` |
| `review_duplicate_candidate_same_source_url` | `20` |
| `hard_stop_lineup_no_hochi_source` | `11` |
| `hard_stop_ranking_list_only` | `3` |
| `review_score_order_mismatch_review` | `3` |
| `review_farm_result_required_facts_weak_review` | `2` |
| `hard_stop_win_loss_score_conflict` | `1` |

## Step 2. duplicate check against tonight's 7 published posts

Tonight-published set treated as authoritative:

- `64272` リチャード復帰戦
- `64396` 西舘勇陽 昇格・復帰
- `64386` 阿部監督
- `64394` 橋上コーチ
- `64402` 山崎伊織 緊急降板
- `64405` 杉内コーチ
- `64294` 小浜佑斗 ドラ5 タイムリー

Current latest stuck rows that now point directly at the tonight-published set:

| stuck post_id | latest hold | duplicate target | reading |
|---|---|---|---|
| `64328` | `review_duplicate_candidate_same_source_url` | `duplicate_of_post_id=64272` | Lane Z live retry reclassified this from `widgets.js` to a real duplicate |
| `64292` | `review_duplicate_candidate_same_source_url` | `duplicate_of_post_id=64386` | same-source duplicate now anchored to a tonight-published manager article |

Result:

- duplicate hit count against tonight’s 7 published posts: **`2`**
- both are **duplicate HOLD**
- no other current latest stuck row in the residual scope points directly at the tonight-published 7

## Step 3. A / B / C classification

### A. still worth treating as publish candidates: `5`

These are same-day `widgets.js` duplicate-review holds with `publishable=true`, `repairable` evidence, and no current real-duplicate reclassification.

| post_id | title | subtype | why still A | likely path |
|---|---|---|---|---|
| `64356` | `山崎伊織、昇格・復帰 関連情報` | `notice` | same-day injury/return-ish notice; only blocker is `widgets.js` same-source review against `64319` | separate narrow widgets.js re-eval |
| `64361` | `【3日の公示】阪神は井坪陽生、巨人は堀田賢慎を登録 日本ハムは古林睿煬、西武…` | `notice` | same-day roster/public-notice family; no hard-stop or stale bucket yet | separate narrow widgets.js re-eval |
| `64374` | `◇セ・リーグ公示（３日） 【出場選手登録】 阪神・井坪陽生外野手 巨人・堀田…` | `notice` | same-day notice family; currently blocked only by `widgets.js` duplicate review | separate narrow widgets.js re-eval |
| `64378` | `緊急降板選手、昇格・復帰 関連情報` | `notice` | same-day injury/return follow-up; false-duplicate pattern is plausible and not yet disproved | separate narrow widgets.js re-eval |
| `64382` | `打球直撃で救急搬送の泉口友汰、４日から１軍合流の可能性 阿部監督「一応、呼ぶ…` | `notice` | injury/return notice that still fits the user’s rescue criteria; only recorded blocker is `widgets.js` same-source review | separate narrow widgets.js re-eval |

### B. legitimate stop / HOLD is acceptable: `401`

Bucket breakdown:

| reason family | count | reading |
|---|---:|---|
| `hard_stop_lineup_duplicate_excessive` | `141` | real lineup duplicate family |
| `backlog_only` | `136` | stale / old-candidate carryover; keep HOLD |
| `hard_stop_farm_result_placeholder_body` | `48` | Lane U sample supports true template/body failure |
| `hard_stop_death_or_grave_incident` | `24` | residual after excluding W2 in-flight 7 |
| `review_date_fact_mismatch_review` except C | `19` | legitimate review hold; not tonight rescue |
| `review_duplicate_candidate_same_source_url` except A/C | `13` | duplicate or late/stale same-day items not worth rescue tonight |
| `hard_stop_lineup_no_hochi_source` | `11` | legitimate source-policy stop |
| `hard_stop_ranking_list_only` | `3` | legitimate range/scope stop |
| `review_score_order_mismatch_review` | `3` | fact/score consistency review hold |
| `review_farm_result_required_facts_weak_review` | `2` | farm-result factual weakness hold |
| `hard_stop_win_loss_score_conflict` | `1` | legitimate score-conflict stop |

Notable B decisions:

| post_id | classification | reason |
|---|---|---|
| `64292` | duplicate HOLD | now directly anchored to tonight-published `64386` |
| `64328` | duplicate HOLD | Lane Z live retry proved it collapses into duplicate of tonight-published `64272` |
| `64335` | legitimate HOLD | `widgets.js` family, but subtype is `lineup`; by `2026-05-03 22:30 JST` it is already a time-decayed lineup rescue, not a priority publish candidate |
| `64331` | legitimate HOLD | `review_date_fact_mismatch_review` plus Lane Q field evidence for non-publish / `401`; not a tonight publish candidate |
| `64352` | legitimate HOLD | `review_date_fact_mismatch_review` plus Lane Q field evidence for non-publish / `401`; keep separate from rescue lane |
| `64280` | legitimate HOLD | Lane N' explicitly left this `general/off_field` widgets.js case as draft, not a recovery target |
| `64333` | legitimate HOLD | `farm_lineup`; same-day game-context lineup/farm-lineup content is operationally stale by late night |
| `64341` | legitimate HOLD | `lineup`; same-day lineup context already decayed by late night |
| `64346` | legitimate HOLD | `lineup` plus reconstruction remained incomplete in Lane L; not safe enough for tonight rescue |

### C. hold pending more evidence: `3`

| post_id | current latest hold | why C |
|---|---|---|
| `64380` | `review_duplicate_candidate_same_source_url` | `widgets.js` family against `64343`, but current sandbox did not recover title/source cleanly enough to say rescue vs duplicate |
| `64384` | `review_duplicate_candidate_same_source_url` | same as `64380`; insufficient local reconstruction, so leave outside A/B certainty |
| `64390` | `review_date_fact_mismatch_review` | guarded latest row is still refused, but queue mirrors carry `【公開済】`-style subject text; without live WP GET the current true visibility cannot be settled here |

## Step 4. totals

Residual scope totals after excluding W2 7 in-flight ids:

- `A = 5`
- `B = 401`
- `C = 3`
- `total residual stuck = 409`

Interpretation:

- there are **still `5` residual publish candidates**
- most of the remaining pool is legitimate HOLD
- the ambiguous remainder is small and does not justify broadening tonight’s lane

## Step 5. answer to the user’s question

Direct answer:

- there are **not zero** residual publish candidates
- the residual pool is **mostly legitimate HOLD**, but **`5` same-day notice / injury-return-ish widgets.js cases** still deserve a publish-candidate look
- the Lane Z residual four are **not all rescue targets**:
  - `64335` = HOLD
  - `64331` = HOLD
  - `64352` = HOLD
  - `64390` = pending / C

Recommended next action if the user wants one more narrow publish lane tonight:

1. do **not** reopen broad residual rescue
2. limit any further live work to:
   - `64356`
   - `64361`
   - `64374`
   - `64378`
   - `64382`
3. keep `64380`, `64384`, `64390` out until a live-capable shell can verify the missing title / true WP status
4. leave all B-class rows alone tonight

If the user does **not** want another narrow lane, tonight can still be wrapped with a clear summary:

- residual publish room exists, but it is already narrow (`5`)
- everything else is duplicate / stale / placeholder / hard-stop / date-fact / out-of-priority HOLD
