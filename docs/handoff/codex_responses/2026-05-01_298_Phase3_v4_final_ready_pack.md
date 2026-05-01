# 298-Phase3 v4 final ready pack

Date: 2026-05-01 JST  
Mode: Lane B round 12 / doc-only / read-only final consolidation  
Pack status: field-complete / user-reply-ready / boundary-conditional

## Decision Header

```yaml
ticket: 298-Phase3
recommendation: GO
decision_owner: user
execution_owner: Claude
risk_class: publish-notice-old-candidate-second-wave
user_go_reason: SECOND_WAVE_PREVENTION_BEFORE_2026-05-02_09:00_JST
expires_at: 2026-05-02 09:00 JST second-wave boundary
```

## 1. Conclusion

- **GO 推奨線は固定**
- 根拠は `alignment 9/9`、`UNKNOWN 0`、`2026-05-02 09:00 JST` second-wave risk `OPEN` の 3 点。
- ただし `2026-05-02 06:00 JST` 時点で preconditions に `PARTIAL/NO` が 1 件でも残るなら、user 提示文は **HOLD** に切り替える。
- 特に境界になるのは `298-Phase3` second-wave boundary close と Codex fire budget reset。

## 2. Scope

- `publish-notice` Cloud Run job のみ
- commit `ffeba45` を基準に clean build(`POLICY §8`)で image rebuild
- job update with new image
- flag OFF deploy のまま `1-2` trigger observe
- 条件 OK で `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1` を apply
- Case A: ledger seed mode で old-candidate second wave を `99 -> 0` target
- flag ON 後 `1-2` trigger observe
- `2026-05-02 09:00 JST` second-wave 防止確認

## 3. Non-Scope

- Team Shiny change
- `289`
- X / SNS
- Scheduler
- `live_update`
- `290`
- `293`
- `282`
- `300`
- `288`
- WP REST mutation
- mail 通知条件の大改修
- 通知体系の全体再設計

## 4. Current Evidence

- bundle:
  - `aa6a8eb` stability evidence pre
  - `cdd0c3f` v4 second-wave pack
  - `9d5620e` alignment review
  - `cf86e88` UNKNOWN close
  - `0ae5505` pack consistency review v2
  - `4abe1d5` INCIDENT_LIBRARY anchor
