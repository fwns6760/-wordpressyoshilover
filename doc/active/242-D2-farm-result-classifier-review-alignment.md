# 242-D2 farm_result classifier / review-flag alignment

- number: 242-D2
- type: incident follow-up / narrow quality gate correction
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 242-D
- related: 242, 242-A, 242-B, 243, 154 publish-policy, 234 subtype contract
- owner: Codex B(implementation) / Claude(dispatch, accept, push)
- lane: B
- created: 2026-04-28

## purpose

Prevent 63845-type broken `farm_result` bodies from reaching publish while avoiding a new regression where `farm_lineup` / lineup articles are caught by a broad farm placeholder gate.

This is a correction ticket for the existing 242-D implementation. The current 242-D commit (`a224add`) added a placeholder detector, but its target subtype set is broader than the final operating contract and does not yet enforce the required `result marker + lineup exclusion marker` classifier boundary.

## highest priority constraint

**No regression is allowed.**

- Do not hard-stop good `farm_result` articles only because H3 is missing.
- Do not apply the `farm_result` body blocker to `farm_lineup`, lineup, or lineup notice articles.
- Do not use Gemini/Codex to fill missing source facts.
- Do not add any new Gemini / LLM call.
- Do not add multi-pass reasoning, rewrite, re-generation, web search, or heavy fact extraction.
- Use only cheap deterministic checks against fields already present in the guarded-publish record: subtype, title, body, summary/source summary, source URL, and existing metadata.
- Do not broaden this into 242-A, 242-B, or 243.
- Do not touch GCP env, Scheduler, Secrets, WP live publish, X live post, or `RUN_DRAFT_ONLY`.

## cost / simplicity guardrail

This ticket must reduce cost and instability. It must not make the pipeline "think harder."

Allowed:

- small regex / substring marker checks
- counting H3 tags
- detecting empty headings
- detecting known placeholder phrases
- checking whether an existing source URL field is present
- emitting hard-stop or review flags from already-available text

Forbidden:

- calling Gemini, Codex, OpenAI, browser search, or external APIs
- asking an LLM to classify `farm_result`
- asking an LLM to extract starter / scoring facts
- rewriting body text
- generating replacement prose
- building a broad template registry
- adding a second validation pass that increases runtime materially

If a required fact cannot be checked cheaply and deterministically in this ticket, do not implement a full extractor. Route only obvious weak cases to review/draft and leave the full template registry for 243.

## final 242-D2 specification

### farm_result article template contract v0

This ticket is not only a placeholder detector. It must also freeze the minimum finished article shape for `farm_result`, so Gemini/Codex does not invent "article-like" filler when the source has no facts.

Target article type:

- second-team / farm / third-team game result
- example: `【二軍】巨人 3-6 楽天`

Maximum body size:

- default target: 450-700 Japanese characters
- if facts are thin: keep shorter and send to review/draft
- do not expand with generic commentary just to reach length

Required facts contract for publish:

- game level: `二軍`, `三軍`, farm, or equivalent
- game date or publish time that clearly identifies the game day
- matchup
- final score
- Giants-side result: win/loss/draw or equivalent wording
- starter pitcher name
- starter pitcher result
- at least one scoring event or run-scoring player name
- source URL

Important implementation limit:

- In 242-D2, this list is the article contract, not permission to build a heavy full fact extractor.
- Hard-stop only concrete broken body patterns.
- For missing required facts, implement only cheap obvious checks where the fields/text are already available.
- If starter / scoring facts are not cheaply and confidently detected, emit `farm_result_required_facts_weak_review` instead of hard-stopping or generating prose.

Optional facts:

- individual player stats
- pitching relay details
- first-team implication
- fan-facing short comment

Optional facts must be omitted when the source does not contain them. Do not ask Gemini/Codex to infer them.

Allowed H2 skeleton:

- `二軍結果の要点`
- `試合の流れ`
- `まとめ`

Allowed body shape:

```text
<p>YYYY年MM月DD日の二軍戦で、巨人は相手チームにスコアで勝利/敗戦した。</p>

<h2>二軍結果の要点</h2>
<p>先発の{starter_pitcher_name}は{starter_pitcher_result}。巨人は{final_score}で{result}。</p>

<h2>試合の流れ</h2>
<p>{scoring_event または run_scoring_player_name}をsource事実だけで短く書く。</p>

<h2>まとめ</h2>
<p>確認できる事実だけで1文にまとめる。sourceにない一軍昇格示唆や選手評価は書かない。</p>
```

H3 policy inside the template:

- H3 optional
- H3 is not required for publish
- max H3 count: 2
- allowed H3:
  - `先発投手の結果`
  - `得点に絡んだ選手`
  - `目立った選手成績`
