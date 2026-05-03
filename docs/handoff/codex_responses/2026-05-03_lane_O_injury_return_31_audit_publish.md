# 2026-05-03 Lane O injury/return hard-stop audit

作成: 2026-05-03 20:09 JST

## scope

- user request: Lane O live ops
- repo mutation: handoff doc only
- code / tests / config change: 0
- live publish result: **plan-only stop**
- reason for stop: local sandbox からの WP REST read が DNS 失敗したため、Step 3 live re-eval / publish は実行していない

## environment note

- GCS read-only access: OK
  - source snapshot: `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
  - downloaded to: `/tmp/lane_o_guarded_publish_history.jsonl`
- publish-notice queue read-only access: OK
  - source snapshot: `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
  - downloaded to: `/tmp/lane_o_publish_notice_queue.jsonl`
- WP REST read-only access from sandbox: NG
  - check time: 2026-05-03 19:57 JST
  - probe: `WPClient.get_post(63661)`
  - failure: `Failed to establish a new connection: [Errno -2] Name or service not known`

## snapshot note

- Lane M の `31件` は `2026-05-03T18:25:41.115990+09:00` 時点の latest-state を再現すると一致した
- 現在の authoritative latest-state は `2026-05-03T19:50:37.005018+09:00` 時点で **32件**
- 追加 1 件は `post_id=64392`
- 追加分 `64392` は current evidence では injury/return ではなく、A 候補数には影響しない

## Step 1. Lane M 31件 per-id table

| post_id | latest ts(JST, Lane M snapshot) | title | source_url | subtype | hold_reason | error detail | keyword hit | fan-important | real-death | bucket |
|---|---|---|---|---|---|---|---|---|---|---|
| 63841 | 2026-04-28T12:30:35.534155+09:00 | 巨人二軍スタメン 若手をどう並べたか | queue subject only | farm_lineup (doc inference) | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | none | no | no | C |
| 64058 | 2026-04-29T23:25:37.461461+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64129 | 2026-05-02T18:50:38.952494+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | none | unknown | unknown | C |
| 64131 | 2026-05-02T18:55:34.227542+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident,ranking_list_only,lineup_duplicate_excessive | none | unknown | unknown | C |
| 63661 | 2026-05-02T19:05:35.162375+09:00 | De、昇格・復帰でどこを見たいか | unreconstructed | unknown (242-E sample) | hard_stop_death_or_grave_incident | death_or_grave_incident | 復帰 | yes | no | A |
| 63517 | 2026-05-02T19:05:35.162375+09:00 | 下半身のコンディション不良で登録抹消へ… | unreconstructed | roster_notice? | hard_stop_death_or_grave_incident | death_or_grave_incident | 負傷,登録,抹消 | yes | no | A |
| 63482 | 2026-05-02T19:05:35.162375+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | none | unknown | unknown | C |
| 63468 | 2026-05-02T19:05:35.162375+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | none | unknown | unknown | C |
| 63385 | 2026-05-02T19:05:35.162375+09:00 | ベテラン、昇格・復帰でどこを見たいか | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | 昇格,復帰 | yes | no | A |
| 63197 | 2026-05-02T19:05:35.162375+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | none | unknown | unknown | C |
| 63175 | 2026-05-02T19:05:35.162375+09:00 | 巨人、田中俊太を支配下登録 | unreconstructed | fact_notice / roster_notice (doc 079) | hard_stop_death_or_grave_incident | death_or_grave_incident | 登録 | yes | no | A |
| 63689 | 2026-05-03T00:15:38.541110+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64070 | 2026-05-03T01:10:41.101062+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 63924 | 2026-05-03T03:15:39.887848+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 63135 | 2026-05-03T08:20:39.894312+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | none | unknown | unknown | C |
| 63093 | 2026-05-03T08:20:39.894312+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64318 | 2026-05-03T11:40:36.493466+09:00 | 投手が１軍に合流 | unreconstructed | 一軍合流 notice (log) | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | 1軍合流見込み | yes | no | C |
| 64264 | 2026-05-03T12:10:39.035340+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64321 | 2026-05-03T12:10:39.035340+09:00 | (登録) (抹消) ※再登録は13日以降 | unreconstructed | notice / 再登録 (log) | hard_stop_death_or_grave_incident | death_or_grave_incident | 登録,抹消 | yes | no | A |
| 63946 | 2026-05-03T12:25:39.330058+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64324 | 2026-05-03T12:25:39.330058+09:00 | ジャイアンツタウンスタジアムでの広島戦で 選手が実戦復帰。昨日同じく実戦復帰… | unreconstructed | injury_recovery_notice (log) | hard_stop_death_or_grave_incident | death_or_grave_incident | 実戦復帰,復帰 | yes | no | A |
| 64332 | 2026-05-03T13:05:39.198788+09:00 | 投手、2球を投じたところで異変を訴えて降板 | https://twitter.com/sanspo_giants/status/2050788652847137131 | farm_lineup (log) | hard_stop_death_or_grave_incident | death_or_grave_incident | 緊急降板,負傷 | yes | no | A |
| 63950 | 2026-05-03T14:10:37.184961+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident,lineup_duplicate_excessive | none | unknown | unknown | C |
| 64096 | 2026-05-03T14:25:40.315287+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 63959 | 2026-05-03T14:35:39.986483+09:00 | 【5/3予告先発】 ー （甲子園、14:00) 巨人:(2勝2敗、防御率1.90) 阪神:(2勝1敗、防御率5.00) | https://twitter.com/sanspo_giants/status/2050430325315264981 | pregame / probable_starter | hard_stop_death_or_grave_incident | death_or_grave_incident | none | no | no | C |
| 64209 | 2026-05-03T16:20:36.887468+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64208 | 2026-05-03T16:20:36.887468+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 63973 | 2026-05-03T16:35:37.326877+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 63972 | 2026-05-03T16:35:37.326877+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64097 | 2026-05-03T16:35:37.326877+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |
| 64012 | 2026-05-03T18:05:38.916436+09:00 | unreconstructed in sandbox evidence | unreconstructed | unknown | hard_stop_death_or_grave_incident | death_or_grave_incident | none | unknown | unknown | C |

