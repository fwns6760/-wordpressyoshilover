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
- `yoshilover-fetcher` Cloud Run service already has legacy `GROK_API_KEY` wired from `yoshilover-grok-api-key`.
- `x-post-mail-lane` Cloud Run Job does not currently have an xAI/X Search credential wired. It only has mail / GCS / project env.
- `src/rss_fetcher.py` already contains direct xAI Responses API usage with `tools: [{"type": "x_search", ...}]`:
  - `fetch_fan_reactions_with_grok()`
  - `generate_article_with_grok()`
- `src/x_post_generator.py` already contains direct xAI Responses API usage with `web_search` + `x_search`.
- Local `hermes` command is not installed (`command -v hermes` returned no path).

### External docs checked

- Hermes X Search docs: `https://hermes-agent.nousresearch.com/docs/user-guide/features/x-search`
- Hermes xAI OAuth guide: `https://hermes-agent.nousresearch.com/docs/guides/xai-grok-oauth`
- Hermes OAuth over SSH / remote host guide: `https://hermes-agent.nousresearch.com/docs/guides/oauth-over-ssh`
- xAI Grok + Hermes announcement: `https://x.ai/news/grok-hermes`
- xAI X Search docs: `https://docs.x.ai/developers/tools/x-search`

Interpretation from evidence:

- GCP implementation should not depend on the user's local PC staying on.
- This is not the X Developer Search API and should not be described as "Grok API" in operator-facing docs. The endpoint is xAI Responses API with the `x_search` tool.
- Hermes docs say `x_search` uses either SuperGrok OAuth or `XAI_API_KEY`; when both are configured, SuperGrok OAuth wins so it uses the subscription quota instead of paid API spend.
- Hermes remote-host docs explicitly include `hermes auth add xai-oauth --no-browser` with SSH local-forward. Therefore "local only" is not proven by docs.
- Cloud Run viability is still unproven. The unknown is not the initial browser handoff; the unknown is whether the resulting Hermes auth artifact can be stored, loaded, refreshed, and used safely in a non-interactive GCP runtime.
- The practical repo-safe default is no paid X Search call: `x_search_cap=0`. Paid `XAI_API_KEY` is explicit opt-in only. Legacy `GROK_API_KEY` remains only as compatibility with older repo code.

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

- Default production behavior must not call paid xAI / X Search: `x_search_cap=0`.
- For top fresh topics only, enrich with X Search when one of the following is explicitly enabled:
  - Hermes Premium OAuth provider after the GCP smoke below passes.
  - xAI Responses API with `XAI_OAUTH_BEARER_TOKEN` / `XAI_BEARER_TOKEN`.
  - xAI Responses API with `XAI_API_KEY` only if user explicitly accepts paid API usage.
- Legacy `GROK_API_KEY` is fallback only and should not be the operator-facing name.
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
  - xAI Responses API `x_search` client now prefers `XAI_OAUTH_BEARER_TOKEN`, `XAI_BEARER_TOKEN`, then `XAI_API_KEY`; legacy `GROK_API_KEY` is fallback only.
  - Default `x_search_call_cap` is `0`, so repo default does not call paid xAI API.
  - When cap is zero, X Search evidence is emitted as `x_search_disabled_no_paid_api`; it is not silently skipped.
  - HTTP 401 / 403 from xAI is surfaced as `x_search_auth_required` for Premium/license follow-up instead of hidden fallback.
  - Mail evidence includes visible credential source.
  - Missing key is surfaced as `missing_api_key`.
  - X Search empty / cap / provider errors are printed in mail evidence.
- Added `src/tools/run_brand_radar_mail.py`.
  - Default is dry-run.
  - `--send` is required for real mail delivery.
  - No X live post and no WP mutation.
  - Subject: `ヨシラバー投稿企画案｜巨人ニュース鮮度レーダー HH:MM JST`.
- Added `tests/test_brand_radar.py`.

## GCP / local decision

Current decision:

- Do not use X Developer API.
- Do not make paid xAI `XAI_API_KEY` the default path.
- Keep the repo implementation safe by default: article/RSS/news planning mail works with `x_search_cap=0`, no X live post, no WP mutation.
- Treat `@yoshilover6760` Premium + Hermes OAuth as a real GCP experiment, not as rejected / impossible.

Recommended path now:

1. Phase A: run the repo-only brand radar from GCP without paid X Search (`x_search_cap=0`) using article / RSS / magazine freshness.
2. Phase B: create a separate Hermes Premium OAuth smoke Job to test whether subscription-backed `x_search` can run on GCP while the user's PC is off.
3. Phase C: only if Phase B passes, add a Hermes-backed X Search provider to `brand_radar`; paid `XAI_API_KEY` remains explicit opt-in only.

Do not run this as a local PC resident job. Local PC can be used once for browser consent / SSH tunnel during auth setup, but the accepted runtime must be GCP.

## Hermes Premium OAuth GCP smoke design

Goal:

- Verify whether `@yoshilover6760` Premium / SuperGrok OAuth can power Hermes `x_search` from GCP without X Developer API and without paid `XAI_API_KEY`.

Evidence basis:

- Hermes X Search docs list SuperGrok OAuth as the preferred credential path and say it wins over `XAI_API_KEY`.
- Hermes xAI OAuth docs say no `XAI_API_KEY` is required and the session refreshes in the background.
- Hermes remote-host docs show `hermes auth add xai-oauth --no-browser` with an SSH local-forward callback. This is evidence that a remote Linux host is supported for initial login.

Unknowns to prove, not assume:

- Exact Hermes auth artifact path and format.
- Whether the auth artifact can be stored in Secret Manager and restored into Cloud Run safely.
- Whether token refresh works in non-interactive Cloud Run after initial consent.
- Whether `@yoshilover6760` Premium tier grants `x_search` through this Hermes path.
- Whether Hermes CLI can be installed in the Job image without leaking auth values to build logs.
- Whether Hermes ever prints token values in stdout/stderr or debug logs.

Smoke phases:

1. H0 install check:
   - In a throwaway GCP/Cloud Shell or local container, verify `hermes` install command, `hermes --version`, and `hermes auth add xai-oauth --no-browser` availability.
   - No login yet, no token generated.
2. H1 OAuth artifact creation:
   - Run `hermes auth add xai-oauth --no-browser`.
   - User completes browser consent as `@yoshilover6760`.
   - Capture only artifact existence/path/mtime/size/hash. Do not print file content.
   - Store artifact in Secret Manager only if it is required for GCP smoke.
3. H2 GCP smoke Job:
   - New one-off Job, proposed name: `brand-radar-hermes-smoke`.
   - Secret mounted or copied into Hermes config path at runtime.
   - Run exactly one harmless query such as `巨人 ニュース`.
   - No WP mutation, no X live post, no mail send unless explicitly approved; logs only.
4. H3 provider integration:
   - If H2 succeeds, add a Hermes CLI provider wrapper behind `brand_radar`.
   - Keep `x_search_cap=0` for paid xAI API; Hermes cap is separate and low.
5. H4 scheduler:
   - Only after multiple manual smoke executions succeed and user approves cadence.

Smoke acceptance:

- No token value is displayed in chat, terminal output, Cloud Logging, GitHub Issue, mail, or commit.
- No X Developer API call.
- No paid `XAI_API_KEY` call.
- No WP mutation.
- No X live post.
- One GCP smoke run performs exactly one X Search query.
- Result is classified visibly as one of:
  - `hermes_missing`
  - `oauth_required`
  - `token_refresh_failed`
  - `x_search_auth_required`
  - `x_search_empty`
  - `x_search_success`
- Cloud Logging output includes command status, query label, result count/citation count when available, and the above classified outcome.
- Cloud Logging output does not include bearer token, refresh token, auth file body, cookie, or authorization URL parameters beyond a redacted host/path.

## Cost guard

GCP compute is expected to be small because this is a short Cloud Run Job with no min instances. The main cost risk is xAI / X Search usage, not Cloud Run CPU.

Current safe default:

- max topics per run: 3
- paid xAI x_search calls per run: 0
- paid xAI x_search calls per day: 0
- Hermes OAuth smoke calls per run: 1, manual only
- scheduled runs per day: 0 until user approves GCP cadence
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
- [x] User approved repo implementation for branding radar mail. Live deploy / env / scheduler remains separate.
- [x] Paid xAI API is disabled by default (`x_search_cap=0`), and zero-cap X Search is visible as `x_search_disabled_no_paid_api`.
- [x] Hermes Premium OAuth is documented as a GCP smoke experiment, not dismissed as impossible.
- [x] Auth/license follow-up is visible: xAI HTTP 401/403 becomes `x_search_auth_required`.
- [x] Credential naming corrected: `XAI_API_KEY` / xAI bearer token paths are primary; `GROK_API_KEY` is compatibility fallback.
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
- `python3 -m unittest tests.test_brand_radar` PASS: 17 tests.
- `python3 -m src.tools.run_brand_radar_mail --source-limit 0 --print-body` PASS, dry-run mail body generated, no network, no send.
- Source dry-run with network approval:
  - command: `python3 -m src.tools.run_brand_radar_mail --source-limit 3 --entry-limit 1 --x-search-cap 0 --print-body`
  - result: candidates_sent=1, x_search_calls_used=0, skipped `{"non_giants_topic": 1, "stale_article": 1, "x_search_disabled_no_paid_api": 1}`
  - evidence: DeNA-looking general RSS topic was rejected as `non_giants_topic`; Full-Count 巨人 坂本記事 remained.

## Remaining blocker

- Live GCP deploy / Secret wiring / Scheduler creation is not done in this commit.
- `x-post-mail-lane` is not replaced.
- To run on GCP without paid X Search, the next approval must explicitly cover:
  1. deploy target: new `brand-radar` Job or replacement of existing `x-post-mail-lane`
  2. mail cadence
  3. daily article/source fetch cap
- To test real X Search without X Developer API / paid xAI API, the next approval must explicitly cover:
  1. Hermes install check target
  2. OAuth setup method for `@yoshilover6760`
  3. Secret Manager name for the Hermes auth artifact, if artifact storage is required
  4. one-off GCP smoke Job execution
  5. log redaction acceptance before any scheduler is created
