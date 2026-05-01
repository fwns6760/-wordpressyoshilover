# 282-COST flag ON 判断 Pack draft

作成: 2026-05-01 JST  
mode: Lane A / doc-only / read-only 解析  
scope: `docs/handoff/codex_responses/2026-05-01_282_COST_pack_draft.md` 新規のみ。実装・deploy・env変更なし。

---

## 1. 結論

- 現時点の判断は **HOLD**
- 理由は `docs/ops/POLICY.md` §7 の順序固定により、**293-COST 完遂 + 24h 安定確認が 282-COST flag ON の前提**だから
- さらに `298-Phase3` は 2026-05-01 14:15 JST 時点で `ROLLED_BACK_AFTER_REGRESSION`、14:20 JST に第二波 risk OPEN が記録されており、`MAIL_BUDGET` 安定完了としては扱えない

---

## 2. 仕様整理

282-COST の目的は、`ENABLE_GEMINI_PREFLIGHT=1` を有効化して **Gemini 呼び出し前** に「そもそも Gemini を使う価値がある候補か」を gate し、無駄 call を削ること。

- 実装本体: `src/gemini_preflight_gate.py`
- deploy 状態: gate code は live、**flag OFF**
- 期待効果: `doc/active/282-COST-gemini-preflight-article-gate.md` では **Gemini call -10%〜-30%** を想定
- 対象 skip_reason は 8 種:
  - `existing_publish_same_source_url`
  - `placeholder_body`
  - `not_giants_related`
  - `live_update_target_disabled`
  - `farm_lineup_backlog_blocked`
  - `farm_result_age_exceeded`
  - `unofficial_source_only`
  - `expected_hard_stop_death_or_grave`

重要なのは、282 は **cache layer の前** に入ること。229-COST が content-hash dedupe なのに対して、282-COST は subtype / source / relevance / placeholder を使う **meta-level gate**。

---

## 3. read-only 解析

### 3.1 gate 本体

`src/gemini_preflight_gate.py` は以下を担う。

- `PREFLIGHT_ENV_FLAG = "ENABLE_GEMINI_PREFLIGHT"` を評価
- flag OFF なら `should_skip_gemini(...)` は即 `False, None`
- flag ON の時だけ 8 skip rule を順に評価
- skip 時は `emit_gemini_call_skipped(...)` で `gemini_call_skipped` event を logger に出す

現状の重要点:

- **可視化は logger のみ**
- local ledger / GCS ledger / publish-notice scanner / mail subject には未接続
- 293-COST はまさにこの silent 化 gap を埋める前提 ticket

### 3.2 candidate_meta 生成

`src/rss_fetcher.py:4445-4489` の `_build_gemini_preflight_candidate_meta(...)` が、preflight 判定に使う最小 metadata を作る。

- `title`
- `summary`
- `category`
- `article_subtype`
- `source_name`
- `source_url`
- `source_type`
- `published_at`
- `has_game`
- `duplicate_guard_context`
- `existing_publish_same_source_url`
- `is_giants_related`

ここで `summary` が `body_text` / `source_body` にも入るため、preflight は source 本文全文ではなく **タイトル + summary + source metadata** ベースで動く。

### 3.3 preflight call site と impact

#### A. `src/rss_fetcher.py:4594-4607`

`_gemini_text_with_cache(...)` 内の本 gate。

- `candidate_meta` がある時だけ preflight 判定
- skip なら:
  - `telemetry["cache_hit_reason"] = "preflight_skip"`
  - `telemetry["gemini_call_made"] = False`
  - `telemetry["skip_reason"] = <reason>`
  - `telemetry["skip_layer"] = "preflight"`
  - `emit_gemini_call_skipped(...)`
  - `return "", telemetry`

impact:

- **Gemini API call 0**
- **229-COST cache lookup も通らない**
- cache hit ratio の分母/分子に影響しうる

#### B. `src/rss_fetcher.py:4954-4970`

postgame strict slot-fill path。

- `_gemini_text_with_cache(...)` に `candidate_meta` を渡す
- preflight skip 時は `PreflightSkipResult(skip_reason)` を返す

impact:

- strict slot-fill は実行されない
- 呼び出し側 `build_news_block(...)` では `PreflightSkipResult` を受けると `return "", ""` に落ちる(`src/rss_fetcher.py:9459-9460`)
- ただし `tests/test_gemini_preflight_gate.py:348-378` は **safe fallback で本文ブロック自体は残る**ことを固定している

#### C. `src/rss_fetcher.py:5100-5116`

postgame parts path。

- 同様に `_gemini_text_with_cache(...)` に `candidate_meta` を渡す
- preflight skip 時は `PreflightSkipResult(skip_reason)` を返す

impact:

- postgame parts render は走らない
- 呼び出し側では strict path と同じく Gemini body を返さず fallback 側へ回る

