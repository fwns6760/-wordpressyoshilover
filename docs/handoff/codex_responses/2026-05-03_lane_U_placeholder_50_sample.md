# Lane U placeholder 50 sample audit

| field | value |
|---|---|
| date | 2026-05-03 JST |
| mode | read-only / doc-only / live-inert |
| target hold_reason | `hard_stop_farm_result_placeholder_body` |
| primary source | `/tmp/guarded_publish_history_live_20260503.jsonl` |
| note | repo-local `logs/guarded_publish_history.jsonl` is stale through 2026-04-26 and does not contain the 2026-05-03 placeholder rows |

## 1. extraction summary

- Requested source file `guarded_publish_history.jsonl` was available as the 2026-05-03 live mirror `/tmp/guarded_publish_history_live_20260503.jsonl`.
- Matching rows in the live mirror: `172`.
- Audit scope for this task: latest `50` matching rows, sorted by `ts desc, post_id desc`.
- Latest-50 window:
  - newest = `2026-05-03T19:15:37.909738+09:00`
  - oldest = `2026-05-02T19:15:36.683609+09:00`
- Latest-50 rows contain `47` unique `post_id`.
- Date split:
  - `2026-05-03`: `46` rows
  - `2026-05-02`: `4` rows
- `13/50` rows also carry `error` detail containing `lineup_duplicate_excessive`, but the persisted `hold_reason` remains `hard_stop_farm_result_placeholder_body`.

## 2. code path confirmation

- History `hold_reason` is created in runner red-entry handling as `hard_stop_<first hard_stop_flag>` at [src/guarded_publish_runner.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_runner.py:2300) and written to history as `error=hard_stop:<flags>` at [src/guarded_publish_runner.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_runner.py:2309).
- The underlying evaluator flag is `farm_result_placeholder_body`, appended at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1804).
- The detector only fires on the farm-result placeholder candidate path:
  - target subtype gate: [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1507)
  - actor placeholder / repeated filler detection: [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1533)
  - bodyless / empty / placeholder heading detection: [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:861)
  - hard-stop decision assembly: [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1585)
  - weak starter/scoring fact and H3 over-limit review details: [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:904), [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1816)

Clarification:

- The code path is effectively the `farm_result` placeholder detector, but some recent audit snapshots record `resolved_subtype=farm` rather than literal `farm_result`.
- That does not weaken the conclusion: these rows still passed the farm-result-like candidate gate and were blocked by the same placeholder detector.

## 3. representative 5-sample table

| post_id | latest ts | title | hold_reason | why placeholder-fired | body sample status | provisional judgment |
|---:|---|---|---|---|---|---|
| `63845` | `2026-05-03 16:40 JST` | `巨人二軍 3-6 結果のポイント` | `hard_stop_farm_result_placeholder_body` | classic actor placeholder repetition + filler outro | actual excerpt available | true placeholder, publish不可 |
| `64376` | `2026-05-03 16:50 JST` | `顔面打球直撃で救急搬送された が4日1軍合流へ 阿部監督明かす 2軍で実戦復…` | `hard_stop_farm_result_placeholder_body` | bodyless template sections (`📌関連ポスト`, `【二軍結果・活躍の要旨】`, `【二軍個別選手成績】`) + weak facts | full body unavailable; heading fragments only | true template-remnant, publish不可 |
| `64123` | `2026-05-03 18:25 JST` | `二軍 楽天・岸が無失点 巨人・中山3安打 西武・ワイナンスがで10K…` | `hard_stop_farm_result_placeholder_body` | bodyless template sections + headline stuffed into bodyless H3 + `h3_count=6` | full body unavailable; heading fragments only | true template-remnant, publish不可 |
| `64339` | `2026-05-03 13:25 JST` | `山崎伊織 わずか２球で緊急降板 ２軍復帰戦で自ら違和感訴え、Ｇタウンは騒然…` | `hard_stop_farm_result_placeholder_body` | bodyless H3 that contains the article headline itself + bodyless stats sections + weak facts | full body unavailable; heading fragments only | true generation/layout failure, publish不可 |
| `64229` | `2026-05-02 19:45 JST` | `育成２年目の西川歩が４日・ハヤテ戦で公式戦初先発へ「このまま２軍に帯同できる…` | `hard_stop_farm_result_placeholder_body` | `bodyless_h3=📌関連ポスト` + weak starter/scoring facts + title/body mismatch | full body unavailable; heading fragment only | rescue可能だが現状 publish不可 |

## 4. per-id detail

