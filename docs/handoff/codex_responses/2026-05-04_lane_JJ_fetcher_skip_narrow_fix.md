# 2026-05-04 Lane JJ fetcher skip narrow fix

作成: 2026-05-04 JST

## scope

- lane: `JJ`
- target: `src/rss_fetcher.py`
- goal: fetcher 内部 skip filter の過剰判定を narrow に緩め、priority source / fan-important 巨人情報だけ draft path に通す
- live mutation in this executor: `none`
- authenticated executor required for Step 8-9: `yes`

## evidence boundary

- direct Cloud Logging query for the user-specified `2026-05-04 00:13-00:26 JST` 5-cycle window was not available in this sandbox
- Step 1-2 below are reconstructed from repo-visible evidence only:
  - [2026-05-04_lane_II_hochi_rss_funnel_audit.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-04_lane_II_hochi_rss_funnel_audit.md)
  - [291-OBSERVE-candidate-terminal-outcome-contract.md](/home/fwns6/code/wordpressyoshilover/doc/waiting/291-OBSERVE-candidate-terminal-outcome-contract.md)
- user-provided live summary counts used as external field input:
  - `post_gen_validate=10`
  - `body_contract_validate=12`
  - `social_too_weak=21`
  - `history_duplicate=18`
  - `pregame_started=6`
  - `comment_required=2`
  - `live_update_disabled=3`

## Step 1: priority-source / fan-important per-id skip slice

Repo-visible high-signal blocked rows from the latest hochi funnel evidence:

| rss_id | source_url | title | skip_reason | subtype estimate | fan-important hits |
|---|---|---|---|---|---|
| `2050885171277099230` | `https://twitter.com/hochi_giants/status/2050885171277099230` | `【巨人】松浦慶斗が初回から緊急リリーフ...` | `pregame_started` | `live_update` / `pregame` | `松浦`, `緊急リリーフ` |
| `2051031133790380168` | `https://twitter.com/hochi_giants/status/2051031133790380168` | `あえて巨人戦はチェックせず 泉口友汰が明かした負傷離脱中の心境` | `social_too_weak` | `player` | `泉口`, `負傷`, `離脱` |
| `2050891541141483536` | `https://twitter.com/hochi_giants/status/2050891541141483536` | `【巨人】ドラ２・田和廉が球団新を更新する１２試合連続無失点 ...` | `social_too_weak` | `player` / `farm_player_result` | `球団新`, `連続無失点` |
| `2051067937851891869` | `https://twitter.com/hochi_giants/status/2051067937851891869` | `「菅野智之さん 安否ヨシッ！」元巨人・宮国椋丞さんが...` | `social_too_weak` | `general` / `column` | `元巨人`, `OB` |
| `2051037501184167955` | `https://twitter.com/hochi_giants/status/2051037501184167955` | `巨人・戸郷翔征「遅くなりましたけど」今季初登板...` | `post_gen_validate` + `postgame_strict_review` | `player` / `pregame` | `戸郷` |
| `2050872467724669124` | `https://twitter.com/hochi_giants/status/2050872467724669124` | `【番記者Ｇ戦記】...橋上コーチ「イメージを変えるような投...」` | `post_gen_validate` + `postgame_strict_review` | `coach_comment` / `postgame` | `コーチ`, `コメント` |

Non-target but important control rows from the same hochi audit:

| rss_id | current state | note |
|---|---|---|
| `2051029788702187840` | earlier draft created, latest rescan `history_duplicate`, later guarded review | fetcher narrow fix targetではない |
| `2051036146163929091` | earlier draft created, later guarded `hard_stop_lineup_duplicate_excessive` | real duplicate-family stop |
| `2051067520736702585` | earlier draft created, later guarded `review_date_fact_mismatch_review` | fetcher narrow fix targetではない |

## Step 2: skip_reason 過剰判定切り分け

### `social_too_weak`

- lane II hochi sample `20` entries中 `10` 件がここで止まっていた
- そのうち repo-visible で user priority に直結する misses:
  - `泉口` injury/return context
  - `田和廉` record/data context
  - `元巨人・宮国` alumni context
- conclusion:
  - current social authority gate is too blunt for `hochi_giants` + fan-important Giants content
  - narrow exempt is justified

### `pregame_started`

- lane II hochi sampleでは `1` 件
- the blocked row was `松浦慶斗 / 緊急リリーフ`
- conclusion:
  - generic stale pregame は止めるべき
  - injury / emergency / manager-comment familyだけ exempt なら narrow

### `post_gen_validate`

- lane II hochi sampleでは blocked `2` 件
- one is clear player-priority (`戸郷`)
- one is coach-comment/postgame hybrid
- current patch decision:
  - rescue only `weak_title` family and `close_marker` only
  - do **not** rescue `postgame_strict_review` or broader strict fallback

### `body_contract_validate`

- exact 5/4 `00:13-00:26 JST` per-id rows were not repo-visible here
- repo-visible current evidence in the parent ticket shows body-contract misses are often `reroll`-class format mismatches such as `first_block_mismatch` / `block_order_mismatch`, not hard-fail fact corruption
- current patch decision:
  - rescue only `action=reroll`
  - keep `action=fail` blocked

### `history_duplicate`