#### D. `src/rss_fetcher.py:8753-8791`

strict fact mode の main path。

- `build_news_block(...)` の strict fact 生成で `candidate_meta` を付けて `_gemini_text_with_cache(...)` を呼ぶ
- ここでは skip layer を明示処理せず、そのまま `cached_text` を返す

impact:

- preflight skip 時は **空文字** が返る
- 実 Gemini request は実行されない
- `tests/test_gemini_preflight_gate.py:348-378` により、preflight skip でも `blocks != ""` / `ai_body != ""` の safe fallback 契約は維持される

### 3.4 実質的な影響まとめ

282 flag ON は、単に Gemini call 数を減らすだけではない。

- Gemini request 前で止まるので **cache lookup 前** に候補が消える
- strict/postgame parts は `PreflightSkipResult` になる
- strict fact mode では空文字 return 経由で fallback に入る
- 293 が無いと、この skip は **mail 上 user-visible にならない**

---

## 4. 前提条件(POLICY §7)

`docs/ops/POLICY.md:165-168` と `docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md:758-816` に従うと、282-COST flag ON の前提は以下。

### 4.1 順序固定

1. `293-COST` impl + test + deploy 完了
2. `293-COST` 24h 安定確認
3. その後に `282-COST` flag ON Pack 提示
4. user GO 後に `ENABLE_GEMINI_PREFLIGHT=1`

逆順は禁止。

### 4.2 Pack 着手前の前提条件判定

| 条件 | 現状判定 | 根拠 |
|---|---|---|
| 293 impl + test + deploy 完了 | **NO** | `docs/ops/OPS_BOARD.yaml` の `293-COST-deploy` は `FUTURE_USER_GO`、evidence は `(impl 未)` |
| 293 24h 安定確認(silent skip 0 / Gemini delta 0 / Team Shiny 維持 / MAIL_BUDGET 内) | **NO** | 293 自体が未実装なので 24h 観察も未成立 |
| 298-Phase3 ROLLED_BACK 後の安定(MAIL_BUDGET 30/h 内継続) | **NO** | 2026-05-01 14:15 JST で rolling 1h 5-6 通まで戻ったが、14:20 JST に第二波 risk OPEN が記録済み |
| 282-COST-flag-on は HOLD_NEEDS_PACK のまま | **YES** | `docs/ops/OPS_BOARD.yaml` で `282-COST-flag-on` は `HOLD_NEEDS_PACK` |

### 4.3 Lane A 解析の 8 項目着手前条件

`docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md:770-781` の 8 項目を、そのまま 282 Pack 前提として使う。

| # | 条件 | 現状 |
|---|---|---|
| 1 | 293 impl + test + deploy 完了 | **NO** |
| 2 | 293 24h 安定確認 pass | **NO** |
| 3 | silent skip 0 維持(`【要review｜preflight_skip】` 導線稼働) | **NO** |
| 4 | Gemini call 24h baseline 計測済(282 ON 後 delta 比較用) | **NO** |
| 5 | Team Shiny From / 289 通知 / 通常 publish notice path 全部稼働 | **YES** |
| 6 | MAIL_BUDGET 30/h・100/d 内 | **PARTIAL** |
| 7 | 282 ON 時の cost 削減見積 evidence あり | **YES** |
| 8 | 282 ON 時の rollback コマンド 1 行確認 | **YES** |

判定:

- **全部 YES ではない**
- よって 282-COST flag ON Pack は **まだ user に上げない**

---

## 5. Acceptance Pack 18 項目 final draft

