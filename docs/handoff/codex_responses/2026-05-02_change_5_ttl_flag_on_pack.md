# 改修 #5 TTL flag ON Acceptance Pack

Date: 2026-05-02 JST  
Mode: doc-only / read-only pack creation  
Target: `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL=1` + `PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL_DAYS=7`

## Decision Header

```yaml
ticket: 改修-5-old-candidate-ledger-ttl flag ON
recommendation: GO
decision_owner: user
execution_owner: Claude
risk_class: low
classification: USER_DECISION_REQUIRED
classification_reason: flag ON で old_candidate permanent_dedup retention semantics が変わるため。real review / 289 / cleanup_required は不変だが、future old_candidate の再 review mail 量に微小影響があり得る。
cleanup_mutation_classification: NO
cleanup_mutation_reason: TTL prune は WP delete / draft 戻し / private 化ではなく、publish-notice 用 GCS hot-state ledger の retention mutation。state mutation ではあるが POLICY の cleanup mutation exemplars とは別。
deployed_code_reference:
  - commit: 6c0cf66
  - bundled_image_commit: c796c77
flag_default_state: OFF
live_state: deployed but inert
```

## 0. Recommended Decision

`GO`

理由: change #5 は既に `default OFF` で deploy 済み、tests evidence も `6c0cf66` に揃っている。`TTL=7d` を 2026-05-02 時点で ON にしても、current ledger `106` 件は 2026-05-01 19:35 JST 以降の pre-seed / auto-append 群が本体で、即時 prune 対象は実質 `0` 件見込み。誤 prune が起きても影響は「該当 candidate が old_candidate review mail flow に戻る」だけで、publish 経路・Gemini call・Team Shiny From・Scheduler・SEO を壊さない。分類は `USER_DECISION_REQUIRED` のままだが、推奨判断は `GO`。

user response format: `GO` / `HOLD` / `REJECT`

## 1. Prune Target Analysis

### 1.1 Current ledger schema

- runtime file: `publish_notice_old_candidate_once.json`
- local default path: `/tmp/pub004d/publish_notice_old_candidate_once.json`
- remote object: `gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json`
- parser acceptance in `src/publish_notice_scanner.py`:
  - live/canonical shape: `dict[str, str]` (`post_id -> ISO8601 ts`)
  - compatibility shape: `dict[str, {"ts": "..."}]`
- write shape of current implementation:
  - scanner appends new rows as bare ISO8601 string
  - prune path preserves surviving row payloads as-is

要点: source code の型は `dict[str, Any]` だが、実運用 ledger は引き続き `dict[str, str]` が本線。`{"ts": ...}` object は互換受理であり、current prod の primary schema ではない。

### 1.2 Prune delete rule

- cutoff rule: `ts < now - TTL_DAYS`
- current default TTL: `7`
- if enablement run happens on `2026-05-02`, cutoff is approximately `2026-04-25` same-clock-time JST
- removal happens once at scanner start via `_prune_old_candidate_ledger(...)`
- emitted log event: `permanent_dedup_ttl_prune`
  - current payload: `count`, `cutoff_ts`
  - deleted `post_id` list is **not** logged

### 1.3 Non-delete rule

The TTL path does **not** remove:

- rows with `ts >= cutoff`
- malformed / missing `ts` rows
  - parser returns `None`
  - implementation keeps them fail-closed
- non-old-candidate state
  - `real review`
  - `289/post_gen_validate`
  - `cleanup_required`
  - `preflight_skip`
  - `publish_notice_history.json`
  - `guarded_publish_history.jsonl`

### 1.4 Estimated prune count at default TTL

Read-only evidence:

- `docs/ops/CURRENT_STATE.md`
  - `GCS ledger pre-seed: 104 -> 106 件`
- `docs/ops/OPS_BOARD.yaml`
  - `gcs_ledger_count: 106`
- `docs/ops/INCIDENT_LIBRARY.md`
  - pre-seed happened `2026-05-01 19:35 JST`
