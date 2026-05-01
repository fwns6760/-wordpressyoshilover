# 293-COST ready pack

Date: 2026-05-01 JST  
Mode: Lane A round 13 / doc-only / read-only final consolidation  
Pack status: field-complete / user-reply-ready / precondition HOLD

## Decision Header

```yaml
ticket: 293-COST
recommendation: HOLD
decision_owner: user
execution_owner: Codex
risk_class: mail-routing-visible-skip-path
user_go_reason: CODE_CHANGE+MAIL_VISIBILITY_PATH
expires_at: 2026-05-02 09:00 JST second-wave boundary close
```

## 1. Conclusion

- **HOLD**
- requested user decision は、`293-COST` の `impl + test + commit + push judgment` を進めるかどうか
- Pack 自体は **18/18 resolved, UNKNOWN 0** だが、impl GO の前提がまだ全部 `YES` ではない。
- `298-Phase3` の second-wave boundary close と Codex fire budget reset が残っているため、現時点では user に `GO` を求めない。

## 2. Scope

- `src/publish_notice_scanner.py`
- `src/cloud_run_persistence.py`
- `src/rss_fetcher.py`
- `src/gemini_preflight_gate.py`
- new env 3:
  - `ENABLE_PREFLIGHT_SKIP_NOTIFICATION`
  - `PREFLIGHT_SKIP_LEDGER_PATH`
  - `PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS`
- new test:
  - `tests/test_preflight_skip_notification.py`
- existing tests 維持
- user GO 後の実行順は `impl -> test -> commit -> Claude review/push judgment`

## 3. Non-Scope

- `282-COST` flag ON
- Gemini call 増加
- Scheduler 変更
- SEO / noindex / canonical / 301
- Team Shiny 変更
- source 追加
- WP REST mutation
- image rebuild + deploy
- deploy 判断そのもの

## 4. Current Evidence

- design v2: `30c8204` + `7f2f3e9`
- final review: `856dd59`
- numbering correction: `6ddff7c`
- pack consistency review v2: `0ae5505`
- `299-QA` baseline evidence: `60242be`
- current canonical ops state:
  - `docs/ops/CURRENT_STATE.md`: `298-Phase3` is `HOLD_NEEDS_PACK`
  - `docs/ops/OPS_BOARD.yaml`: second-wave risk remains `OPEN`
  - `docs/ops/POLICY.md`: `Silent Skip Policy` / `Mail Storm Rules` / `Acceptance Pack Requirement` are current truth
- production state as of this Pack:
  - Phase3 flag is `OFF_OR_ABSENT`
  - persistent old-candidate ledger is disabled
  - storm is contained
  - 293 code / deploy evidence is still `0`

## 5. User-Visible Impact

- current Pack 自体は doc-only なので production change は `0`
- 293 impl + deploy 完了後も、`ENABLE_PREFLIGHT_SKIP_NOTIFICATION` が OFF のままなら新 mail は出ない
- 293 完了後に将来 `282-COST` が ON になると、preflight skip は `【要review｜preflight_skip】` として visible 化される
- 既存の `publish / normal review / hold / 289 post_gen_validate / error` path は維持
- X candidate path は不変

## 6. Mail Volume Impact

- this ticket only:
  - expected mails/hour: `0`
  - expected mails/day: `0`
  - reason: doc-only now, deploy なし, flag default OFF
- future effect after `282-COST` ON:
  - **YES**, 新しい preflight-skip review path が出現しうる
  - ただし定量見積は `282-COST` Pack 側で行う
- MAIL_BUDGET:
  - current Pack は compliance 問題なし
  - future `282` 側で mail impact が UNKNOWN なら `HOLD`

## 7. Gemini / Cost Impact

- Gemini call increase: **NO**
- Token increase: **NO**
- source/candidate count impact: **NO**
- Cache impact: **NO**
- note:
  - 293 は scanner / persistence / ledger touch のみ
  - Gemini call path を活性化するのは `282-COST` であり、本 ticket ではない

## 8. Silent Skip Impact

