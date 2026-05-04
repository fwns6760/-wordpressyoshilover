# 2026-05-04 body template v2 deploy result

## Summary

- Result: `PARTIAL / NEEDS ONE MORE LIVE SAMPLE`
- Reason:
  - `ENABLE_BODY_TEMPLATE_V2=1` is now live on `yoshilover-fetcher`.
  - First env-only rollout landed on revision `00191-v58`, but that revision still ran image digest tagged `1b003ec`, not `dce7622`.
  - After correcting the service image to existing registry tag `dce7622`, revision `00192-n8g` produced live `game_v2` / `social_v2` drafts.
  - Acceptance target required `3+` new posts. The 15-minute observation window produced only `2` new drafts on the corrected revision.

## Step 1 read-only verify

- `git log --oneline -5` confirmed `dce7622 lane-QQ: body template v2 section header rename + H3 reduction (preview only, default OFF)` is on `master`.
- Preview docs reviewed:
  - `docs/handoff/codex_responses/2026-05-04_lane_QQ_template_v2_preview.md`
  - `docs/handoff/codex_responses/2026-05-04_lane_QQ_template_audit.md`
- Repo spot-check confirmed:
  - `ENABLE_BODY_TEMPLATE_V2_ENV_FLAG` exists in `src/rss_fetcher.py`.
  - `MANAGER_REQUIRED_HEADINGS_V2`, `GAME_REQUIRED_HEADINGS_V2`, `FARM_REQUIRED_HEADINGS_V2`, `NOTICE_REQUIRED_HEADINGS_V2` exist.
  - `SOCIAL_REQUIRED_HEADINGS_V2` renames `【発信内容の要約】` -> `【投稿で出ていた内容】`.
  - `MANAGER_REQUIRED_HEADINGS_V2` renames `【文脈と背景】` -> `【この話が出た流れ】`.
  - Generic section heading switches `【ここに注目】` -> `【今回のポイント】` when v2 is enabled.
  - `_rendered_heading_level()` demotes the auxiliary section to `H4`, matching the `H3<=2` preview contract.
- Targeted baseline test:
  - `pytest -x -q tests/ -k "template_v2 or body_template"`
  - Result: `34 passed, 2227 deselected, 0 failures`
  - Pre-existing failures in this targeted slice: `0`

## Deploy chronology

### A. Initial env-only flip

- Previous ready revision: `yoshilover-fetcher-00190-tj8`
- Command applied:
  - `gcloud run services update yoshilover-fetcher --region=asia-northeast1 --update-env-vars=ENABLE_BODY_TEMPLATE_V2=1`
- New revision: `yoshilover-fetcher-00191-v58`
- Env check after rollout:
  - `RUN_DRAFT_ONLY=1`
  - `ENABLE_BODY_TEMPLATE_V2=1`

### B. Live mismatch found on 00191

- `00191-v58` log evidence:
  - `2026-05-04T10:01:46Z social_body_template_applied ... post_id=64528 ... template_version=social_v1`
- Revision/image evidence:
  - `00190-tj8` and `00191-v58` both pointed to digest `sha256:9630ca4d...`
  - Artifact Registry tag lookup mapped that digest to tag `1b003ec`
  - Artifact Registry already had tag `dce7622` at digest `sha256:97ccb6e3...`
- Conclusion:
  - The user assumption "current image already contains dce7622" was false for live fetcher.
  - Env was reflected, but the running image was not the Lane QQ image.

### C. Corrective image switch without rebuild

- Because `dce7622` already existed in Artifact Registry, no rebuild was needed.
- Command applied:
  - `gcloud run services update yoshilover-fetcher --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:dce7622`
- Final ready revision: `yoshilover-fetcher-00192-n8g`
- Final live image digest:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher@sha256:97ccb6e352bcfdd89cea9696c7a77beecb3ec1a986df998e1569b88515cdfed3`
- Final env check:
  - `RUN_DRAFT_ONLY=1`
  - `ENABLE_BODY_TEMPLATE_V2=1`

## Live verify window

- Effective v2 observation window start: `2026-05-04 19:04:56 JST`
- Observation end: `2026-05-04 19:19:46 JST`

### Run summaries on corrected revision `00192-n8g`

- `2026-05-04T10:07:32Z`
  - `drafts_created=0`
  - `error_count=0`
- `2026-05-04T10:11:38Z`
  - `drafts_created=2`
  - `error_count=0`
- `2026-05-04T10:16:59Z`
  - `drafts_created=0`
  - `error_count=0`

### New posts created on corrected revision

#### 1. post_id `64532`

- Status: `draft` (from `[WP] 記事draft`)
- Title: `【記事全文】巨人 脳振とう特例措置から復帰の泉口友汰が第1打席で即、左前打！…`
- URL:
  - `https://yoshilover.com/?p=64532`
