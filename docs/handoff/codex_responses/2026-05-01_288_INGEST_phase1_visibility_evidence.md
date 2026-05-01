# 288-INGEST Phase 1 candidate visibility contract evidence

Date: 2026-05-01 JST  
Mode: Lane B round 20 / read-only verify  
Target commit baseline: `fedf159`

## 1. silent skip violation grep 結果

Verdict:

- `unexpected_new_paths = 0`
- `known_policy_marker_paths != 0`
- POLICY §19.1 の marker は既知の file 群に残っており、Phase 1 を `PASS` にはできない

Read-only grep(`src` text files only, `__pycache__` 除外):

- `src/publish_notice_scanner.py`
  - `REVIEW_POST_DETAIL_ERROR` at `1241`
  - `REVIEW_POST_MISSING` at `1244`
  - `PREFLIGHT_SKIP_MISSING_DEDUPE_KEY` at `1682`
  - `PREFLIGHT_SKIP_MISSING_SOURCE_URL` at `1692`
- `src/tools/draft_body_editor.py`
  - `llm_skip` / `content_hash_dedupe` family at `864-931`, `1242-1243`
- `src/tools/run_draft_body_editor_lane.py`
  - `no_op_skip` at `1083-1107`, `1478-1483`, `1929-1934`
  - `llm_skip` / `refused_cooldown` at `1543-1585`
- `src/repair_fallback_controller.py`
  - `content_hash_dedupe` return path at `202-257`
- `src/llm_call_dedupe.py`
  - `content_hash_dedupe` ledger/cache helpers only

Interpretation:

- `0` なのは「未知の新規 path」であり、marker 自体はまだ codebase 上に存在する
- 特に `publish_notice_scanner.py` の malformed payload skip と `draft_body_editor` lane の `no_op_skip` / `llm_skip` は、POLICY §19.1 が deploy 前 sample verify を要求している既知 path

## 2. candidate visibility 経路 inventory

Contract reference:

- `doc/active/291-OBSERVE-candidate-terminal-outcome-contract.md:17-25`
- `prepared candidate` は `publish / review_notified / hold_notified / skip_notified / error_notified` の 5 terminal outcome に落ちる必要がある
- `Cloud Logging only` は不可

### 2.1 `src/rss_fetcher.py`

Boundary split:

- `pre-prepared filters`
  - `history_duplicate` `13824-13829`
  - `missing_published_at` `13831-13836`
  - `not_giants_related` `13859-13874`
  - `stale_postgame` `13892-13897`
  - `stale_player_status` `13898-13903`
  - `video_promo` `13905-13911`
  - `live_update_disabled` `13912-13918`
  - `comment_required` `13919-13927`
  - `social_too_weak` `13929-13944`
  - `pregame_started` `13985-14001`
  - `thin_source_fact_block` `14080-14104`
- `prepared candidate stage`
  - `weak_generated_title_review` `14271-14292`
  - `weak_subject_title_review` `14293-14315`
  - `duplicate_news_pre_gemini_skip` `14337-14341`
  - `postgame_strict_review` `14342-14361`
  - `manager_quote_zero_review` `14362-14381`
  - `body_contract_validate` `14396-14430`
  - `post_gen_validate` `14431-14451`
  - draft create / publish hold / publish success `14463-14766`

Terminal mapping:

- `post_gen_validate` family:
  - `_log_article_skipped_post_gen_validate()` at `7885-7931`
  - `_record_post_gen_validate_skip_history()` at `8105-8148`
  - scanner route exists only when `ENABLE_POST_GEN_VALIDATE_NOTIFICATION` is true
  - outcome class = `skip_notified` candidate route, conditionally wired
- `body_contract_validate` family:
  - `validate_body_candidate()` returns `action=fail|reroll` in `src/body_validator.py:561-710`
  - fetcher path only increments `skip_reason_counts["body_contract_validate"]`, emits `_log_body_validator_fail()` / `_log_body_validator_reroll()`, then `continue`
  - evidence: `src/rss_fetcher.py:14396-14430`, helper bodies at `13071-13121`
  - outcome class = `log-only`, not `skip_notified`
- immediate publish path:
  - publish success goes through `finalize_post_publication()` after `14675-14683`
  - publish notice then depends on `publish_notice_scanner.scan()` published-post route `1879-1906`
  - outcome class = `publish`
