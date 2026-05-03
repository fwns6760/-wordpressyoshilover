# 2026-05-03 BUG-004+291 subtask-10a postgame_strict fact recovery design

## scope / method

- scope: `postgame_strict` の `required_facts_missing` / `strict_contract_fail` のうち、**source body に fact があるのに現行 strict path が拾えていない**ものだけを rescue 対象として切り分ける。
- mode: read-only only. `src/` / `tests/` / `config/` / deploy / env / Scheduler / WP / Gemini / mail は未変更。
- evidence inputs:
  - worker A evidence: `docs/handoff/codex_responses/2026-05-03_BUG004_291_cross_subtype_track.md`
  - public source read: 12 candidate URLs, direct open/search only, volume scrape なし
  - code read: `src/rss_fetcher.py`, `src/postgame_strict_template.py`, `src/body_validator.py`, `src/title_validator.py`, `src/baseball_numeric_fact_consistency.py`
- external HTTP count used for this investigation: **23**

## strict answer

- worker A の 12 unique `postgame_strict_review_fallback` 候補を確認した。
- **possible = 5**
  - source body に `game_date / opponent / giants_score / opponent_score / decisive_event` を十分に置ける material がある。現行 strict path の source pickup / deterministic fill 不足が主因。
- **partial = 4**
  - source body に一部 fact はあるが、strict 必須 4軸のどれか、または decisive event が source 上で弱い。**緩和なし前提では review 維持**が妥当。
- **impossible = 3**
  - exact source が Giants first-team postgame ではない、または exact source を public read で確認できない。**rescue 対象外**。
- narrow rescue pool は **5 unique**。
- strict gate 自体を緩める必要はない。必要なのは **source-derived fact pickup の狭い補強**だけ。

## 12 candidate verdicts

| # | source_url | worker A rewritten title | worker A fail reason | public source verdict | rescue decision |
|---|---|---|---|---|---|
| 1 | `https://baseballking.jp/ns/694560/` | 巨人戦 終盤の一打で動いた試合 | `strict_contract_fail:postgame_opponent_missing,postgame_decisive_event_missing` | **impossible**: public page is MLB Blue Jays article about 岡本和真, not Giants first-team postgame | exclude |
| 2 | `https://www.nikkansports.com/baseball/news/202605020000169.html` | 巨人阪神戦 田中将大の試合後発言整理 | `required_facts_missing:giants_score,opponent_score` | **partial**: page date and opponent are visible, but final scoreline is not visible in source body; decisive event also weak | keep review |
| 3 | `https://www.nikkansports.com/baseball/news/202605020001031.html` | 【巨人】9回2発の反撃も届かず… | `required_facts_missing:game_date,giants_score` | **possible**: body has `阪神7-5巨人`, match day, opponent, and decisive play variants (`適時二塁打`, `8号ソロ`) | rescue candidate |
| 4 | `https://www.nikkansports.com/baseball/news/202605020001323.html` | 巨人阪神戦 阿部の試合後発言整理 | `required_facts_missing:game_date,giants_score,opponent_score` | **possible**: body has `阪神7-5巨人`, match day, opponent, and decisive events (`適時打`, 9回反撃 details) | rescue candidate |
| 5 | `https://twitter.com/TokyoGiants/status/2050493960901320727` | 巨人5-7 勝利の分岐点 試合の流れ | `required_facts_missing:game_date` | **partial**: exact tweet body was not retrievable in this session; rewritten title strongly implies scoreline exists, but source-body evidence was not confirmable | keep review |
| 6 | `https://baseballking.jp/ns/694514/` | 巨人戦 岡本和真の試合後発言整理 | `strict_contract_fail:postgame_opponent_missing,postgame_decisive_event_missing` | **impossible**: public page is MLB Blue Jays article, not Giants first-team postgame | exclude |
| 7 | `https://www.nikkansports.com/baseball/news/202605010002189.html` | 【とっておきメモ】巨人田中将大は… | `required_facts_missing:game_date,giants_score,opponent_score` | **impossible** for evidence: exact URL could not be opened/indexed in this session; nearest indexed result was a different 2025 article | keep review |
| 8 | `https://www.nikkansports.com/baseball/news/202605010002047.html` | 【巨人】阿部監督「最近四球がキーワード…」 | `required_facts_missing:game_date,giants_score,opponent_score` | **possible**: body has `阪神3-5巨人`, match day, opponent, and decisive batting events (`先制2点適時打`, `7号3ラン`) | rescue candidate |
| 9 | `https://www.nikkansports.com/baseball/news/202605010002095.html` | 【巨人】阿部監督「いた投手みんな頑張ってくれた」… | `required_facts_missing:game_date,giants_score,opponent_score` | **possible**: body has `阪神3-5巨人`, match day, opponent, and decisive batting events (`先制2点適時打`, `7号3ラン`) | rescue candidate |
| 10 | `https://www.nikkansports.com/baseball/news/202605010002174.html` | 【巨人】田中将大ホッとした203勝目… | `required_facts_missing:game_date,giants_score,opponent_score` | **partial**: body has date/score/opponent, but decisive event is weak; article centers on milestone / relief, not turning-point play | keep review |
| 11 | `https://baseballking.jp/ns/694482/` | 巨人戦 田中瑛斗の試合後発言整理 | `required_facts_missing:game_date,opponent` | **partial**: body has `5-3` and reliever context, but opponent/date are not obvious in visible source text and decisive event is weak | keep review |
| 12 | `https://www.nikkansports.com/baseball/news/202605010001921.html` | 【巨人】田中将大が日米203勝目… | `required_facts_missing:game_date,opponent,giants_score,opponent_score` | **possible**: body has `阪神3-5巨人`, match day, opponent, and decisive batting events (`先制2点適時打`, `7号3ラン`) | rescue candidate |