### post-Lane-M delta

| post_id | latest ts(JST, current snapshot) | title | source_url | subtype | hold_reason | error detail | keyword hit | fan-important | real-death | bucket |
|---|---|---|---|---|---|---|---|---|---|---|
| 64392 | 2026-05-03T18:50:39.173956+09:00 | 選手「中野さんを切っていれば流れは変わった」 関連発言 | unreconstructed | player / social (log) | hard_stop_death_or_grave_incident | death_or_grave_incident | none | no | no | C |

## Step 2. 3 区分 list

Lane M 31 snapshot (`2026-05-03 18:25:41 JST`):

- A fan-important publish candidates: **7**
  - `63175` 巨人、田中俊太を支配下登録
  - `63385` ベテラン、昇格・復帰でどこを見たいか
  - `63517` 下半身のコンディション不良で登録抹消へ…
  - `63661` De、昇格・復帰でどこを見たいか
  - `64321` (登録) (抹消) ※再登録は13日以降
  - `64324` ジャイアンツタウンスタジアムでの広島戦で 選手が実戦復帰。昨日同じく実戦復帰…
  - `64332` 投手、2球を投じたところで異変を訴えて降板
- B real death-grave HOLD: **0 confirmed**
- C ambiguous / not fan-important on current evidence: **24**

Current latest-state snapshot (`2026-05-03 19:50:37 JST`):

- A: **7**
- B: **0**
- C: **25**
  - delta = `64392`

## Step 3. 区分 A narrow re-eval + publish

結果:

- **plan-only stop**
- live re-eval / publish は未実行

stop reason:

- sandbox から WP REST read が失敗したため、local `run_guarded_publish_evaluator` / `run_guarded_publish --live` の実行は安全に完遂できない
- stop condition `sandbox WP REST 不通 -> Step 3 plan only` に一致

A candidates for live shell:

| post_id | current latest refused ts(JST) | extra gate in error? | should delete 24h refused row before rerun? | rerun expectation |
|---|---|---|---|---|
| 63175 | 2026-05-03T19:05:39.742769+09:00 | no | yes | publish candidate |
| 63385 | 2026-05-03T19:05:39.742769+09:00 | no | yes | publish candidate |
| 63517 | 2026-05-03T19:05:39.742769+09:00 | no | yes | publish candidate |
| 63661 | 2026-05-03T19:05:39.742769+09:00 | no | yes | publish candidate |
| 64321 | 2026-05-03T12:10:39.035340+09:00 | no | yes | publish candidate |
| 64324 | 2026-05-03T12:25:39.330058+09:00 | no | yes | publish candidate |
| 64332 | 2026-05-03T13:05:39.198788+09:00 | no | yes | publish candidate |

