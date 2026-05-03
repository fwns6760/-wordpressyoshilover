# 2026-05-03 BUG-004+291 review-stuck + draft-stuck track

作成: 2026-05-03 15:20 JST 以降  
監査窓: **2026-05-03 09:00:00-15:00:00 JST** (`2026-05-03T00:00:00Z`-`2026-05-03T06:00:00Z`)

## scope

- read-only / doc-only
- src / tests / config change: 0
- deploy / env / Scheduler / WP REST / Gemini / mail mutation: 0
- live read:
  - `gcloud logging read`
  - `gcloud run jobs describe guarded-publish`
  - read-only state rows:
    - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
    - `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`

## live target confirmation

`gcloud run jobs describe guarded-publish --project=baseballsite --region=asia-northeast1`

| item | value |
|---|---|
| job generation | `21` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc` |
| env | `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1` |

## evidence basis

### fetcher side

- Cloud Logging `resource.labels.service_name="yoshilover-fetcher"`
- `rss_fetcher_run_summary`
- `rss_fetcher_flow_summary`
- `title_template_selected`
- `article_skipped_post_gen_validate`
- `body_validator_fail`
- `title_player_name_review`
- `weak_title_narrow_unlock`
- text lines:
  - `[下書き維持] post_id=...`
  - `[下書き止め] post_id=...`
  - `[公開] post_id=...`
  - `[公開済み] post_id=...`

### publish-notice side

- Cloud Logging `resource.labels.job_name="publish-notice"`
- `[summary] sent=... suppressed=... errors=... reasons=...`
- `[skip] post_id=... reason=...`
- `publish_notice/queue.jsonl`

### guarded-publish side

- durable history: `guarded_publish_history.jsonl`
- Cloud Logging sanity: `duplicate_target_integrity_check`

Note:

- fetcher logs are not `jsonPayload`; they are `textPayload` with embedded JSON.
- guarded-publish stdout is fragmented in Cloud Logging, so **candidate-level gate counts are taken from durable history**, with Cloud Logging used to confirm duplicate-integrity behavior.
- guarded-publish subtype labels are partly inferred from `publish_notice/queue.jsonl` subjects and are therefore **heuristic**. For the first 6 duplicate near-miss rows, precise subtype attribution is cross-checked against [2026-05-03_BUG004_291_guarded_gate_audit.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-03_BUG004_291_guarded_gate_audit.md).

## window summary

| metric | count |
|---|---:|
| fetcher runs | `74` |
| fetcher drafts_created | `32` |
| fetcher skip_duplicate | `1248` |
| fetcher skip_filter | `8179` |
| fetcher error_count | `0` |
| publish-notice sent | `8` |
| publish-notice suppressed | `25` |
| publish-notice errors | `0` |
| guarded-publish unique post_ids in window | `180` |
| guarded latest `sent` | `8` |
| guarded latest non-sent | `172` |

## phase 1: review-stuck candidate accounting

### 1.1 unique review-stuck total

- unique review-stuck candidates: **21**
- source of count: union of `article_skipped_post_gen_validate` `source_url_hash`

### 1.2 subtype x gate (unique)

| subtype | gate | unique candidates |
|---|---|---:|
| `postgame` | `postgame_strict_review_fallback` | `12` |
| `farm` | `weak_generated_title_review` | `3` |
| `farm` | `close_marker` | `1` |
| `general` | `close_marker` | `1` |
| `general` | `intro_echo` | `1` |
| `lineup` | `post_gen_validate_no_game_but_result` | `1` |
| `manager` | `weak_generated_title_review` | `1` |
| `player` | `weak_generated_title_review` | `1` |

### 1.3 fail_axis breakdown

#### raw

| fail_axis | raw hits |
|---|---:|
| `postgame_strict_review` | `463` |
| `weak_generated_title:no_strong_marker` | `99` |
| `weak_generated_title:blacklist_phrase:ベンチ関連の発言ポイント` | `69` |
| `close_marker` | `36` |
| `NO_GAME_BUT_RESULT` | `23` |
| `intro_echo` | `1` |

#### unique

| fail_axis | unique candidates |
|---|---:|
| `postgame_strict_review` | `12` |
| `weak_generated_title:no_strong_marker` | `4` |
| `close_marker` | `2` |
| `NO_GAME_BUT_RESULT` | `1` |
| `intro_echo` | `1` |
| `weak_generated_title:blacklist_phrase:ベンチ関連の発言ポイント` | `1` |

### 1.4 review-stuck read

- **review volumeの主因は postgame strict**。`12 unique / 463 raw` で、review familyの中では圧倒的。
- **manager lane は duplicate/body ではなく weak title**。`title_player_name_review` raw `154`、`weak_generated_title:blacklist_phrase...` raw `69` が残る。
- **lineup lane の review は 1 系統だけ**。Yahoo game page 由来 `NO_GAME_BUT_RESULT` 1 unique。

## phase 2: body_contract / pre-publish stop accounting

### 2.1 unique body_contract stop

- unique body-contract blocked candidates: **13**

| subtype | gate | unique candidates |
|---|---|---:|
| `postgame` | `no_game_but_result` | `11` |
| `farm` | `no_game_but_result` | `2` |

### 2.2 fail axes

| fail_axis | raw hits | unique candidates |
|---|---:|---:|
| `NO_GAME_BUT_RESULT` | `451` | `13` |
| `first_block_mismatch` | `319` | n/a same rows |
| `required_block_missing` | `319` | n/a same rows |

### 2.3 terminal view after `title_template_selected`

This is the `title_template_selected` unique source universe only, so **pre-template weak-title review is not included**.

| terminal gate | unique candidates |
|---|---:|
| `created_or_downstream` | `32` |
| `no_game_but_result` | `13` |
| `postgame_strict_review_fallback` | `12` |
| `close_marker` | `2` |
| `post_gen_validate_no_game_but_result` | `1` |

Read:

- `title_template_selected` 以降で止まる主因は `postgame_strict_review_fallback` と `body_contract(NO_GAME_BUT_RESULT)`。
- weak-title family は **title-template 前段**で落ちているため、この terminal view には乗らない。

## phase 3: draft-stuck accounting

### 3.1 fetcher created vs downstream publish

- `drafts_created=32`
- fetcher terminal lines上、**32/32 が一旦 draft 維持**
- そのうち **7/32** は 15:00 JST までに guarded-publish downstream で `sent`
- 残り **25/32** が draft-stuck

`publish-notice sent_total=8` との差分 `1` は、**当日 09:00 以降の新規作成 draft ではない既存候補**が window 内で publish-notice を出したため。

### 3.2 draft-stuck reason (25 stopped / 7 sent)

| latest downstream reason | count |
|---|---:|
| `hard_stop_farm_result_placeholder_body` | `11` |
| `review_duplicate_candidate_same_source_url` | `8` |
| `hard_stop_death_or_grave_incident` | `4` |
| `review_date_fact_mismatch_review` | `2` |
| `sent` | `7` |

### 3.3 draft-stuck read

- **draft-stuck の最多理由は placeholder**。これは `farm_result` 系の本文欠落で、publish阻害として正当。
- **2番手は same_source_url duplicate review**。ここが user 指示の「guarded-publish 後段で publish 化されない」系の主要 near-miss。
- **numeric/date review は 2件**で、volume主因ではない。

## phase 4: guarded-publish post-gate accounting

### 4.1 latest outcome by unique post_id

| latest status in window | unique post_ids |
|---|---:|
| `skipped` | `130` |
| `refused` | `42` |
| `sent` | `8` |

### 4.2 hold_reason (unique latest state)

| hold_reason | unique post_ids |
|---|---:|
| `backlog_only` | `130` |
| `hard_stop_farm_result_placeholder_body` | `18` |
| `hard_stop_death_or_grave_incident` | `9` |
| `review_duplicate_candidate_same_source_url` | `8` |
| `review_date_fact_mismatch_review` | `6` |
| `hard_stop_lineup_duplicate_excessive` | `1` |

### 4.3 gate family counts (unique latest state)

| gate family | unique post_ids | note |
|---|---:|---|
| `backlog_only` | `130` | freshness/backlog 起因 |
| `placeholder` | `18` | `farm_result_placeholder_body` |
| `duplicate` | `9` | `same_source_url` 8 + `lineup_duplicate_excessive` 1 |
| `numeric` | `6` | `review_date_fact_mismatch_review` |
| `body_contract` | `0` | guarded後段では未実装。upstream fetcher 側で `13 unique` |
| `review_hold` | `0` | family単独の latest stop は今回なし。review系は duplicate/numeric に集約 |
| `other` | `17` | 主に `hard_stop_death_or_grave_incident` |

### 4.4 subtype / scope notes

- `backlog_only` は subject heuristic で `other / lineup / notice / comment / injury` に分散して見えるが、**history row に subtype が無いため broad bucket 扱い**に留める。
- `placeholder` は code path 上 **`farm_result` 限定**で扱ってよい。
- duplicate near-miss 8件のうち、**6件は `duplicate_target_source_url=https://platform.twitter.com/widgets.js` が history row に残る**。
- duplicate near-miss の precise subtype は [2026-05-03_BUG004_291_guarded_gate_audit.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-03_BUG004_291_guarded_gate_audit.md) の 14:43 JST 監査を正とすると、最初の 6 件は `farm_result 2 / lineup 2 / farm_lineup 1 / injury_recovery_notice 1`。  
  15:00 まで拡張すると **同系の same_source_url review が 2 件追加**され、total は `8`。