## code-path findings

### 1. strict source block is title + RSS summary only

- `src/rss_fetcher.py:14710-14728` prepares candidates from `entry.title` and `entry.summary` / `entry.description`.
- `src/rss_fetcher.py:2807-2825` builds `source_fact_block` from `title` and `summary` only. `news` source では public page body は読まない。
- result: page本文にある `＜阪神7－5巨人＞◇2日◇甲子園` や 1〜2段落目の score / opponent / play が、RSS summary に載っていない限り strict path には入らない。

### 2. published_at exists but strict prompt input does not expose it

- `src/rss_fetcher.py:14750` で `published_at` は candidate に入っている。
- しかし `src/rss_fetcher.py:5371-5380` の strict `source_block` は `title`, `summary`, `source_name`, `source_url`, `source_fact_block` だけ。
- `game_date` missing 9/12 はこの設計と整合する。page publish date を source 事実として prompt に渡していない。

### 3. strict path has no deterministic repair before validation

- `src/rss_fetcher.py:5423-5443` で Gemini JSON parse 後すぐ `validate_postgame_strict_payload(...)` に入る。
- `src/postgame_strict_template.py:108-149` は `game_date`, `opponent`, `giants_score`, `opponent_score`, `result` を required にしており、missing なら即 review fallback。
- parse 後に `published_at`, `scoreline`, `team names`, `body excerpt` から埋め直す deterministic step は存在しない。

### 4. existing opponent fallback is too naive for rescue

- `src/rss_fetcher.py:3934-3942` の `_extract_game_opponent_label()` は source text 内の **最初の非巨人 team marker** を返すだけ。
- team order / score orientation / mixed-scope article を見ない。
- そのため `阪神3-5巨人` のような opponent-first scoreline の deterministic repair には不十分。

### 5. existing reusable score/date parsers already exist, but strict path does not use them

- `src/baseball_numeric_fact_consistency.py:122-191` has `ScoreToken` / `DateToken`.
- `src/baseball_numeric_fact_consistency.py:266-309` has `extract_scores(text)` and already understands left/right team orientation.
- `src/baseball_numeric_fact_consistency.py:462-500` has `extract_dates(text)` and `DateToken.resolve(publish_time_iso)`.
- These helpers are not wired into `postgame_strict` parse/validate flow.