- H3 over limit is review, not hard_stop
- empty / placeholder / bodyless H3 is hard_stop

Forbidden sections unless the source has concrete facts:

- `二軍個別選手成績`
- `一軍への示唆`
- `ファームのハイライト`
- `注目ポイント`

If these sections appear without concrete player names / stats / source-backed facts, the article must not auto-publish.

Forbidden prose:

- `先発の 投手`
- `選手の適時打`
- player-less active phrases such as "選手が活躍"
- repeated generic link/outro such as `試合の詳細はこちら`
- source-free first-team promotion implications
- source-free player evaluation
- prose whose main job is to make the article feel longer

Missing facts behavior:

- missing optional facts: omit the optional section
- missing starter name or starter result: review/draft
- missing scoring event or scoring player: review/draft
- missing source URL: review/draft
- concrete placeholder remains in body: hard_stop
- ambiguous `farm_result` vs `farm_lineup`: review/draft
- never call Gemini/Codex to fill the missing slot
- if cheap deterministic checks are insufficient, do not over-engineer; review/draft is the safe fallback

### farm_result classifier

Treat an article as a `farm_result` candidate only when all of the following are true:

- resolved `article_subtype` is `farm` or `farm_result`
- title / body / summary / source summary contains at least one result marker
- title / body / summary / source summary contains no lineup exclusion marker
- the article reads as a postgame result article, not a lineup or batting-order article

Result markers:

- `結果`
- `試合結果`
- `敗れ`
- `勝利`
- `黒星`
- `白星`
- score pattern such as `3-6`
- score pattern such as `3－6`

Lineup exclusion markers:

- `スタメン`
- `打順`
- `先発メンバー`
- `1番`
- `2番`
- `3番`
- `4番`
- `5番`
- `6番`
- `7番`
- `8番`
- `9番`

Do not decide `farm_result` from only `二軍` + score. Result markers and lineup exclusion markers must both be checked.

Lineup exclusion must be scoped. Do not scan the whole body for `1番`-`9番` and exclude the article only because those words appear in result prose such as `8番打者` or `9番の選手`.

Apply lineup exclusion in this priority order:

1. title
2. summary
3. source summary
4. opening heading
5. lineup-like block

Body-wide lineup exclusion is allowed only when the body contains a lineup-like block, such as a batting-order table/list, repeated multi-line `1番`-`9番` entries, or a clear starting-member block.

Required boundary:

- 63841-type title/summary/header with `スタメン` / `打順` / `先発メンバー` is outside the farm_result blocker.
- 63845-type farm_result must remain inside the farm_result blocker even if body prose mentions `8番` or `9番`.

### farm_lineup exclusion

If a scoped lineup exclusion marker exists in title / summary / source summary / opening heading, or if a lineup-like block exists in body, the article is outside this blocker, even when the article also has `farm` as the broad subtype.

Do not exclude a result article only because body prose contains isolated `1番`-`9番` terms.

Required regression target:

- `63841`-type farm lineup articles are not blocked by 242-D2.

### hard_stop conditions

Add or adjust the hard-stop flag:

- `farm_result_body_placeholder`

It should fire only for a confirmed `farm_result` candidate when any high-confidence broken body condition exists:

- `先発の 投手`
- `選手の適時打`
- `試合の詳細はこちら` / `詳細はこちら` / `詳しくはこちら` style generic detail paragraph appears 2 or more times as body filler
- empty H2/H3
- empty `【】`
- section heading with no body below it
- placeholder H2/H3
- H3 exists but has no body
- empty slot text remains directly in body prose

The flag is a hard stop:

- `publishable=false`
- article goes to review/draft path
- no Gemini/Codex completion is invoked

### review conditions

Facts weakness is not a hard stop in this ticket unless the body contains concrete placeholders above.

Add or wire review flags:

- `farm_result_required_facts_weak_review`
- `farm_result_h3_over_limit_review`

Review-only cases:

- score exists but starter / scoring facts are weak
- optional sections are inflated without enough facts
- farm_result vs farm_lineup classification is ambiguous
- H3 count exceeds the farm_result limit
- score exists but the body is thin without explicit placeholder text

Review flags must not be counted as `hard_stop_flags`.

If the current evaluator has an existing "review but do not publish" mechanism, use it. If not, implement the smallest non-publishable review path needed for these flags. Do not convert weak facts into a hard stop just to reuse existing infrastructure.

### H3 policy

For `farm_result`:

- H3 is optional
- missing H3 must not block
- `max_h3_count = 2`
- H3 count over 2 is review, not hard_stop
- empty H3 / placeholder H3 / H3 without body is hard_stop

### scope out

Do not implement:

