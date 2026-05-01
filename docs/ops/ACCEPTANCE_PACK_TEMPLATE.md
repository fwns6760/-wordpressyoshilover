# Acceptance Pack Template(永続正本)

user GO が必要な案件は **必ず本 template の 13 項目** で提示する。
詳細 policy は `docs/ops/POLICY.md` section 9 参照。

---

## Template(13 項目、全部必須)

```markdown
## Acceptance Pack: <ticket_id>

- **Decision**: GO / HOLD / REJECT(本 Pack の総評)
- **Requested user decision**: <user に求める判断 1 行、何を ON/OFF / deploy / accept するか>
- **Scope**: <変更範囲、touch する file / service / env / scheduler を明示>
- **Not in scope**: <意図的に触らないもの、混入禁止 list>
- **Why now**: <なぜこの timing で判断するか、urgent / 効果 timing>
- **Preconditions**: <着手前提条件(289 24h 安定 / 293 完遂 / 5 条件達成 等、全部達成確認済か)>
- **Cost impact**: <Gemini call ±N% / Cloud Run / mail emit / 課金影響、定量>
- **User-visible impact**: <user 体感変化(publish 数 / mail subject / 件数 等)>
- **Rollback**: <1 コマンド or revert 手順、env flag remove で済むか image 戻しか>
- **Evidence**: <事前 evidence(test pass / commit hash / GH green) + 完了 evidence の予定>
- **Stop condition**: <着手後即停止すべき条件(silent skip 出現 / errors > 0 / publish 急減 等)>
- **Expiry**: <本 Pack の有効期限(judgment 決まる timing)>
- **Recommended decision**: GO / HOLD / REJECT
- **Recommended reason**: <1-2 行、なぜこの推奨か>

---

User reply format: 「GO」/「HOLD」/「REJECT」のみ
```

---

## 推奨判断の決め方(永続)

| 状況 | 推奨判断 |
|---|---|
| 全 13 項目埋まる + Cost impact ≤ 想定 + Rollback 1 コマンド可能 | **GO 推奨** |
| Preconditions 未達 / Cost impact 不明 / Rollback 不能 | **HOLD 推奨** |
| Scope に IRREVERSIBLE 含む or 公開影響大 | **REJECT 推奨**(scope 縮小して再 Pack) |

---

## 禁止 pattern(本 template 違反、`POLICY.md` section 9 違反)

- Acceptance Pack なしの「進めてよいですか?」「確認お願い」(全面禁止)
- 候補 2-3 並列で user に選ばせる(推奨 1 つに圧縮)
- Cost impact / Stop condition / Expiry / Rollback 省略
- Evidence なしで GO 提示
- 不安なら user に聞くのではなく **Acceptance Pack を作る**

---

## 作成例(参考、近期想定 Pack)

### 例 A: 290-QA deploy + flag ON(production_health 17:00 結果 OK 後)

```markdown
## Acceptance Pack: 290-QA-deploy

- Decision: GO
- Requested user decision: 290-QA deploy(fetcher rebuild) + ENABLE_WEAK_TITLE_RESCUE=1 を実施するか
- Scope: yoshilover-fetcher service image rebuild → :c14e269 / env ENABLE_WEAK_TITLE_RESCUE=1
- Not in scope: publish-notice / guarded-publish / Scheduler / Team Shiny From / SEO / X 自動投稿
- Why now: 289 silent skip 解消後、A/B 7 候補(泉口/山崎+西舘/阿部/平山関連 3/竹丸+内海)を publish に戻すため。LLM 不要 regex 救済
- Preconditions: production_health_observe 17:00 結果 OK / GH Actions green / pytest baseline 維持
- Cost impact: Gemini call 0 増(regex/metadata only)、Cloud Build 1 回、mail emit 微増可能性
- User-visible impact: A/B 7 候補が publish に戻る、または review_reason 明示で見える化
- Rollback: gcloud run services update --remove-env-vars=ENABLE_WEAK_TITLE_RESCUE(env 戻し 1 コマンド) / image revert :4be818d
- Evidence: 事前 = pytest 1865/7 維持 + GH success / 完了 = 救済 candidate ledger + Gemini call 不変
- Stop condition: silent skip 出現 / Gemini call +20% 超 / publish 急減 / Team Shiny From 変化
- Expiry: 2026-05-02
- Recommended decision: GO
- Recommended reason: 設計済 / Pack 13 項目埋まる / Rollback 1 コマンド / Cost impact 0

User reply format: 「GO」/「HOLD」/「REJECT」のみ
```

---

## 関連

- `docs/ops/POLICY.md`(section 9 で本 template の必須 13 項目永続化)
- `docs/ops/CURRENT_STATE.md`(READY / HOLD_NEEDS_PACK / FUTURE_USER_GO で Pack 作成 timing 管理)
- `docs/ops/OPS_BOARD.yaml`(各 ticket の `user_go_required` / `user_go_reason` 機械可読)