### 6. body validator is strict about decisive-event wording

- `src/body_validator.py:529-557` requires:
  - result block: score, win/loss, opponent, date
  - highlight block: `POSTGAME_DECISIVE_EVENT_RE`
- current decisive-event regex only accepts tokens such as `決勝打`, `勝ち越し`, `本塁打`, `適時打`, `先制`, `好投`, `セーブ`.
- source variants like `適時二塁打`, `8号ソロ`, `7号3ラン` are semantically decisive but not always canonicalized into the accepted token set.

### 7. two candidates are not rescue misses but upstream Giants-scope false positives

- `src/rss_fetcher.py:13207-13215` treats any Giants keyword or Giants roster-name hit as `is_giants_related=true`.
- MLB `岡本和真` pages at `694560` and `694514` passed this gate and then fell into `postgame` templating because score/result language existed.
- These should **not** be included in the narrow rescue pool for subtask-10b. They are upstream scope/mixed-team hygiene, not source-fact pickup misses.

## narrow recovery design

### gap type A: `game_date` is available in candidate metadata but never reaches strict source input

- current problem:
  - `published_at` exists on the candidate, but `source_block` omits it.
  - strict payload must emit `YYYY-MM-DD`, so pages that only show `5月1日` / `2日` or rely on page publish date fall into `required_facts_missing:game_date`.
- narrow fix:
  - add a deterministic prefill stage **after parse / before validate** for `postgame_strict` only.
  - build `source_text_for_repair = title + summary + source_fact_block + published_at_iso + published_day_label`.
  - if `payload.game_date` is empty:
    - run `extract_dates(source_text_for_repair)`
    - resolve with candidate `published_at`
    - fill only when a single non-ambiguous date resolves
  - if ambiguous or absent, keep current review fallback.
- affected unique candidates:
  - **9** have `game_date` missing
  - **5** are still rescue-eligible after keeping partial/impossible cases blocked
- positive fixture candidates:
  - `202605020001323` (`阪神7-5巨人`, `2日`, page timestamp visible)
  - `202605010001921` (`阪神3-5巨人`, `1日`, page timestamp visible)
- negative fixture candidates:
  - `2050493960901320727` exact tweet body unavailable in current session
  - `202605010002189` exact source URL not retrievable in current session

### gap type B: score/opponent are in public page body but strict path only sees RSS summary

- current problem:
  - strict source block never fetches page lead/meta for `news` sources.
  - Nikkan-style body lead `＜阪神7－5巨人＞◇2日◇甲子園` is visible on the page but may be absent from RSS summary.
- narrow fix:
  - introduce a **review-path-only** source enrichment step for whitelisted domains (`nikkansports.com`, optionally `baseballking.jp` only if body lead is deterministic).
  - trigger only when first strict pass fails with any of:
    - `required_facts_missing:game_date`
    - `required_facts_missing:opponent`
    - `required_facts_missing:giants_score`
    - `required_facts_missing:opponent_score`
  - fetch a minimal body slice:
    - page timestamp / meta description / first 2-3 article paragraphs
    - do not full-scrape beyond the lead
  - merge only those lead facts into `source_text_for_repair`, then rerun deterministic fill or a second strict parse.
  - if enrichment still cannot prove the fact, keep review.
- affected unique candidates:
  - **6** Nikkan result/quote pages show score/date/opponent in public page body
  - **5** of those remain rescue-eligible after decisive-event check
- positive fixture candidates:
  - `202605020001031`
  - `202605010002047`
- negative fixture candidates:
  - `202605020000169` Instagram reaction article: no final scoreline in visible body
  - `694560` MLB Blue Jays article: body fetch would be available but article is out-of-scope

### gap type C: existing code has deterministic team-aware score parsing, but postgame_strict does not reuse it

