# 373-INSIGHT defense player comparison table

## meta

- ticket: 373-INSIGHT-defense-player-comparison-table
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/42
- status: REVIEW_NEEDED
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16 JST

## observed facts

- User reported post `68665`: title is about `中山礼都`, but the article ranks `巨人` as a club.
- WP REST status check confirmed post `68665` was `publish`.
- Original title:
  - `【巨人データ】中山礼都の右翼守備、巨人は簡易UZR -0.009でセ・リーグ3/6位（直近30日）`
- Original body used:
  - `巨人の右翼守備の簡易UZRは、セ・リーグ6球団中 3位`
  - table header `順位 | 球団 | 簡易UZR | 守備機会 | アウト化率`
  - `関連した巨人選手 | 中山礼都`
- Production DB copy showed only Giants right-field rows had usable player names in the 30-day window:
  - `平山 功太`: 36 opportunities / 13 converted outs
  - `中山礼都`: 15 opportunities / 4 converted outs

## root cause

Tickets 360/361 correctly moved defense metric bodies toward table format, but they made the comparison table team-first.
That works for team-subject articles, but 68665 is a player-subject anomaly article.
When the title says `中山礼都`, the comparison table must rank players at the same position. Falling back to club ranking makes the article look like the wrong subject.

## scope

- Change UZR / fielding-rate defense anomaly rendering to try player comparison first.
- If Central League player-name coverage is sufficient, render `セ・リーグ選手別`.
- If non-Giants player names are missing but Giants has at least two same-position players, render `巨人選手別`.
- Keep table-first body contract.
- Keep true-UZR disclaimer: this remains a box-score-derived proxy, not real UZR.
- Repair existing published post `68665` title/content after status check, without changing status.

## non-goals / forbidden

- Do not disable mail or mail schedulers.
- Do not change Scheduler / env / Secret / X / SNS.
- Do not run insight-nightly manually just to generate extra publish/mail.
- Do not use LLM / Gemini or memory-based reconstruction.
- Do not silently skip the Giants fallback when league player rows are sparse.
- Do not rely on self-evaluation only; fixture-backed tests are required.

## acceptance

- `68665` title/body are player-comparison based and no longer club-ranking based.
- Future UZR / fielding-rate defense articles with player subjects do not render `セ・リーグ球団別` tables.
- League-wide player rows produce `セ・リーグ選手別` comparison.
- Sparse league rows with at least two Giants players produce `巨人選手別` comparison.
- Title still includes player name, metric value, rank, total, and period.
- Tests cover both league player comparison and Giants fallback.

## implementation evidence

- Code:
  - Added `_defense_player_comparison_rows()`.
  - Added `_render_defense_player_table_md()`.
  - Added `_render_defense_player_comparison_article()`.
  - `render_defense_uzr_article()` and `render_defense_fielding_pct_article()` now use player comparison before fallback prose.
  - UZR note now says `選手別アウト化率`, not `チーム別アウト化率`.
- Tests:
  - Added league player comparison fixture.
  - Added Giants-player fallback fixture matching the 68665 production shape.
  - `python3 -m py_compile src/analysis/anomaly_article_publisher.py tests/test_insight_step3_part2_records.py`
  - `python3 -m compileall -q src/analysis/anomaly_article_publisher.py tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py tests/test_insight_whitelist_gate.py tests/test_ranking_article_publisher.py`
  - AST parse OK for touched / related Python files.
  - `python3 -m pytest -q tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py tests/test_insight_whitelist_gate.py tests/test_ranking_article_publisher.py` => `103 passed, 3 warnings`
- Production DB copy preview:
  - title: `【巨人データ】中山礼都、右翼守備の簡易UZR -0.067で巨人選手別2/2位（直近30日）`
  - body has `巨人選手別ランキング（右翼守備・直近30日）`
  - body does not include `セ・リーグ球団別` or `巨人は簡易UZR`
- WP existing post repair:
  - post `68665` status before update: `publish`
  - post `68665` status after update: `publish`
  - updated title/content only
  - verification: `has_giants_player_ranking=true`, `has_team_ranking=false`

## deploy / observe

- Pending deploy to `insight-nightly`.
- Scheduler / env / Secret / X / SNS / mail must remain unchanged.
- Do not manually execute the job unless user explicitly asks; natural fire can verify future generation.