- immediate draft hold path:
  - `publish_skip_reasons` logs `_log_publish_gate_skipped()` / `[下書き維持]` at `13375-13391`, `14630-14766`
  - no direct mail path inside fetcher
  - later visibility depends on downstream guarded-publish/report path, not on fetcher itself
- `pre-prepared filters` listed above:
  - all are counter/log only via `skip_reason_counts` + flow summary at `14772-14820`
  - no terminal mail/digest route in current file

Assessment:

- `post_gen_validate` is the only explicit fetcher-side `skip_notified` route
- `body_contract_validate` is still silent
- several fetcher skip families remain summary/log only, so 291 terminal contract is not yet satisfied

### 2.2 `src/guarded_publish_runner.py`

Evidence:

- `review` report entries -> `refused` + live history row `status="refused"` at `1759-1774`, `2014-2047`
- `red` / `hard_stop` -> `refused` + live history row `status="refused"` at `1955-2013`
- verdict-filter `held_entries` -> `skipped` + `hold_reason` at `2054-2092`
- `backlog_only` -> `skipped` + `hold_reason="backlog_only"` at `2093-2143`
- `backlog_deferred_for_fresh` -> `skipped` at `2150-2195`
- `hourly_cap` / `burst_cap` / `daily_cap` -> `skipped` at `2212-2294`
- `CandidateRefusedError` / cleanup / duplicate candidate -> `refused` at `2330-2416`
- publishable candidates -> `proposed_public` / `proposed_internal` at `2418-2421`
- live publish -> `status="sent"` or `status="refused"` history rows at `2423-2503`

Terminal mapping:

- downstream output is explicit:
  - `proposed` = publish candidate
  - `refused` = review/hold candidate metadata
  - `executed.status in {"sent","refused","skipped"}` when live
- this file does produce durable terminal metadata in `guarded_publish_history.jsonl`
- scanner later converts eligible `refused/skipped` records into review/hold mail

Assessment:

- guarded-publish itself is visibility-friendly
- the gap is not in `proposed/refused` generation but in what reaches this runner from upstream

### 2.3 `src/publish_notice_scanner.py`

Positive routes:

- published posts -> `PublishNoticeRequest` queued at `1879-1906`
- guarded review/hold -> `scan_guarded_publish_history()` emits review requests at `1205-1304`
- class reserve defaults after fix #6:
  - real review `3`
  - post-gen-validate `2`
  - error `1`
  - evidence `34-41`, `84-90`, `1036-1104`, `1926-2000`
- `post_gen_validate` ledger -> request queue at `1477-1539`
- `preflight_skip` ledger -> request queue at `1673-1733`

Known non-visible drops:

- guarded review fetch errors:
  - `REVIEW_POST_DETAIL_ERROR` `1238-1242`
  - `REVIEW_POST_MISSING` `1243-1245`
- preflight malformed payload:
  - `PREFLIGHT_SKIP_MISSING_DEDUPE_KEY` `1679-1683`
  - `PREFLIGHT_SKIP_MISSING_SOURCE_URL` `1689-1693`
- these branches append to `skipped[]` only and do not create `PublishNoticeRequest`

Assessment:

- scanner is the mail visibility hub once ledger/input is well-formed
- malformed review/preflight payloads still break the contract

### 2.4 `src/tools/draft_body_editor.py` / `src/tools/run_draft_body_editor_lane.py` / `src/repair_fallback_controller.py`

Evidence:

- editor dedupe path emits `llm_skip` and may return cached success or fail without new mail route
  - `src/tools/draft_body_editor.py:873-934`, `1232-1245`
- lane-level skip aggregation is JSON/session-log only
  - `_append_skip_outcome()` `1068-1080`
  - summary payload `1145-1174`
  - `_emit_no_op_skip_log()` `1083-1107`
- `no_repair_candidates` no-op at `1477-1500`
- `refused_cooldown` skip at `1543-1585`
- `api_fail` / `input_error` / `put_fail` remain per-run summary/session-log outcomes at `1636-1697`, `1780-1902`
- all-dedupe/all-cooldown emits `no_op_skip` at `1928-1934`
- fallback controller reuses `content_hash_dedupe` in memory/ledger only at `202-257`

Assessment:

- editor lane has good machine-readable skip accounting
- it does not connect to publish-notice mail/digest
- this is a known POLICY §19.1 marker family, still log/ledger-only

## 3. `body_contract_validate` visibility

Current code path:

1. `validate_body_candidate()` decides `accept / reroll / fail` in `src/body_validator.py:561-710`
2. fetcher consumes result at `src/rss_fetcher.py:14396-14430`
3. failure branch only calls:
   - `_log_body_validator_fail()` `13097-13121`
   - `_log_body_validator_reroll()` `13071-13095`
4. branch ends with `continue`

What is missing:

- no `_record_post_gen_validate_skip_history()` call
- no dedicated body-contract ledger
- no `publish_notice_scanner` consumer for body-contract failures

Policy/doc alignment:

- `doc/active/291-OBSERVE-candidate-terminal-outcome-contract.md:29-38`
  - explicitly names `body_contract_validate` as a known silent path
- `doc/active/292-OBSERVE-body-contract-fail-notification.md:17-18`
  - goal is to stop ending this path with log only
- `doc/active/292-OBSERVE-body-contract-fail-notification.md:55-63`
  - acceptance requires ledger + publish-notice scan + mail emit

Judgement:

- current state = `log-only`
- 289 route does not cover it
- improvement required = `YES`

## 4. 新 source 追加時 risk 想定

Source-specific observations:

- `sponichi.co.jp` and `sanspo.com` already exist in `src/source_trust.py:60-72`
- `NNN` / `news.ntv.co.jp` / `nnn.co.jp` have no trust profile hit in current source tree

Likely new skip patterns if Phase 3 adds `NNN web / スポニチ web / サンスポ web`:

1. `source_attribution_ambiguous` or related body-contract failure
- especially likely for `NNN` because trust/family registration is absent
- current visibility: `body_contract_validate` branch is log-only

2. cross-source duplicate/title-collision growth
- new web sources increase same-story multi-source collisions
- current fetcher-side `history_duplicate` and pre-gemini duplicate skips are not mail-visible
- 288 draft already forbids source-distinct silent disappearance

3. short or quote-less web headlines
- can increase `comment_required`, `thin_source_fact_block`, `weak_subject_title`, `weak_generated_title`
- visibility split:
  - `weak_*` under `post_gen_validate` can become visible when flag/path is active
  - `comment_required` and `thin_source_fact_block` stay log/counter only

4. live ticker / partial game snippets
- can increase `live_update_disabled` and subtype misclassify fallout
- current visibility: log/counter only in fetcher

5. malformed downstream payload risk
- if Phase 2 fallback/trust work emits incomplete review/preflight data, scanner can still drop records as:
  - `REVIEW_POST_DETAIL_ERROR`
  - `REVIEW_POST_MISSING`
  - `PREFLIGHT_SKIP_MISSING_*`
- current visibility: `skipped[]` only, no request queued

## 5. Phase 1 OBSERVED 判定

Judgement: `FAIL`

Reason:

- 291 contract requires mail/digest-visible terminal outcomes for prepared candidates
- current codebase still has at least these contract breaks:
  1. `body_contract_validate` is log-only
  2. malformed guarded/preflight review payloads are skipped without notification
  3. draft-body-editor `no_op_skip` / `llm_skip` / cooldown families are log/ledger only
  4. multiple fetcher skip families remain counter/log only outside the explicit `post_gen_validate` ledger path

What is still true:

- `0` unexpected grep paths were found
- guarded-publish and publish-notice core mail routes are structurally present
- `post_gen_validate` and `preflight_skip` notification code paths exist behind env-gated scanners

Why not `PARTIAL`:

- this is not just missing evidence; the repo already contains explicit log-only branches that 291/292 docs classify as unresolved silent paths

## 6. Phase 2 fallback + trust impl への引継ぎ事項

1. Do not add source URLs before closing `body_contract_validate` visibility.
2. For `NNN`, trust/family registration is not optional; otherwise source attribution risk stays concentrated there.
3. Phase 2 fallback/trust work should preserve well-formed payload guarantees so scanner never emits `REVIEW_POST_*` or `PREFLIGHT_SKIP_MISSING_*`.
4. If duplicate/title-collision handling changes, require visible terminal evidence for the losing source-distinct candidate.
5. Keep 289/292/291 ordering intact:
   - `289` stable route for `post_gen_validate`
   - `292` body-contract notification
   - `291` unified terminal accounting
   - only then Phase 3 source add

## 7. Summary for Claude

- `unexpected_new_policy_paths = 0`
- `known_log_only_or_drop_families = present`
- `phase_1_observed = FAIL`
- immediate blocker for 288 source add is still visibility contract, not source list mechanics