- current live state:
  - `298-Phase3 = ROLLED_BACK_AFTER_REGRESSION`
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` is OFF/absent
  - persistent ledger behavior is disabled
  - `publish-notice` image family is still rollback-era baseline behavior
- observed risk:
  - backlog-only pool = `103 unique post_id`
  - morning storm group = `99 unique post_id`(`63003-63311`)
  - no mitigationなら `2026-05-02 09:00 JST` 前後に `~99 mails / ~50 min = 118.8/h`, `99/100 per day`
- current safety notes:
  - `2026-05-01 17:00 JST production_health_observe` pass は downstream ready packs / next-day summary に反映済み
  - `299-QA` は `N=2` green evidence まで fixed、ただし `N=3` close は未達

## 5. User-Visible / Mail / Gemini / Silent Skip

- current live impact は `0`。この pack 自体は doc-only で production change を含まない。
- Case A の user-visible effect は old-candidate second wave だけを抑えること。target は `【要確認(古い候補)】 99 -> 0`。
- `real review` / `289 post_gen_validate` / error mail / Team Shiny From / normal publish-notice path は維持。
- mail impact は **YES(reduction)**。no-mitigation profile は `118.8/h` と `99/100 per day`、Case A target は second-wave `0/h`, `0/d`。
- Gemini call increase は **NO**、token increase は **NO**、cache impact は **NO**。
- silent skip impact は **NO hidden path**。publish / review / hold / skip visibility contract を増やさず、internal-log-only outcome を作らない。

## 6. Implementation Order (Case A)

1. latest HEAD fresh `pytest`
   - `0 failures` または `3 pre-existing transient / +0 increase`
2. `299-QA` evidence re-check
   - `N=2 0/0` は確認済み、`N=3` close は未達のため朝時点 judgment を再確認
3. clean build
   - `/tmp/yoshi-deploy-head` clean export
4. HOLD-carry verify
   - `git log <prev>..HEAD --oneline`
   - `c14e269` は `290` live-inert(`ENABLE_WEAK_TITLE_RESCUE` absent)
5. rollback target baseline lock
   - `publish-notice:4be818d`
6. image rebuild + job update
   - env unchanged
   - flag OFF default
7. observe `1-2` trigger
   - 挙動 `100%` 不変
8. 条件 OK で flag ON
   - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
   - Case A = ledger seed mode
9. observe `1-2` trigger
   - old-candidate `sent=0`
   - normal path unchanged
10. `2026-05-02 09:00 JST` second-wave prevention check

### Test / observe gates

- unit/regression: latest HEAD `pytest` は `+0` regression が条件
- targeted: Case A scanner / persistence / post-gen / sender tests `7 cases`
- smoke: flag OFF `1-2` trigger で `100%` behavior parity
- mail checks: `real review` / `289` / error path / Team Shiny 不変
- rollback checks: env remove -> image revert -> ledger archive の 3-tier を即実行可能

## 7. 9/9 Alignment Lock

| item | final answer |
|---|---|
| old candidate pool cardinality estimate | **YES**: `~99` storm group / `103` backlog-only pool |
| expected first-send mail count | **YES**: Case A seed modeなら `~0`、seed なし first emit は `~99` |
| max mails/hour | **YES**: ceiling `30/h` 維持、Case A target は second-wave `0/h` |
| max mails/day | **YES**: ceiling `100/d` 維持、Case A target は second-wave `0/d` |
| stop condition | **YES**: section 9 に固定 |
| rollback command | **YES**: 3-tier command fixed |
| `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` currently OFF/absent | **YES** |
| persistent ledger behavior currently disabled | **YES** |
| normal review / `289` / error mail remain active | **YES** |

### Rollback command (3-tier)

1. env rollback

```bash
gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE
```

2. image rollback

```bash
gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4be818d
```

3. ledger archive

```bash
gsutil mv \
  gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json \
  gs://baseballsite-yoshilover-state/publish_notice/archive/<timestamp>.json
```

## 8. 18-Field Resolution

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
| Mail volume impact | **YES**(`99 -> 0` reduction target) |

### Net

- resolved: **18 / 18**
- unknown: **0**
- decision gate: **GO line fixed / final morning prompt becomes HOLD if any precondition remains `PARTIAL/NO`**

## 9. Stop Conditions

- real review(`【要確認】` / `【要review】`) emit 減少
- Team Shiny From 変化
- `289` emit 減少
- `errors > 0`
- silent skip 増(`POLICY §8` 違反)
- `cap=10` / `24h dedupe` 違反
- `MAIL_BUDGET 30/h・100/d` 違反
- `publish-notice` 全停止
- repeated old-candidate mail 再出現

## 10. Preconditions

All must be `YES` before the `GO` prompt.

| precondition | judgment | note |
|---|---|---|
| `298-Phase3` ROLLED_BACK 後 `24h` 安定 | **PARTIAL** | rollback 起点は `2026-05-01 13:55 JST`。`2026-05-02 06:00 JST` 時点は `16h` 経過、正確な `24h` close は `2026-05-02 13:55 JST` |
| `2026-05-01 17:00 JST production_health_observe` pass | **YES** | downstream ready packs / summary で pass 記録あり、`silent skip 0` 維持 |
| `299-QA` flaky/transient 整理 | **PARTIAL** | `N=2` green evidence は fixed、`N=3` close は未達で明朝 deferred |
| Codex fire budget reset | **PARTIAL** | `2026-05-01` は P1 exception で `22+` fire。`2026-05-02 00:00 JST` 後の reset 想定だが、この pack 単体では未証跡 |

## 11. User Reply

`GO` / `HOLD` / `REJECT`
