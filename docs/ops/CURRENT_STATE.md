# YOSHILOVER 現在地正本(CURRENT_STATE)

本 doc は **次回セッション開始時に最初に読む** 正本。
6 カテゴリ board(ACTIVE / OBSERVE / READY / HOLD_NEEDS_PACK / FUTURE_USER_GO / DONE)で表示。

最終更新: **2026-05-01 09:50 JST**(P1 mail storm hotfix env removal + Codex A/B 並行 fire 後)
更新責任: Claude(本 file は session 単位で更新、自律 GO 範囲)

---

## P0 / Safety 状態

**P1 mail storm 進行中**(2026-05-01 09:00 JST 開始、止血 hotfix 1 段目実施 + 効かず継続中):

- 5/1 09:00 JST 直後 `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` env apply → 09:05-09:30 sent=10 × 6 trigger 連続(60 通)
- 5/1 09:33 JST 同 env 削除(default 24h 復帰、user 明示 GO で Claude 直接実行)
- 5/1 09:35 JST trigger でも sent=10 継続(env=168 単独原因ではない確定)
- 真因仮説: guarded-publish job が */5 trigger ごとに ~100 件の old backlog post を skip 再評価し fresh ts record を append、publish-notice 24h scan で picks up、24h dedup expire で循環
- 進行中: Codex A(read-only 観察 + 最小 hotfix 案)/ Codex B(恒久対策設計 + Acceptance Pack 起草)を並行 fire
- 次 user GO 候補: Codex B 完了後、code fix Acceptance Pack(scanner に WP publish date base max_age_days filter 追加)

未確定で観察継続:
- cache_hit 99% 真因(production_health_observe 内)
- 次 deploy 前 clean build 必須(294-PROCESS で標準化予定)

---

## ACTIVE(最大 2 件)

| # | ticket | phase | status | next_review_at |
|---|---|---|---|---|
| 1 | **298-MAIL-STORM-Phase3-deploy-pack**(P1)| 1 Pack 条件付き段階化、本日 Pack 整備のみ、deploy は明日 | Phase 2 impl + push 完了(`d44594a` + `ffeba45`)、Phase 3 Pack 18+5 項目 OPS_BOARD entry に embed 済、明日朝 user 1 行提示 | 2026-05-02 06:00 JST |

本日 active 1(298-Phase3 Pack 整備、本日 deploy しない、Codex 追加 fire しない)。

### Phase 1 完了(HOLD で自然終息)/ Phase 2 完了(impl + push)

- Phase 1 = user 判断「storm 自然停止なら HOLD」該当、09:55 JST 自然終息(累積 90 通)、env=0 hotfix 回避で real review path 維持
- Phase 2 = `d44594a`(impl + 7 tests + 3 env knobs default OFF)+ `ffeba45`(deploy Pack final)、push 完了、pytest +0 regression(Claude 追認済)

---

## OBSERVE(最大 1 件、production health 統合)

| # | name | observation 対象 | next_review_at |
|---|---|---|---|
| 1 | **production_health_observe**(統合)+ **299-QA**(postgame_strict 3 pre-existing failures 統合観察) | 289 24h sent/errors/silent / 282-COST flag OFF live / 205 cursor scan / cache_hit 99% / 277 rescue / 281 / 290 NOT_DEPLOYED / 299-QA postgame_strict 3 failures 真因 / MAIL_BUDGET 30h/100d / 298-Phase3 Pack 完成度 | 2026-05-01 17:00 JST |

---

## READY(最大 3 件、Acceptance Pack 完成済 + user 即返答可)

| # | ticket | Pack 状態 |
|---|---|---|
| (空き) | - | - |

**現状 0 件**。Pack 完成案件なし。HOLD_NEEDS_PACK が READY 昇格する timing で更新。

---

## HOLD_NEEDS_PACK(user GO 必須、Pack 未完成、近期 READY 昇格候補)

