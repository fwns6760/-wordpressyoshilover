# Theme 3 body quality small fix

theme: `theme3_body_quality_small_fix`
date: 2026-05-06
scope: repo-only, default OFF, no deploy, no env flip

## audit summary

### 1. NG表現除去

- existing cover:
  - `src/article_quality_guards.py` already had `ENABLE_FORBIDDEN_PHRASE_FILTER`, heading rewrite, and visible-phrase detection for `目を引きます` / `注目が集まります` / `ファン必見です` / `今後の動向から目が離せません` / `と言えるでしょう` / `ではないでしょうか`
- gap:
  - `find_forbidden_phrase()` detected `と言えるでしょう` / `ではないでしょうか`, but `sanitize_forbidden_visible_text()` did not repair them
  - prompt-side banned wording `注目されます` / `期待されます` / `着目していきます` was not in forbidden coverage
- fix:
  - extend forbidden rewrite + detection only under existing `ENABLE_FORBIDDEN_PHRASE_FILTER`

### 2. H3過多

- existing cover:
  - `ENABLE_H3_COUNT_GUARD` in post-gen validate rejected `3+` H3
- gap:
  - detect-only; no repair path
- fix:
  - add `ENABLE_H3_COUNT_REPAIR`
  - render-time only: after 2 visible H3s, later H3s are demoted to H4 before validate/output

### 3. title / H3 / lead 重複

- existing cover:
  - `ENABLE_BODY_DUP_REDUCTION` removed intro duplication only in the first section
  - `ENABLE_BODY_LEAD_PARAPHRASE_GUARD` paraphrased first lead only
- gap:
  - later section lead under H3 could still restate the heading/title and survive
- fix:
  - extend existing `ENABLE_BODY_DUP_REDUCTION`
  - section-local first sentence removal now applies to every section when there is another sentence to keep

### 4. source 外推測

- existing cover:
  - `detect_source_entity_conflict()` only looked at source title/summary
  - `ENABLE_SOURCE_GROUNDING_STRICT` / numeric guard handled score grounding elsewhere, but not sentence-level body cleanup
- gap:
  - generated body could still add score / quote / team / actor lines not present in source
- fix:
  - add `ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR`
  - repair path removes sentences with ungrounded `score / quote / non-source team / different actor` when that section still has another sentence
  - remaining single-sentence unresolved cases are routed to review by post-gen validate with `source_grounding_drift:*`

### 5. short 素材短文化

- existing cover:
  - `ENABLE_FARM_SHORT_POST_TEMPLATE`
  - `ENABLE_SOURCE_LINK_ONLY_TEMPLATE`
  - `ENABLE_SHORT_SOURCE_NARROW_TEMPLATE`
- gap:
  - if those pre-routing flags were off, a short source could still keep an overlong already-generated body
- fix:
  - add `ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR`
  - post-process only: if source is short and generated body is clearly overlong, swap to existing compact template builder result

## before / after samples

### forbidden phrase

- before:
  - `この見方が妥当ではないでしょうか。`
- after:
  - `この見方が妥当とも見られます。`

### H3 repair

- before:
  - `<h3>【ハイライト】</h3><h3>【選手成績】</h3><h3>【試合展開】</h3>`
- after:
  - `<h3>【ハイライト】</h3><h3>【選手成績】</h3><h4>【試合展開】</h4>`

### lead dedupe

- before:
  - `【試合展開】`
  - `試合展開は終盤の継投が焦点だった。`
  - `七回の継投が流れを変えた。`
- after:
  - `【試合展開】`
  - `七回の継投が流れを変えた。`

### source grounding drift

- before:
  - `阿部監督が若手起用の意図を説明した。`
  - `5-3で逃げ切った流れも振り返りたい。`
- after:
  - `阿部監督が若手起用の意図を説明した。`

### short-source shrink

- before:
  - short X/news source + 220 chars超の長文 body
- after:
  - existing compact template body with `出典:` line, shorter by 40+ chars

## removed / shortened content types

- forbidden visible phrases rewritten:
  - `注目されます`
  - `期待されます`
  - `着目していきます`
  - `と言えるでしょう`
  - `ではないでしょうか`
- H3 overcount repair demotes extra headings instead of reject
- duplicate lead repair drops section-first duplicate sentences
- source grounding drift repair drops:
  - ungrounded score lines
  - ungrounded quote lines
  - ungrounded non-source team lines
  - lines whose detected actor differs from the source actor
- short-source shrink swaps inflated long body to compact body when savings are meaningful

## flags

- existing:
  - `ENABLE_FORBIDDEN_PHRASE_FILTER`
  - `ENABLE_BODY_DUP_REDUCTION`
- new:
  - `ENABLE_H3_COUNT_REPAIR`
  - `ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR`
  - `ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR`

all new flags default to OFF. Existing default values unchanged.

## skipped ambiguous scope

- free-form player/entity inference beyond the existing source actor detector was not added
- section-empty rewrite for single-sentence source-drift violations was not auto-repaired; those stay review-routed
- no validator/body-contract relaxation, no deploy, no env flip, no guarded-publish / publish-notice edits

## suggested enable order for later preview/deploy judgment

1. `ENABLE_FORBIDDEN_PHRASE_FILTER` with the added rewrite coverage
2. `ENABLE_H3_COUNT_REPAIR`
3. `ENABLE_BODY_DUP_REDUCTION` extended section-lead repair
4. `ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR`
5. `ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR`
