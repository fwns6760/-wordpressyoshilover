# Lane S BUG-003 3 proposals detail

更新: 2026-05-03 JST

## Scope

- read-only / doc-only / live-inert
- input audit:
  - `7ee5906` `docs/handoff/codex_responses/2026-05-03_lane_Q_bug003_14_audit.md`
  - `docs/ops/bug003_wp_status_mutation_audit.md`
  - `docs/ops/bug003_bug004_291_status_revert_3_audit.md`
  - `docs/ops/bug003_bug004_291_status_revert_broad_audit.md`
- static code review only:
  - `src/wp_client.py`
  - `src/rss_fetcher.py`
  - `src/guarded_publish_runner.py`
  - direct publish callers under `src/`
- no `src/**` / `tests/**` / `config/**` mutation
- no live ops / WP write / mail send / env / Scheduler / image change

## 14-id cohort recap

Target 14 ids:

- `64196`, `64198`, `64352`
- `64259`, `64080`, `64085`, `64167`, `64169`, `64331`, `64177`, `64183`, `64201`, `64368`, `64207`

Observed split from Lane Q:

- current field fact: 14/14 are treated as current `401` / non-publish
- latest guarded cluster `skipped / backlog_only / cleanup_required=true / cleanup_success=false`: 8 ids
  - `64198`, `64259`, `64085`, `64167`, `64169`, `64177`, `64183`, `64201`
- latest guarded cluster `refused / review_date_fact_mismatch_review`: 5 ids
  - `64196`, `64352`, `64080`, `64331`, `64207`
- latest guarded cluster `refused / review_farm_result_required_facts_weak_review`: 1 id
  - `64368`

Interpretation lock:

- `C` is the only proposal that can identify the actual WP-side final mutator of the current `401` state.
- `B` is the strongest repo-side fix for the shared ledger mismatch pattern: all 14 have `publish_time_iso`, but none has current-day guarded `status=sent`.
- `A` is mostly cleanup/log semantics hygiene for the 8 backlog-only rows and is the weakest explanatory fit for the current 14-id incident.

## Executive matrix

| proposal | main purpose | primary target ids | immediate direct rescue of current 14 | direct diagnostic / containment coverage | live mutation in first step | impl cost | recommendation |
|---|---|---|---:|---:|---|---|---|
| `C` WP-side trace | identify actual current `401` actor and exact final WP state | pivot first `64196 / 64198 / 64352 / 64331 / 64368 / 64207`, then all 14 | `0/14` in pure read-only trace | `14/14` | read-only in phase 1 | `M` | `高` |
| `B` publish path hardening | stop silent publish visibility and ledger mismatch inside repo | all 14 as a shared unanchored-publish cohort | `0/14` for already-broken posts | `14/14` ledger containment | code change only; no WP write until future runtime publish | `M` | `高` |
| `A` cleanup path hygiene | separate cleanup semantics from history-only reevaluation | mainly backlog/cleanup flag 8 ids | `0/14` | `8/14` diagnostic clarity | code change only | `S` | `低` |

Important read:

- if the question is “who made these 14 ids become current `401`?”, `C` is the real fix path
- if the question is “how do we stop repo-side publish visibility without a guarded `sent` anchor?”, `B` is the real fix path
- `A` does not solve either root question by itself

## Proposal C

### Name

`C = WP-side immutable trace first, optional audit hook second`

### 対象

- post_ids:
  - pivot set: `64196`, `64198`, `64352`, `64331`, `64368`, `64207`
  - expand set: `64259`, `64080`, `64085`, `64167`, `64169`, `64177`, `64183`, `64201`
- 影響範囲:
  - current WP-side final state only
  - manual admin edit
  - plugin hook
  - WP cron
  - out-of-band REST actor
- 修正対象 src file 等:
  - phase 1 read-only trace: repo code changeなし
  - optional phase 2 hook: `src/yoshilover-post-noindex.php` を拡張するか、別 plugin file を新設して `transition_post_status` / `save_post` / `rest_after_insert_post` / revision trail を immutable log に書く

### 効果

- 14/14 について `draft` / `private` / `trash` / other の exact final state を確定できる
- actual actor が repo 外か repo 内かを切り分けられる
- `64196 / 64352 / 64331 / 64368` の later GCP trace stop を、WP-side actor 不在ではなく “GCP外 actor” として証明できる
- current 14-id repair を行うなら prerequisite。これなしで B だけ先にやると、current `401` actor は未確定のまま残る

