# 229 Gemini cost governor + LLM call reduction

- number: 229
- type: audit + plan
- status: REVIEW_NEEDED
- priority: P0.5
- parent: -
- created: 2026-04-27
- lane: Codex B

## background

- 2026-04-26 の Gemini 2.5 Flash 消費が約 310 円 / 日まで上がり、auto publish / draft repair / article generation 周辺の常時実行コストが無視できなくなった。
- 本票の目的は「品質を落とさず、無駄 call を減らす」ための read-only audit と 5 sub-ticket の設計。
- 実装は別便。本票では `src/` / `tests/` / `config/` / GCP live / WP / mail / X / Gemini API 実 call は触らない。

## audit basis

- baseline HEAD: `c2e3678`
- 調査は repo read-only grep / source read のみ
- 実行した観点:
  - `gemini|Gemini|GenerativeModel|generate_content|google.generativeai|genai`
  - `GEMINI_API_KEY|GEMINI_MODEL`
  - `src/llm_*.py`, `src/*gemini*.py`

## high-level finding

- 現在の Gemini コスト中心は `rss_fetcher` 系の記事生成と `draft_body_editor` 系の本文修復。
- user 想定に反して、`guarded_publish_evaluator.py`、`publish_notice_scanner.py`、`publish_notice_email_sender.py` は現状 rule-based / deterministic であり、ここに Gemini 実 call はない。
- `audit_notify.py` は `AUDIT_OPINION_USE_LLM` の mode 名をログに出すだけで、repo 上に Gemini 実 call は未実装。
- 既存の hash/cache は部分的に存在する:
  - `src/pre_publish_fact_check/llm_adapter_gemini.py`: `post_id + content_hash` cache あり
  - `src/repair_fallback_controller.py`: `input_hash` / `idempotency_key` は記録するが、skip / 再利用には使っていない
  - `src/publish_notice_scanner.py`: mail duplicate history はあるが LLM dedupe ではない

## non-call confirmation

以下は今回の audit で「Gemini cost source ではない」と確認できた箇所。

- `src/guarded_publish_evaluator.py`
  - subtype 解決、freshness、title-body mismatch は rule-based
  - `validate_title_body_nucleus(...)` は deterministic validator
- `src/publish_notice_scanner.py`
  - subtype 推定と duplicate suppression は regex / history ベース
- `src/publish_notice_email_sender.py`
  - 件名分類、manual X candidate、suppression は deterministic
- `src/audit_notify.py`
  - `opinion_check_mode` のログ出力のみ。Gemini adapter 呼出は repo 上にない

## LLM call site inventory

重複 wrapper を除いた logical call site family は 10 本。

