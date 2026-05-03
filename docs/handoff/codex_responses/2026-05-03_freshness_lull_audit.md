# 2026-05-03 freshness lull audit

作成: 2026-05-03 18:30 JST 前後  
mode: read-only / doc-only / live-inert

## scope

- code / tests / config / env / Scheduler / GCS write / WP write / mail send: 0
- live read sources:
  - `gcloud run jobs describe guarded-publish`
  - `gcloud run jobs describe publish-notice`
  - `gcloud logging read` for `yoshilover-fetcher` / `guarded-publish` / `publish-notice`
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
  - `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
  - `gs://baseballsite-yoshilover-state/publish_notice/history.json`
  - `gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json`
- code trace:
  - `src/guarded_publish_evaluator.py`
  - `src/guarded_publish_runner.py`
  - `src/publish_notice_scanner.py`
  - `src/publish_notice_email_sender.py`

## hard limit

- durable `guarded_publish_history.jsonl` row does **not** persist exact `content_date` / WP `created_at` value
- therefore this audit can prove:
  - latest `hold_reason`
  - `freshness_source`
  - first observed guarded-history time
  - first observed publish-notice queue time
- but it cannot deterministically print the original stored `source_date` / WP `created_at` field value for every old row from read-only artifacts alone
- where exact field values are unavailable, this memo uses **lower-bound age evidence**:
  - `first_guarded_ts`
  - `first_queue_recorded_at`

## live target confirmation

### guarded-publish

- generation: `23`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:565ef9a`
- live env present:
  - `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`
  - `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT=1`
- freshness env override: **none observed**

### publish-notice

- visibility-layer env present:
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL=1`
  - `ENABLE_PUBLISH_NOTICE_CLASS_RESERVE=1`
  - `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR=1`
  - `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`

Implication:

- `BACKLOG_SUMMARY_ONLY` / `OLD_CANDIDATE_PERMANENT_DEDUP` are **publish-notice visibility controls**
- they do **not** explain why fresh 5/3 candidates fail to publish

## executive conclusion

- `publish=0` after **2026-05-03 17:00 JST** is **not** explained by freshness being too strict on fresh same-day content
- direct cause split:
  1. fetcher is active but **fresh items are not becoming drafts**: `prepared=33`, `created=0`
  2. guarded-publish is mostly replaying a **legacy stale backlog pool**: the same `135` `backlog_only` rows every 5 minutes
  3. publish-notice is mostly quiet because recent cycles have either `sent=0 suppressed=0` or `BACKLOG_SUMMARY_ONLY` suppressions
- therefore the lull is **not a healthy normal lull** in the sense of “no source activity”; source activity exists
- but it is also **not mainly a freshness-threshold bug** for the current 5/3 postgame / 5/4 pregame stream
- the first thing to fix is **upstream postgame/post-gen/body-contract flow**, not global freshness relaxation

---

## Q-A. backlog_only 多発の根本原因切り分け

### A-1. direct answer

- root cause is a **replayed stale backlog pool**, not a fresh-content freshness miss
- latest 6 guarded cycles from **18:00:46 JST** to **18:25:41 JST**:

| cycle ts (JST) | rows | backlog_only | other hold |
|---|---:|---:|---|
| `18:00:46` | `135` | `135` | `0` |
| `18:05:38` | `136` | `135` | `hard_stop_death_or_grave_incident=1` |
| `18:10:38` | `135` | `135` | `0` |
| `18:15:47` | `135` | `135` | `0` |
| `18:20:39` | `135` | `135` | `0` |
| `18:25:41` | `136` | `135` | `hard_stop_farm_result_placeholder_body=1` |

- in the recent **18:00-18:25 JST** raw window:
  - rows = `812`
  - latest unique post_ids = `137`
  - latest hold split = `backlog_only 135`, `hard_stop_death_or_grave_incident 1`, `hard_stop_farm_result_placeholder_body 1`

### A-2. last 1-2 cycle comparison

