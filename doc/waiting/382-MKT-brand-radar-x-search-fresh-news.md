# 382-MKT brand radar X search fresh news

status: BLOCKED_USER
owner: Codex
lane: A
created: 2026-05-18 JST
github_issue: #56
scope: Yoshilover branding X-post planning mail from fresh Giants news + X search evidence

## User problem

- user lock: ヨシラバーの X 投稿案は、成績ランキングではなく「巨人の新鮮なニュース」を軸にしたい。
- user lock: 目的はブランディング。「ヨシラバーのポストを見たい」と思わせる。
- user idea: Hermes Agent / X Premium / X Search と記事記録を合わせて、巨人ファン向けの投稿企画を作る。
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
- [ ] Repo-only tests prove fresh-news-first ordering: fresh article candidates outrank data-only candidates.
- [ ] Repo-only tests prove official X is lower priority than newspaper / specialist / magazine sources when fresh article sources exist.
- [ ] Repo-only tests prove X Search empty/failure is visible, not silently skipped.
- [ ] Repo-only tests prove no X live post or WP mutation is possible from this lane.
- [ ] Mail fixture contains source URL, source time, X Search query, evidence URLs or explicit unavailable reason.
- [ ] Cost guard fixture enforces per-run and per-day x_search caps.
- [ ] User approves one of:
  - A: GCP direct xAI API key
  - B: local Hermes smoke first
  - C: do not use X Search, article-only branding radar

## Proposed write scope after user GO

- `src/brand_radar.py`
- `src/tools/run_brand_radar_mail.py`
- `tests/test_brand_radar.py`
- `Dockerfile.brand_radar` or reuse existing x-post mail image pattern
- `cloudbuild_brand_radar.yaml` if creating a separate image
- `doc/waiting/382-MKT-brand-radar-x-search-fresh-news.md`
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

## Current blocker

User decision required:

1. Use existing GCP `GROK_API_KEY` / xAI API path for implementation?
2. Initial budget cap: accept the proposed 15 x_search calls/day, or choose a lower number?
3. Should the first implementation be a new `brand-radar` Job, or should it replace the current `x-post-mail-lane` output?
