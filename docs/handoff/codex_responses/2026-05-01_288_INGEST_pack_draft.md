# 288-INGEST source add judgment Pack draft

Date: 2026-05-01 JST  
Lane: Codex B (doc-only)  
Scope: pack draft only. No `src/` / `tests/` / `scripts/` / `config/` mutation, no deploy, no env, no gcloud, no WP, no scheduler action.

## 1. Policy alignment and current state

- 現行 repo 正本(`2026-05-01`)では、**「候補消失しない契約が先」**の順序固定は `docs/ops/POLICY.md` **§7**、`§22` は **MAIL_BUDGET**。本 draft は現行 policy 文面に合わせて整理する。
- `docs/ops/OPS_BOARD.yaml` では `288-INGEST-source-add` は **`HOLD_NEEDS_PACK`**。evidence は `5 条件未達(289+290+295+候補終端契約+cost 抑制策)`。
- 現行 source 構成は **13 sources**:
  - **9** `social_news` via rsshub(X feed)
  - **4** web RSS
- 288 の将来 scope は **`config/rss_sources.json` に 1-3 個の新 RSS endpoint を追加**すること:
  - NNN web
  - スポニチ web
  - サンスポ web
- この ticket は **source coverage 拡張の judgment pack** であり、実装・deploy は含まない。
- 将来の実施単位は「config 追加 + fetcher deploy + 24h 観察」。もし config 追加だけで済まず `src/` / `tests/` 変更が要るなら、**scope 拡大として再 Pack** が必要。

## 2. 仕様整理

### 2.1 288 の定義

- 288 は **`config/rss_sources.json` に新 RSS endpoint を追加する判断**。
- 主目的は既存 coverage gap の補完であり、`title rescue` / `subtype fix` / `terminal outcome contract` / `preflight visible化` の代替ではない。
- source 追加は **publish 候補数を増やす可能性**がある一方で、同時に **Gemini call / token / Cloud Run / mail review volume を増やす方向**に働く。

### 2.2 現時点の候補 source

| candidate | current state | note |
|---|---|---|
| NNN web | 未登録 | 既存 13 source に含まれない |
| スポニチ web | 未登録 | 既存は `@SponichiYakyu` X feed のみ |
| サンスポ web | 未登録 | 既存は `@Sanspo_Giants` X feed のみ |

### 2.3 cost 増加の考え方

- 新 source 追加は **per-article の既存処理をそのまま増やす**性質の変更。
- したがって Gemini call 増加は概ね次式で見る:

```text
Gemini call delta(%) =
  ((new_source_candidates_24h x avg_gemini_calls_per_candidate)
   / current_gemini_calls_24h) x 100
```

- 厳密な `X%` は **source 追加後の 24h 実測が必要**。
- policy 上は `UNKNOWN cost impact = GO 禁止`(`docs/ops/POLICY.md` §7)なので、実測が無い間は **最低 HOLD**。

## 3. 5 conditions precondition gate

**判定ルール**:

- 5 条件 **全部 YES** で初めて user 提示可能
- **UNKNOWN が 1 つでも HOLD**
- 288 は `SOURCE_ADD + COST_INCREASE` の複合判断なので、cost と candidate disappearance の両方を満たす必要がある

| # | precondition | YES 定義 | current | note |
|---|---|---|---|---|
| 1 | **289 24h 安定** | `post_gen_validate` skip の silent 0 が 24h 維持 | **NO** | `289-OBSERVE` は `REVIEW_NEEDED`、24h 安定完了 evidence なし |
| 2 | **290 deploy + 24h 安定** | weak title rescue を live 化し、救済効果とデグレなしを 24h 確認 | **NO** | 290 は Pack draft 済だが `NOT_DEPLOYED` |
| 3 | **295 impl 完遂** | subtype 誤分類 fix が code/deploy/24h 観察まで完了 | **NO** | `295-QA` は `DESIGN_DRAFTED + HOLD` |
| 4 | **候補終端契約 確立** | 新旧 source の candidate が必ず visible terminal outcome に落ちる | **NO** | `291-OBSERVE` は設計段階、289/292/293 依存 |
| 5 | **cost 抑制策 確立** | `282-COST` 系の preflight/cost gate を通した後、24h Gemini call delta が **`< +20%`** | **UNKNOWN** | `293-COST` 未完、282 flag ON も未実施、実測不能 |

