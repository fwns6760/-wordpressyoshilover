# 298-Phase3 v4 Pack alignment review

作成: 2026-05-01 JST  
mode: Lane B round 5 / doc-only / read-only review / single-file diff  
scope: `docs/handoff/codex_responses/2026-05-01_298_phase3_v4_alignment_review.md` 新規のみ

---

## 0. 結論

- 現行 `298-Phase3 v4 Pack` は、`ACCEPTANCE_PACK_TEMPLATE.md` の `298-Phase3 Additional Required Fields` と照合すると **6 / 9 充足**。
- よって `docs/ops/OPS_BOARD.yaml` の `hold_needs_pack.298-Phase3.re_on_forbidden_until` は **未解除**。明日朝の user 提示は **HOLD 維持** が妥当。
- 特に穴が残るのは `rollback command`、`persistent ledger disabled の明示確認`、`normal review / 289 / error mail 維持確認`。
- `5/2 09:00 JST` 第二波 `99 unique post_id` / `first emit 99 通` / `118.8 通/h` / `99/100 通/d` の危険数値自体は v4 Pack に反映済み。

---

## 1. 9 項目 cross-check

判定ルール:

- `YES`: v4 Pack 本文だけで required field が埋まっている
- `NO`: v4 Pack 本文に required field が未固定
- `UNKNOWN`: field はあるが、required meaning まで確定せず追加 evidence が必要

| # | required field | v4 Pack | v4 Pack evidence | 補強 evidence / review note |
|---|---|---|---|---|
| 1 | old candidate pool cardinality estimate | **YES** | `2026-05-01_298_Phase3_v4_second_wave_pack.md:30-31` に `103 unique post_id` / `99 unique post_id` | 元数値 source は `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md:45`。`stability_evidence_pre.md` 自体は `99` を持たない |
| 2 | expected first-send mail count | **YES** | `...v4_second_wave_pack.md:37` と `:213`, `:221` に `99 通` | 元数値 source は `session_logs/...:45` |
| 3 | max mails/hour | **YES** | `...v4_second_wave_pack.md:38-39` に `118.8 通/h` | `MAIL_BUDGET 30/h` 超過を明示済み |
| 4 | max mails/day | **YES** | `...v4_second_wave_pack.md:40` に `99/100 通`、通常 mail 1 通で `100/d` 違反と明記 | safe 設計ではなく breach 診断値。re-ON GO 根拠にはまだならない |
| 5 | stop condition | **YES** | `...v4_second_wave_pack.md:230` | field 自体はあるが、`POLICY.md §7` が要求する `Repeated old-candidate mail is P1 recurrence` を stop 条件へ直書きした方が整合が強い |
| 6 | rollback command | **UNKNOWN** | `...v4_second_wave_pack.md:75`, `:222` は rollback **plan** まで | `session_logs/...:43` に env remove の実行例はあるが、image revert / ledger archive restore の **command 固定** は reviewed sources 内で未提示 |
| 7 | `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` OFF/absent 確認 | **YES** | `...v4_second_wave_pack.md:12` | `stability_evidence_pre.md:127-131` と `OPS_BOARD.yaml:99-103` が補強 |
| 8 | persistent ledger behavior disabled 確認 | **NO** | v4 Pack 本文に current state としての明示行なし | `OPS_BOARD.yaml:99-103` には `persistent_ledger_function: disabled`、`session_logs/...:43` には `permanent_ledger 機能無効化` があるので、Pack へ明示転記が必要 |
| 9 | normal review / 289 / error mail remain active 確認 | **UNKNOWN** | `...v4_second_wave_pack.md:221`, `:229-230` で normal review / `289` 維持は読める | `error mail remain active` の明示確認は v4 Pack 本文にない。`OPS_BOARD.yaml:162` は board-level evidence、`stability_evidence_pre.md:23-31`, `:65-75`, `:148-155` は review/289/errors=0 までで、error mail path 生存の positive proof までは固定していない |

集計:

- `YES`: **6 / 9**
- `NO`: **1 / 9**
- `UNKNOWN`: **2 / 9**

UNKNOWN 残:

- `rollback command`
- `normal review / 289 / error mail remain active` のうち、特に `error mail remain active`

template rule:

- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md:102` の通り、**1 つでも UNKNOWN が残る限り recommendation は HOLD**。

---

## 2. rollback / stop / mail volume 穴埋め review

### rollback review

- v4 Pack の rollback 方針は **narrow rollback** で、`POLICY.md §7` の
  - `Do not stop all mail`
  - `Do not pause Scheduler as the normal fallback`
  - `Do not reapply PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`
  とは**矛盾しない**。
- ただし `OPS_BOARD.yaml:106-113` と `ACCEPTANCE_PACK_TEMPLATE.md:96-99` が求めるのは `rollback command` であり、v4 Pack は `env remove + image revert + ledger archive restore` という **工程名** に留まる。
- reviewed sources で concrete なのは `session_logs/2026-05-01_p1_mail_storm_hotfix.md:43` の `gcloud run jobs update publish-notice --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` まで。image revert と ledger restore は **command 未固定**。
- よって rollback は **policy-aligned だが Pack field としては未完成**。

### stop condition review

- v4 Pack の stop condition 本体 `...v4_second_wave_pack.md:230` は、
  - normal review 減少
  - `289` 減少
  - Team Shiny From 変化
  - `errors > 0`
  - `silent skip` 増
  - `MAIL_BUDGET 30/h or 100/d` 違反
  を持ち、`POLICY.md §7` の主要事故軸とは概ね整合。
- ただし `POLICY.md:112` は `Repeated old-candidate mail is P1 recurrence` を permanent rule にしているため、stop 条件には
  - `【要確認(古い候補)】` の再出現
  - old-candidate repeat emit の再発
  を明示追加した方がよい。
- また `POLICY.md:113` は `error notifications alive` を要求するため、stop 条件に
  - `error notification path disappears`
  を入れると template 9 項目とも繋がる。

### mail volume impact review

- 第二波 math は v4 Pack `:37-40` で explicit。
- 判定:
  - `99 通 / 約 50 分` = **118.8 通/h**
  - `MAIL_BUDGET 30/h` に対して **+88.8 通/h 超過**
  - `99/100 通/d` は old-candidate group だけで **日次予算 99% 消費**
  - 通常の review / `289` / error mail が **1 通でも重なると 100/d 違反**
- したがって現行 v4 Pack は **mail volume impact を unknown にしていない点は良い**が、現時点の second-wave profile 自体は **MAIL_BUDGET 内設計ではない**。
- re-ON を GO にするには、chosen mitigation 後の想定 first-send profile が
  - `<= 30/h`
  - `<= 100/d`
  を満たす evidence まで必要。

---

## 3. 第二波想定数値の最新化 review

現行 v4 Pack への反映状況:

- `...v4_second_wave_pack.md:31-33`
  - `99 unique post_id`
  - `2026-05-01 09:00 JST` 既送
  - `2026-05-02 09:00 JST` dedup expiry 後に再 emit 想定
- `...v4_second_wave_pack.md:37-40`
  - `first emit 99 通`
  - `118.8 通/h`
  - `99/100 通/d`

補強 evidence path:

- cardinality 正本: `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md:45`
- rollback 後 baseline 補強:
  - `docs/handoff/codex_responses/2026-05-01_298_Phase3_stability_evidence_pre.md:23-34`
  - `...:127-131`
  - `...:148-161`

review note:

- `stability_evidence_pre.md` は rollback 後の `errors=0` / `silent skip=0` / old-candidate emit `0` / flag absent を補強する doc であり、**`99 unique post_id` そのものの source ではない**。
- したがって user 提示前に Claude が v4 Pack を再整形する場合、`99` の footnote は `stability_evidence_pre.md` 単独ではなく `session_logs/...:45` と組で示すのが安全。

---

## 4. re-ON 禁止条件 解除順序 提案

解除ルール:

1. `OPS_BOARD.yaml:106-113` の `re_on_forbidden_until` 7 項目を全部 `YES`
2. `ACCEPTANCE_PACK_TEMPLATE.md:98-100` の追加 2 項目を全部 `YES`
3. `UNKNOWN = 0`
4. second-wave mitigation 後の max mail profile が `MAIL_BUDGET 30/h・100/d` 内

現状判定:

- `YES 6/9` のため **re-ON forbidden 継続**
- `UNKNOWN 2` が残るため **template rule 上も HOLD**

明日朝 06:00 JST の user 提示順序:

1. Claude が v4 Pack へ alignment review 結果を反映
2. 9/9 `YES` かつ `UNKNOWN=0` を再判定
3. 条件を満たした場合のみ 1 行で user 提示
4. user 返答は `GO` / `HOLD` / `REJECT`

1 行提示ルール:

- **GO 提示可の条件**: `9/9 YES` かつ `UNKNOWN=0` かつ budget-safe mitigation evidence あり
- **1 つでも UNKNOWN**: user には **HOLD 維持** を 1 行で出す
- **NO が残る**: GO 提示不可。HOLD 維持

現時点の推奨 1 行:

```text
298-Phase3 は rollback command と error-mail 維持確認が未固定のため HOLD 維持。GO 提示は 9/9 YES + UNKNOWN 0 の後。
```

補足:

- v4 Pack `:209` は `Decision: HOLD` で整合している。
- ただし `:232` の `Recommended decision: GO(条件付き)` は **未来条件付き** の文言であり、現状の 06:00 JST user prompt にそのまま流用しない方が安全。

---

## 5. Claude 向け最小差分メモ

- v4 Pack に追加すべき最小差分は次の 3 点。
- `persistent ledger behavior is currently disabled` を current state として明示。
- `rollback command` を env remove / image revert / ledger restore の command 形式で固定。
- `normal review / 289 / error mail remain active` を 1 行で明示し、可能なら error notification path の evidence path を添える。

この 3 点が埋まるまでは、298-Phase3 の再 ON 提示は **HOLD 維持**。