- `docs/handoff/session_logs/2026-05-02_morning_verify.md`
  - one run still showed `40+` permanent dedup skips, so the ledger is actively used

Estimate:

- current ledger size: `106` rows
- rows already older than `2026-04-25` cutoff: **best estimate `0`**
- conservative range: **`0-1`**
  - only if the single pre-existing legacy row (`+ 1 旧`) carried a timestamp older than `2026-04-25`

Operational reading: for a flag ON run on `2026-05-02`, expected immediate prune count is effectively `0`.

## 2. Dry-Run / Canary

### 2.1 Count-only dry-run availability

`NO` as an operator-facing path.

- `src/tools/run_publish_notice_email_dry_run.py --scan` is mail-dry-run only
- it still calls `scan()` and therefore still mutates:
  - cursor
  - history
  - queue
  - old-candidate ledger when prune/write conditions are met
- internal `capture_only=True` exists in scanner internals, but no CLI / Cloud Run entrypoint exposes a safe count-only TTL preview

### 2.2 What current implementation can verify

Current implementation can verify only:

- prune hook is wired
- cutoff timestamp is correct
- pruned row count is emitted

Current implementation cannot verify in logs:

- exact deleted `post_id` list
- deleted row contents

### 2.3 Recommended pre-enable check

Recommended before env apply:

1. read-only copy current GCS ledger object
2. inspect timestamps offline
3. confirm expected expired rows are `0` before enabling

If Claude wants a production-path canary without real deletions:

- enable TTL with `PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL_DAYS=999`
- observe one run
- confirm `permanent_dedup_ttl_prune count=0`

This canary validates env wiring and log emission only. It does **not** prove real deletion contents.

## 3. Rollback

### Tier 1 env rollback

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL
```

- expected time: `~30 sec`
- effect: stops further TTL pruning immediately

### Tier 2 image rollback

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:9e9302f
```

- expected time: `~2-3 min`
- effect: removes the TTL code path entirely
- note: this is a broader runtime rollback than `git revert 6c0cf66`; it also drops later bundled image content

### Tier 3 ledger restore

Versioning-based restore:

- repo evidence of GCS object versioning: **not found**
- versioning availability: **unconfirmed**

Documented supported path today is archive/restore, not bucket versioning:

```bash
gsutil mv \
  gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json \
  gs://baseballsite-yoshilover-state/publish_notice/archive/<timestamp>.json
```

```bash
gsutil cp \
  gs://baseballsite-yoshilover-state/publish_notice/archive/<known_good>.json \
  gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json
```

- prerequisite: Claude archives the live object immediately before enablement if a known-good archive does not already exist
- restore owner: authenticated executor

### Source rollback

If the code itself must be removed from future builds:

```bash
git revert 6c0cf66
```

### Rollback order

1. Tier 1 env rollback
2. Tier 2 image rollback
3. Tier 3 ledger restore

Deleted-row restoration is needed only if immediate dedup state recovery is required. Tier 1 alone stops new pruning but does not resurrect already removed entries.

## 4. Mis-Prune Impact

- one wrongly deleted permanent_dedup row = one `post_id` can later re-enter old-candidate review flow
- impact unit: at most `+1` review mail per candidate when that candidate re-qualifies
- no effect on:
  - WP publish path
  - Team Shiny From
  - Gemini calls
  - source ingestion
  - Scheduler
  - silent skip suppression for other lanes

MAIL_BUDGET fit:

- current expected immediate prune count is `0`
- even a single mistaken delete implies only `+1` possible review mail
- this is operational noise, not a structural storm trigger by itself

Severity judgment:

- not fatal
- primary failure mode is duplicate review noise
- not a publish-break / silent-skip / Gemini-cost incident

## 5. Classification Judgment

### 5.1 cleanup mutation?

`NO`

Reason:

- POLICY examples define cleanup mutation as `WP delete / draft 戻し / private 化`
- this change prunes only publish-notice dedup hot state
- it does not mutate posts, review judgments, or publication state

### 5.2 Why still USER_DECISION_REQUIRED