### リスク

- phase 1 read-only trace は低リスク
- phase 2 audit hook は中リスク
  - actor/user/plugin name capture による log hygiene 注意
  - WP plugin deploy/activate coordination が必要
  - hook を雑に書くと autosave/revision noise が増える
- 本物 duplicate 通り抜けには直接効かない
- ledger 一致は直接は改善しない

### rollback

- phase 1 read-only trace: rollback不要
- phase 2 hook:
  - default OFF flag / option を remove
  - plugin deactivate
  - `git revert`
  - hook導入後に副作用があれば WP-side audit log だけ残し、status repair は別便に分離

### live mutation 有無

- phase 1: `read-only`
- phase 2: `code change + WP plugin deploy/activate`
- WP post status write: `なし`
- mail send: `なし`

### 想定 mail 数 / Gemini call 増 / Scheduler 影響

- mail: `0`
- Gemini: `0`
- Scheduler: `0`
- default OFF flag:
  - phase 1 は不要
  - phase 2 をやるなら `ENABLE_WP_STATUS_AUDIT=0` で inert start が望ましい

### 推奨度

`高`

### impl 工数

`M`

Reason:

- pure field trace だけなら `S`
- reusable WP-side audit hook まで入れると `M`
- current decision material としては `M` 扱いが妥当

### 14 ids のうち直接救う件数

- immediate direct rescue: `0/14`
- diagnostic coverage: `14/14`
- if user later authorizes targeted live repair after actor confirmation: potential repair scope `14/14`

### 本物 fix needed か symptom mitigation か

- `real fix needed`
- reason: current `401` actor の特定は symptom 整理ではなく root-cause discovery

## Proposal B

### Name

`B = publish writer unification + explicit reuse status upgrade opt-in`

### 対象

- post_ids:
  - direct relevance: all 14
  - strongest validation set: `64196`, `64198`, `64352`, `64331`, `64368`, `64207`
- 影響範囲:
  - repo-internal publish visibility
  - guarded ledger consistency
  - manual/autonomous publish entrypoints
- 修正対象 src file 等:
  - `src/wp_client.py`
    - `_reuse_existing_post()`
    - `create_post()`
  - `src/rss_fetcher.py`
    - `finalize_post_publication()`
  - `src/guarded_publish_runner.py`
    - publish helper reuse or central publish transition extraction
  - direct publish callers that currently rely on `create_post(... status=\"publish\")`
    - `src/manual_post.py`
    - `src/sports_fetcher.py`
    - `src/weekly_summary.py`
    - `src/data_post_generator.py`

### 効果

- all 14 share the same mismatch signature:
  - `publish_time_iso` exists
  - current-day guarded durable state is not `sent`
- this proposal is the best repo-side answer to that pattern
- expected gains:
  - no silent `draft/pending/future/auto-draft -> publish` inside `_reuse_existing_post()`
  - no direct `wp.update_post_status(post_id, "publish")` bypass from `rss_fetcher`
  - every future publish transition can carry `writer_lane`, `caller`, `source`, `status_before`, `status_after` into the guarded ledger
- ledger 一致改善見込み:
  - `14/14` cohort pattern is directly targeted
  - future “publish-visible but non-sent in guarded history” incidents should materially drop

### リスク

- true intentional reuse flow may stop promoting old draft-like posts unless caller opt-in is added correctly
- manual/utility scripts may unexpectedly create new drafts/posts instead of reusing and publishing an old draft
- if routed too aggressively through guarded rules, some legacy manual utilities may start hitting cap/review semantics they did not previously see
- scope外影響:
  - publish path is central; caller review漏れがあると partial behavior drift になる
- current 14 ids themselves are not repaired by this change alone

### rollback

- preferred staged rollback:
  - remove opt-in env flags if rollout is flag-gated
  - image revert
  - `git revert`
- WP draft 戻し:
  - normally `不要`
  - only needed if a live-enabled future publish run mutates new posts incorrectly; not part of default rollback

### live mutation 有無

- `code change`
- initial deploy can be `live-inert` if gated behind default OFF flags
- no immediate WP write at deploy time
- future runtime publish paths do write WP only when a later publish job actually fires
- mail send: `なし`