- 293 の目的は preflight skip を internal log-only で終わらせず、durable ledger + scanner path で visible 化すること
- visible contract:
  - publish
  - review notification
  - hold notification
  - skip notification
- `289 post_gen_validate` path は維持し、293 はその横に preflight parallel path を足す
- dedupe は `24h`
- shared cap / existing route を壊さないことが acceptance

## 9. Preconditions

All must be `YES` before GO.

| precondition | judgment | note |
|---|---|---|
| `298-Phase3` ROLLED_BACK stability close | **NO** | `17:00` observe pass は後続 evidence にあるが、current canonical ops state では `2026-05-02 09:00 JST` second-wave boundary close 前で `OPEN` |
| `2026-05-01 17:00 JST production_health_observe` 異常 0 | **YES** | next-day summary では `17:00 observe pass` 記録あり |
| `silent skip 0` 維持確認 | **YES** | observe evidence と policy baseline 上は pass 扱い |
| Codex fire budget reset | **NO** | design v2 / final review の通り「明日朝以降」の前提 |

## 10. Implementation Order

1. commit 1: ledger schema + persistence scaffold  
   `src/cloud_run_persistence.py` + related tests
2. commit 2: scanner parallel path  
   `src/publish_notice_scanner.py` + tests + `tests/test_preflight_skip_notification.py`
3. commit 3: rss_fetcher + gemini_preflight_gate skip-layer output  
   `src/rss_fetcher.py` + `src/gemini_preflight_gate.py`
4. commit 4: tests 7 cases 全部 green 化

## 11. Tests

1. fetcher が flag ON 時に preflight ledger row を書く
2. scanner が flag ON 時に mail request を emit する
3. flag OFF 時は silent skip `0` を保つ
4. `24h` dedupe window を守る
5. 8 reason label mapping を table-driven で固定する
   - `existing_publish_same_source_url`
   - `placeholder_body`
   - `not_giants_related`
   - `live_update_target_disabled`
   - `farm_lineup_backlog_blocked`
   - `farm_result_age_exceeded`
   - `unofficial_source_only`
   - `expected_hard_stop_death_or_grave`
6. `post_gen_validate` path 維持(`289` 不変)
7. persistence entrypoint が ledger download / cursor upload を守る

## 12. Rollback

- **Phase A**: env remove  
  `--remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION`  
  owner: Claude authenticated executor  
  expected time: `~30 sec`
- **Phase B**: publish-notice image rollback to previous SHA  
  owner: Claude authenticated executor  
  expected time: `~2-3 min`
- **Phase C**: GCS state cleanup  
  archive / remove `preflight_skip_history.jsonl`  
  owner: Claude authenticated executor  
  expected time: `~2-5 min`
- note:
  - 将来 `282` が already ON の状態で 293 rollback を切るなら、fetcher 側 gate OFF を先に打って silent skip を再発させない

## 13. Stop Conditions

- `289` emit 減少
- Team Shiny 変
- silent skip 増(`POLICY.md §8` 違反)
- Gemini call 増(本 ticket 経由でなく)
- `cap=10` / `24h dedupe` 違反
- `MAIL_BUDGET` 違反

## 14. 18-Field Resolution

### Pack completeness 13/13

| field | judgment |
|---|---|
| Conclusion | **YES** |
| Scope | **YES** |
| Non-Scope | **YES** |
| Current Evidence | **YES** |
| User-Visible Impact | **YES** |
| Mail Volume Impact | **YES** |
| Gemini / Cost Impact | **YES** |
| Silent Skip Impact | **YES** |
| Preconditions | **YES** |
| Tests | **YES** |
| Rollback | **YES** |
| Stop Conditions | **YES** |
| User Reply | **YES** |

### Additional 5 required answers

| item | final answer |
|---|---|
| Gemini call increase | **NO** |
| Token increase | **NO** |
| Candidate disappearance risk | **NO** |
| Cache impact | **NO** |
| Mail volume impact | **YES** |

### Net

- resolved: **18 / 18**
- unknown: **0**
- decision gate: **HOLD** because preconditions still include `NO`

## 15. User Reply

`GO` / `HOLD` / `REJECT`
