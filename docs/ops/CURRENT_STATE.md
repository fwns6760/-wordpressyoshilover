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

| # | ticket | status | next_review_at |
|---|---|---|---|
| 1 | **298-MAIL-STORM-HOTFIX**(P1) | env=168 削除済、storm 継続(09:35 sent=10)、Codex A/B 並行調査中 | 2026-05-01 10:30 JST(Codex 完了 + Acceptance Pack 提示)|

本日 active 1(P1 mail storm 進行中、Codex A/B 並行で止血 hotfix 案 + 恒久対策 Acceptance Pack 起草中)。

---

## OBSERVE(最大 1 件、production health 統合)

| # | name | observation 対象 | next_review_at |
|---|---|---|---|
| 1 | **production_health_observe**(統合) | 289 24h sent/errors/silent / 282-COST flag OFF live 挙動 / 205 cursor scan / cache_hit 99% / 277 rescue 効果(290 deploy 後) / 281 <24h positive case / 290 NOT_DEPLOYED 維持 | 2026-05-01 17:00 JST |

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
| 290-QA deploy + flag ON | PROD_DEPLOY+FLAG_ENV | production_health 17:00 結果 | 2026-05-02 |
| 282-COST flag ON | FLAG_ENV+COST_INCREASE | 293 完遂 + 24h | 293 完遂 + 24h |
| 288-INGEST source 追加 | SOURCE_ADD+COST_INCREASE | 5 条件達成 | 5 条件達成後 |

---

## FUTURE_USER_GO(いつか必要、今は聞かない、Pack 提示 timing 待ち)

| ticket | user_go_reason | 提示 timing |
|---|---|---|
| 293-COST deploy + flag ON | PROD_DEPLOY+FLAG_ENV+MAIL_ROUTING_MAJOR | 293 impl 完遂 + 24h |
| 295-QA deploy | PROD_DEPLOY | 295 impl 完遂 + 24h |
| 296 codex-shadow deploy | PROD_DEPLOY+SCHEDULER_CHANGE | 296 設計完了 + redesign image build 後 |
| 229-COST C deploy + flag ON | PROD_DEPLOY+FLAG_ENV+COST_INCREASE | 282 flag ON + 24h cost 効果確認 + impl 完遂 |
| 278/279/280 deploy | PROD_DEPLOY+MAIL_ROUTING_MAJOR | 290 deploy + 24h + 統合 impl 完遂 |
| 264 cleanup mutation | IRREVERSIBLE | 264 Phase 1 audit 完了 + 個別 post_id GO |

---

## DONE(OBSERVED_OK evidence あり、close 済)

| ticket | OBSERVED_OK evidence |
|---|---|
| 276-QA test mock fix | CI run 25146349669 success / 1820 tests OK |
| 283-MKT 要件定義 doc | commit a2777f9 push / user 確認済 |
| 297-OPS codex-shadow PAUSE | scheduler state=PAUSED / 24h publish-mail trigger 維持 / Cloud Run job 残存 |
| ops_reset_2026-05-01 | session_logs commit `913844b` + `6b7d77b` push 済(履歴側)/ **docs/ops/ 5 file は本 commit(2026-05-01 09:55 JST 予定)で初永続化**(前回 session で untracked のまま誤判定、本 commit で正本化)|

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

**298-MAIL-STORM-HOTFIX**(P1 進行中):
1. Codex A/B 完了待ち(~10-30 min)
2. Codex B 出力の Acceptance Pack を user 提示(code fix scanner max_age_days)
3. user GO 受領後 → Codex 実装便 + image rebuild + deploy
4. deploy 後 sent=0 verify + 24h 観察

並行実施(Claude 自律 GO):
- POLICY.md §14(P0/P1 自律 hotfix 範囲)/ §15(Outcome Ledger format)永続化済(本 commit で push)
- CURRENT_STATE.md / OPS_BOARD.yaml に 298 ticket ACTIVE 化(本 commit)

**production_health_observe を 2026-05-01 17:00 JST に 1 度だけ実行**(read-only):
- publish-notice 24h sent/errors/silent
- post_gen_validate_history silent skip 維持(2808 → 増加分も 0)
- 282-COST flag OFF live 挙動不変(preflight skip 0 維持)
- cache_hit ratio(99% 持続 or 変動)
- env / Team Shiny From / Scheduler 不変
- Gmail sample 実到達

異常 0 + 298 hotfix 完遂なら **本セッション ops reset + 298 close を確定**、異常検出時は P0 即報告(自律対処しない)。

---

## user に今見せる判断

**0 件 → 1 件 候補**(298-MAIL-STORM-HOTFIX code fix Acceptance Pack):
- Codex B 完成後、scanner max_age_days filter 案を 13 項目で提示
- 提示 timing:Codex B 完了 + Claude 影響範囲 review 後(~30 min 内予想)

その後の Acceptance Pack 提示候補:**290-QA deploy**(production_health_observe 17:00 結果 + 298 安定後)。

---

## 不変方針(`docs/ops/POLICY.md` section 12 参照)

- ENABLE_LIVE_UPDATE_ARTICLES=0 / Team Shiny From / SEO / X / Scheduler 頻度変更 / 新 subtype / 既存 prompt text:全部不変

これらを変更する場合 = **フェーズ変更**、user 明示 GO 必須。