- `18:20 JST` guarded execution: `135/135` were `backlog_only`
- `18:25 JST` guarded execution: same `135` `backlog_only` rows plus one new legitimate placeholder hard-stop (`post_id 64123`)
- difference between the two latest cycles:
  - only new post in `18:25 JST` = `64123`
  - no fresh publishable proposal appeared

### A-3. backlog_only pool shape

latest-state `backlog_only` unique pool at `18:25 JST`:

- total unique latest rows: `137`
- `freshness_source=source_date`: `78`
- `freshness_source=created_at`: `59`
- `old_candidate_once` ledger overlap: `121/137`
- not in old-candidate ledger yet: `16/137`

lower-bound age from first guarded-history appearance:

- min: `1.92h`
- p25: `94.09h`
- median: `154.34h`
- max: `167.57h`

Interpretation:

- the pool is dominated by **multi-day old rows**
- a small same-day tail exists, but most of the `backlog_only` storm is legacy

### A-4. backlog_only candidate examples

Exact `source_date` / WP `created_at` field value is not persisted in durable history.  
Below table uses `freshness_source` plus first observable queue time as evidence.

| post_id | inferred subtype | freshness_source | first queue seen | subject | is_backlog rationale |
|---|---|---|---|---|---|
| `64373` | `lineup` | `created_at` | `2026-05-03 16:35 JST` | `【公開済】巨人スタメン 阪神戦(甲子園、14:00)...` | same-day lineup, but game start `2026-05-03 14:00 JST` is already past; `expired_lineup_or_pregame` path is expected |
| `64259` | `farm` | `created_at` | `2026-05-03 10:26 JST` | `【公開済】【三軍】巨人 vs JR秋田 ... 11...` | same-day farm game context; by `18:25 JST` game context is long expired |
| `64218` | `roster_notice` | `source_date` | `2026-05-03 16:56 JST` | `【要確認】（１日）巨人・中山礼都...` | title itself points to `5/1`; by `2026-05-03 18:25 JST` this is 48h+ old |
| `64167` | `lineup` | `created_at` | `2026-05-03 13:01 JST` | `【要確認(古い候補)】巨人スタメン 岡本和真 第3打席...` | in-game lineup/live-update style content; after game progress it is stale for breaking board use |
| `64212` | `roster_notice` | `source_date` | `2026-05-03 16:41 JST` | `【要確認・X見送り】巨人が6人入れ替え...` | notice family with source-date aging; not a “fresh postgame” case |

### A-5. backlog_only ではない recent blockers

- recent 30m raw window:
  - `hard_stop_death_or_grave_incident = 1`
  - `hard_stop_farm_result_placeholder_body = 1`
- latest total latest-state stuck upper bound:
  - `hard_stop_lineup_duplicate_excessive = 141`
  - `backlog_only = 137`
  - `hard_stop_farm_result_placeholder_body = 50`
  - `hard_stop_death_or_grave_incident = 31`
  - `review_duplicate_candidate_same_source_url = 29`
  - `review_date_fact_mismatch_review = 22`

Takeaway:

- recent real-time silence is **almost entirely** `backlog_only`
- the non-backlog blockers are legitimate hard/review stops and low volume in the last two cycles

---

## Q-B. 18:16 prepared 33件 の内訳と guarded 判定 distribution

### B-1. fetcher side

`rss_fetcher_flow_summary` around `2026-05-03 18:16 JST` and `18:21 JST` is effectively stable:

- `prepared_category_counts = {"OB・解説者":1,"コラム":16,"試合速報":14,"首脳陣":2}`
- `prepared_subtype_counts = {"general":1,"manager":2,"postgame":24,"pregame":6}`
- `created_category_counts = {}`
- `created_subtype_counts = {}`
- `publish_skip_reason_counts = {}`

`rss_fetcher_run_summary` in the same band:

- `draft_only=true`
- `drafts_created=0`
- `error_count=0`

### B-2. why 33 prepared did not reach guarded-publish

These `33` prepared items did **not** become new guarded candidates because they never became drafts.

Dominant upstream skip reasons in the same summaries:

- `body_contract_validate = 17`
- `post_gen_validate = 11`
- `comment_required = 2`
- `pregame_started = 5`
- `social_too_weak = 20`
- `stale_postgame = 1`