### 3.1 precondition summary

- 現状は **YES 0 / NO 4 / UNKNOWN 1**
- よって 288 は **HOLD 維持が正**
- user に今見せる状態ではなく、`HOLD_NEEDS_PACK` のまま Pack draft だけ先に固定する

## 4. 候補消失契約(最重要)

288 は **source を増やす前に「候補が消えない」契約が先**。この条件を満たせないなら source 追加は禁止。

### 4.1 terminal outcome contract

新 source 由来の prepared candidate は、既存 source と同じく必ず次の 5 terminal outcome のどれかに落ちること:

1. `publish`
2. `review_notified`
3. `hold_notified`
4. `skip_notified`
5. `error_notified`

**Cloud Logging のみは不可**。mail or digest で user-visible であることが条件。

### 4.2 source 追加時の禁止事項

- 新 source を入れた結果、**既存 source の visible candidate 数が減る**状態
- `source_url_hash` / title hash collision により、**source-distinct candidate が silent に消える**状態
- dedup で落としたのに `skip_notified` / `history_duplicate` 等の visible 終端が残らない状態

### 4.3 dedup contract

- **`source_url_hash`**:
  - exact duplicate URL の統合にのみ使う
  - duplicate と判断した場合も、先行 candidate に visible terminal outcome があること
- **title hash**:
  - headline が同一でも、URL が別なら **即 silent drop しない**
  - merge するなら merge evidence を残す
  - merge しないなら `review_notified` または `skip_notified(history_duplicate 等)` に落とす

### 4.4 WP 側の期待値

- 288 の user-visible 期待値は **publish 機会が増えるか、少なくとも review/hold/skip として可視化されること**
- source 追加の効果は「候補が増える方向」だけが許容で、**既存候補が見えなくなる方向は不可**

## 5. Acceptance Pack 18 項目 final draft

## Acceptance Pack: 288-INGEST-source-add

- **Decision**: `HOLD`
- **Requested user decision**: 5 条件達成後に、`config/rss_sources.json` へ NNN web / スポニチ web / サンスポ web の RSS endpoint を最大 3 件追加し、`yoshilover-fetcher` に deploy してよいか
- **Scope**: `config/rss_sources.json` への source endpoint 追加 1 file、`yoshilover-fetcher` rebuild/deploy 1 回、deploy 後 24h observe
- **Not in scope**: `src/` / `tests/` / `scripts/` の logic change、289/290/291/293/295 本体実装、Scheduler、Secret、Team Shiny From、SEO、X、自動 publish policy 緩和、WP 直接 mutation、mail routing major redesign
- **Why now**: 288 は既に `HOLD_NEEDS_PACK` にあり、coverage gap 自体は認識済み。一方で順序を誤ると source 追加が silent candidate disappearance を拡大するため、**実装前に Pack の判定軸だけを固定**しておく必要がある
- **Preconditions**:
  - 289 が 24h 安定(`silent skip 0`)
  - 290 が deploy 済みで 24h 安定(weak title rescue 効果確認)
  - 295 が impl/deploy/24h 観察まで完了(subtype 誤分類 fix)
  - 291 系の candidate terminal contract が成立し、新 source 由来候補も必ず visible terminal outcome に落ちる
  - 282/293 系の cost 抑制策が先に成立し、source 追加後 24h の Gemini call delta が **`< +20%`**
  - **上記のうち 1 つでも NO/UNKNOWN なら実行不可**
