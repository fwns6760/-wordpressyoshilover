# 2026-05-02 改修 #2 / #3 default 値解析

mode: read-only / doc-only / production 不触  
target: 改修 #2 `91ddfdf` / 改修 #3 `76f748b`

## 結論サマリ

| change | compile-time default | blind enable safety | recommendation | 要点 |
|---|---:|---|---|---|
| #2 cache miss breaker | threshold `0.5`, window `3600s` | `RISKY` | `NEED_TUNING` | `miss_rate > 0.5` に最小母数条件がなく、quiet window の最初の cold miss `1/1` でも trip する |
| #3 per-post 24h budget | limit `5` | `INERT` | `HOLD` | `post_id` 解決が前提だが、現行 `rss_fetcher` main path の `candidate_meta` に `post_id` が入っておらず `applicable=false` になりやすい |

---

## 1. 改修 #2 default values

### 1.1 compile-time default

`91ddfdf` 導入の現行実装では、default は以下です。

- `DEFAULT_GEMINI_CACHE_MISS_BREAKER_THRESHOLD = 0.5`
- `DEFAULT_GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS = 3600`

根拠:

- `src/llm_call_dedupe.py:21-28`
- `src/llm_call_dedupe.py:152-168`

### 1.2 値の意味

breaker 判定は `evaluate_gemini_cache_miss_breaker()` で行われます。

- 集計窓: 直近 `window_seconds` 秒
- 集計対象: `llm_call_dedupe` ledger 上の `hit` / `miss`
- 判定式: `tripped = enabled and total_count > 0 and miss_rate > threshold`

根拠:

- `src/llm_call_dedupe.py:343-370`

したがって default の意味は:

- 直近 `3600` 秒で
- `miss_count / (miss_count + hit_count) > 0.5`
- なら `cache_miss_circuit_breaker` で Gemini call を止める

重要なのは、**最小母数条件が無い**ことです。  
`1 miss / 1 total = 1.0` なので、quiet な 1 時間の最初の cold miss 1 件でも trip します。

### 1.3 postgame surge 時の cache miss 想定発生率

実装面:

- cache miss は cache lookup 後に `record_gemini_cache_outcome(... miss ...)` を書いた直後に breaker 判定される
- breaker は **Gemini 実 call 前** に走る

根拠:

- `src/rss_fetcher.py:4708-4715`
- `src/rss_fetcher.py:4779-4791`

観測面:

- `logs/llm_call_dedupe_ledger.jsonl` の `2026-05-02 12:18-12:21 JST` に、postgame 系 34 row を確認
- 内訳:
  - `postgame_article_parts_v1`: `1 miss + 12 hit`
  - `postgame_strict_slotfill_v1`: `1 miss + 20 hit`
  - 合計: `2 miss / 34 total = 5.88%`
- 同一 `source_url_hash=292fe03766cd9637` に対し、各 template の最初の cold lookup だけ miss、その後は hit 優勢

このことから、**同一 postgame 素材を繰り返し処理する steady/replay 局面**では miss 率は低いです。

ただし、時系列順で見ると最初の row は以下でした。

- `2026-05-02T12:18:14.394950+09:00 miss postgame_article_parts_v1`

この 1 件目時点の累積は `1 miss / 1 total = 100%` です。  
default breaker をその場で ON にしていた場合、式上は **その最初の miss で即 trip** します。

つまり observed steady-state `5.88%` は、

- flag OFF だったので最初の miss 後も実 call が継続し
- cache save 後の hit が後から積み上がった

結果です。  
**default ON の世界では、その後の hit が育つ前に brake が掛かる**ため、同じ miss/hit 曲線にはなりません。

### 1.4 default で blind enable した場合の予想動作

判定: **`RISKY`**

理由:

1. default `0.5 / 3600s` は cold start に弱い  
   最初の miss `1/1` で trip し得る
2. breaker は cache miss を「異常」だけでなく「初回正当 miss」も同じ 1 miss として扱う  
   `src/llm_call_dedupe.py:357-369`
3. breaker は Gemini 実 call 前に発火するため、cache warm-up 前に review/hold へ倒し得る  
   `src/rss_fetcher.py:4779-4836`

結果として、postgame surge が

