# 282-COST / 288-INGEST UNKNOWN flag resolution

Date: 2026-05-01 JST  
Mode: Codex Lane A round 5 / doc-only / read-only analysis

## 0. Scope normalization

- `docs/handoff/codex_responses/2026-05-01_pack_consistency_review.md` counted **3 Acceptance-pack UNKNOWN fields**:
  - `282-COST`: `Candidate disappearance risk`
  - `282-COST`: `Cache impact`
  - `288-INGEST`: `Cache impact`
- User prompt の「282 cost impact 定量化」は、上記 3 field を確定するための**補助 evidence**として扱う。
- この doc は既存 Pack を編集せず、UNKNOWN field を YES/NO に落とすための read-only resolution note。

## 1. Verdict summary

| pack | field | prior | verdict | core evidence | result |
|---|---|---|---|---|---|
| `282-COST` | `Candidate disappearance risk` | UNKNOWN | **NO** | preflight skip 後に `build_news_block()` が safe fallback を返す code/test 契約あり | Pack unknown 解消 |
| `282-COST` | `Cache impact` | UNKNOWN | **YES** | preflight gate は cache lookup **前**に return し、cache denominator を変える | Pack unknown 解消 |
| `288-INGEST` | `Cache impact` | UNKNOWN | **YES** | source add は新しい `source_url_hash` key を増やし、cold miss を発生させる | Pack unknown 解消 |

## 2. Evidence and judgment

### 2.1 `282-COST` `Candidate disappearance risk` -> NO

#### Read-only evidence

- `src/rss_fetcher.py:4594-4607`
  - `_gemini_text_with_cache()` は preflight skip 時に `emit_gemini_call_skipped(...)` を出して `return "", telemetry` する。
- `src/rss_fetcher.py:4970`, `5116`, `9459-9605`
  - postgame strict / parts path は `PreflightSkipResult` を返しうるが、`build_news_block()` 側では `rendered_ai_body_html` が空の時に `_apply_article_guardrails()` → `_build_safe_article_fallback()` へ落とす。
- `tests/test_gemini_preflight_gate.py:348-378`
  - `test_build_news_block_preflight_skip_still_returns_safe_fallback`
  - `blocks != ""` かつ `ai_body != ""` を assert。

#### Judgment

- 現 mainline の本文生成契約では、preflight skip は **Gemini call を止める**が、**candidate / draft 本文そのものを消さない**。
- よって Acceptance Pack field の `Candidate disappearance risk` は **NO**。
- ただし `293-COST` が要求しているのは「candidate 消失防止」ではなく、**preflight が発火した事実を user-visible にすること**。ここは別論点。

#### Important distinction

- `src/rss_fetcher.py:9581-9589` の `duplicate_guard skip` や `postgame_strict_review_reason` は `return "", ""` になるが、これは preflight 固有の振る舞いではない。
- 今回 NO 判定に使ったのは **preflight skip path 自体の fallback 契約**である。

### 2.2 `282-COST` `Cache impact` -> YES

#### Read-only evidence

- `src/rss_fetcher.py:4594-4607`
  - `_gemini_text_with_cache()` は `should_skip_gemini(...)` を **cache lookup 前**に評価する。
  - skip 成立時は `_gemini_cache_lookup(...)` を呼ばずに return する。
  - telemetry には `cache_hit_reason="preflight_skip"` / `gemini_call_made=False` が入る。
- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md:32`
  - `Cache impact` は `cache_hit ratio 変動 / TTL 変更 / 新 cache key` の有無で YES/NO/UNKNOWN を判定する field。
- `docs/ops/OPS_BOARD.yaml:202-207`
  - current observe evidence は `cache_hit 99% (498/500)`。
  - 同 observe に `282-COST flag OFF live 挙動不変` が含まれる。
- `gcloud logging read` on `yoshilover-fetcher`, `textPayload:"gemini_call_skipped"`:
  - 2026-05-01 実行結果は **0 rows**。現時点では flag OFF のため live skip event はまだ無い。

#### Judgment

- preflight gate が live ON になれば、match した candidate は cache layer を通らない。
- したがって `cache_hit ratio` の分母/分子が変わることは**設計上確定**している。
- よって Acceptance Pack field の `Cache impact` は **YES**。UNKNOWN ではない。

#### What is still not measurable

- `Cache impact = YES` と `exact cache delta = 未測定` は両立する。
- 現時点では flag OFF なので、**どちら向きに何 pt 動くか**は未実測。
- 補助 evidence として、`gcloud logging read` の最新 `rss_fetcher_flow_summary` 2 件では:
  - `live_update_disabled = 15`
  - `not_giants_related = 49`
  - `history_duplicate = 13`
- ただしこれは **flow-level skip summary** であり、preflight ON 時の incremental cache delta をそのまま定量化する証拠にはならない。

### 2.3 `288-INGEST` `Cache impact` -> YES

#### Read-only evidence

- `src/rss_fetcher.py:4430-4444`
  - cache key は `GeminiCacheKey(source_url_hash, content_hash, prompt_template_id)`。
- `src/rss_fetcher.py:10769-10775`
  - `source_url_hash` は `sha256(full_url)[:16]`。
- `src/gemini_cache.py:191-230`
  - cache storage は `source_url_hash` 単位の local/remote object に分かれる。
- `config/rss_sources.json`
  - current source set は 13 entries。
  - `NNN web` / `スポニチ web` / `サンスポ web` は未登録。
- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md:32`
  - `Cache impact` field は `new cache key` を含めて YES 判定対象。