`USER_DECISION_REQUIRED`

Reason:

- flag ON behavior-changing env apply
- suppression retention window changes for old_candidate replay
- future review-mail volume can increase after TTL expiry
- even though immediate expected prune count is `0`, this is not `CLAUDE_AUTO_GO`

### 5.3 unaffected axes

- Gemini call increase: `none`
- source addition: `none`
- Scheduler change: `none`
- SEO change: `none`
- real review / 289 / cleanup_required contract: `unchanged`
- publish/review/hold/skip core criteria: `unchanged outside old_candidate permanent dedup retention window`

## 6. CLAUDE_AUTO_GO 14-Condition Evaluation (env apply phase)

| # | condition | judgment | note |
|---|---|---|---|
| 1 | flag OFF deploy | NO | this phase is flag ON |
| 2 | live-inert deploy | NO | enablement changes runtime behavior |
| 3 | behavior-preserving image replacement | NO | env-only, but semantics still change |
| 4 | tests are green | YES | `6c0cf66`: baseline `1896/7 -> 1905/7` |
| 5 | rollback target confirmed | PARTIAL | Tier 1/2 yes, Tier 3 versioning unconfirmed; archive/restore is available |
| 6 | Gemini call increase none | YES | scanner / ledger only |
| 7 | mail volume increase none | PARTIAL | immediate expected delta `0`, but future old_candidate re-entry is possible |
| 8 | source addition none | YES | no source touch |
| 9 | Scheduler change none | YES | none |
| 10 | SEO/noindex/canonical/301 none | YES | none |
| 11 | publish/review/hold/skip criteria unchanged | PARTIAL | core routes unchanged, old_candidate suppression retention window changes |
| 12 | cleanup mutation none | YES | strict POLICY sense: no WP cleanup mutation |
| 13 | candidate disappearance risk none/proven unchanged | YES | risk is re-entry/noise, not disappearance |
| 14 | stop condition written | YES | see section 8.12 |
| +1 | post-deploy verify plan written | YES | see sections 8.10a / 8.10b |

Summary:

- this phase does **not** satisfy `CLAUDE_AUTO_GO`
- failing conditions are structural (`flag ON`, `live-inert NO`, behavior-changing env)
- final classification stays `USER_DECISION_REQUIRED`

## 7. Acceptance Pack 13+1

### 1. Conclusion

- `GO`
- immediate expected prune count is effectively `0`, and the blast radius of an incorrect prune is bounded to duplicate review noise

### 2. Scope

- enable `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL=1`
- keep `PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL_DAYS=7`
- allow scanner to prune only expired rows from `publish_notice_old_candidate_once.json`

### 3. Non-Scope

- no source changes
- no Scheduler change
- no SEO change
- no Gemini prompt/provider/cache change
- no mail routing change
- no WP write / publish / cleanup mutation
- no changes to `real review`, `289`, `cleanup_required`, `preflight_skip`

### 4. Current Evidence

- implementation commit: `6c0cf66`
- bundled deploy image commit: `c796c77`
- commit note: `old_candidate ledger TTL prune - default OFF flag`
- tests recorded in commit message: baseline `1896/7 -> 1905/7`
- prod ledger evidence:
  - `106` rows
  - pre-seed at `2026-05-01 19:35 JST`
  - `40+` permanent dedup skips still observed on `2026-05-02`

### 5. User-Visible Impact

- publish notices: unchanged
- normal review mail: unchanged
- hold mail: unchanged
- old_candidate mail:
  - immediate effect expected `0`
  - after `7d`, pruned old rows can allow a candidate to be shown again once
- X candidate flow: unchanged

### 6. Mail Volume Impact

- immediate expected delta: `0`
- conservative current-day delta: `0-1`
- worst-case unit impact: one wrong deletion can later mean `+1` review mail for that candidate
- `MAIL_BUDGET 100/d` compatibility: immediate enablement is well within budget because expected prune count is `0`

### 7. Gemini / Cost Impact