## phase 5: publish-notice visibility layer

### 5.1 summary totals

| metric | total |
|---|---:|
| sent | `8` |
| suppressed | `25` |
| errors | `0` |

suppression reasons:

| reason | count |
|---|---:|
| `PUBLISH_ONLY_FILTER` | `24` |
| `BACKLOG_SUMMARY_ONLY` | `1` |

### 5.2 skip line reasons

| reason | raw hits |
|---|---:|
| `POST_GEN_VALIDATE_RECENT_DUPLICATE` | `4742` |
| `OLD_CANDIDATE_PERMANENT_DEDUP` | `226` |
| `REVIEW_RECENT_DUPLICATE` | `32` |

Read:

- `PUBLISH_ONLY_FILTER` は **mail suppress** であって publish blocker ではない。
- ただし review visibility は publish-notice 層でかなり dedupe/suppress されているため、**mail volume減少 = publish-path回復**ではない。

## phase 6: scope-eligible subset cross-reference

### upstream worker A cross-reference

Reference: [2026-05-03_BUG004_291_cross_subtype_track.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-03_BUG004_291_cross_subtype_track.md)

- strict scope-eligible upstream stuck set: **14 unique**
  - `postgame_strict_review_fallback = 12`
  - `farm close_marker = 1`
  - `lineup NO_GAME_BUT_RESULT = 1`