| ticket | user_go_reason | pack 完成 precondition | expiry |
|---|---|---|---|
| **298-Phase3 deploy(1 Pack 段階化)** | PROD_DEPLOY+FLAG_ENV+MAIL_ROUTING_MAJOR | 本日 80% 完成、明日朝 user 提示で READY 化 | 2026-05-02 09:00 JST(第二波前)|
| 290-QA deploy + flag ON | PROD_DEPLOY+FLAG_ENV | production_health 17:00 結果 | 2026-05-02 |
| 282-COST flag ON | FLAG_ENV+COST_INCREASE | **293 完遂 + 24h**(POLICY §7 順序、293 が前提)| 293 完遂 + 24h |
| 288-INGEST source 追加 | SOURCE_ADD+COST_INCREASE | 5 条件達成 | 5 条件達成後 |

---

## FUTURE_USER_GO(いつか必要、今は聞かない、Pack 提示 timing 待ち)

| ticket | user_go_reason | 提示 timing |
|---|---|---|
| 293-COST deploy + flag ON | PROD_DEPLOY+FLAG_ENV+MAIL_ROUTING_MAJOR | 293 impl 完遂 + 24h(282 flag ON の前提、POLICY §7 順序)|
| 295-QA deploy | PROD_DEPLOY | 295 impl 完遂 + 24h |
| 296 codex-shadow deploy | PROD_DEPLOY+SCHEDULER_CHANGE | 296 設計完了 + redesign image build 後 |
| 229-COST C deploy + flag ON | PROD_DEPLOY+FLAG_ENV+COST_INCREASE | 282 flag ON + 24h cost 効果確認 + impl 完遂 |
| 278/279/280 deploy | PROD_DEPLOY+MAIL_ROUTING_MAJOR | 290 deploy + 24h + 統合 impl 完遂 |
| 264 cleanup mutation | IRREVERSIBLE | 264 Phase 1 audit 完了 + 個別 post_id GO |
| **300-COST source-side 削減** | PROD_DEPLOY+COST_INCREASE | 298-Phase3 deploy + 24h 安定後(本日 deferred 起票)|

---

## DONE(OBSERVED_OK evidence あり、close 済)

| ticket | OBSERVED_OK evidence |
|---|---|
| 276-QA test mock fix | CI run 25146349669 success / 1820 tests OK |
| 283-MKT 要件定義 doc | commit a2777f9 push / user 確認済 |
| 297-OPS codex-shadow PAUSE | scheduler state=PAUSED / 24h publish-mail trigger 維持 / Cloud Run job 残存 |
| ops_reset_2026-05-01 | session_logs commit `913844b` + `6b7d77b` push 済(履歴側)/ docs/ops/ 5 file は `0b64078` + `5fe7fad` + `66af52a` で永続化済(運用 active 正本)|
| **298-Phase1**(P1 mail storm 即時止血) | user HOLD 判断 + storm 自然終息 / 09:55 JST 以降 sent=0 維持 / env=0 hotfix 実施せず real review 影響回避 / 90 通の第一波で完結 / 不変方針(Team Shiny / 289 / X / Scheduler / Gemini / code) 全部維持 |

---

## 別 view(active board に表示しない、user に毎回見せない)

### FROZEN(本フェーズ着手 0、別 view、本日 file move 0)

16 件 + 凍結 candidate(file move は次セッション以降):
`234-impl-7` / `245` / `246-viral-topic-detection` / `247-QA-postgame-strict-slot-fill-poc` / `250-QA-1` / `250-QA-3` / `251-SEO` / `252-QA` / `253-QA` / `254-QA` / `255-MKT(待機)` / `256-QA(待機)` / `248-MKT-2` / `248-MKT-3a` / `260-MKT(待機)` / `274-OPS` / `284-287-MKT`

### DEEP_FROZEN(`doc/waiting/`、永続 NEVER)

21 件、フェーズ変更時のみ user 判断で再評価。

---

## Claude 自律 GO 候補(USER_GO_REQUIRED=false、Pack 不要、Claude が進める)

本日中に着手可能(impl 着手禁止、設計 doc 整備までに限定):

