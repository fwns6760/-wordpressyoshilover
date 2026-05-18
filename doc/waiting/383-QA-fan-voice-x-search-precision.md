# 383-QA fan voice X Search precision

status: BLOCKED_USER
owner: Codex
lane: B
created: 2026-05-18 JST
github_issue: #57
scope: Improve article-body fan voice precision using X Search evidence

## User problem

- user request: 本文の「皆の声 / ファンの声」を、RSS / Yahoo リアルタイム検索寄りではなく X Search で精度を上げたい。
- user clarification: 382 と同じ仕様。Hermes Agent からでもよいが、目的は X Search で精度を上げること。
- hard rule: 推測で補わない。隠さない。自己評価で OK にしない。証拠だけ出す。

## Current evidence

- Current body block is rendered as `💬 ファンの声（Xより）` in `src/rss_fetcher.py`.
- Current primary fetch path is `fetch_fan_reactions_from_yahoo()`, which uses Yahoo realtime search entries and filters them.
- The render slot embeds reaction URLs via `build_oembed_block()` when a reaction URL exists.
- Existing xAI / Grok code already exists:
  - `fetch_fan_reactions_with_grok()`
  - `generate_article_with_grok()`
  - `src/x_post_generator.py` direct xAI Responses API with `x_search`
- 382 investigation already found:
  - local `hermes` command is not installed
  - Secret Manager has `yoshilover-grok-api-key`
  - `yoshilover-fetcher` has `GROK_API_KEY` wired

## Decision

Use the same implementation principle as 382:

- GCP direct xAI Responses API + `x_search` is the main implementation path.
- Hermes Agent is acceptable only as a local/manual smoke or fallback path, not the required production runtime.
- PC-off operation should not depend on a local Hermes process.

## Proposed implementation

### Phase 0: adapter and tests

- Add an X Search fan voice adapter with injectable client for tests.
- Proposed module options:
  - `src/fan_voice_x_search.py`
  - or a narrow helper inside `src/rss_fetcher.py` if keeping file count down is preferred
- Unit tests must use fake xAI responses only. No network call in tests.

### Phase 1: X Search candidate shape

Each reaction candidate must preserve:

- handle or author label when provided
- text
- X URL / citation URL
- created_at or observed_at
- query
- provider
- evidence status:
  - `x_search_cited`
  - `x_search_uncited`
  - `x_search_empty`
  - `x_search_error`

If no URL/citation exists, the candidate may be shown as text only only if the mail/body clearly marks it as uncited. Prefer URL-backed candidates.

### Phase 2: picker order

Default order after implementation:

1. X Search URL-backed fan voices
2. X Search uncited but clearly returned fan voices
3. Existing Yahoo realtime path as fallback
4. No fan voice block, with visible log reason

Do not silently fill with low-quality or unrelated comments.

### Phase 3: precision gates

X Search fan voice must match article context:

- Giants topic required
- player / manager / team subject overlap required when article has a subject
- fresh window required:
  - primary: 0-24 hours
  - fallback: 48 hours max only for weekly / magazine context
- low-value posts rejected:
  - campaign / giveaway / follow request
  - media promotion
  - pure URL share
  - unrelated baseball team
  - same handle over cap
  - near-duplicate text

### Phase 4: body rendering

Keep the canonical heading:

- `💬 ファンの声（Xより）`

But the source should be X Search-backed where available.

The block should not claim Yahoo/RSS provenance when X Search was used. Evidence should be available in logs, and tests should prove reaction URLs are rendered as embeds when present.

## Cost guard

Initial cap should mirror 382 but scoped to article-body enrichment:

- max x_search calls per fetcher run: 5
- max x_search calls per article: 1
- max fan voices per article: existing `FAN_REACTION_LIMIT`
- timeout per xAI call: 30 seconds
- provider errors should disable further X Search calls for that run

Acceptance must log:

- `fan_voice_x_search_calls_used`
- `fan_voice_x_search_cap`
- `fan_voice_x_search_provider_error`
- `fan_voice_x_search_empty`
- fallback to Yahoo reason

## Out of scope

- X live posting
- New WP posts outside normal fetcher flow
- Existing WP article mutation
- Scheduler / Secret / env changes until implementation/deploy approval
- Changing article title generation
- Replacing the `💬 ファンの声（Xより）` heading
- Lowering publish safety gates
- Displaying token / secret values

## Acceptance

- [x] Ticket has GitHub Issue linked: https://github.com/fwns6760/-wordpressyoshilover/issues/57
- [ ] Tests prove X Search URL-backed results outrank Yahoo realtime results.
- [ ] Tests prove empty/error X Search is logged and falls back visibly, not silently.
- [ ] Tests prove unrelated X Search comments are rejected by subject overlap.
- [ ] Tests prove source URLs are embedded via existing oEmbed path when present.
- [ ] Tests prove low-value campaign / media-promo / pure-share posts are rejected.
- [ ] Tests prove call caps stop excessive xAI usage.
- [ ] Tests prove no X live post and no WP existing article mutation can occur in this path.

## Proposed write scope after user GO

- `src/fan_voice_x_search.py` or narrow `src/rss_fetcher.py` helper
- `src/rss_fetcher.py`
- `tests/test_fan_voice_x_search.py`
- existing Yahoo / body template tests only if needed
- `doc/waiting/383-QA-fan-voice-x-search-precision.md`
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

Ticket-only request. Implementation waits for explicit user GO.