| # | area | file / function | runtime | current model / path | A/B/C | notes |
|---|---|---|---|---|---|---|
| 1 | draft repair core | `src/tools/draft_body_editor.py::call_gemini` | active | `gemini-2.5-flash` REST | C | 042 本線の本文修復コア。`src/tools/run_draft_body_editor_lane.py` と `src/repair_fallback_controller.py` から利用 |
| 2 | postgame article parts JSON render | `src/rss_fetcher.py::_maybe_render_postgame_article_parts` -> `_request_gemini_strict_text` | active/conditional | `gemini-2.5-flash` REST | C | `STRICT_FACT_MODE` + `ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME` 時のみ。postgame の構造化生成 |
| 3 | strict article generation | `src/rss_fetcher.py::generate_article_with_gemini` strict path | active/conditional | `gemini-2.5-flash` REST | C | source block を強く使う本文生成本線 |
| 4 | grounded general article generation | `src/rss_fetcher.py::generate_article_with_gemini` grounded path | active/conditional | `gemini-2.5-flash` + `google_search` | C | offday / fallback を含む本文生成。prompt が最も長い |
| 5 | post-generation numeric fact check | `src/rss_fetcher.py::_fact_check_article` | active/conditional | `gemini-2.0-flash` + `google_search` | C | 数字入り記事だけ実行。hallucination/数値修正寄り |
| 6 | X copy generation | `src/x_post_generator.py::_generate_with_gemini_response` | optional/live config dependent | `gemini-2.5-flash` REST or `gemini` CLI opt-in | B | 失敗時は deterministic fallback あり。現状 publish-notice mail 本体はここを使っていない |
| 7 | pre-publish fact-check live detect | `src/pre_publish_fact_check/llm_adapter_gemini.py::GeminiFlashAdapter.detect` | PARKED / user-go boundary | `google.generativeai` SDK + `gemini-2.5-flash` | C | `113 HALLUC-LANE-002`。既に `content_hash` cache + `max_calls` cap あり |
| 8 | manual post body generation | `src/manual_post.py::generate_body_with_gemini` | manual only | `gemini-2.5-flash` REST | A | convenience path。日次 mainline ではない |
| 9 | weekly digest generation | `src/weekly_summary.py::generate_weekly_summary` | scheduled/manual weekly | `gemini-2.5-flash` REST | B | 低頻度 summary task。Lite 化しやすい |
| 10 | debug endpoint | `src/server.py` `/test-gemini` | debug only | local `gemini` CLI | A | 運用価値が低く、コスト governor 対象にしやすい |

## A/B/C classification

### A. Gemini 不要(削減可能)

1. `src/manual_post.py::generate_body_with_gemini`
   - manual one-shot convenience path
   - `--body` 明示入力で代替可能
   - mainline 品質 gate と独立
2. `src/server.py:/test-gemini`
   - debug endpoint で production value が薄い
   - cost guard の対象にしやすい

### B. Flash-Lite 候補(品質影響少)

1. `src/x_post_generator.py::_generate_with_gemini_response`
   - 現在でも deterministic fallback を持つ
   - 失敗時の user-visible regression が限定的
   - mail sender 本体は deterministic なため、Lite 化しても publish gate には直結しない
2. `src/weekly_summary.py::generate_weekly_summary`
   - 低頻度 summary / recap 系
   - strict source correction や WP publish gate とは別レーン

補足:

- prompt にある「subtype fallback」「mail classification」「publish notice の軽いラベル付け」は、current repo では既に deterministic 実装であり Gemini call site ではない。
- したがって 229-D は「既存の B call を Lite に落とす」ことが主で、publish gate / subtype 系を新たに LLM 化する話ではない。

### C. Flash 維持(品質直結)

1. `src/tools/draft_body_editor.py::call_gemini`
   - 本文修復コア
   - source grounding / heading invariance / scope invariance guard と一体
2. `src/rss_fetcher.py::_maybe_render_postgame_article_parts`
   - postgame の構造化本文生成
   - score / facts / fan-view のバランスを壊しやすい
3. `src/rss_fetcher.py::generate_article_with_gemini` strict path
   - source block と strict prompt に強く依存
4. `src/rss_fetcher.py::generate_article_with_gemini` grounded path
   - offday / fallback 本文生成の主力
5. `src/rss_fetcher.py::_fact_check_article`
   - 数字・成績・日付・選手状態の補正
   - hallucination / stale 数値 / injury 周辺の safety と直結
6. `src/pre_publish_fact_check/llm_adapter_gemini.py::GeminiFlashAdapter.detect`
   - まだ parked だが、live 化するなら Lite 化より cache / cap / compression 優先

## existing governor hooks already present

- `src/rss_fetcher.py`
  - `LOW_COST_MODE`
  - `STRICT_FACT_MODE`
  - `GEMINI_STRICT_MAX_ATTEMPTS`
  - `GEMINI_GROUNDED_MAX_ATTEMPTS`
- `src/x_post_generator.py`
  - `LOW_COST_MODE`
  - `X_POST_AI_MODE`
  - `X_POST_AI_CATEGORIES`
  - `X_POST_GEMINI_ALLOW_CLI`
