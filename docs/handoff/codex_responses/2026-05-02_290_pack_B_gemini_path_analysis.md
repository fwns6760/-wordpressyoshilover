# 290 Pack B Gemini Path Analysis

Date: 2026-05-02 JST  
Mode: Codex B / read-only analysis / doc-only  
Scope: `ENABLE_WEAK_TITLE_RESCUE=1` enablement時の Gemini call delta を source path のみで見積もる

## 0. Conclusion Snapshot

- `weak_title_rescue` helper 自体は **Gemini を呼ばない**
- ただし rescue 成功で candidate が `post_gen_validate` title skip を通過すると、通常の本文生成 lane に復帰し、**downstream では Gemini に到達し得る**
- source だけで見た conservative upper bound は **`+7 logical Gemini entries/day`**、現在の live baseline proxy 比で **`+8.8%` から `+11.6%`**
- 判定: **`EXTEND_HOLD`**
  - 理由1: `+5%` 閾値を conservative upper bound が超える
  - 理由2: Pack A `OBSERVED_OK` 1週間 (`2026-05-08 JST`) gate は別条件として依然必要

## 1. weak title rescue 実装 path

### 1-1. flag hit file

`ENABLE_WEAK_TITLE_RESCUE` の source hit は `src/rss_fetcher.py` のみ。

- `src/rss_fetcher.py:193` `WEAK_TITLE_RESCUE_ENV_FLAG = "ENABLE_WEAK_TITLE_RESCUE"`
- `src/rss_fetcher.py:12734-12810` `_maybe_apply_weak_title_rescue(...)`
- `src/rss_fetcher.py:14251` dry-run path call site
- `src/rss_fetcher.py:14371` live path call site

関連 helper / validator:

- `src/weak_title_rescue.py:291-336` `rescue_related_info_escape(...)`
- `src/weak_title_rescue.py:339-390` `rescue_blacklist_phrase(...)`
- `src/weak_title_rescue.py:282-288` `is_strong_with_name_and_event(...)`
- `src/title_validator.py:290-298` `no_strong_marker` narrow exception

### 1-2. call chain

Live path の chain は以下。

1. `src/rss_fetcher.py:14349-14357` `_rewrite_display_title_with_guard(...)`
2. `src/rss_fetcher.py:14358-14370` `_apply_title_player_name_backfill(...)`
3. `src/rss_fetcher.py:14371-14383` `_maybe_apply_weak_title_rescue(...)`
4. `src/rss_fetcher.py:14384-14428`
   - `_maybe_route_weak_generated_title_review(...)`
   - `_maybe_route_weak_subject_title_review(...)`
5. rescue / narrow exception で title weak 判定を抜けた場合のみ
   `src/rss_fetcher.py:14430-14442` `build_news_block(...)`
6. `src/rss_fetcher.py:9814-9910` `_generate_gemini_body()`
7. 条件次第で
   - rule-based body (`Gemini skip`)
   - preflight / cache / duplicate guard (`Gemini skip`)
   - `generate_article_with_gemini(...)` (`Gemini path`)

### 1-3. rescue 発火条件

`_maybe_apply_weak_title_rescue(...)` が動く条件:

1. env flag `ENABLE_WEAK_TITLE_RESCUE=1`
2. `news` / `social_news` article path で title rewrite 済み
3. rewritten title が次のどちらか
   - `is_weak_generated_title(...) = True`
   - `is_weak_subject_title(...) = True`

rescue strategy は 2 つ:

- `related_info_escape`
  - `src/weak_title_rescue.py:299-336`
  - 末尾 `関連情報` 系 escape title を source title / metadata から再構成
- `blacklist_phrase`
  - `src/weak_title_rescue.py:347-390`
  - `ベンチ関連発言` / `発言ポイント` 系を source title ベースで再構成

別系統の narrow exception:

- `src/title_validator.py:290-298`
- `no_strong_marker` でも `人名 + 具体イベント語` を満たせば weak 判定解除

### 1-4. subtype / failure-path 境界

- code 上は **subtype hard whitelist なし**
- 実際の trigger は `weak_subject_title:*` / `weak_generated_title:*` 系に限定
- `postgame_strict:*` は **290 rescue helper の trigger ではない**
- `doc/active/290-QA-weak-title-rescue-backfill.md` 実装メモにもある通り、`#20` の `postgame_strict` 主因は 295 scope 寄りで、290 の本筋は weak title path

