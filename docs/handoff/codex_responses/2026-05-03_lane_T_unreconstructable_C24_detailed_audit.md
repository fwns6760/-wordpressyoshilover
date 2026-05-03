# 2026-05-03 Lane T unreconstructable C24 detailed audit

作成: 2026-05-03 JST

## scope

- user request: read-only audit only
- live mutation: 0
- code / tests / config change: 0
- repo mutation: handoff doc only

## inputs used

- `docs/handoff/codex_responses/2026-05-03_lane_O_injury_return_31_audit_publish.md`
- `/tmp/lane_o_guarded_publish_history.jsonl`
- `/tmp/publish_notice_queue_20260503_audit.jsonl`
- `/tmp/good_draft_rescue_eval_20260503.json`
- `/tmp/good_draft_rescue_runner_dryrun_20260503.json`
- `doc/done/2026-04/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`

## environment note

- current WP status is **`unverified` for all 24 IDs**
- reason: sandbox からの WP REST read は Lane O 時点と同様に DNS failure
- therefore this audit only promotes rows when title / subtype / duplicate evidence is locally reconstructable enough to be safe

## per-id table

| post_id | title | source_url | subtype | WP status | hold_reason | duplicate signal | keyword hit | class |
|---|---|---|---|---|---|---|---|---|
| 63093 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 63135 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive` gate only | none surfaced | D |
| 63197 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive` gate only | none surfaced | D |
| 63468 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive` gate only | none surfaced | D |
| 63482 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive` gate only | none surfaced | D |
| 63689 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 63841 | 巨人二軍スタメン 若手をどう並べたか | queue subject only; URL unreconstructed | `farm_lineup` (doc inference) | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive` gate only | none surfaced | D |
| 63924 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 63946 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 63950 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive` gate only | none surfaced | D |
| 63959 | 【5/3予告先発】 ー （甲子園、14:00) 巨人:(2勝2敗、防御率1.90) 阪神:(2勝1敗、防御率5.00) | `https://twitter.com/sanspo_giants/status/2050430325315264981` | `pregame` / `probable_starter` | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 63972 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 63973 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 64012 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 64058 | unreconstructed | unreconstructed | unknown | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 64070 | 巨人戦 杉内俊哉先発 試合前情報 | unreconstructed | `pregame` | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 64096 | 投手陣「あんまり良くないっていうのは確か」 ベンチ関連発言 | unreconstructed | `comment` | unverified | `hard_stop_death_or_grave_incident` | none in history | none surfaced | C |
| 64097 | 【4/30公示】 (登録) (抹消)なし | unreconstructed | `notice` | unverified | `hard_stop_death_or_grave_incident` | none in history | `roster` semantic only | C |
| 64129 | 選手「打撃の神様」 関連発言 | unreconstructed | `comment` | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive`; `duplicate_title_match_types=exact_title_match,normalized_suffix_title_match` | none surfaced | D |
| 64131 | 選手「打撃の神様」 関連発言 | unreconstructed | `comment` | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive`; `duplicate_title_match_types=exact_title_match,normalized_suffix_title_match` | none surfaced | D |
| 64208 | 1軍に合流した 投手 ノックで元気な姿を見せています | unreconstructed | `notice` | unverified | `hard_stop_death_or_grave_incident` | none in history | `return` / `roster` semantic only | C |
| 64209 | (登録) (抹消) ※再登録は11日以降 | unreconstructed | `roster` | unverified | `hard_stop_death_or_grave_incident` | none in history | `roster` semantic only | C |
| 64264 | 【5/2公示】 (登録)なし (抹消)なし | unreconstructed | `notice` | unverified | `hard_stop_death_or_grave_incident` | none in history | `roster` semantic only | C |
| 64318 | 投手が１軍に合流 | unreconstructed | `notice` / `一軍合流` (log inference) | unverified | `hard_stop_death_or_grave_incident` | `lineup_duplicate_excessive` gate only | `return` / `roster` semantic only | D |

## classification notes

- `A` was reserved for rows where injury/return importance became clear **and** duplicate / grave signals were absent **and** other gates looked plausibly passable.
- `B` requires confirmed death / obituary / memorial evidence. That evidence was not recovered for any of the 24 IDs.
- `D` is used conservatively when the strongest recoverable evidence is a real duplicate suspicion, even if `duplicate_of_post_id` / `duplicate_target_source_url` stayed empty.

## important per-id notes

- `63841`
  - queue evidence exists: `【公開済】` and `【要確認】` subject lines were found in `/tmp/publish_notice_queue_20260503_audit.jsonl`
  - current WP status is still `unverified`, so this does **not** override the table
- `63924`
  - older history includes `hard_stop_farm_result_placeholder_body` on `2026-04-29`
  - latest recoverable hold reason is still `hard_stop_death_or_grave_incident`
- `64129` / `64131`
  - duplicate suspicion is stronger than the generic history rows because `good_draft_rescue_eval_20260503.json` preserved `duplicate_title_match_types`
- `64208` / `64209` / `64264` / `64318`
  - roster / return semantics became visible only after local reconstruction
  - however source URL, current WP state, and non-stale passability remain insufficient for safe A promotion

## aggregate

- `A fan-important publish candidate`: **0**
- `B real death-grave HOLD`: **0**
- `C ambiguous / still unreconstructable`: **15**
- `D duplicate suspicion HOLD`: **9**

## publish candidate list

- none
- expected incremental mail count: **0**
- rollback hint: n/a because no new safe publish candidate was extracted from the C24 bucket

## recommendation

- keep all remaining `C` rows on HOLD
- keep all `D` rows on HOLD unless a live shell can recover:
  - current WP status
  - concrete source URL
  - duplicate target identity when `lineup_duplicate_excessive` is present
- on current evidence, **blind publish remains unsafe for the full C24 set**