### 想定 mail 数 / Gemini call 増 / Scheduler 影響

- mail: `0`
- Gemini: `0`
- Scheduler: `0`
- default OFF flag examples:
  - `ENABLE_GUARDED_PUBLISH_WRITER=0`
  - `ENABLE_EXPLICIT_REUSE_STATUS_UPGRADE=0`

### 推奨度

`高`

### impl 工数

`M`

Reason:

- change points are several, but all are bounded to publish path discipline
- it becomes `L` only if the team wants every manual utility fully requalified in the same release

### 14 ids のうち直接救う件数

- immediate direct rescue of current 14: `0/14`
- direct containment of shared ledger mismatch pattern: `14/14`

### 本物 fix needed か symptom mitigation か

- repo-internal silent publish / ledger mismatchに対しては `real fix needed`
- current `401` persistenceに対しては `symptom mitigation only` until `C` confirms the final actor

## Proposal A

### Name

`A = cleanup path hygiene + status-write intent ledger`

### 対象

- primary post_ids:
  - `64198`, `64259`, `64085`, `64167`, `64169`, `64177`, `64183`, `64201`
- secondary observation only:
  - `64196`, `64352`, `64080`, `64331`, `64368`, `64207`
- 影響範囲:
  - cleanup-related history rows
  - backlog-only reevaluation semantics
  - future audit readability
- 修正対象 src file 等:
  - `src/guarded_publish_runner.py`
    - backlog hold branch
    - cleanup-required branch
    - `_hold_reason_for_candidate_error()`
    - `_history_row(...)` payload fields

### 効果

- current logs conflate:
  - `cleanup_required=true`
  - `cleanup_success=false`
  - history-only reevaluation
- this proposal would add explicit fields such as:
  - `write_attempted`
  - `status_before`
  - `status_after`
  - `mutation_actor=history_only|cleanup_publish|guarded_publish`
- for the 8 backlog/cleanup-flag ids, next audit could reject “cleanup was the mutator” almost immediately
- ledger 一致改善見込み:
  - small
  - mostly observability quality, not business-state repair

### リスク

- if implemented as new history rows instead of additive fields, mail/scanner consumers may misread volume
- if hold_reason semantics drift, review mail routing could break
- does not stop true duplicate pass-through
- does not identify out-of-band WP actor
- does not repair current 14

### rollback

- remove flag if feature-gated
- image revert
- `git revert`
- historical rows remain; no WP state rollback needed

### live mutation 有無

- `code change`
- no WP write
- no mail send

### 想定 mail 数 / Gemini call 増 / Scheduler 影響

- mail: `0` if additive fields only
- Gemini: `0`
- Scheduler: `0`
- recommended flag:
  - `ENABLE_CLEANUP_STATUS_TRACE=0`

### 推奨度

`低`

### impl 工数

`S`

### 14 ids のうち直接救う件数

- immediate direct rescue: `0/14`
- direct diagnostic clarity: `8/14`

### 本物 fix needed か symptom mitigation か

- `symptom mitigation`
- exact current issueに対する root fix ではない

## Sequential / parallel recommendation

Recommended order:

1. `C` phase 1 read-only trace
2. `B` repo hardening design -> impl -> default OFF deploy only after explicit go
3. `A` only if ambiguity remains, or fold the additive fields into `B`

Why this order:

- `C` first preserves the best chance to identify the actual current `401` actor before repo behavior changes
- `B` next removes the strongest repo-side bypass regardless of whether `C` finds a WP/plugin/manual actor
- `A` last because it mainly improves observability and overlaps with `src/guarded_publish_runner.py`, which `B` is already likely to touch

Parallelism assessment:

- `C` read-only trace can run in parallel with a design review for `B`
- `B` impl and `A` impl are better kept sequential
  - both are likely to touch guarded-publish / history semantics
  - parallel implementation increases merge and interpretation risk without improving decision quality much

## Final recommendation

- best decision path for the current 14-id incident: `C -> B -> A`
- if user wants the minimum-risk next step, choose `C` phase 1 only
- if user wants the best repo-side hardening after evidence capture, choose `B` next
- `A` should not be the first live fix choice

## One-line user decision summary

`現行14件の401 actorを本当に特定したいなら C を先に、repo内の silent publish / ledger mismatch を先に潰したいなら B を次に、A は最後の観測性補強です。`