### sample A: `63845`

- evidence:
  - latest history row in `/tmp/guarded_publish_history_live_20260503.jsonl` at `2026-05-03T16:40:40.633160+09:00`
  - publish notice subject recovered from `/tmp/publish_notice_queue_20260503_audit.jsonl`:
    - `【公開済】巨人二軍 3-6 結果のポイント | YOSHILOVER`
  - body excerpt preserved in [doc/done/2026-04/242-D-farm-result-placeholder-body-publish-blocker.md](/home/fwns6/code/wordpressyoshilover/doc/done/2026-04/242-D-farm-result-placeholder-body-publish-blocker.md:17)
- classifier reason:
  - this is the exact class targeted by `_placeholder_actor_signal(...)` and repeated filler detection
  - confirmed patterns from the preserved body:
    - `先発の 投手`
    - `選手の適時打`
    - `試合の詳細はこちら`
  - relevant code:
    - actor placeholder hard-stop when 2+ hits in one or adjacent sentences: [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1533)
    - repeated filler detail: [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1578)
- body sample:
  - verified excerpt:
    - `先発の 投手は5回3失点`
    - `選手の適時打などで`
    - `試合の詳細はこちら`
- provisional judgment:
  - `true placeholder`
  - this is not a strict-classifier false positive; it is an obviously broken generated body.

### sample B: `64376`

- evidence:
  - latest history row at `2026-05-03T16:50:36.023288+09:00`
  - title recovered from `/tmp/good_draft_rescue_eval_20260503.json`
  - recent audit snapshot fields:
    - `resolved_subtype=farm`
    - `category=hard_stop`
- classifier reason:
  - hard-stop detail:
    - `bodyless_h3=📌関連ポスト`
    - `bodyless_h2=【二軍結果・活躍の要旨】`
    - `bodyless_h3=【二軍個別選手成績】`
  - review detail:
    - `starter_fact_weak=1`
    - `h3_count=5`
  - relevant code:
    - bodyless heading => hard-stop at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:889)
    - weak starter/scoring fact review at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:922)
- body sample:
  - full draft body: `unverified`
  - verified fragments available only from classifier detail:
    - `📌関連ポスト`
    - `【二軍結果・活躍の要旨】`
    - `【二軍個別選手成績】`
- provisional judgment:
  - `true template-remnant`
  - title itself is already malformed (`救急搬送された が...`), which strengthens the “body generation / template assembly failure” reading.

### sample C: `64123`

- evidence:
  - latest history row at `2026-05-03T18:25:41.115990+09:00`
  - title recovered from `/tmp/good_draft_rescue_eval_20260503.json`
  - this row was called out in prior freshness audit as the only new placeholder stop in that execution window
- classifier reason:
  - hard-stop detail:
    - `bodyless_h3=📌関連ポスト`
    - `bodyless_h2=【二軍結果・活躍の要旨】`
    - `bodyless_h3=【ファーム情報】楽天・岸が5回無失点巨人・中山3安打西武・ワイナンスが6回途中で10K-スポニチSponichiAnnex野球。`
    - `bodyless_h3=【二軍個別選手成績】`
  - review detail:
    - `starter_fact_weak=1`
    - `h3_count=6`
  - relevant code:
    - bodyless heading detection at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:861)
    - H3 over-limit review at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1818)
- body sample:
  - full draft body: `unverified`
  - verified fragments from classifier detail:
    - empty `📌関連ポスト`
    - empty `【二軍結果・活躍の要旨】`
    - an external-summary-looking H3 with no section prose under it
- provisional judgment:
  - `true template-remnant`
  - this does not look like a readable article being over-blocked; it looks like section headings were generated but the prose under them never materialized.

### sample D: `64339`

- evidence:
  - latest history row at `2026-05-03T13:25:38.951689+09:00`
  - title recovered from `/tmp/good_draft_rescue_eval_20260503.json`
- classifier reason:
  - hard-stop detail:
    - `bodyless_h3=📌関連ポスト`
    - `bodyless_h2=【二軍結果・活躍の要旨】`
    - `bodyless_h3=【巨人】山崎伊織わずか２球で緊急降板２軍復帰戦で自ら違和感訴え、Ｇタウンは騒然-スポーツ報知。`
    - `bodyless_h3=【二軍個別選手成績】`
  - review detail:
    - `starter_fact_weak=1; scoring_fact_weak=1`
    - `h3_count=6`
  - relevant code:
    - bodyless H2/H3 hard-stop at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:889)
    - weak starter/scoring fact review at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:924)
