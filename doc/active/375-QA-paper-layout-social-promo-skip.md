# 375-QA paper layout social promo skip

## meta

- ticket: 375-QA-paper-layout-social-promo-skip
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/46
- status: LIVE_DEPLOYED_OBSERVE
- priority: P0.5
- owner: Codex
- lane: B
- created: 2026-05-17 JST

## observed facts

- User reported `68812` had a bad title and half-baked body.
- Cloud Logging confirmed:
  - `post_id=68812` was created from `https://twitter.com/hochi_giants/status/2055771985750397083`.
  - title path included `RT スポーツ報知 レイアウト担当: 5/17付 スポーツ報知`.
  - `social_body_template_applied` selected `social_v2` with `final_category=コラム`.
  - `unpublish_success post_id=68812` ran shortly after creation.
- This source is a paper-layout / newspaper notice RT, not a standalone article source.

## root cause

The trusted social rescue and weak social evaluation treated important game words such as `5連勝` and player words as enough signal. Existing negative keywords included `紙面`, `レイアウト`, and `RT `, but the code still allowed negative + multiple positive keywords to be rescued. That let a paper-layout notice become a `social_news` article.

## scope

- Add a deterministic hard stop for paper-layout social promos.
- Match `レイアウト担当`, `紙面レイアウト`, and date-prefixed newspaper edition notices such as `5/17付 スポーツ報知`.
- Apply the guard at:
  - trusted social keyword rescue
  - template v2 selection
  - authoritative social entry evaluation
  - main RSS candidate intake before article creation

## non-goals / forbidden

- Do not infer source facts from memory.
- Do not use LLM / Gemini for this filter.
- Do not silently skip: emit `paper_layout_social_promo_skip`.
- Do not change Scheduler / env / Secret / X / SNS / mail behavior.
- Do not republish `68812`.

## acceptance

- 68812-type title/summary is not rescued by trusted social logic.
- 68812-type title/summary remains unworthy even when weak social rescue is enabled.
- Template v2 marks the source as `skip / paper_layout_social_promo`.
- Normal trusted social articles such as lineup, pregame starter, and game notices remain accepted.
- Cloud Run deploy is verified by `/health` and new-revision error logs.

## implementation evidence

- GitHub Issue #46 created.
- Code:
  - Added `_should_skip_paper_layout_social_promo()` in `src/rss_fetcher.py`.
  - Added structured `paper_layout_social_promo_skip` log in the RSS intake path.
  - Added paper-layout hard stop to trusted social rescue, social worthiness evaluation, and template v2 selection.
- Tests:
  - Added 68812 fixtures in `tests/test_rss_trusted_social_rescue.py`.
  - `python3 -m pytest tests/test_rss_trusted_social_rescue.py -q` = 28 passed.
  - `python3 -m pytest tests/test_rss_trusted_social_rescue.py tests/test_yahoo_realtime.py tests/test_rss_template_routing_v2.py tests/test_rss_classification_regression_2026_05_17.py -q` = 113 passed.
  - `python3 -m py_compile src/rss_fetcher.py tests/test_rss_trusted_social_rescue.py`
  - `python3 -m compileall -q src/rss_fetcher.py tests/test_rss_trusted_social_rescue.py`
  - AST parse OK.

## deploy

- commit: `ed237ea`
- build context: clean `git archive HEAD` export `/tmp/yoshilover-build-ed237ea.hqaMLl` (dirty worktree 混入なし)
- Cloud Build: `3daeb97b-9252-4fb6-82d8-bc546ae46403` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:375-paper-layout-ed237ea`
- digest: `sha256:3f2aff2f70245bb2034fd6f290f1389dcfda13fdbcdc32329f92ba5c372e3db2`
- Cloud Run revision: `yoshilover-fetcher-00412-4kg`
- traffic: 100%
- `/health`: `OK`
- startup log: `Default STARTUP TCP probe succeeded after 1 attempt`
- new revision ERROR logs: 0
- Scheduler / env / Secret / X / SNS / mail 条件は未変更。

## live notes

- Public WP REST for `68812` returns `rest_forbidden` 401, consistent with the post no longer being public.
- Natural fire observation should show `paper_layout_social_promo_skip` when the same pattern appears again.
