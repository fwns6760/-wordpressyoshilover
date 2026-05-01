# 282-COST flag ON 判断 READY Pack

作成: 2026-05-01 JST  
mode: Lane A / doc-only / read-only consolidation  
use: `293-COST` 完遂 + 24h 安定確認後に user へそのまま提示する 1 page Pack

```yaml
ticket: 282-COST
recommendation: HOLD
decision_owner: user
execution_owner: Claude
risk_class: FLAG_ENV+COST_CHAIN
user_go_reason: 282-COST flag ON は 293-COST visible skip readiness 完了後のみ判断可能
expires_at: 293 complete + 24h stable + cost evidence locked
```

## Conclusion

- **結論: HOLD**
- 理由: `ENABLE_GEMINI_PREFLIGHT=1` は `293-COST` 実装・test・commit・push・24h 安定確認の後でしか GO 推奨できない。
- **GO 推奨条件**: `293` 完遂 + 24h 安定 + cost 削減見積 evidence + cache baseline/effect 比較が揃った後。

## Scope

- `yoshilover-fetcher` service env に `ENABLE_GEMINI_PREFLIGHT=1` を適用することだけ。

## Non-Scope

- image rebuild
- `293-COST` 実装
- Scheduler 変更
- SEO/noindex/canonical/301
- Team Shiny From
- source 追加
- mail 大改修
- `ENABLE_LIVE_UPDATE_ARTICLES` を含む他 env 変更

## Implementation Order

- なし。live 変更は env 1 個 apply のみ。
- 実行コマンド:

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_GEMINI_PREFLIGHT=1
```

## Current Evidence

- pack bundle:
  - `1fd2755` `2026-05-01_282_COST_pack_draft.md`
  - `925003d` `2026-05-01_282_COST_pack_supplement.md`
  - `ade62fb` `2026-05-01_unknown_flags_resolution.md`
  - `0ae5505` `2026-05-01_pack_consistency_review_v2.md`
- current prod state:
  - 282 gate code は live、`ENABLE_GEMINI_PREFLIGHT` は **OFF**
  - `future_user_go.282-COST` は `293-COST visible skip readiness` に block されている
  - `Candidate disappearance risk = NO`
  - `Cache impact = YES`
- current recommendation basis:
  - `293` 未完遂
  - `293` 24h stability 未確認
  - `282` ON 後の exact Gemini delta / cache delta は未実測

## User-Visible Impact

- flag ON 後は Gemini に進まない候補が増える。
- 正常系では候補は silent に消えず、`293` path 経由で `【要review｜preflight_skip】...` mail として可視化される。
- したがって user-visible 影響は「候補消失」ではなく「publish/review から preflight_skip review への一部 route 変更」。

## Mail Volume Impact

- **判定: YES**
- 方向は `publish/review` 減少、`preflight_skip` 増加の composition shift。
- 許容条件は **flat to slight down**。`MAIL_BUDGET 30/h・100/d` を超えないこと。
- `293` path が無い状態で ON にすると silent skip になり得るため不可。

## Gemini / Cost Impact

- **Gemini call increase: NO**
- **Token increase: NO**
- 想定方向は cost 減少。preflight gate により Gemini call を止めるため、逆方向 anomaly は stop 条件。
- exact 削減率は `293` 完遂後に 24h baseline 比較で確定する。

## Silent Skip Impact

- `293` 完遂前に 282 を ON にしない。
- `293` 完遂後は preflight skip が必ず visible route に出ることを verify する。
- internal log only は acceptance 不可。

## Preconditions

- `293-COST` impl + test + commit + push 完了
- `293` 24h 安定確認 pass
- silent skip `0`
- Gemini delta `0` or reverse-direction anomaly `0` on `293`-only window
- Team Shiny From 維持
- `MAIL_BUDGET` 内
- `298-Phase3` ROLLED_BACK 後の安定確認
- `17:00 production_health_observe` pass
- Codex 上限超過解消
- cache_hit ratio baseline lock 済み(282 ON 後 delta 比較用 24h 集計)

## Test Plan

- **precondition test**
  - `293` impl/test 完了
  - `293` 24h で silent skip `0` 維持
  - Team Shiny / `289 post_gen_validate` / normal review / error mail が不変
- **flag ON verify**
  - `preflight_skip` event が `【要review｜preflight_skip】` mail で visible 化される
  - `ENABLE_GEMINI_PREFLIGHT=1` 後に Gemini call が増えない
- **regression**
  - `289 post_gen_validate` emit 不変
  - Team Shiny 不変
  - review cap `10/run` 不変
  - 24h dedup 不変
  - publish/review/hold/error mail 導線不変

## Rollback Plan

- **Phase A only**
  - env rollback:

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_GEMINI_PREFLIGHT
```

- expected time: `~30 sec`
- image rollback: **不要**。本 ticket は env 操作のみで image 不変。
- ただし `293` path も同時に live で visibility contract を壊す場合は、293 rollback も handoff で同時実施する。

## Stop Conditions

- silent skip 増加(`293` path を経由せず user-visible にならない)
- `289` emit 減少
- Team Shiny From 変化
- Gemini call 逆方向 anomaly
- cache_hit ratio 急変(`±15%pt` 超)
- publish 急減
- candidate disappearance 増加
- `MAIL_BUDGET 30/h・100/d` breach

## 18-Field Readiness

| field | verdict | note |
|---|---|---|
| Pack field: Conclusion | YES | HOLD 固定 |
| Pack field: Scope | YES | env 1 個 apply のみ |
| Pack field: Non-Scope | YES | image / 293 impl / Scheduler / SEO / source add なし |
| Pack field: Current Evidence | YES | 4 doc bundle + current prod state 固定 |
| Pack field: User-Visible Impact | YES | visible route change として記述済み |
| Pack field: Mail Volume Impact | YES | composition shift + budget 条件記述済み |
| Pack field: Gemini / Cost Impact | YES | 増加 NO、exact delta は post-293 observe |
| Pack field: Silent Skip Impact | YES | 293 必須と明記済み |
| Pack field: Preconditions | YES | 293 + 24h + 298 rollback 後安定を固定 |
| Pack field: Tests | YES | precondition / verify / regression 記述済み |
| Pack field: Rollback | YES | Phase A env remove 明記済み |
| Pack field: Stop Conditions | YES | 8 条件固定 |
| Pack field: User Reply | YES | `GO` / `HOLD` / `REJECT` |
| Risk flag: Gemini call increase | NO | 逆方向 anomaly は stop |
| Risk flag: Token increase | NO | call 減少方向 |
| Risk flag: Candidate disappearance risk | NO | `ade62fb` 固定 |
| Risk flag: Cache impact | YES | preflight は cache 前 return |
| Risk flag: Mail volume impact | YES | `preflight_skip` 可視化増加可能性あり |

## User Reply

`GO` / `HOLD` / `REJECT`

## Claude Handoff

- この Pack は **282-COST READY 化完了**として保持し、**user 提示は `293` 完遂 + 24h 安定後**に行う。
- 現時点の運用判定は **HOLD**。`293` 未完遂のため、まだ GO 提示しない。
