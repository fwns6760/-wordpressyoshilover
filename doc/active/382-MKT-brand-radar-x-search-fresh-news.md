# 382-MKT brand radar X search fresh news

status: REVIEW_NEEDED
owner: Codex
lane: A
created: 2026-05-18 JST
github_issue: #56
scope: Yoshilover branding X-post planning mail from fresh Giants news + X search evidence

## User problem

- user lock: ヨシラバーの X 投稿案は、成績ランキングではなく「巨人の新鮮なニュース」を軸にしたい。
- user lock: 目的はブランディング。「ヨシラバーのポストを見たい」と思わせる。
- user idea: Hermes Agent / X Premium / X Search と記事記録を合わせて、巨人ファン向けの投稿企画を作る。
- user clarification: `@yoshilover6760` がヨシラバー本人で、X Premium に入っている。X Search のライセンス / 認証が必要な場合は明示する。
- user constraint: PC を落とすため、ローカル常駐前提の仕組みは弱い。
- hard rule: 推測で補わない。隠さない。自己評価で OK にしない。証拠だけ出す。

## Investigation evidence

### Existing production capability

- `gcloud secrets list --filter='grok OR xai'` showed `yoshilover-grok-api-key` exists in Secret Manager. Secret value was not read or displayed.
- `yoshilover-fetcher` Cloud Run service already has `GROK_API_KEY` wired from `yoshilover-grok-api-key`.
- `x-post-mail-lane` Cloud Run Job does not currently have `GROK_API_KEY` wired. It only has mail / GCS / project env.
- `src/rss_fetcher.py` already contains direct xAI Responses API usage with `tools: [{"type": "x_search", ...}]`:
  - `fetch_fan_reactions_with_grok()`
  - `generate_article_with_grok()`
- `src/x_post_generator.py` already contains direct xAI Responses API usage with `web_search` + `x_search`.
- Local `hermes` command is not installed (`command -v hermes` returned no path).

### External docs checked

- Hermes X Search docs: `https://hermes-agent.nousresearch.com/docs/user-guide/features/x-search`
- Hermes xAI OAuth guide: `https://hermes-agent.nousresearch.com/docs/guides/xai-grok-oauth`
- xAI Grok + Hermes announcement: `https://x.ai/news/grok-hermes`

Interpretation from evidence:

- GCP implementation should not depend on a local Hermes process.
- The practical GCP path is direct xAI Responses API using `GROK_API_KEY`, because that pattern already exists in repo and the secret is already present for `yoshilover-fetcher`.
- Hermes OAuth can be a local research / fallback path, but Cloud Run operation would require browser auth handoff and token persistence. That is more fragile than API-key backed Job execution.

## Root cause of current mismatch

Current `x-post-mail-lane` still behaves like a data-candidate filler:

1. It starts from DB ranking candidates.
2. News/opinion only fills missing slots.
3. When news/opinion runs, current source order can fill with official X before newspapers / magazines.
4. The mail title and copy still frame the output as X post candidates, not a Yoshilover branding plan.

This does not satisfy the user goal: fresh Giants-topic planning that makes readers want to see Yoshilover posts.

## Proposed implementation

Create a dedicated branding radar pipeline. It may share mail helpers with `x-post-mail-lane`, but the scoring and source order must be separate.

### Phase 0: repo-only design + fake xAI adapter

- Add a new module, proposed name: `src/brand_radar.py`.
- Add deterministic models:
  - `FreshArticleTopic`
  - `XSearchSignal`
  - `BrandPostPlan`
- Add a fake/injected X search client for unit tests.
- No network call in tests.
- No Secret / Scheduler / env change.

### Phase 1: fresh article collector

- Read `config/rss_sources.json`.
- Use only Giants-safe article sources:
  - `news`
  - `tag_scrape`
  - optionally `social_news` only after article sources are exhausted
- Prioritize fresh windows:
  - primary: 0-6 hours
  - fallback: 6-24 hours
  - older than 24h should not be normal candidates unless explicitly marked as weekly magazine context
- Emit visible skip reasons:
  - `no_fresh_article`
  - `non_giants_topic`
  - `duplicate_topic`
  - `source_fetch_failed`

### Phase 2: X Search signal enrichment

- For top fresh topics only, call xAI Responses API with `x_search`.
- Use `GROK_API_KEY`; do not depend on Hermes local OAuth for Cloud Run.
- Required per-result evidence:
  - query string
  - x_search date range
  - returned citation URL or quoted source URL when available
  - response usage / tool usage when provider returns it
  - failure reason if x_search fails
- Never invent fan reactions, quotes, numbers, standings, injuries, or player status.
- Empty X Search result must be visible in the mail, not silently replaced with made-up reaction.

### Phase 3: branding scorer

Score candidate plans by:

- freshness
- source importance
- Giants specificity
- fan-interest type
- X Search reaction signal
- duplicate / same-player recent history

Fan-interest types:

- `lineup`
- `starter`
- `manager`
- `player_quote`
- `young_player`
- `farm`
- `injury_recovery`
- `roster_move`
- `controversy`
- `magazine_angle`
- `data_support`

Data is allowed only as support. It must not dominate the candidate list.

### Phase 4: mail output

Subject should change from data framing to branding framing, for example:

- `ヨシラバー投稿企画案｜巨人ニュース鮮度レーダー HH:MM JST`

Each candidate must show:

- suggested post text
- why now
- source name
- source URL
- source published/observed time when known
- X Search query and evidence URL(s), or explicit `X signal unavailable`
- topic type
- confidence / risk label
- skip/fallback notes

