# 300-COST ready pack

Date: 2026-05-01 JST  
Mode: Lane B round 13 / doc-only / read-only final consolidation  
Pack status: field-complete / user-reply-ready / ready_pending_298

## Decision Header

```yaml
ticket: 300-COST
recommendation: HOLD
decision_owner: user
execution_owner: Codex
risk_class: source-side-idempotent-history
user_go_reason: CODE_CHANGE+GUARDED_PUBLISH_BEHAVIOR
expires_at: 2026-05-02 14:15 JST earliest 298 24h stability close
```

## 1. Conclusion

- **HOLD**
- `GO` 推奨は、preconditions が **全て YES** になった後のみ。
- 現在の主 blocker は `298-Phase3`。rollback 起点は `2026-05-01 14:15 JST` なので、最短の `24h` stability close は `2026-05-02 14:15 JST`。
- `300-COST` は standalone で先に入れない。`source_analysis_v2` が示した reminder-layer disappearance nuance を避けるため、`298` の first-notice contract 安定後にだけ impl 起票する。

## 2. Scope

- `src/guarded_publish_runner.py` のみ変更。
- Option C-narrow:
  - `hold_reason=backlog_only`
  - latest row が存在
  - latest row と今回 row の `status / judgment / hold_reason` が同一
  - 上記を全て満たすときだけ fresh `ts` 再 append を skip
- env 追加は `ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY` の 1 個だけ。
- blast radius は source-side guarded history append に限定。`real review unchanged`、`sent`、`refused`、他 `hold_reason` は対象外。

## 3. Non-Scope

- `298-Phase3`
- `293-COST`
- `282-COST`
- `290-QA`
- `288-INGEST`
- Scheduler
- SEO / noindex / canonical / `301`
- Team Shiny
- WP REST mutation
- `publish-notice` routing / subject / cap / `24h` dedup redesign
- Cloud Run execution count/day 削減
- GCS whole-file upload count/day 削減

## 4. Current Evidence

- source/evidence bundle:
  - `7a946a8` `2026-05-01_300_COST_source_analysis.md`
  - `54c2355` `2026-05-01_300_COST_pack_draft.md`
  - `c959327` `2026-05-01_300_COST_pack_supplement.md`
  - `ead78a3` `2026-05-01_300_COST_source_analysis_v2.md`
- measured `24h` actuals from v2:
  - total guarded history rows/day: `29,756`
  - `backlog_only` rows/day: `29,481`
  - current latest-state backlog pool: `104`
  - projected pool at `2026-05-02 09:00 JST`: `~108`
- Option C-narrow estimate:
  - rows/day: `29,756 -> ~281`
  - raw append/day: `~10.36 MiB -> ~0.11 MiB`
  - reduction surface is history/scanner input only
- canonical ops state:
  - `docs/ops/CURRENT_STATE.md`: `300-COST = ACTIVE(read-only analysis only)`
  - `docs/ops/OPS_BOARD.yaml`: `300-COST` forbidden without user GO = implementation / deploy / source behavior change
  - `298-Phase3 = HOLD_NEEDS_PACK / ROLLED_BACK_AFTER_REGRESSION`
- `2026-05-01 17:00 JST production_health_observe` pass は downstream packs に記録済み。ただし canonical state 上はまだ `298` 24h gate close 前。

## 5. User-Visible Impact

- current production impact は `0`。本 Pack は doc-only。
- impl 後も意図する user-visible routing 変更は `0`。狙いは repeated `backlog_only` source rows の抑制だけ。
- `backlog_only` unchanged candidate の source reevaluation 自体は継続する。失うのは duplicate source-row append だけで、新規 publish chance を消す設計ではない。
- ただしこの `NO` judgment は `298` first-notice contract 安定後を前提にしたもの。standalone 300 は out-of-order として禁止。

## 6. Mail Volume Impact

- **NO**
- source-side only のため、mail class / recipient / subject / cap / sender は変えない。
- expected mails/hour delta: `0`
- expected mails/day delta: `0`
- `MAIL_BUDGET 30/h, 100/d` への想定影響はなし。
- もし `real review` / `289` / visible skip の emit が痩せるなら、それは削減効果ではなく stop condition。

## 7. Gemini / Cost Impact

- Gemini call increase: **NO**
- Token increase: **NO**
- Cache impact: **NO**
- Cloud Run job executions/day: `288 -> 288`
- GCS object uploads/day: `288 -> 288`
- cost reduction の主対象:
  - `guarded_publish_history.jsonl` row growth
  - raw append bytes/day
  - scanner new-row input volume
- job duration reduction は second-order。`300-COST` を wall-clock 削減 ticket として扱わない。

## 8. Silent Skip Impact

- **NO**。`POLICY §8` の通り internal-log-only outcome は不可。
- `publish / review / hold / skip` visibility contract は維持する。
- `real review unchanged` は引き続き append を維持し、review reminder semantics を痩せさせない。
- `289 post_gen_validate` / normal review / error mail / Team Shiny は不変でなければならない。