non-A examples that must stay out of the narrow re-eval set:

- `63841`, `63135`, `64318`, `63950`, `64129`, `64131`, `63482`, `63468`, `63197`
  - death hold co-occurs with `lineup_duplicate_excessive` and/or `ranking_list_only`
- `63959`
  - recovered title is pregame/probable-starter, not injury/return
- `64392`
  - recovered title is player comment, not injury/return

prepared backup artifact:

- backup path: `/tmp/lane_O_backup_20260503T200906/dedupe_pre.jsonl`
- contents: exactly the **7 refused rows within the active 24h dedupe window** for the A set
- dedupe cutoff used: `2026-05-02T19:50:37.005018+09:00`

live shell procedure:

1. Refresh a full evaluator pack:
   ```bash
   python3 -m src.tools.run_guarded_publish_evaluator \
     --window-hours 999999 \
     --max-pool 500 \
     --exclude-published-today \
     --format json \
     --output /tmp/lane_o_full_eval.json
   ```
2. Back up the live rows to remove:
   ```bash
   mkdir -p /tmp/lane_O_backup_$(date +%Y%m%dT%H%M%S)
   cp /tmp/lane_O_backup_20260503T200906/dedupe_pre.jsonl \
      /tmp/lane_O_backup_$(date +%Y%m%dT%H%M%S)/dedupe_pre.jsonl
   ```
3. Delete only the matching 24h `refused` rows for the 7 A IDs from live `guarded_publish_history.jsonl`
4. Filter the full evaluator pack to one post at a time and rerun serially:
   ```bash
   python3 - <<'PY'
   import json
   TARGET=63175
   src=json.load(open('/tmp/lane_o_full_eval.json', encoding='utf-8'))
   out={}
   for key in ('green','yellow','red','review'):
       out[key]=[row for row in src.get(key, []) if int(row.get('post_id') or 0)==TARGET]
   open(f'/tmp/lane_o_{TARGET}.json','w',encoding='utf-8').write(json.dumps(out, ensure_ascii=False))
   PY

   python3 -m src.tools.run_guarded_publish \
     --input-from /tmp/lane_o_63175.json \
     --max-burst 1 \
     --live \
     --daily-cap-allow \
     --format json
   ```
5. Repeat step 4 for:
   - `63385`
   - `63517`
   - `63661`
   - `64321`
   - `64324`
   - `64332`
6. After each live publish:
   - confirm the post became `publish`
   - confirm publish-notice queue/history advanced
   - confirm mail send within 5-10 min in logging

## Step 4. current outcome / rollback

actual outcome in this sandbox run:

- publish count: `0`
- draft count unchanged by this run: `all`
- unreconstructable metadata rows: `24` in Lane M snapshot + current delta `64392`
- mail delta actual: `0`

public URLs:

- none emitted in this sandbox run

publish-notice mail timestamps:

- none emitted in this sandbox run

rollback procedure for the future live shell:

1. If only history rows were deleted and no publish happened:
   - append back the saved rows from `/tmp/lane_O_backup_20260503T200906/dedupe_pre.jsonl`
2. If a post was published by mistake:
   - set the post back to `draft` via WP admin or WP REST `update_post_status(post_id, "draft")`
   - restore the deleted dedupe rows from `dedupe_pre.jsonl`
   - do not touch unrelated history rows, queue files, or publish-notice cursor

per-id rollback note for planned A set:

- `63175`, `63385`, `63517`, `63661`, `64321`, `64324`, `64332`
  - restore the single deleted 24h refused row from `dedupe_pre.jsonl`
  - if publish already happened, revert post status to `draft` before re-appending the row

## remaining risk

- `24` of the Lane M 31 rows still lack reconstructed title/source evidence in this sandbox, so they remain bucket `C`
- current latest-state is already `32`, not `31`; any future live apply must account for `64392`
- `64318` looks fan-important by title, but the same row also carries `lineup_duplicate_excessive`, so it is not a clean A candidate
- since WP REST is unreachable here, this turn cannot verify post status transitions, publish-notice queue mutation, or mail send timestamps

## next user action

- use an authenticated/live shell with WP REST reachability
- apply the 7-row narrow dedupe delete using the backup above
- rerun the 7 A candidates one by one with `run_guarded_publish`
- verify publish-notice mail after each publish before widening beyond the A set