Key point:

- “prepared 33” is **not** the same as “33 entered guarded-publish”
- for this band, **guarded-publish received 0 newly-created drafts from the fetcher**
- guarded-publish kept processing only the older backlog pool

### B-3. subtype hit pattern

- `postgame 24` is the bulk of the prepared stream
- but today’s postgame family is being killed **upstream** by `body_contract_validate` and `post_gen_validate`, not by guarded freshness
- `pregame 6` also does not reach guarded; sample titles show tomorrow pregame pieces are being caught by `pregame_started` / `post_gen_validate`

---

## Q-C. freshness threshold の現値

### C-1. current code values

`src/guarded_publish_evaluator.py`

- `lineup = 6h`
- `pregame = 6h`
- `probable_starter = 6h`
- `farm_lineup = 6h`
- `postgame = 24h`
- `game_result = 24h`
- `roster / injury / notice / recovery / player_notice = 24h`
- `comment / speech / manager / program / off_field / farm_feature = 48h`
- fallback default = `24h`

Structural rules in `freshness_check(...)`:

- lineup / pregame family:
  - expire once `now >= estimated game_start_dt`
  - or expire if `age_hours > 6h`
- postgame / game_result family:
  - expire if `age_hours > 24h`
- other families:
  - stale if over their subtype threshold

Runtime note:

- current `guarded-publish` live env shows **no freshness override env**
- therefore live threshold is the code constant above

### C-2. can `5/4` pregame fall to backlog_only on `2026-05-03 18:30 JST`?

Direct answer: **not by this freshness gate if the item is truly for 2026-05-04 18:00 JST**.

Reason:

- official Tokyo Dome schedule shows **Giants vs Yakult on 2026-05-04 at 18:00 JST**
  - source: Tokyo Dome schedule / ticket pages  
    - https://www.tokyo-dome.co.jp/dome/baseball/giants/ticket/ticket_sale.html
    - https://www.tokyo-dome.co.jp/dome/baseball/giants/ticket/general.html
- at `2026-05-03 18:30 JST`, that game is still ~23.5h away
- freshness logic would not mark a true `5/4 18:00` pregame item as expired yet

What the pipeline actually shows:

- fetcher sample titles include `あす5/4の予告先発 巨人 戸郷翔征 ヤクルト 奥川恭伸 18時 東京ドーム`
- that sample appears under **`post_gen_validate`** and **`pregame_started`** buckets in fetcher logs
- it does **not** appear as a guarded `backlog_only` case in the recent history window

Conclusion:

- if a `5/4` pregame piece is failing at `2026-05-03 18:30 JST`, current evidence says the failure is **upstream**, not freshness backlog

### C-3. can `5/3` immediate postgame fall to backlog_only right after game end?

Direct answer: **not normally**.

Reason:

- `postgame` threshold is `24h`
- a genuine `2026-05-03` postgame article published shortly after the game should still be fresh

What the pipeline actually shows:

- current `5/3` postgame sample titles are landing in:
  - `body_contract_validate`
  - `post_gen_validate`
  - `comment_required`
- they are **not** showing up as same-cycle guarded `backlog_only`

Conclusion:

- immediate postgame silence on `2026-05-03` is explained by **upstream validation**, not by postgame freshness strictness

---

## Q-D. Good Draft Rescue 候補母集団

### D-1. current pool size

From latest row per `post_id` in `guarded_publish_history.jsonl`:

- upper bound stuck universe = `430`
  - latest `status=refused|skipped`
- known already-published rows from latest `publish_notice/queue.jsonl` subject prefix `【公開済】` = `18`
- conservative draft-like lower bound = `412`

Reason for upper/lower bound split:

- no WP GET available in this sandbox
- `【公開済】` subject prefix is the only reliable published signal visible from read-only artifacts

### D-2. hold_reason distribution

upper bound (`430`):