No X live post. No WP mutation. Mail only.

## Implementation landed

- Added `src/brand_radar.py`.
  - `FreshArticleTopic` / `XSearchSignal` / `BrandPostPlan` models.
  - Fresh article collector from `config/rss_sources.json`.
  - Article sources are prioritized over official/social X sources.
  - General RSS summary-only Giants hits are rejected; Giants-specific source name, title keyword, or known Giants player name is required.
  - xAI Responses API `x_search` client uses `GROK_API_KEY`.
  - HTTP 401 / 403 from xAI is surfaced as `x_search_auth_required` for Premium/license follow-up instead of hidden fallback.
  - Missing key is surfaced as `missing_api_key`.
  - X Search empty / cap / provider errors are printed in mail evidence.
- Added `src/tools/run_brand_radar_mail.py`.
  - Default is dry-run.
  - `--send` is required for real mail delivery.
  - No X live post and no WP mutation.
  - Subject: `ヨシラバー投稿企画案｜巨人ニュース鮮度レーダー HH:MM JST`.
- Added `tests/test_brand_radar.py`.

## GCP / local decision

Recommended path:

- GCP Cloud Run Job using xAI API key.
- PC can be off.
- Secret Manager should provide `GROK_API_KEY`.
- If this is implemented as a new Job, add a new scheduler only after user approves cadence and budget.

Not recommended as first path:

- Hermes local command on the user PC.
- Reason: local PC must stay on, and local OAuth/session renewal becomes an ops dependency.

Hermes fallback path:

- Local manual smoke only, if direct xAI API key does not have working X Search access.
- If Hermes OAuth is required, create a separate user-runbook ticket instead of putting browser OAuth into this pipeline.

## Cost guard

GCP compute is expected to be small because this is a short Cloud Run Job with no min instances. The main cost risk is xAI / X Search usage, not Cloud Run CPU.

Initial safe cap proposal:

- max topics per run: 3
- max x_search calls per run: 3
- max scheduled runs per day: 5
- max x_search calls per day: 15
- timeout per xAI call: 30 seconds
- stop sending xAI calls after repeated provider errors

Acceptance must log and mail:

- x_search_calls_used
- x_search_call_cap
- provider_error_count
- candidates_sent
- candidates_skipped_by_reason

## Out of scope

- X live posting
- WP publish / draft creation
- WP existing article mutation
- Changing fetcher publish gates
- Lowering numeric fact / hard-stop guards
- Storing or displaying auth token values
- Cloud Run / Scheduler / Secret mutation until user explicitly approves implementation and live execution

## Acceptance

- [x] Ticket has GitHub Issue linked. #56
- [x] Repo-only tests prove fresh-news-first ordering: fresh article candidates outrank data-only candidates.
- [x] Repo-only tests prove official X is lower priority than newspaper / specialist / magazine sources when fresh article sources exist.
- [x] Repo-only tests prove X Search empty/failure is visible, not silently skipped.
- [x] Repo-only tests prove no X live post or WP mutation is possible from this lane.
- [x] Mail fixture contains source URL, source time, X Search query, evidence URLs or explicit unavailable reason.
- [x] Cost guard fixture enforces per-run and per-day x_search caps.
- [x] User approved A for repo implementation: GCP direct xAI API / X Search path. Live deploy / env / scheduler remains separate.
- [x] Auth/license follow-up is visible: xAI HTTP 401/403 becomes `x_search_auth_required`.
- [x] Dry-run source smoke with `--x-search-cap 0` proved source mail rendering and showed skip reasons.

## Proposed write scope after user GO

- `src/brand_radar.py`
- `src/tools/run_brand_radar_mail.py`
- `tests/test_brand_radar.py`
- `doc/active/382-MKT-brand-radar-x-search-fresh-news.md`
- `doc/README.md`
- `doc/active/assignments.md`

## Do not touch

- `.env`
- secret values
- Cloud Scheduler
- Cloud Run env
- existing WP posts
- X API live posting
- `RUN_DRAFT_ONLY`
- unrelated frontend/plugin files

## Verification

- `python3 -m py_compile src/brand_radar.py src/tools/run_brand_radar_mail.py tests/test_brand_radar.py` PASS.
- `python3 -m unittest tests.test_brand_radar` PASS: 13 tests.
- `python3 -m src.tools.run_brand_radar_mail --source-limit 0 --print-body` PASS, dry-run mail body generated, no network, no send.
- Source dry-run with network approval:
  - command: `python3 -m src.tools.run_brand_radar_mail --source-limit 3 --entry-limit 1 --x-search-cap 0 --print-body`
  - result: candidates_sent=1, x_search_calls_used=0, skipped `{"non_giants_topic": 1, "stale_article": 1, "x_search_cap_exceeded": 1}`
  - evidence: DeNA-looking general RSS topic was rejected as `non_giants_topic`; Full-Count 巨人 坂本記事 remained.

## Remaining blocker

- Live GCP deploy / Secret wiring / Scheduler creation is not done in this commit.
- `x-post-mail-lane` is not replaced.
- To run on GCP with real X Search, the next approval must explicitly cover:
  1. deploy target: new `brand-radar` Job or replacement of existing `x-post-mail-lane`
  2. Secret/env wiring: `GROK_API_KEY` for the chosen runtime
  3. mail cadence and daily `x_search` cap
  4. if xAI returns `x_search_auth_required`, use `@yoshilover6760` Premium/license path for auth follow-up