#### Judgment

- 288 で新 source を追加すると、**新しい source URL 群**に対する `source_url_hash` bucket が必ず増える。
- そのため source add 直後は cold miss が増え、cache ratio には**確実に影響が出る**。
- よって Acceptance Pack field の `Cache impact` は **YES**。

#### Collision sub-judgment

- user prompt が懸念した「new source per article の cache key collision」は、read-only code から見る限り **NO** が妥当。
- 理由:
  - cache key は **title ではなく full source URL hash**。
  - hash は `sha256(... )[:16]` で、通常運用上の accidental collision を前提にする設計ではない。
  - title 競合は cache layer ではなく、`src/rss_fetcher.py:11412-11439` の `rewritten_title_norm` / `title_collision_detected` layer で別管理。
- `gcloud logging read` on `yoshilover-fetcher`, `textPayload:"title_collision_detected"`:
  - 2026-05-01 実行結果は **0 rows**
- `gcloud logging read` on `yoshilover-fetcher`, `textPayload:"same_fire_distinct_source_detected"`:
  - 2026-05-01 実行結果も **0 rows**

## 3. Residual unknowns

### 3.1 Pack-field residual UNKNOWNs

- **0 / 3**
- `2026-05-01_pack_consistency_review.md` で検出された 3 field は、この doc で全て YES/NO 化できる。

### 3.2 Supplemental unknowns still left after this doc

以下は **Acceptance Pack の UNKNOWN field ではない**が、post-deploy 実測が必要な補助論点。

| topic | current state | why still unknown | next verify path |
|---|---|---|---|
| `282-COST` exact Gemini call delta (`-X%`) | 未確定 | flag OFF のため `gemini_call_skipped` 実測 0。flow summary は preflight incremental delta を直接示さない | `293` live 完了後に `282` flag ON、24h で `gemini_call_skipped` / `gemini_cache_lookup` / publish count を比較 |
| `282-COST` exact cache-hit delta (direction / pt) | 未確定 | `Cache impact=YES` までは確定できるが、上がるか下がるかは live match mix 依存 | same 24h observe で `cache_hit ratio` before/after 比較 |
| `288-INGEST` exact cache-hit delta after source add | 未確定 | source add 未実施のため cold miss 量は未実測 | source add deploy 後 24h で `cache_hit ratio`, `title_collision_detected`, `same_fire_distinct_source_detected` を比較 |

## 4. Decision update for each Pack

### 4.1 `282-COST` Pack

- before:
  - `HOLD`
  - reason = `293` 未達 + UNKNOWN 2 件
- after this resolution:
  - `HOLD` 維持
  - reason = **`293` 未達 / 24h stability 未達 / 298 安定未達**
  - UNKNOWN blocker は解消済み

#### Practical meaning

- `282-COST` は、これ以降 `GO 推奨禁止` の理由が **UNKNOWN 残存**ではなく**precondition 未達**に整理される。
- Claude は Pack 更新時に `Candidate disappearance risk=NO`, `Cache impact=YES` を反映できる。

### 4.2 `288-INGEST` Pack

- before:
  - `HOLD`
  - reason = 5 preconditions 未達 + `Cache impact` UNKNOWN
- after this resolution:
  - `HOLD` 維持
  - reason = **289 / 290 / 295 / 291 / 282-293 cost chain の 5 条件未達**
  - `Cache impact` UNKNOWN は解消済み

#### Practical meaning

- `288-INGEST` も、以後の HOLD 理由は **precondition-only** になる。
- Claude は Pack 更新時に `Cache impact=YES` を反映しつつ、collision concern は note で `NO` と明記できる。

## 5. Claude handoff note

- Pack review が数えた 3 UNKNOWN field は、この resolution doc で全部 YES/NO に落ちた。
- ただし user prompt が挙げた「282 exact cost delta」は、field そのものではなく**補助 quant**としてはまだ post-deploy verify が必要。
- Pack 更新時は以下の 2 点を分けて書くのが安全:
  - `Acceptance Pack field` の確定値
  - `post-enable / post-source-add でしか取れない exact delta`