| hold_reason | count |
|---|---:|
| `hard_stop_lineup_duplicate_excessive` | `141` |
| `backlog_only` | `137` |
| `hard_stop_farm_result_placeholder_body` | `50` |
| `hard_stop_death_or_grave_incident` | `31` |
| `review_duplicate_candidate_same_source_url` | `29` |
| `review_date_fact_mismatch_review` | `22` |
| `hard_stop_lineup_no_hochi_source` | `11` |
| `hard_stop_ranking_list_only` | `3` |
| `review_score_order_mismatch_review` | `3` |
| `review_farm_result_required_facts_weak_review` | `2` |
| `hard_stop_win_loss_score_conflict` | `1` |

draft-like lower bound (`412`, excluding `【公開済】` rows):

| hold_reason | count |
|---|---:|
| `hard_stop_lineup_duplicate_excessive` | `141` |
| `backlog_only` | `120` |
| `hard_stop_farm_result_placeholder_body` | `50` |
| `hard_stop_death_or_grave_incident` | `31` |
| `review_duplicate_candidate_same_source_url` | `29` |
| `review_date_fact_mismatch_review` | `21` |
| `hard_stop_lineup_no_hochi_source` | `11` |
| others | `9` |

### D-3. widgets.js false-positive lane

latest-state `review_duplicate_candidate_same_source_url = 29`

- widgets.js target = `12`
- non-widgets / null target = `17`

widgets.js group:

| post_id | latest ts | age since first seen | duplicate_of_post_id |
|---|---|---:|---:|
| `64328` | `2026-05-03 12:36 JST` | `5.83h` | `64297` |
| `64333` | `2026-05-03 13:10 JST` | `5.25h` | `64326` |
| `64335` | `2026-05-03 13:20 JST` | `5.09h` | `64299` |
| `64341` | `2026-05-03 13:45 JST` | `4.67h` | `64299` |
| `64346` | `2026-05-03 14:10 JST` | `4.26h` | `64299` |
| `64356` | `2026-05-03 14:40 JST` | `3.75h` | `64319` |
| `64361` | `2026-05-03 15:15 JST` | `3.17h` | `64319` |
| `64374` | `2026-05-03 16:50 JST` | `1.59h` | `64319` |
| `64378` | `2026-05-03 16:55 JST` | `1.51h` | `64319` |
| `64380` | `2026-05-03 16:55 JST` | `1.51h` | `64343` |
| `64382` | `2026-05-03 17:15 JST` | `1.17h` | `64319` |
| `64384` | `2026-05-03 17:25 JST` | `1.01h` | `64343` |

Read:

- these `12` are the cleanest rescue lane
- but as of `2026-05-03 18:25 JST`, they are only `1.01h-5.83h` old
- if the intended operational rule is “wait for 24h TTL / dedup horizon first”, **none of them matures tonight**

### D-4. non-widgets duplicate lane

- `17` latest rows have `duplicate_target_source_url = null`
- treat as **HOLD**
- oldest rows in this lane are already `43h-91h` from first observed guard hit

### D-5. legitimate stop lanes

Treat as non-rescue / HOLD:

- `hard_stop_farm_result_placeholder_body = 50`
- `hard_stop_death_or_grave_incident = 31`
- `review_date_fact_mismatch_review = 22`
- `hard_stop_lineup_duplicate_excessive = 141`
- `hard_stop_lineup_no_hochi_source = 11`

### D-6. backlog_only rescue lane

- legacy backlog pool = `121` rows already in `old_candidate_once` ledger
- newer backlog rows not yet in old-candidate ledger = `16`
- among those newer `16`:
  - `6` already carry `【公開済】`
  - `10` remain draft-like

newer draft-like backlog examples:

| post_id | subtype | freshness_source | first queue seen | note |
|---|---|---|---|---|
| `64167` | `lineup` | `created_at` | `2026-05-03 13:01 JST` | in-game lineup/live-update style |
| `64169` | `lineup` | `created_at` | `2026-05-03 13:01 JST` | in-game lineup/live-update style |
| `64177` | `farm` | `created_at` | `2026-05-03 13:06 JST` | same-day farm game context |
| `64183` | `lineup` | `created_at` | `2026-05-03 13:36 JST` | lineup after game progress |
| `64198` | `general` | `source_date` | `2026-05-03 14:41 JST` | front/event style |
| `64201` | `general` | `source_date` | `2026-05-03 15:01 JST` | RT/front style |
| `64212` | `notice` | `source_date` | `2026-05-03 16:41 JST` | roster move |
| `64214` | `notice` | `source_date` | `2026-05-03 16:41 JST` | roster move |
| `64218` | `notice` | `source_date` | `2026-05-03 16:56 JST` | title points to `5/1` |
| `64242` | `lineup` | `created_at` | `2026-05-02 22:56 JST` | old lineup-like item |