- current problem:
  - current strict flow relies on Gemini to map `阪神3-5巨人` into `giants_score=5`, `opponent_score=3`, `opponent=阪神`.
  - no deterministic orientation repair exists before validation.
- narrow fix:
  - reuse `extract_scores(...)` from `src/baseball_numeric_fact_consistency.py`.
  - prefill rules:
    - if payload scores are missing and exactly one non-ambiguous Giants-oriented score token exists, fill `giants_score`, `opponent_score`, and `result`.
    - if payload opponent is missing and the chosen score token has `left_team` or `right_team`, fill opponent from the non-Giants side.
    - do not fill anything when no Giants side can be proven.
  - this is not gate relaxation; it is a deterministic read of source text already present.
- affected unique candidates:
  - **6** opponent-first Nikkan scorelines are good fits
  - **1** BaseballKing commentary page (`694482`) has score but not enough team orientation, so it should remain blocked
- positive fixture candidates:
  - `202605020001031`
  - `202605010002095`
- negative fixture candidates:
  - `694482` (`5-3` visible but opponent unclear)
  - `202605020000169` (no final scoreline in visible body)

### gap type D: decisive-event phrases are present, but canonical strict token may be missing

- current problem:
  - body validator requires decisive-event tokens in `【ハイライト】`.
  - public source often expresses the event as `適時二塁打`, `8号ソロ`, `7号3ラン`.
  - those are real source facts, but current canonical token set is narrower.
- narrow fix:
  - add a deterministic `decisive_event` picker on the repair path only.
  - source phrase classes that are safe to canonicalize:
    - `適時二塁打` / `適時三塁打` -> canonical token `適時打`
    - `○号ソロ` / `○号2ラン` / `○号3ラン` -> canonical token `本塁打`
    - `先制の...` -> canonical token `先制`
  - renderer/highlight line should keep the original source evidence, but emitted highlight text may use the canonical decisive token so body validator can verify it.
  - if the source has no decisive play at all, keep review.
- affected unique candidates:
  - clear need: **1** (`202605020001031`)
  - likely helpful but not mandatory: `202605020001323`, `202605010002047`, `202605010002095`, `202605010001921`
- positive fixture candidates:
  - `202605020001031` (`適時二塁打`, `8号ソロ`)
  - `202605010001921` (`先制2点適時打`, `7号3ラン`)
- negative fixture candidates:
  - `202605010002174` (milestone/relief focus, no clear decisive play in visible source)
  - `202605020000169` (Instagram reaction article)

## narrow rescue boundary for subtask-10b

- rescue target should be limited to these **5**:
  - `202605020001031`
  - `202605020001323`
  - `202605010002047`
  - `202605010002095`
  - `202605010001921`
- keep blocked / do not rescue:
  - `694560`, `694514`: non-Giants MLB false positives
  - `202605020000169`: scoreline not visible in source body
  - `2050493960901320727`: exact tweet body unavailable in this investigation
  - `202605010002189`: exact URL not retrievable in this investigation
  - `202605010002174`: decisive play weak
  - `694482`: score visible but opponent/date weak

## acceptance guidance for subtask-10b

- keep `postgame_strict` gate unchanged.
- only rescue when the source-derived repair proves the fact.
- do not rescue candidates whose source still lacks one of the strict required axes after repair.
- do not rescue MLB / mixed-team / non-Giants scope leaks under the name of fact recovery.
- recommended minimum fixture set for impl:
  - positive:
    - `202605020001031`
    - `202605020001323`
    - `202605010002047`
    - `202605010001921`
  - negative:
    - `694560`
    - `202605020000169`
    - `202605010002174`
    - `694482`

## recommended next Claude decision

- proceed to `subtask-10b` as a **narrow recovery impl**:
  - deterministic date/score/opponent prefill
  - review-path-only lead/body enrichment for whitelisted news domains
  - decisive-event canonicalization from source phrases
  - default OFF, live-inert, fixture-backed