```markdown
## Acceptance Pack: 282-COST-flag-on

- **Decision**: HOLD
- **Requested user decision**: `ENABLE_GEMINI_PREFLIGHT=1` を fetcher に適用して preflight gate を有効化するか
- **Scope**: `yoshilover-fetcher` の env に `ENABLE_GEMINI_PREFLIGHT=1` を追加し、282-COST preflight gate を live 有効化する
- **Not in scope**: 293-COST 実装 / publish-notice scanner 改修 / source 追加 / Scheduler 変更 / SEO / X / Team Shiny From / `ENABLE_LIVE_UPDATE_ARTICLES` / code diff / image rebuild判断以外の実装
- **Why now**: 282 gate 自体は live で flag OFF のまま眠っており、293 完遂後に user GO を取るための判断 pack を先に固定しておく価値があるため
- **Preconditions**:
  - 293-COST impl + test + deploy 完了
  - 293-COST 24h 安定確認(silent skip 0 / Gemini call delta 0 / Team Shiny 維持 / MAIL_BUDGET 内)
  - 298-Phase3 ROLLED_BACK 後の安定継続
  - Lane A 8 項目着手前条件が全部 YES
  - 2026-05-01 現在はいずれも未達なので実行不可
- **Cost impact**:
  - Gemini call: **-10%〜-30% 想定**
  - token: 1 call あたり不変、総 token は call 減に連動して減少方向
  - Cloud Run / build: flag ON 自体は env 変更のみ、ただし 293 導線を先に live 化しておく必要がある
  - mail: 293 visible path を前提に `preflight_skip` 通知が **+N/d**
- **User-visible impact**:
  - Gemini 生成に進まない候補が増える
  - その分 `【要review｜preflight_skip】...` など 293 導線で skip が見える
  - visible 化なしで ON にすると「候補が減った」に見えるため 293 前提は必須
- **Rollback**:
  - 第一手: `gcloud run services update yoshilover-fetcher --remove-env-vars=ENABLE_GEMINI_PREFLIGHT`
  - 293 path も同時 rollback が必要な場合は handoff 順序に従い `ENABLE_PREFLIGHT_SKIP_NOTIFICATION` 側も OFF
  - 282 already ON の rollback 順は `Phase A0(fetcher OFF) → Phase A(notification OFF)` を守る
- **Evidence**:
  - 282 gate code は live、flag OFF (`docs/ops/OPS_BOARD.yaml`)
  - preflight call site は `src/rss_fetcher.py:4594-4607 / 4954-4970 / 5100-5116 / 8753-8791`
  - 293 v2 doc で順序固定・rollback・8 項目条件が明文化済み
  - ただし 293 impl/test/deploy evidence は未成立
- **Stop condition**:
  - Gemini call が増える(逆方向 anomaly)
  - silent skip が増える
  - candidate disappearance が増える
  - MAIL_BUDGET 30/h または 100/d を超える
  - Team Shiny From / 289 通知 / 通常 publish notice path にデグレが出る
- **Expiry**: `293 完遂 + 24h` を満たすまでは保留。満たした日から 2026-05-15 までを再判断 window とする
- **Recommended decision**: HOLD
- **Recommended reason**: POLICY §7 の順序未達。293 impl evidence 0、298 second-wave risk OPEN、candidate disappearance / cache impact も未測定
- **Gemini call increase**: NO
- **Token increase**: NO
- **Candidate disappearance risk**: UNKNOWN(要評価。preflight skip により publish 機会が消える可能性があるため、293 visible 化後に件数計測が必要)
- **Cache impact**: UNKNOWN(要評価。preflight が cache lookup 前で止まるため cache_hit ratio の分母/分子に影響しうる)
- **Mail volume impact**: YES(293 path で `preflight_skip` 可視化が増える。設計上は 24h dedup + shared cap + MAIL_BUDGET 30/h・100/d 内が前提)

User reply format: 「GO」/「HOLD」/「REJECT」のみ
```

補足:

- `Candidate disappearance risk` と `Cache impact` は **UNKNOWN(要評価)** とした
- `docs/ops/POLICY.md` §18 により、この UNKNOWN が残る限り推奨判断は **最低 HOLD**

---

## 6. rollback plan

282-COST flag ON の rollback は、最短では fetcher env 1 コマンド。

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_GEMINI_PREFLIGHT
```

ただし 293 path が同時に live の場合、handoff は 293 v2 の順を使う。

1. **Phase A0**: fetcher 側 preflight gate を OFF  
   `--remove-env-vars=ENABLE_GEMINI_PREFLIGHT`
2. **Phase A**: publish-notice 側 visible 化を OFF  
   `--remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION`
3. 必要時のみ image / state cleanup

理由:

- 282 already ON のまま 293 visible path だけ止めると、preflight skip が再び silent 化する
- そのため rollback は **282 → 293 の順** ではなく、**fetcher OFF → notification OFF** の順が必要

---

## 7. stop condition 詳細

282 flag ON 後に即停止すべき条件を明示しておく。

- **Gemini call increase**: 削減施策なのに 24h call 数が増える
- **silent skip increase**: `gemini_call_skipped` は出るが mail / ledger で見えない
- **candidate disappearance increase**: preflight skip 増に対して publish / review / hold の visible 件数が落ちる
- **MAIL_BUDGET violation**: 30 通/h または 100 通/d 超過
- **normal path regression**: `post_gen_validate` / 通常 publish notice / Team Shiny From に変化
- **cache anomaly**: cache_hit ratio が急変して 229-COST 側の効果分離ができなくなる

---

## 8. Claude 向け next action

- `282-COST-flag-on` は `docs/ops/OPS_BOARD.yaml` 上 **HOLD_NEEDS_PACK** 維持でよい
- user に上げる timing は **293 完遂 + 24h + 298 second-wave risk 解消後**
- その時点で本 doc を元に Pack を最終化し、UNKNOWN 2 項目を実測で YES/NO に寄せる