- **Cost impact**:
  - Gemini call: **増加方向**
  - 定量式: `X% = ((new_source_candidates_24h x avg_gemini_calls_per_candidate) / current_gemini_calls_24h) x 100`
  - 実行許容条件: 24h 実測で `X < +20%`
  - token: call 増加に比例して増加方向
  - Cloud Run / Logging: source fetch / article prepare / log emit の分だけ微増
  - mail emit: review / hold / skip 通知も増えうるため、`MAIL_BUDGET 30/h・100/d` 内設計が必須
- **User-visible impact**:
  - publish 候補数が増える可能性
  - 同時に review / hold / skip 通知件数も増える可能性
  - user 体感としては「候補が増える」か「候補が見える」方向だけが許容。候補消失は不可
- **Rollback**:
  - repo: `config/rss_sources.json` 追加 commit を `git revert`
  - runtime: 問題発生時は pre-288 image へ fetcher image rollback
  - observe: 288 適用 window の ledger / mail sample を archive して before/after を切り分ける
- **Evidence**:
  - 現行 source は 13 件(9 X feed via rsshub + 4 web RSS)を read-only 確認済み
  - `docs/ops/OPS_BOARD.yaml` で 288 は `HOLD_NEEDS_PACK`
  - `doc/active/288-INGEST-source-coverage-expansion.md` は 5 条件管理を明文化済み
  - `doc/active/291-OBSERVE-candidate-terminal-outcome-contract.md` は terminal outcome 5 種を明文化済み
  - 現時点では precondition が揃っていないため evidence は **HOLD 維持の根拠**に限る
- **Stop condition**:
  - 24h Gemini call delta **`> +30%`**
  - candidate disappearance 検出(新旧 source いずれでも visible outcome なし)
  - silent skip 増加
  - Team Shiny From 変化
  - `MAIL_BUDGET` 違反(`>30/h` or `>100/d`)
  - cache hit ratio が baseline から `15pt` 超悪化
- **Expiry**: 5 条件のいずれかの status が変わった時点、または user 提示直前の whichever comes first。precondition 未達のまま固定利用しない
- **Recommended decision**: `HOLD`
- **Recommended reason**: 288 は `SOURCE_ADD + COST_INCREASE` の二重判断で、現状は `289/290/295/291/282-293` の前提が未成立。source を先に増やすと「coverage 増」ではなく「silent candidate disappearance 増」を招く可能性がある
- **Gemini call increase**: `YES`
- **Token increase**: `YES`
- **Candidate disappearance risk**: `NO`(この条件を evidence で満たせない限り GO を出さない。候補消失は契約違反として停止)
- **Cache impact**: `UNKNOWN`(新 source の cache_hit ratio / duplicate rate / title collision rate を 24h 実測するまで確定不可)
- **Mail volume impact**: `YES`(publish/review/hold/skip の visible 件数増加方向。`MAIL_BUDGET 30/h・100/d` 内設計必須)

User reply format: `GO` / `HOLD` / `REJECT`

## 6. rollback quick reference

### 6.1 repo rollback

```bash
git revert <288-source-add-commit>
```

### 6.2 runtime rollback

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --image=<pre-288-image>
```

### 6.3 ledger handling

- 288 適用後に rollback した場合でも、適用 window の ledger / mail sample は archive して残す
- 理由は「source 追加が cost 増だったのか」「candidate disappearance を起こしたのか」を切り分けるため

## 7. Claude next action

1. `288-INGEST-source-add` の `HOLD_NEEDS_PACK` entry に本 Pack path を紐付ける review を行う。
2. 289 / 290 / 295 / 291 / 282-293 の status 変化時に本 Pack の precondition table を更新する。
3. **5 条件が全部 YES になった時だけ** user 提示用に昇格し、`GO/HOLD/REJECT` の 1 画面圧縮を準備する。