- Gemini call delta/day: `0`
- API call delta/day: `0`
- Cloud Run executions/day: unchanged
- storage cost: neutral to lower over time because stale rows can be removed

### 7a. Prompt-ID Cost Review

| prompt-id | activation path | Gemini delta/day upper bound | mail volume estimate | API calls/day | cost upper bound | judgment |
|---|---|---:|---|---:|---|---|
| none | no prompt path touched | 0 | `0 immediate`, future old_candidate replay only | 0 | tokens/day `0`, external API/day `0`, Cloud Run/day unchanged | PASS |

Reason: this change touches scanner retention only. No prompt template, fallback prompt, rescue prompt, or cache-key prompt path is edited or activated.

### 8. Silent Skip Impact

- silent skip increase: `none expected`
- TTL prune does not delete candidates from visibility
- failure mode is re-entry, not disappearance
- log-only disappearance is not introduced

### 9. Preconditions

All should be true before Claude asks for final `GO` / `HOLD` / `REJECT`:

1. current ledger object is archived or a known-good archive exists
2. authenticated executor is available for Tier 1 rollback
3. Claude confirms current ledger rows are still effectively all newer than `2026-04-25 JST`
4. no active mail anomaly (`sent burst`, `silent skip`, `errors`) exists at enablement time

### 10. Tests

- commit evidence:
  - new targeted file `tests/test_publish_notice_ledger_ttl_prune.py`
  - `9` cases added
- regression intent from code/test bundle:
  - expired row prunes
  - within-TTL row stays
  - flag OFF baseline unchanged
  - empty ledger no-op
  - full prune to empty
  - partial prune
  - prune-only persist path
  - size non-increase
  - malformed `ts` preserved fail-closed

### 10a. Post-Deploy Verify Plan

After env apply, verify:

1. `gcloud run jobs describe publish-notice` shows TTL flag ON and no unrelated env drift
2. next publish-notice trigger exits cleanly
3. log contains `permanent_dedup_ttl_prune`
4. `count` is `0` or at most the expected tiny bound
5. `errors=0`
6. `silent skip=0`
7. normal review / 289 / error routes remain alive
8. `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` is unchanged

### 10b. Production-Safe Regression Scope

Allowed:

- read-only job describe
- read-only log inspection
- one normal scheduled trigger observation
- state object archive/restore preparation

Forbidden:

- bulk mail experiment
- source addition
- Gemini increase
- publish criteria change
- WP cleanup mutation
- user-GO-less flag ON beyond this ticket

### 11. Rollback

- runtime rollback:
  - Tier 1 env remove command above
  - Tier 2 image revert command above
- source rollback:
  - `git revert 6c0cf66`
- expected rollback time:
  - Tier 1: `~30 sec`
  - Tier 2: `~2-3 min`
  - Tier 3: depends on archive copy, typically `~1-3 min`
- rollback owner: authenticated executor
- last known good runtime anchor before this enablement:
  - env: TTL flag absent
  - image: `publish-notice:9e9302f` (per deploy context)

### 12. Stop Conditions

Stop and rollback if any of these occur:

1. `permanent_dedup_ttl_prune count` is unexpectedly large
2. log errors / traceback appear
3. `silent skip > 0`
4. normal review / `289` / error notifications drop unexpectedly
5. rolling `1h sent > 30` or day total approaches `100`
6. Team Shiny From changes
7. ledger restore target is unavailable after a bad prune

### 13. User Reply

One line only: `GO` / `HOLD` / `REJECT`

## 8. Final Recommendation

`GO`

この enablement は `CLAUDE_AUTO_GO` ではないが、`USER_DECISION_REQUIRED` の中ではかなり低リスクです。理由は、current ledger `106` 件の大半が `2026-05-01 19:35 JST` 以降の recent rows で、`TTL=7d` を `2026-05-02` に ON にしても実際に消える row がほぼ無いからです。誤 prune の worst case も duplicate review noise に留まり、publish path / Gemini / Scheduler / Team Shiny を壊しません。前提は、Claude が env apply 前に current ledger object の archive を確保することです。