- 同一記事の再処理中心なら inert に近く見える
- **新規 source_url / 新規 content_hash が連続する本来の surge** では過剰 fire

になりやすいです。

### 1.5 safe enable recommendation

判定: **`NEED_TUNING`**  
運用上の実行判断は **実質 `HOLD` 相当**

理由:

- env knob が `threshold` / `window` しかない
- しかし今回の主問題は **threshold より前の「最小母数 0」** にある
- `threshold < 1.0` なら `1/1` で trip し得る
- `threshold = 1.0` にすると `miss_rate > 1.0` は成立せず、breaker は実質無効

よって **env だけで安全域を作るのは難しい**です。

推奨:

- 現状 default のまま ON は避ける
- safe enable 前に最低でも「min sample floor」か「min miss count」を code 側に追加する
- threshold/window だけで無理に運用するなら、実質は OFF 維持しかない

---

## 2. 改修 #3 default values

### 2.1 compile-time default

`76f748b` 導入の現行実装では、default は以下です。

- `DEFAULT_PER_POST_24H_GEMINI_BUDGET_LIMIT = 5`

根拠:

- `src/llm_call_dedupe.py:24-29`
- `src/llm_call_dedupe.py:171-181`

### 2.2 値の意味

budget 判定は `evaluate_per_post_24h_gemini_budget()` で行われます。

- 窓: 固定 `24h`
- 対象単位: `post_id`
- count source:
  - 優先: `gemini_call_attempt` explicit row
  - fallback: `gemini_cache_outcome == miss`
- 判定式: `enabled and applicable and remaining_calls <= 0`

根拠:

- `src/llm_call_dedupe.py:410-463`

したがって default の意味は:

- 同一 `post_id` に対して
- 直近 24h の Gemini call count が `5` に達したら
- 6 発目以降を `per_post_24h_gemini_budget_exhausted` で止める

### 2.3 現行配線での実効性

ここが最重要です。

budget は `candidate_meta` から `post_id` を解決できた時だけ applicable になります。

- `src/rss_fetcher.py:4469-4478`  
  `_resolve_cache_metric_post_id()` は `post_id` / `wp_post_id` / `id` しか見ない
- `src/rss_fetcher.py:4481-4525`  
  `_build_gemini_preflight_candidate_meta()` の戻り値にはその 3 key が無い
- `src/rss_fetcher.py:4688`  
  `budget_post_id = _resolve_cache_metric_post_id(candidate_meta)`
- `src/rss_fetcher.py:4838-4843`  
  `budget_state = evaluate_per_post_24h_gemini_budget(budget_post_id, ...)`
- `src/rss_fetcher.py:4360-4369`  
  explicit attempt row も `budget_post_id is not None` の時だけ記録

さらに、`rss_fetcher` 内の `_gemini_text_with_cache()` 呼び出し 3 箇所はすべてこの builder を使っています。

- postgame strict slot-fill: `src/rss_fetcher.py:5199-5210`
- postgame article parts: `src/rss_fetcher.py:5336-5356`
- strict fact main path: `src/rss_fetcher.py:9125-9149`

実際に builder をそのまま評価すると `resolved_post_id = None` です。  
つまり現行 fetcher main path では **flag を ON にしても `applicable=false` で予算判定に入らない**可能性が高いです。

### 2.4 通常 post の Gemini call 数推定

budget が狙っているのは `_request_gemini_strict_text()` 経由の Gemini 2.5 Flash call です。

根拠:

- explicit attempt row 記録は `src/rss_fetcher.py:4358-4370` のみ
- strict retry 上限 default は `GEMINI_STRICT_MAX_ATTEMPTS = 3`  
  `src/rss_fetcher.py:1160-1169`

通常 post の推定:

1. strict fact main path
   - 成功時は通常 `1 call`
   - retry worst-case は `3 call`
2. postgame strict slot-fill または postgame article parts
   - 成功時は通常 `1 call`
   - retry worst-case は `3 call`
3. `_fact_check_article()` の Gemini 2.0 Flash numeric check
   - 別 call site
   - **今回の per-post budget には入っていない**
   - 根拠: `src/rss_fetcher.py:8924-9008`

したがって、「budget が本当に `post_id` へ効く」前提での normal estimate は:

- budget 対象 subset: **平均ほぼ 1 call / post、悪くて 3 call / post**
- total Gemini call で見ると、数値補正が乗る記事は **+1 call** の可能性があるが、これは #3 の count 外

この前提なら `LIMIT=5` 自体は**tight すぎる値ではない**です。  
通常成功 1 回、たまに retry が入る程度なら legitimate call を切りにくい値です。

### 2.5 default で blind enable した場合の予想動作

判定: **`INERT`**

理由:

1. 現行 fetcher main path の `candidate_meta` に `post_id` が無い
2. `applicable=false` だと trip しない  
   `src/llm_call_dedupe.py:447-462`
3. explicit `gemini_call_attempt` row も `budget_post_id is not None` でないと書かれない  
   `src/rss_fetcher.py:4360-4369`

つまり blind enable しても、

- safety 面では block しすぎない
- しかし cost guard としてもほぼ効かない

可能性が高いです。

### 2.6 safe enable recommendation

判定: **`HOLD`**

理由:

- `LIMIT=5` という数字自体は概ね妥当
- ただし現行 fetcher 配線では budget が main path に乗っていない
- inert な flag ON は cost 抑制効果を持たず、観測だけを汚す

推奨:

- まず `candidate_meta` に stable な `post_id` / `wp_post_id` を載せる wiring が必要
- その後の初期値は **`LIMIT=5` 維持**でよい
  - normal 1 call / post
  - retry 含みでも worst-case 3
  - 5 なら legitimate call を切りにくい

---

## 3. Safe Enable Recommendation

| change | recommendation | 理由 |
|---|---|---|
| #2 | `NEED_TUNING` | default `0.5 / 3600s` は first cold miss `1/1` でも trip。threshold/window だけでは safe tuning が難しい |
| #3 | `HOLD` | default `LIMIT=5` は妥当だが、現行 fetcher main path では `post_id` 不在で inert。まず wiring 修正が先 |

補足:

- #2 は「値が緩すぎて inert」ではなく、**式が tight すぎて over-block 側**
- #3 は「値が tight」ではなく、**配線不足で inert 側**

---

## 4. 282-COST との chain order interaction

### 4.1 実行順

`_gemini_text_with_cache()` の順序は以下です。

1. `282-COST preflight`
2. cache lookup
3. #2 cache miss breaker
4. #3 per-post 24h budget
5. actual Gemini request

根拠:

- preflight: `src/rss_fetcher.py:4689-4707`
- cache miss breaker: `src/rss_fetcher.py:4779-4836`
- per-post budget: `src/rss_fetcher.py:4838-4898`

### 4.2 #2/#3 を 282 前に ON した場合の attribution risk

#### #2 の risk

高いです。

- 282 は preflight で Gemini 前に止める cost guard
- #2 は cache miss 後に止める cost guard
- 両方 ON だと Gemini 減少分が
  - preflight による削減か
  - cache miss breaker による削減か
  を分離しにくい
- 特に #2 は cache warm-up 前の cold miss で止まり得るため、`282` の効果測定前に call volume / cache mix / review volume を変えてしまう

#### #3 の risk

現行 source では低めですが、ゼロではありません。

- いまの fetcher main path では inert 寄り
- ただし `post_id` wiring が入った瞬間に same-post retry を削るため、282 の Gemini delta と混ざる
- 単一 change で比較したいなら 282 観測期間は OFF 維持が妥当

### 4.3 282 effect 計測時の懸念

282 の本質は **preflight stage での call 削減** です。  
この測定中に #2/#3 も ON だと、delta 解釈が混ざります。

- #2 ON:
  - cold miss surge を breaker が吸う
  - 282 前後の cache miss ratio / Gemini delta が濁る
- #3 ON:
  - same-post retry を別の理由で削る
  - 282 由来の削減と見分けにくい

したがって、**282-COST の効果計測 window では #2 / #3 は OFF のまま固定**が安全です。

---

## 5. 最終判断

- 改修 #2:
  - default threshold/window のまま blind enable は非推奨
  - 実質判断は `HOLD`
  - formal label は `NEED_TUNING`
- 改修 #3:
  - default limit `5` は数字としては妥当
  - ただし現行 fetcher 配線では inert
  - よって判断は `HOLD`