Observed target family は ticket 上 `7` 件:

- `related_info_escape` 2
- `blacklist_phrase` 3
- `no_strong_marker` narrow exception 2

## 2. Gemini call 有無判定

### 2-1. direct rescue path

**NO**

`_maybe_apply_weak_title_rescue(...)` と `src/weak_title_rescue.py` helper 群は regex / metadata / title backfill だけで完結している。Gemini call site は無い。

Direct rescue path 内で行うこと:

- weak 判定
- metadata 構築
- regex 抽出
- safety blocker 判定
- title rewrite
- rescue 後の weak 再判定
- `weak_title_rescued` log emit

### 2-2. end-to-end path after rescue

**YES, downstream conditional**

Rescue 成功で `continue` skip を回避すると、candidate は `build_news_block(...)` に進む。そこから Gemini 到達条件は以下。

1. `src/rss_fetcher.py:1121-1142` `_resolve_article_ai_strategy(...)`
   - `試合速報` / `選手情報` / `首脳陣` は AI route に入りやすい
2. `src/rss_fetcher.py:1145-1152` `get_article_ai_mode(...)`
   - default は `gemini` または `auto`
3. `src/rss_fetcher.py:9870-9892`
   - rule-based subtype (`lineup` / `program` / `notice`) なら Gemini skip
   - ただし rule-based は env allowlist 依存で default empty
4. それ以外は `src/rss_fetcher.py:9893-9908` `generate_article_with_gemini(...)`

### 2-3. model / prompt / attempts

Strict path:

- entry: `src/rss_fetcher.py:9107-9149`
- request function: `src/rss_fetcher.py:4328-4377`
- model: `gemini-2.5-flash`
- endpoint: `.../models/gemini-2.5-flash:generateContent?key={api_key}`
- prompt: `_build_gemini_strict_prompt(...)`
- max attempts: `src/rss_fetcher.py:1160-1169` より `1-3`、strict default `3`
- max output tokens: `src/rss_fetcher.py:4351` で `1536`

Grounded path:

- entry: `src/rss_fetcher.py:9480-9547`
- model: `gemini-2.5-flash`
- tool: `google_search`
- prompt: category/subtype ごとの grounded prompt
- max attempts: `src/rss_fetcher.py:1160-1169` より non-strict `1-2`
- max output tokens: `src/rss_fetcher.py:9485` で `2048`

Caching / preflight:

- `src/rss_fetcher.py:4668-4940` `_gemini_text_with_cache(...)`
- preflight skip / cache hit / miss-breaker / per-post budget により `gemini_call_made=false` の可能性あり

### 2-4. runtime auth / cost caveat

`rss_fetcher` の traced path は `GEMINI_API_KEY` を直接参照する。

- `src/rss_fetcher.py:9045` `api_key = os.environ.get("GEMINI_API_KEY", "")`
- `src/rss_fetcher.py:4370` / `9495` で API key 付き `generateContent`

`src/entrypoint.sh` は `GEMINI_OAUTH_CREDS` を `/root/.gemini/oauth_creds.json` に展開するが、今回 traced した `rss_fetcher` Gemini path 自体はその OAuth creds を参照していない。よって source-only 解析としては、**token 単価より call-count delta を主要指標にすべき**。

## 3. Gemini delta 見積もり (Pack B enablement 時)

### 3-1. rescue 発火頻度の proxy

read-only で拾える明示 evidence は以下。

- `doc/active/289-OBSERVE-post-gen-validate-mail-notification.md`
  - 15:00 trigger で `prepared 27 / post_gen_validate skip 22 / created 0`
- `doc/active/290-QA-weak-title-rescue-backfill.md`
  - このうち 290 の target は `A/B 7` candidate family

そこから置ける proxy:

- rescue target rate vs prepared entries: `7 / 27 = 25.9%`
- rescue target rate vs post_gen_validate skips: `7 / 22 = 31.8%`

これは 1 trigger の audit snapshot であり、**日次 recurring 実測ではない**。したがって日次見積もりは upper-bound として `+7 rescued candidates/day` を採用するのが安全。