Read:

- backlog rescue is **not** a single homogeneous freshness bug
- same-day lineup/farm entries are expiring because the game already started or ended
- roster/source-date entries are genuinely old by board standards

---

## Q-E. 今日中 publish 期待値

### E-1. sports calendar sanity

- internal pipeline shows today’s game context is **Hanshin vs Giants at Koshien**, and current postgame subjects refer to a `0-3` result
- official public schedule confirms the next Giants home game is:
  - **2026-05-04 18:00 JST, Giants vs Yakult at Tokyo Dome**
  - sources:
    - https://www.tokyo-dome.co.jp/dome/baseball/giants/ticket/ticket_sale.html
    - https://www.tokyo-dome.co.jp/dome/baseball/giants/ticket/general.html

### E-2. what can still naturally appear tonight

Potential natural content between `18:30` and `24:00 JST`:

- postgame manager/player comments from today’s `5/3` game
- late newspaper/comment follow-ups
- no legitimate `5/4 pregame freshness` unlock is needed tonight; tomorrow’s pregame is still far away

### E-3. what the pipeline says right now

Negative evidence:

- `2026-05-03 17:37 JST` through `18:21 JST` fetcher runs all show `drafts_created=0`
- recent prepared stream is stable at roughly:
  - `postgame 23-24`
  - `pregame 5-6`
  - `manager 2`
  - `general 1`
- recent blockers are stable too:
  - `body_contract_validate = 17`
  - `post_gen_validate = 10-11`
  - `comment_required = 2`
- guarded-publish latest two cycles show:
  - `proposed = []`
  - `135 backlog_only` replay
- publish-notice summary lines from `18:21 JST` to `18:41 JST` are all:
  - `sent=0`
  - `suppressed=0`

Positive evidence:

- if a clean late manager/player comment arrives, current freshness thresholds would allow it
- tonight’s expected comment family would be `24h-48h` fresh, so **freshness is not the blocker**

### E-4. expectation call

Current call at `2026-05-03 18:30 JST`: **Low**

Reason:

- there is still source activity, so a late clean comment article is possible
- but the observed pipeline pattern is twelve consecutive fetcher runs with `created=0`
- the current guarded lane has no fresh proposal buffer
- widgets.js duplicate candidates are only `1h-6h` old and do not naturally clear a `24h` wait tonight

Operationally:

- if no distinctly cleaner manager/player comment enters by around `19:30-20:00 JST`, the more likely outcome is **continued silence until tomorrow morning**

---

## recommended next action

1. **Do not relax freshness first.**
2. Treat the incident as:
   - primary: upstream `postgame/body_contract/post_gen_validate` choke
   - secondary: legacy `backlog_only` replay noise
3. Next best audit/repair target:
   - `postgame_strict_review` / `body_contract_validate` / `post_gen_validate` trace for the `5/3` postgame family
4. Separate lane:
   - widgets.js duplicate narrow audit remains valid, but it is a **rescue lane**, not tonight’s root publish unlock

## final verdict

- Q-A: `backlog_only` dominance is **real**, but it is mostly a replayed stale pool; fresh 5/3 content is not mainly dying on freshness
- Q-B: `prepared 33` never reached guarded; `created=0`
- Q-C: current freshness thresholds are code-constant (`6h` lineup/pregame, `24h` postgame/notice, `48h` comment/manager); `5/4` pregame and immediate `5/3` postgame are **not** explainable as freshness backlog misses
- Q-D: rescue pool exists, but the clean widgets.js subset is only `12` rows and is still too young for a 24h-wait strategy tonight
- Q-E: tonight publish expectation is **Low**