- all-template contract registry
- H3 required rules
- farm-wide generic blocker
- 242-A death/grave precision changes
- 242-B entity contamination blocker
- 243 template contract registry
- Gemini prompt rewrite
- Gemini call increase
- source-fact completion
- GCP env / Scheduler / Secret / WP / X live changes

## implementation targets

Primary files:

- `src/guarded_publish_evaluator.py`
- `tests/test_guarded_publish_evaluator.py`

Documentation sync:

- `doc/active/242-D2-farm-result-classifier-review-alignment.md`
- `doc/active/242-D-farm-result-placeholder-body-publish-blocker.md`
- `doc/README.md`
- `doc/active/assignments.md`

Do not touch unrelated dirty files, logs, build artifacts, data files, env files, or front assets.

## required implementation notes

- Replace broad target-subtype logic with a helper that checks both result markers and lineup exclusion markers.
- Remove `farm_lineup`, `lineup`, and `lineup_notice` from the farm_result placeholder detector target path.
- Keep existing 63845 placeholder detection, but gate it behind the corrected farm_result classifier.
- Add review-flag handling for facts-weak and H3-over-limit cases.
- Keep facts-weak detection deliberately shallow: source URL missing, result marker present but body lacks any obvious named actor around starter/scoring phrases, optional sections inflated without concrete names/numbers, or ambiguous farm_result/farm_lineup markers.
- Scope lineup exclusion markers to title, summary, source summary, opening heading, or body lineup-like blocks. Do not use isolated body-wide `1番`-`9番` mentions as exclusion.
- Do not build a comprehensive Japanese named-entity extractor in this ticket.
- Keep current 242-A medical roster behavior unchanged.
- Keep existing freshness, lineup duplicate, cleanup, and hard-stop gates unchanged.

## fixtures

### bad fixture: 63845 type

Record characteristics:

- `post_id=63845`
- subtype is `farm` or `farm_result`
- result marker exists
- no lineup exclusion marker
- body contains:
  - `先発の 投手`
  - `選手の適時打`
  - repeated `試合の詳細はこちら`
  - farm result headings

Expected:

- `farm_result_body_placeholder` in hard_stop flags
- `publishable=false`

### good fixture: valid farm_result without H3

Record characteristics:

- second-team/farm result article
- matchup present
- score present
- game date or publish time present
- starter pitcher name and starter result present
- scoring event or scoring player present
- source URL present
- no H3

Expected:

- no `farm_result_body_placeholder`
- no H3-missing block
- publishable under existing gates

### regression fixture: 63841 type farm_lineup

Record characteristics:

- broad subtype may be `farm`
- contains lineup exclusion markers such as `スタメン`, `打順`, `1番`, `2番`
- no result marker requirement should be met for farm_result

Expected:

- farm_result placeholder detector is not applicable
- 242-D2 does not block this article

## required tests

Add or adjust tests with these names or equivalent names:

- `test_farm_result_placeholder_body_is_hard_stop_for_63845`
- `test_good_farm_result_without_h3_is_publishable`
- `test_farm_result_missing_optional_sections_does_not_block_when_required_facts_exist`
- `test_farm_lineup_is_not_blocked_by_farm_result_validator`
- `test_empty_heading_is_hard_stop_for_farm_result`
- `test_generic_detail_paragraph_repetition_is_hard_stop_for_farm_result`
- `test_farm_result_too_many_h3_is_review_not_hard_stop_unless_empty_or_placeholder`
- `test_farm_result_detection_requires_result_marker_and_no_lineup_marker`
- `test_farm_result_required_facts_weak_is_review_not_hard_stop`
- `test_farm_result_body_batting_order_words_do_not_trigger_lineup_exclusion`
- `test_farm_lineup_title_marker_excludes_from_farm_result_blocker`

Each test must explicitly protect one boundary:

- 63845-type placeholder body is a hard stop
- good farm_result passes without H3
- farm_lineup is excluded
- H3 absence is not a blocker
- H3 over limit is review
- empty / placeholder H3 is hard stop
- weak facts are review/draft, not hard_stop
- `二軍` + score alone does not define farm_result
- isolated `8番` / `9番` in result prose does not exclude farm_result
- title `スタメン` excludes 63841-type farm_lineup from farm_result blocker

## dry-run verification

After implementation:

- run `python3 -m unittest tests.test_guarded_publish_evaluator`
- verify 63845 fixture has `farm_result_body_placeholder`
- verify 63845 is `publishable=false`
- verify good farm_result remains publishable under existing gates
- verify 63841-type farm_lineup is outside this blocker
- verify farm_result body prose containing `8番` / `9番` remains applicable to the farm_result blocker when title/summary are result-like
- verify title/summary/header `スタメン` excludes 63841-type farm_lineup
- verify H3 over limit produces `farm_result_h3_over_limit_review`, not hard_stop
- verify facts weakness produces `farm_result_required_facts_weak_review`, not hard_stop
- verify Gemini call count does not increase
- verify implementation is deterministic and does not add LLM/browser/API calls