- `src/pre_publish_fact_check/llm_adapter_gemini.py`
  - `post_id + content_hash` cache
  - `max_calls`

現状の問題は「hook がない」ことより、「lane 横断の統一 cost ledger / skip policy / compression policy がない」こと。

## sub-ticket spec

### 229-A: LLM call audit + cost report

- goal:
  - 全 Gemini call に `model / prompt_token / output_token / estimated_cost / call_id / context` を残す
  - daily / hourly aggregate を 1 つの format で出す
- likely files:
  - `src/llm_cost_audit.py` new
  - `src/tools/draft_body_editor.py`
  - `src/rss_fetcher.py`
  - optional 2nd wave: `src/x_post_generator.py`, `src/pre_publish_fact_check/llm_adapter_gemini.py`
- implementation note:
  - first wave は mainline cost center である `draft_body_editor` + `rss_fetcher` 優先
  - token 数は API response usage が取れない path では rough estimate 可
- acceptance:
  - 1 call 1 row の structured log or ledger row が出る
  - `lane`, `post_id`, `content_hash/input_hash`, `model`, `estimated_cost_jpy` を最低限保持
  - daily 集計で「どの lane が何円使ったか」が見える
- risk:
  - 品質影響なし
  - 観測系のみ

### 229-B: content_hash dedupe + refused cooldown

- goal:
  - 同一 `post_id + content_hash` 再評価で LLM call を飛ばす
  - refused / no-change 記事は 24h cooldown
- likely files:
  - `src/repair_fallback_controller.py`
  - `src/tools/run_draft_body_editor_lane.py`
  - `src/repair_provider_ledger.py`
  - optional new helper: `src/llm_call_cache.py`
- implementation note:
  - 既存 `input_hash` / `idempotency_key` を再利用できる
  - pre-publish fact-check の `content_hash` cache 設計を draft repair 側へ横展開するのが最短
  - `refused` / `guard_fail` / `shadow_only no-change` を cooldown 対象にする
- acceptance:
  - 同一本文に対する連続実行で Gemini 実 call が発生しない
  - 本文変更後は cache miss で再評価される
  - 24h 経過後は再試行可能
- expected effect:
  - 最も即効性が高い
  - mainline で 30-50% の call 削減を期待
- risk:
  - 品質影響ほぼなし
  - stale cache 事故だけ注意

### 229-C: prompt input compression

- goal:
  - `title / summary / source / suspect_blocks` 中心に入力を圧縮
  - 全文 5000 字級を 1000 字前後へ落とす
- likely files:
  - `src/tools/draft_body_editor.py`
  - `src/rss_fetcher.py`
  - `src/pre_publish_fact_check/llm_adapter_gemini.py`
  - optional follow-up: `src/x_post_generator.py`
- implementation note:
  - compress 前後で guard pass / quality flags / publishable rate を比較する
  - postgame / lineup / recovery / notice で prompt contract を分ける必要がある
- acceptance:
  - prompt size が lane 別に明示的に減る
  - 既存 test fixture で quality regression がない
  - strict path の source grounding を壊さない
- expected effect:
  - token 50% 前後の削減余地
- risk:
  - C より品質リスクは小さいが、source omission / mismatch の副作用あり

### 229-D: Flash-Lite routing for low-risk classification

- goal:
  - B bucket のみ Lite へ落とす
  - Flash 維持対象と分離した model selector を作る
- likely files:
  - `src/llm_model_selector.py` new
  - `src/x_post_generator.py`
  - `src/weekly_summary.py`
  - optional manual-only path: `src/manual_post.py`
- implementation note:
  - first target は `x_post_generator` と `weekly_summary`
  - publish gate / source照合 / repair core には適用しない
- acceptance:
  - model routing が file-local if 文で散らばらない
  - Lite へ落とした path の fallback が維持される
  - canary / A-B compare が可能