- Source/type evidence:
  - `game_body_template_applied`
  - `subtype=pregame`
  - `template_version=game_v2`
  - `section_count=3`
- H3 count:
  - Direct WP body fetch from this sandbox failed on DNS resolution, so exact live HTML H3 count was not inspectable here.
  - Based on the reviewed v2 contract for `pregame`, expected H3 count remains `<=2`.
- Forbidden headings / phrases:
  - Not directly body-verified from WP due DNS failure.
  - No forbidden strings were observed in Cloud Logging for this revision.
- Mail trace:
  - Unknown from this lane; user/Claude confirmation still required.

#### 2. post_id `64534`

- Status: `draft` (from `[WP] 記事draft`)
- Title: `選手「チームが勝てるようにしっかり貢献したい」 関連発言`
- URL:
  - `https://yoshilover.com/?p=64534`
- Source/type evidence:
  - `social_body_template_applied`
  - `template_version=social_v2`
  - `section_count=4`
  - `quote_count=1`
- H3 count:
  - Direct WP body fetch from this sandbox failed on DNS resolution, so exact live HTML H3 count was not inspectable here.
  - Based on the reviewed v2 contract for `social_v2`, expected H3 count is `<=2`.
- Forbidden headings / phrases:
  - Not directly body-verified from WP due DNS failure.
  - No forbidden strings were observed in Cloud Logging for this revision.
- Mail trace:
  - Unknown from this lane; user/Claude confirmation still required.

### Sample shortfall

- Required acceptance sample: `3-5` new posts
- Verified live v2 sample on corrected revision within the 15-minute window: `2` posts
- Therefore acceptance is not fully complete yet.

## Logging and service health

- `gcloud run services describe yoshilover-fetcher --format=json(status.conditions)` showed:
  - `Ready=True`
  - `ConfigurationsReady=True`
  - `RoutesReady=True`
- `severity>=ERROR` logs for `yoshilover-fetcher` in the last 45 minutes:
  - none returned

## Constraint compliance

- Touched live resource:
  - `yoshilover-fetcher` service only
- Not touched:
  - `publish-notice`
  - `guarded-publish`
  - `draft-body-editor`
  - `codex-shadow`
  - Cloud Scheduler
  - Secret Manager
  - mail env / mail secrets
  - `RUN_DRAFT_ONLY`
  - `ENABLE_FORBIDDEN_PHRASE_FILTER`
  - `ENABLE_H3_COUNT_GUARD`
  - `ENABLE_SOURCE_GROUNDING_STRICT`
  - `ENABLE_QUOTE_INTEGRITY_GUARD`
  - WordPress PUT/DELETE on existing posts
  - `src/` implementation files
  - `tests/`
  - frontend/plugin/comment CTA
  - X/SNS env changes

## Remaining risk

1. Acceptance is still short by one live sample. `00192-n8g` produced only `2` drafts in the observed 15-minute window.
2. WP REST body inspection from this sandbox was blocked by DNS resolution failure against `yoshilover.com`, so exact live HTML checks for:
   - H3 count
   - `【発信内容の要約】`
   - `【文脈と背景】`
   - `【まとめ】直近10件`
   - forbidden phrase family
   were not directly executed here.
3. `post_id=64528` on intermediate revision `00191-v58` used `social_v1` and must not be counted as a v2 acceptance sample.

## Recommended next step

1. Keep `00192-n8g` live as-is.
2. Let the next natural fetcher cycle create at least one more draft on `00192-n8g`.
3. From a shell that can resolve `yoshilover.com`, open and inspect:
   - `https://yoshilover.com/?p=64532`
   - `https://yoshilover.com/?p=64534`
   - the next `00192-n8g` draft
4. Only after that final body-level spot check should Lane QQ be marked fully accepted.