- body sample:
  - full draft body: `unverified`
  - verified fragment:
    - the article headline itself was used as an H3, but the section under it had no prose
- provisional judgment:
  - `true generation/layout failure`
  - there may be source material worth rewriting manually, but the stored draft is not publishable as-is.

### sample E: `64229`

- evidence:
  - latest history row at `2026-05-02T19:45:36.481962+09:00`
  - title recovered from `/tmp/good_draft_rescue_eval_20260503.json`
- classifier reason:
  - hard-stop detail:
    - `bodyless_h3=📌関連ポスト`
  - review detail:
    - `starter_fact_weak=1; scoring_fact_weak=1`
    - `h3_count=4`
  - repairable detail:
    - `title_body_mismatch_partial=SUBJECT_ABSENT`
  - relevant code:
    - even a single bodyless heading becomes hard-stop at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:889)
    - review weak-facts are appended separately at [src/guarded_publish_evaluator.py](/home/fwns6/code/wordpressyoshilover/src/guarded_publish_evaluator.py:1816)
- body sample:
  - full draft body: `unverified`
  - verified fragment:
    - empty `📌関連ポスト` section
- provisional judgment:
  - `rescue possible, but current hard-stop is still reasonable`
  - this is the closest sample to “classifier may feel strict” because the title reads like a real farm note, but the stored draft still lacked core result facts and carried empty template structure.

## 5. supporting note on `post_id=64313`

- not included in the 5-sample core table because the local artifacts do not preserve its exact placeholder `detail` string
- still verified:
  - title/source recovered in [doc/waiting/291_subtask_7_guarded_publish_audit.md](/home/fwns6/code/wordpressyoshilover/doc/waiting/291_subtask_7_guarded_publish_audit.md:42)
  - title:
    - `二軍 森田駿哉が２戦連続の快投 ３安打無失点で３勝目「変化球の精度も良くなっ…`
  - source:
    - `スポーツ報知巨人班X`
    - `https://twitter.com/hochi_giants/status/2050514017743999210`
  - guarded-publish outcome:
    - `post_id=64313` was deterministically blocked as `hard_stop_farm_result_placeholder_body`
- reading:
  - this supports the same conclusion as the 5 samples: source/title may look legitimate, but the generated draft body still fell into the placeholder blocker.

## 6. extrapolation to the latest 50 rows

### directly observed patterns

- In the `13` recent unique rows preserved in `/tmp/good_draft_rescue_eval_20260503.json`:
  - `13/13` have `farm_result_placeholder_body`
  - `13/13` also have `farm_result_required_facts_weak_review`
  - `13/13` also have `farm_result_h3_over_limit_review`
  - `13/13` include `bodyless_h3=📌関連ポスト`
  - `6/13` additionally include bodyless standard template sections:
    - `【二軍結果・活躍の要旨】`
    - `【二軍個別選手成績】`
- Canonical published incident `63845` shows the other major family:
  - actor-name placeholders left blank
  - repeated filler outro
- `13/50` latest rows also carry `lineup_duplicate_excessive` in `error`, which points to low-quality or cross-classified draft artifacts rather than clean readable farm results.

### inference

- strongest reading:
  - the latest-50 set is dominated by `body generation failure / template remainder / structurally incomplete draft` cases
  - not by “perfectly readable article blocked only because classifier is too strict”
- conservative estimate for the latest `50` rows:
  - `true placeholder or structurally incomplete as-is`: `42-48`
  - `editorially rescuable after manual cleanup or subtype/body rewrite, but still publish不可 as-is`: `2-8`
  - `clean false-positive (already readable/publishable body, blocked only by strict classifier)`: `0-2`

Reason for using ranges:

- only `14` unique cases in the latest-50 window had enough local evidence for close inspection (`13` eval snapshots + canonical `63845`)
- the remaining rows are history-only in this sandbox

### answer to the user’s question

- The evidence does **not** support “classifier が厳しすぎて普通に読める記事を大量に placeholder 扱いしている” as the main explanation.
- The dominant explanation is:
  - template sections were emitted with no prose under them
  - actor names / scoring facts were not concretized
  - related-post / component blocks remained inside the body
- Some drafts may be recoverable with manual cleanup or a future narrow body-repair flow, but they are not safe to auto-publish in their current stored form.

## 7. one-line judgment

- latest `50` placeholder rows are best understood as **mostly real body/template failures, with only a small salvageable edge and no observed mass false-positive pattern**.