- expected effect:
  - 対象 task の単価 80% 前後削減余地
- risk:
  - 本票の中で最も品質低下 risk がある
  - wording quality と CTA quality の軽微劣化は起こり得る

### 229-E: daily budget / cap + alert

- goal:
  - 日次 / 時間帯ごとの推定 cost を budget と比較し、上限で alert
  - 上限到達時は low-risk path だけ skip または deterministic fallback
- likely files:
  - `src/llm_cost_audit.py`
  - `src/rss_fetcher.py`
  - `src/x_post_generator.py`
  - `src/tools/draft_body_editor.py`
  - optional helper: `src/llm_budget_guard.py`
- implementation note:
  - skip 対象は B / A のみ
  - C lane は hard stop ではなく alert 優先、もしくは attempt limit を先に絞る
- acceptance:
  - `estimated_daily_cost_jpy` が budget を超えそうな時に structured alert を出す
  - B lane は deterministic fallback に落ちる
  - C lane は品質を落とさない保護動作になる
- expected effect:
  - 暴走防止
  - 直接の節約より上限管理の意味合いが強い
- risk:
  - A/B skip 条件の設計を誤ると user-facing output が減る

## recommended implementation order

1. `229-A`
   - まず計測し、lane 別の真のコスト配分を見る
2. `229-B`
   - 既存 `input_hash` と相性がよく、即効性が高い
3. `229-E`
   - budget overrun の再発防止
4. `229-C`
   - 圧縮は効くが、quality verify を伴う
5. `229-D`
   - Lite routing は最後。B 以外へ広げない

単独で 1 本だけ先に実装するなら `229-B` を推奨。`229-A` は並行で入れてよい。

## estimated savings

- `229-B`
  - same hash dedupe + refused cooldown で 30-50% call 減を見込む
  - 特に draft repair の再実行ループで効く可能性が高い
- `229-C`
  - prompt token 50% 前後削減余地
  - `rss_fetcher` grounded path と draft repair で寄与が大きい
- `229-D`
  - Lite 化した low-risk path は単価 80% 前後削減余地
- `229-E`
  - 直接節約より「日次 500 円上限を越えない」制御効果

## quality regression risk

- high:
  - `229-D` Lite routing
- medium:
  - `229-C` prompt compression
- low:
  - `229-A` audit only
  - `229-B` dedupe / cooldown
  - `229-E` budget / alert

## file candidates by sub-ticket

| ticket | first candidate files | note |
|---|---|---|
| 229-A | `src/llm_cost_audit.py`, `src/tools/draft_body_editor.py`, `src/rss_fetcher.py` | phase-1 は mainline cost center 優先 |
| 229-B | `src/repair_fallback_controller.py`, `src/tools/run_draft_body_editor_lane.py`, `src/repair_provider_ledger.py` | 既存 `input_hash` 再利用が本命 |
| 229-C | `src/tools/draft_body_editor.py`, `src/rss_fetcher.py`, `src/pre_publish_fact_check/llm_adapter_gemini.py` | test 影響が最も広い |
| 229-D | `src/llm_model_selector.py`, `src/x_post_generator.py`, `src/weekly_summary.py` | B bucket だけ対象 |
| 229-E | `src/llm_cost_audit.py`, `src/rss_fetcher.py`, `src/x_post_generator.py`, `src/tools/draft_body_editor.py` | alert と fallback policy を分離 |

## next flight

- first implementation ticket:
  - `229-B content_hash dedupe + refused cooldown`
- parallel acceptable:
  - `229-A LLM call audit + cost report`

## non-goals

- 全 Gemini path を Flash-Lite 化しない
- publish gate を緩めない
- source 照合を弱めない
- auto publish を止めない
- `guarded_publish_evaluator.py` や `publish_notice_email_sender.py` を「LLM 前提」に作り替えない
- `113 HALLUC-LANE-002` を本票で live 化しない
