# 2026-05-03 Lane CC farm / OB publish-forward

作成: 2026-05-04 00:00 JST

## mode

- live ops request received
- scope intent: 三軍 / 二軍 / ファーム / 育成 / 支配下 / 故障明け / 実戦復帰 / 引退後 / OB 系 stuck draft の publish-forward
- protected no-touch honored:
  - already-published set: `64272 / 64396 / 64386 / 64394 / 64402 / 64405 / 64294 / 63385 / 63661`
  - Lane BB protected set left untouched: `64356 / 64361 / 64374 / 64378 / 64382`
  - Lane Z / ZZ confirmed stop set left untouched: `64328 / 64335 / 64331 / 64352 / 64390`
- code / tests / config edits: `0`
- live history delete / upload / guarded-publish manual execute: `0`

## Step 1 stuck draft scan

Read-only sources used:

- `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
- `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`

Local read-only snapshots:

- `/tmp/lane_cc_scan/guarded_publish_history.jsonl`
- `/tmp/lane_cc_scan/publish_notice_queue.jsonl`

Scan rule:

- latest entry per `post_id`
- latest status in `{refused, skipped}`
- priority window: latest `48h`
- then narrowed by Lane CC keyword family

Scan result:

- raw Lane CC keyword-hit stuck rows after protected-ID exclusion: `16`
- stale backlog / already-published-or-notified rows among those `16`: `13`
- current recent unresolved rows needing 4-stage filter: `3`
  - `64250`
  - `63845`
  - `64368`

## Step 2 4-stage filter

### `64250`

- A. Giants related: yes
  - notice subject: `【要review】RT 【公式】ジャイアンツタウンスタジアム: 【完売御礼🎊】 開催のファーム…`
- B. Lane CC keyword hit: yes
  - `ファーム`
- C. stop classification: yes
  - latest guarded status: `refused`
  - latest hold: `review_date_fact_mismatch_review`
- D. publish candidate: no

### `63845`

- A. Giants related: yes
  - notice subject: `【要確認】巨人二軍 3-6 結果のポイント`
- B. Lane CC keyword hit: yes
  - `二軍`
- C. stop classification: yes
  - latest guarded status: `refused`
  - latest hold: `hard_stop_farm_result_placeholder_body`
- D. publish candidate: no

### `64368`

- A. Giants related: yes
  - guarded subtype observation in prior audit: `farm`
- B. Lane CC keyword hit: yes
  - `復帰`
  - `実戦復帰`
- Current stuck row:
  - latest guarded status: `refused`
  - latest hold: `review_farm_result_required_facts_weak_review`
  - notice subject: `【要review】が2軍戦で実戦復帰＆2安打「問題なくプレーできた。いつ呼ばれてもいい状態」`
- C. duplicate-risk stop: yes
  - same guarded batch timestamp already contains sibling `64366` as `sent`
  - `64366` publish evidence:
    - guarded history: `2026-05-03T15:50:37.938431+09:00` `status=sent`
    - publish-notice queue: `post_id=64366`
    - queued subject: `【公開済】復帰戦で泉口友汰がマルチ安打「いつ呼ばれてもいい状態ではある」脳しんとう特例…`
    - notify timestamp: `2026-05-03T15:55:58.603492+09:00`
    - publish_time_iso: `2026-05-03T15:50:41+09:00`
- Conclusion:
  - `64368` is not safe to publish-forward tonight
  - forcing it would risk duplicate / malformed-partial twin publish against already-published `64366`
- D. publish candidate: no

## D candidates

- total: `0`
- per-id list: none

Reason:

- `64250` stopped by date-fact mismatch
- `63845` stopped by placeholder body
- `64368` stopped by same-event already-published sibling overlap (`64366`)

## Step 3 per-id outcome

No live mutation was executed.

- backup: none created
- narrow delete: none
- guarded-publish manual execution: none

## Step 4 public URL / mail verify

New publish created by Lane CC:

- none

Historical read-only publish evidence observed during scan only:

- `https://yoshilover.com/64366`
  - publish-notice timestamp: `2026-05-03T15:55:58.603492+09:00`
  - this was pre-existing evidence, not a Lane CC mutation

## Step 5 record

- D candidate total: `0`
- mail delta actual caused by Lane CC: `0`
- backup path: none created
- per-id rollback: not applicable because no row was deleted and no publish was triggered

## rollback

No-op lane. Rollback not required.

## next user action

1. Keep Lane BB protected set separate unless that lane is explicitly released back into CC scope.
2. If `64368` still matters, do not force-publish from guarded history alone. First prove WP-side current state and whether `64366` and `64368` are true duplicates or a malformed partial-twin pair.
3. Otherwise wait for the next Lane CC-class stuck row that clears all four stop conditions.