### subtask-10b expected resolution

Reference: [2026-05-03_BUG004_291_subtask10a_postgame_recovery_design.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-03_BUG004_291_subtask10a_postgame_recovery_design.md)

- worker A 14件のうち、`postgame_strict` 12件は further triage 済み
- **safe rescue target = 5**
- therefore subtask-10b の期待解消数は **5**
- subtask-10b 後も残る upstream gap は **9**
  - unresolved `postgame_strict` = `7`
  - `farm close_marker` = `1`
  - `lineup NO_GAME_BUT_RESULT` = `1`

### guarded-publish near-miss cross-reference

Reference: [2026-05-03_BUG004_291_guarded_gate_audit.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-03_BUG004_291_guarded_gate_audit.md)

- 14:00 JST までの worker B near-miss: **6**
- 15:00 JST まで拡張した本監査: **8**
- interpretation:
  - **6** = widget-script anchor が history row に見えている fully evidenced false-duplicate track
  - **2** = same_source_url review だが target source field が row に無い legacy/partial-evidence repeat

## final judgment

### top stop reasons

1. **review-stuck 主因** = `postgame_strict_review_fallback`
   - `12 unique / 463 raw`
   - ただし worker A triage 済みで **safe rescue は 5**
2. **draft-stuck 主因** = `hard_stop_farm_result_placeholder_body`
   - `11/32` created drafts
   - legitimate exclusion
3. **guarded post-gate near-miss 主因** = `review_duplicate_candidate_same_source_url`
   - `8 unique latest stops`
   - `6` は `platform.twitter.com/widgets.js` anchor 明示
4. **always-on volume 主因** = `backlog_only`
   - `130 unique / 9394 raw rows中の majority`
   - publish-path全体を細らせるが、scope-eligible recovery target ではない

### legitimacy assessment

| gate | assessment |
|---|---|
| `hard_stop_farm_result_placeholder_body` | legitimate exclusion |
| `hard_stop_death_or_grave_incident` | legitimate exclusion on current evidence |
| `review_date_fact_mismatch_review` | probably legitimate until fact mismatch samples prove otherwise |
| `backlog_only` | largely legitimate policy gate; not a same-day recovery target |
| `postgame_strict_review_fallback` | mixed: gate自体は維持妥当、ただし source-derived fact pickup不足で **5件は過剰除外** |
| `review_duplicate_candidate_same_source_url` | **over-exclusion suspect**; widgets.js anchor is the concrete false-positive lead |
| `body_contract(NO_GAME_BUT_RESULT)` | mixed: some are legitimate, but `lineup 1` と `farm close_marker 1` は narrow follow-up候補 |

### what subtask-10b will and will not solve

- solve:
  - `postgame_strict` rescue **5**
- will not solve:
  - widgets.js duplicate review **8**
  - placeholder **11 created-draft stuck / 18 guarded unique**
  - numeric/date review **2 created-draft stuck / 6 guarded unique**
  - farm `close_marker` **1**
  - lineup `NO_GAME_BUT_RESULT` **1**
  - manager weak-title lane **1 unique / 69 raw**

### remaining gap candidates after subtask-10b

1. **duplicate target source anchor narrowing**
   - focus: `review_duplicate_candidate_same_source_url`
   - strongest concrete lead: `platform.twitter.com/widgets.js`
2. **body_contract durable accounting completion**
   - current guarded後段 count is `0` by design
   - actual upstream blocked set is `13 unique`
3. **manager weak-title deterministic backfill**
   - raw `69`, unique `1`
4. **lineup/farm NO_GAME_BUT_RESULT follow-up**
   - `lineup 1` review
   - `farm 2` body-contract stop

## answer to the user question

- **要確認(review)止まり candidate** は raw では `postgame_strict_review` が圧倒的、unique では **21**。scope-eligible strict set は worker A 基準で **14**。
- **draft 止まり candidate** は `drafts_created=32` のうち **25**。停止理由は `placeholder 11 / same_source_url duplicate 8 / death_or_grave 4 / date_fact_mismatch 2`。
- **guarded-publish 後段で publish 化されない理由** は unique latest で `backlog_only 130 / placeholder 18 / death_or_grave 9 / duplicate same_source_url 8 / numeric 6 / lineup duplicate 1`。hidden cleanup/cap stop は今回観測されていない。
- **subtask-10b** が解消できるのは **5件**。残りは duplicate anchor / body_contract accounting / weak-title / lineup/farm narrow follow-up が必要。