### 3-2. additional Gemini calls/day

Direct helper delta:

- `+0`

End-to-end logical delta upper bound:

- rescued candidate `1` 件が本文生成まで進み、rule-based / preflight / cache hit で止まらない場合
  - **`+1 logical Gemini generation entry`**
- target family upper bound `7/day`
  - **`+7 logical Gemini entries/day`**

Retry-aware HTTP request upper bound:

- strict path default `3 attempts` なので worst case `+21 HTTP requests/day`
- grounded path default upper `2 attempts` なので worst case `+14 HTTP requests/day`

### 3-3. baseline compare

Current live proxy from existing observe docs:

- `docs/handoff/codex_responses/2026-05-01_282_COST_pack_supplement.md`
  - `gemini_call_made=true = 4` in `95m33s`
  - day-rate proxy `~60.3 calls/day`
- `docs/handoff/codex_responses/2026-05-01_298_Phase3_stability_evidence_pre.md`
  - `gemini_call_made=true = 1` in `18m12s`
  - day-rate proxy `~79.1 calls/day`

Against those baselines:

- `+7/day` vs `60.3/day` = **`+11.6%`**
- `+7/day` vs `79.1/day` = **`+8.8%`**

つまり source-only conservative upper bound は **`+5%` 閾値を超える**。

### 3-4. token/day upper bound

Observed token telemetry is not available for 290 candidates themselves, so config upper bounds only:

- strict path output upper bound: `7 * 1536 = 10,752 output tokens/day`
- grounded path output upper bound: `7 * 2048 = 14,336 output tokens/day`
- plus prompt input tokens (prompt 長は source / reactions / stats block に依存)

Pack B の cost議論では token 単価より **`gemini_call_made:true` / actual request count** を見る方が確実。

## 4. HOLD 解除可能性判定

### 4-1. proposed threshold

- release candidate 条件:
  - Pack A `OBSERVED_OK` 1週間 (`2026-05-08 JST`) 達成
  - Gemini delta conservative estimate or live verify が `<= +5%`
- hold 維持条件:
  - conservative source-only upper bound が `> +5%`
  - または live env 不明点が多く safe に `<= +5%` を言えない

### 4-2. judgment for current task

**Current judgment: `EXTEND_HOLD`**

理由:

1. direct helper は non-LLM だが、successful rescue は downstream Gemini lane を reopen する
2. `+7/day` upper bound は current baseline proxy 比 `+8.8%` から `+11.6%`
3. `ARTICLE_AI_MODE` / `STRICT_FACT_MODE` / `RULE_BASED_SUBTYPES` / cache hit 実効値が read-only source だけでは固定できず、safe に `<= +5%` と断言できない
4. Pack A 1週間 observe gate (`2026-05-08 JST`) は independent precondition のまま

### 4-3. independence from other HOLD conditions

この解析は **Gemini delta UNKNOWN** を縮める材料であり、以下を代替しない。

- Pack A 1週間 `OBSERVED_OK` (`2026-05-08 JST`)
- mail burst / silent skip / Team Shiny invariants
- `298/293/300` 周辺の production stability gates

## 5. HOLD residual risks

1. `2026-05-08 JST` wait は依然必須
2. conservative upper bound では Gemini delta `> +5%`
3. `rss_fetcher` traced path は `GEMINI_API_KEY` 使用であり、`GEMINI_OAUTH` 前提は source 上は確認できない
4. `RULE_BASED_SUBTYPES` が default empty のため、rescued candidate の多くは rule-based skip より Gemini lane に入りやすい
5. 290 helper は `postgame_strict` 主因を直接は解消しないため、ticket 上の #20 類型は 295 scope 側の残リスクがある

## 6. Recommendation to Claude

- Pack B を `RELEASE_CANDIDATE_5/8` に上げる前に、少なくとも以下 4 点を live config / observe で確認した方がよい
  1. `ARTICLE_AI_MODE`
  2. `STRICT_FACT_MODE`
  3. `RULE_BASED_SUBTYPES`
  4. `gemini_call_made:true` baseline の正式 24h 窓
- source-only 判断では `Gemini delta = 0` は成立しない
- 本 doc をもって `UNKNOWN` は **「helper 直下は 0、end-to-end upper bound は > +5%」** に更新するのが妥当