## live verify handoff

Claude / authenticated executor handles live verification after Codex commit and push:

- compare recent guarded publish history before/after deploy
- confirm 63845-type articles do not publish
- confirm good farm_result articles are not over-blocked
- confirm farm_lineup articles are not blocked by this detector
- confirm review/draft reason is visible in logs or mail
- confirm no GCP env, Scheduler, Secret, WP bulk action, or X live post change was made by Codex

## acceptance checklist

- [ ] Existing 242-D broad target subtype logic is corrected
- [ ] `farm_lineup`, `lineup`, and `lineup_notice` are not farm_result detector targets
- [ ] result markers and lineup exclusion markers are both checked
- [ ] lineup exclusion markers are scoped to title / summary / source summary / opening heading / lineup-like body block
- [ ] isolated body `1番`-`9番` mentions do not exclude farm_result
- [ ] 63845 fixture hard-stops as `farm_result_body_placeholder`
- [ ] good farm_result without H3 passes
- [ ] 63841-type farm_lineup is not blocked
- [ ] H3 missing does not block
- [ ] H3 over limit is review, not hard_stop
- [ ] empty / placeholder / bodyless H3 remains hard_stop
- [ ] facts weakness is review/draft, not hard_stop
- [ ] no Gemini completion path is added
- [ ] no new LLM / browser / API call is added
- [ ] no full fact extractor is added; only cheap deterministic checks are used
- [ ] 242-A / 242-B / 243 are not touched
- [ ] GCP env / Scheduler / Secret / WP live / X live are not touched
- [ ] tests pass
- [ ] Codex commits only explicit paths; no `git add -A`
- [ ] Claude accepts, pushes, then handles live verify

## commit rule for Codex

- Codex may implement and commit.
- Codex must not push.
- Use explicit path staging only.
- Suggested commit message: `242-D2: align farm_result placeholder gate with classifier and review flags`

## Claude handoff

Claude should dispatch this as a narrow Codex B implementation ticket only after acknowledging:

- Claude does not edit `src/` or `tests/`
- Claude does not commit the implementation
- Claude only dispatches, accepts, pushes, and handles authenticated live verification
- If Codex proposes broader template registry / Gemini prompt rewrite / entity contamination work, reject as scope creep and split into later tickets

## later tickets

- 242-A remains the death/grave false-positive precision line
- 242-B remains the Giants entity contamination / 63844 line
- 243 remains the full template contract registry line

## 242-D2 implementation summary

- pytest diff: `112 collected / 112 passed / 12 subtests passed` → `124 collected / 124 passed`(required 11 evaluator fixtures + 1 runner review-hold regression added)
- 採用 logic: resolved subtype が `farm` / `farm_result` のときだけ cheap `farm_result` classifier を通し、`result marker(title/body/summary/source summary)` あり + `scoped lineup exclusion(title/summary/source summary/opening heading/lineup-like body block)` なしの case にだけ既存 placeholder gate を適用し、required facts weak / H3 over limit は review hold に倒す
- classifier 経路: `_evaluate_record()` → `resolve_guarded_publish_subtype(raw_post, record)` → `_farm_result_candidate_context(raw_post, record, subtype=resolved_subtype)` → `_placeholder_body_reason(..., classifier_context=...)`
- review flag 経路: `_evaluate_record()` → `_farm_result_review_reasons(record, classifier_context)` → `category=review` with `farm_result_required_facts_weak_review` / `farm_result_h3_over_limit_review` → `guarded_publish_runner` refused `hold_reason=review_*`
- 追加 fixture 数: evaluator required 11 件(`63845 hard_stop` / `good no-H3 publishable` / `optional sections omit OK` / `farm_lineup exclusion` / `empty heading hard_stop` / `generic detail repetition hard_stop` / `H3 over limit review` / `result marker + no lineup marker boundary` / `required facts weak review` / `body 8番/9番 allowed` / `title スタメン exclusion`) + runner review-hold 1 件

## 242-D2 live verify pending

- TODO(authenticated executor): recent guarded-publish dry-run / canary diff で `farm_result_placeholder_body` が 63845 type にだけ立ち、63841 type `farm_lineup` は blocker 外のままなことを確認
- TODO(authenticated executor): good `farm_result` sample(no H3, starter/scoring/source URL あり) が publishable 維持、`farm_result_h3_over_limit_review` / `farm_result_required_facts_weak_review` が hard_stop ではなく review hold として可視化されることを確認
- TODO(authenticated executor): Gemini/LLM call count・env/secret/Scheduler/WP/X live mutation に増分がないことを deploy verify に記録