- repo-visible hochi rows that surfaced here had already reached draft creation in earlier runs
- real duplicate and already-published-family suppression is a user stop condition
- current patch decision:
  - unchanged

## Step 3-4: code patch

Code commit:

| item | value |
|---|---|
| commit | `1ccda1b` |
| message | `bug-004-291: fetcher fan-important narrow exempt for priority source + injury/return/coach (default OFF)` |

Implementation summary:

- added env flag:
  - `ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT`
- added helper family in `src/rss_fetcher.py`:
  - `_fetcher_fan_important_narrow_exempt_enabled()`
  - `_build_fan_important_priority_content_context(...)`
  - `_is_fan_important_priority_content(...)`
  - `_fetcher_fan_important_narrow_exempt_context(...)`
  - `_log_fetcher_fan_important_narrow_exempt(...)`
- priority source logic:
  - `hochi.news`
  - `sports.hochi.co.jp`
  - `hochi` family via source-trust
  - handles `hochi_giants`, `sportshochi`, `hochi_baseball`
- fan-important signals:
  - `戸郷`, `泉口`, `松浦`
  - `二軍 / 三軍 / ファーム / 育成`
  - `OB / 元巨人`
  - `故障 / 負傷 / 離脱 / 復帰 / 1軍合流`
  - `緊急降板 / 緊急リリーフ`
  - `球団新 / 連続無失点 / 記録室`

Hooked skip sites:

- `live_update_disabled`
- `comment_required`
- `social_too_weak`
- `pregame_started`
- weak-title review path:
  - `_maybe_route_weak_generated_title_review`
  - `_maybe_route_weak_subject_title_review`
- late validators:
  - `body_contract_validate` only when `action=reroll`
  - `post_gen_validate` only when `fail_axes == {"close_marker"}`

Kept unchanged:

- `history_duplicate`
- `postgame_strict_review`
- `body_contract_validate action=fail`
- hard-stop / obituary-like content
- placeholder-like content
- old lineup-only stale rows

## Step 5-6: tests

Added:

- [tests/test_rss_fetcher_fan_important_narrow_exempt.py](/home/fwns6/code/wordpressyoshilover/tests/test_rss_fetcher_fan_important_narrow_exempt.py)

Covered positive cases:

- `social_too_weak`
- `comment_required`
- `live_update_disabled`
- `pregame_started`
- `body_contract_validate(action=reroll)`
- `post_gen_validate(close_marker only)`
- `weak_generated_title`

Covered negative / guardrail cases:

- `history_duplicate`
- `body_contract_validate(action=fail)`
- `post_gen_validate(close_marker + extra axis)`
- obituary / hard-stop row
- flag OFF inert for weak-title route

Pytest:

```bash
python3 -m pytest tests/test_rss_fetcher_fan_important_narrow_exempt.py -q
python3 -m pytest tests/test_rss_fetcher_*.py -q
```

Result:

- `9 passed` on the new focused file
- `60 passed`, `47 subtests passed` on `tests/test_rss_fetcher_*.py -q`
- warnings: `3`, all pre-existing dependency warnings only

## Step 7: commit

- repo implementation commit created: `1ccda1b`
- push: `not run` (Claude lane)

## Step 8: image build + env apply

Status in this executor: `plan only`

Reason:

- network/authenticated live GCP mutation is outside this sandbox boundary

Authenticated executor commands:

```bash
gcloud builds submit \
  --project=baseballsite \
  --tag=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:1ccda1b

gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:1ccda1b

gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT=1
```

Expected post-apply verify:

- service image tag = `:1ccda1b`
- env contains `ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT=1`
- pre-existing envs remain unchanged

## Step 9: live verify + publish-forward

Status in this executor: `not executed`

Expected verify window:

1. watch next `5-15 min` fetcher cycles
2. confirm `fetcher_fan_important_narrow_exempt` events appear for rescued rows
3. confirm rescued rows reach draft creation
4. confirm guarded-publish either:
   - `sent`, or
   - explicit review/hold terminal state
5. if a rescued id still stalls, use per-id Lane ZZ re-eval only after durable reason is known

New public URLs from Lane JJ session:

- none yet

New publish-notice mail timestamps from Lane JJ session:

- none yet

Relevant pre-existing hochi publishes from Lane II reference:

| post_id | public URL | mail timestamp JST |
|---|---|---|
| `64394` | `https://yoshilover.com/64394` | `2026-05-03 19:36:31.963`, `19:37:39.164` |
| `64396` | `https://yoshilover.com/64396` | `2026-05-03 19:11:09.067` |
| `64405` | `https://yoshilover.com/64405` | `2026-05-03 20:11:02.087` |
| `64418` | `https://yoshilover.com/64418` | `2026-05-04 05:31:06.096` |

## Step 10: rollback

### repo rollback

```bash
git revert 1ccda1b
```

### runtime rollback

Remove the env flag:

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT
```

If image rollback is needed, restore the last known fetcher image recorded in the repo before Lane JJ apply:

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:e0a58bb
```

Rollback trigger:

- any real duplicate rescued into publish
- placeholder / hard-fail body rescued into publish
- Giants-unrelated publish
- obituary / grave hard-stop leak
- mail burst anomaly