## 9. Implementation Order

1. **commit 1: env scaffold + idempotent helper**  
   `src/guarded_publish_runner.py` に default-OFF env 読み出しと narrow helper を追加する。
2. **commit 2: backlog_only unchanged 判定 logic**  
   `hold_reason=backlog_only` かつ `status / judgment / hold_reason` 同一時だけ append skip。`real review unchanged` は append 維持。
3. **commit 3: tests 5 cases**  
   `tests/test_guarded_publish_runner.py` を主対象に `tests/test_publish_notice_scanner.py` の consumer 整合も追加する。
4. **commit 4: docstring + integration verify**  
   helper/docstring を確定し、runner/scanner の integration verify を実施して single-purpose commit として閉じる。

## 10. Test Plan

1. `backlog_only unchanged`  
   flag ON、same `post_id`、same `status / judgment / hold_reason`。期待: `ts` 再 append skip。
2. `real review unchanged`  
   review 系 hold が不変。期待: 従来通り append 維持、`300` の影響なし。
3. `backlog_only changed`  
   `status` または `judgment` または `hold_reason` が変化。期待: append 実行。
4. `flag OFF baseline`  
   env unset/0。期待: 挙動 `100%` 不変。
5. `scanner consumer compatibility`  
   source-side no-new-row でも `298` ledger / cursor / queue / history contract と整合。`publish_notice_scanner` は `cursor_at_head` 側で正常継続。

## 11. Preconditions

All must be `YES` before GO.

| precondition | judgment | note |
|---|---|---|
| `298-Phase3` ROLLED_BACK 後 `24h` 安定確認 | **NO** | rollback 起点 `2026-05-01 14:15 JST`、最短 close は `2026-05-02 14:15 JST` |
| `2026-05-01 17:00 JST production_health_observe` pass | **YES** | downstream packs / summary に pass 記録あり |
| source v2 evidence 固定 | **YES** | `29,756/day -> ~281/day`、`104 -> ~108` projection、standalone risk nuance まで確定済み |
| Cloud Run executions/day=`288` / GCS uploads/day=`288` は別 ticket と理解済み | **YES** | `300` は source-row reduction ticket であり upload-count reduction ticket ではない |

## 12. Rollback Plan

- **Phase A: env rollback**  
  `gcloud run jobs update guarded-publish --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY`  
  expected time: `~30 sec`
- **Phase B: image rollback**  
  `gcloud run jobs update guarded-publish --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:6df049c`  
  expected time: `~2-3 min`
- **Phase C: ledger archive retreat(anomaly-only)**  
  current `guarded_publish_history.jsonl` を archive 退避し、consumer anomaly が proven のときだけ関連 state を restore。通常 rollback では不要。

## 13. Stop Conditions

- `real review unchanged` が `ts` append を失う
- silent skip 増加(`POLICY §8` 違反)
- mail 通知 path 影響
- `cap=10/run` または `24h dedup` contract drift
- GCS write 削減効果なし、または Option C-narrow logic failure で source-row reduction が出ない

## 14. 18-Field Resolution

| field | judgment | note |
|---|---|---|
| Conclusion | **YES** | `HOLD` 固定 |
| Scope | **YES** | `guarded_publish_runner.py` + env 1 個 |
| Non-Scope | **YES** | `298/293/282/290/288`、Scheduler、SEO、Team Shiny、WP mutation なし |
| Current Evidence | **YES** | 4 doc bundle + canonical ops state 固定 |
| User-Visible Impact | **YES** | impl-only で routing delta `0`、standalone 300 は禁止 |
| Mail Volume Impact | **YES** | emit delta `0`、budget 不変 |
| Gemini / Cost Impact | **YES** | Gemini/token/cache `0`、row growth 大幅減 |
| Silent Skip Impact | **YES** | internal-log-only 不可、visible contract 維持 |
| Preconditions | **YES** | `298` 24h close 待ちを明示 |
| Tests | **YES** | 5 cases 固定 |
| Rollback | **YES** | Phase A/B/C 明記 |
| Stop Conditions | **YES** | 5 条件固定 |
| User Reply | **YES** | `GO` / `HOLD` / `REJECT` |
| Gemini call increase | **NO** | source-side append suppressionのみ |
| Token increase | **NO** | Gemini path 不変 |
| Candidate disappearance risk | **NO** | `298` stable 後の sequenced GO 前提。new publish chance は失わない |
| Cache impact | **NO** | cache path 不変 |
| Mail volume impact flag | **NO** | sink-side emit count 変更なし |

### Net

- resolved: **18 / 18**
- unknown: **0**
- decision gate: **HOLD**
- ready status: **ready_pending_298**

## 15. User Reply

`GO` / `HOLD` / `REJECT`