| # | 作業 | category |
|---|---|---|
| 1 | 264-QA Phase 1 audit(read-only) | READ_ONLY+EVIDENCE_ONLY |
| 2 | 293-COST 起票 prompt 整備 / 仕様 finalize(設計のみ) | DOC_ONLY+TEST_DESIGN |
| 3 | 291-OBSERVE 統一 ledger 設計(292/293 統合 doc) | DOC_ONLY+BOARD_COMPRESSION |
| 4 | 294-PROCESS clean build gate checklist 文書化 | DOC_ONLY+ROLLBACK_CATALOG |
| 5 | 295-QA / 296 / 229-C 設計 doc 整備(設計のみ) | DOC_ONLY+TEST_DESIGN |
| 6 | 278/279/280 統合 doc 設計(283-MKT 配下子化) | DOC_ONLY+BOARD_COMPRESSION |
| 7 | EXPIRY 到来 HOLD escalate 通知 | HANDOFF_UPDATE |
| 8 | silent skip / cost 監視自律(production_health_observe) | READ_ONLY+EVIDENCE_ONLY |

**重要:本日 impl 着手禁止 = Codex impl + push 0 = 設計 doc 整備のみ**。Codex impl 自律 GO は次セッション以降。

---

## 次の 1 手

**運用立て直し**(本日の主目的、Claude 自律):
- POLICY §3 自律 GO 10 categories 化(`INCIDENT_ANALYSIS` / `P0_P1_NARROW_HOTFIX` 追加)
- POLICY §14 user 明示 GO 不要化(8 条件 全部 AND で Claude 自律即時 hotfix 可能)
- POLICY §15 Outcome Ledger format(完了 evidence 永続記録)
- CURRENT_STATE / OPS_BOARD に 298 Phase 1 / 2 ACTIVE entry
- session log に 09:00-09:50 1 行履歴
- commit + push で repo 正本化

**298 P1 mail storm**(Codex 並行処理結果を Claude が圧縮):
- Phase 1 即時止血 Acceptance Pack 提示(env-only、real review 影響 trade-off)
- Phase 2 恒久 fix Acceptance Pack 提示(Codex B Option B、code fix + deploy、HOLD 推奨)
- 第一波は cap=10 × ~10 trigger ≒ 09:55 JST 頃に自然終息(Phase 1 不実施でも残 20 min)
- 第二波は 24h 後(5/2 09:00 JST 頃)、Phase 2 deploy で防止前提

**production_health_observe を 2026-05-01 17:00 JST に 1 度だけ実行**(read-only):
- publish-notice 24h sent/errors/silent
- post_gen_validate_history silent skip 維持(2808 → 増加分も 0)
- 282-COST flag OFF live 挙動不変(preflight skip 0 維持)
- cache_hit ratio(99% 持続 or 変動)
- env / Team Shiny From / Scheduler 不変
- Gmail sample 実到達

異常 0 + 298 Phase 2 deploy 完遂なら **本セッション ops reset + 298 close を確定**、異常検出時は P0 即報告(自律対処しない)。

---

## user に今見せる判断(Acceptance Pack 2 件)

1. **298-Phase1**(即時止血 env-only):real review 影響あり、自律 GO 8 条件のうち「既存通知全停止ではない」境界で安全側 user GO 求める
2. **298-Phase2**(恒久対策 code fix):Codex B Option B(persistent sent ledger)、PROD_DEPLOY+FLAG_ENV、Codex 実装便 + image rebuild + deploy

判断は最終報告 10 項目の中で 1 行に圧縮提示。

その後の Acceptance Pack 提示候補:**290-QA deploy**(production_health_observe 17:00 結果 + 298 安定後)。

---

## 不変方針(`docs/ops/POLICY.md` section 12 参照)

- ENABLE_LIVE_UPDATE_ARTICLES=0 / Team Shiny From / SEO / X / Scheduler 頻度変更 / 新 subtype / 既存 prompt text:全部不変

これらを変更する場合 = **フェーズ変更**、user 明示 GO 必須。
