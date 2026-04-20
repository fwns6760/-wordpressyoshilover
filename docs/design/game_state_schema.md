# game_state schema

## Scope
- This note defines the read-time schema and dry-run derivation rule for `meta.game_state`.
- A3 does not write WordPress meta. It derives and reports only.
- This schema layers on top of the canonical `game_id` note in `docs/design/game_id_schema.md`.

## Canonical enum
- `pre`: 試合開始前
- `live`: 試合中
- `post`: 試合終了後

## State machine
- `pre -> live`
  - Required: scheduled `game_start_time` has been reached
  - Required: a source signal is observed in title/body/source text
  - Accepted start signals: `試合開始`, `プレイボール`, first-inning markers such as `1回表`, `1回裏`, `初回`
  - Time alone does not transition `pre` to `live`
- `live -> post`
  - Immediate transition when a close signal is observed
  - Accepted close signals: `試合終了`, `ゲームセット`, `9回` 以上の close marker
  - Timeout transition is allowed when elapsed time since `game_start_time` exceeds 5 hours and no later in-game update is observed
- `post -> *`
  - Terminal
  - No return to `live` or `pre`

## Read-time inputs
- `meta.article_subtype`
- title/body text
- `modified_gmt`
- source URLs already attached to the Draft
- optional `meta.game_id`
- optional scheduled start fields such as `meta.game_start_time`

## Draft -> game_state derivation
1. Resolve subtype.
   - Prefer `meta.article_subtype`
   - If absent, infer from title/body markers only
2. Apply subtype mapping.
   - `pregame` -> `pre`
   - `lineup` -> `pre`
   - `live_update` -> `live`, unless a close marker is detected -> `post`
   - `live_anchor` -> `live`, unless a close marker is detected -> `post`
   - `postgame` -> `post`
   - `farm` result-style posts -> `post`
   - `fact_notice` -> `null`
3. Timeout promotion for live states.
   - If subtype is `live_update` / `live_anchor`
   - And `game_start_time + 5h < now`
   - And the last in-game update timestamp does not exceed the 5-hour threshold
   - Then derive `post` even without a close marker
4. Unsupported or ambiguous cases return `null`.

## Close-marker contract
- Exact close markers:
  - `試合終了`
  - `ゲームセット`
- Regex-style close markers:
  - `9回` 以上 + `終了`
  - `延長10回終了` のような延長 close marker
- A close marker always wins over subtype defaulting.

## Null-return contract
- `subtype_no_game_state`
  - Reserved for `fact_notice`
- `subtype_unresolved`
  - Subtype could not be inferred
- `subtype_not_supported`
  - Non-game Drafts outside the A3 mapping
- `farm_not_result`
  - `farm` subtype exists, but result/close markers are absent

## Dry-run tool contract
- CLI: `python3 src/tools/derive_game_state.py --max-posts 30 --output /tmp/game_state_derive_2026-04-21.md`
- Fetch target: recent Drafts only
- Transport: `WPClient.list_posts()` only
- Forbidden in A3:
  - `POST`, `PUT`, `DELETE`
  - scheduler / mail / automation changes
  - runtime writes to `meta.game_state`

## Assumptions
- A Draft is evaluated independently; A3 does not stitch multiple posts into one match timeline
- `modified_gmt` is treated as the last observed in-game update timestamp when timeout logic is evaluated
- If `game_id` is absent, derivation still runs; the report prints `null` for `game_id`

## Reserved for later便
- scoreboard ticker support
- multiple `game_id` under one `live_anchor`
  - Current assumption: one `live_anchor` belongs to one scheduled game
