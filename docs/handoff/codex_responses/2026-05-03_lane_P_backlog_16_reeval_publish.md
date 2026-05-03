# 2026-05-03 Lane P backlog_only 16 newer batch re-eval + publish

作成: 2026-05-03 JST

## mode

- request type: live ops
- actual execution: Step 1 read-only + Step 2 reclassification complete
- Step 3 status: not executed
- mutation count: `0`
- touched live systems: none

Reason Step 3 did not run:

1. `publish 候補 bucket A` が 0 件になった
2. current sandbox から WordPress REST に到達できなかった

This means:

- `24h dedupe` row deletion: `0`
- backup creation: `0`
- guarded publish live re-eval: `0`
- WordPress publish write: `0`
- new publish-notice mail: `0`

## authoritative local inputs

- latest guarded history mirror: `/tmp/guarded_publish_history_20260503_live.jsonl`
- latest queue mirror: `/tmp/publish_notice_queue_20260503_audit.jsonl`
- supplemental queue mirror for `64212 / 64214 / 64218`: `/tmp/lane_o_publish_notice_queue.jsonl`
- evaluator snapshot: `/tmp/good_draft_rescue_eval_20260503.json`
- Cloud Logging local mirror: `/tmp/gcloud-config-dkatcxfx/gcloud/logs/2026.05.03/`

Important date clarification:

- Many of the queue timestamps are from **2026-05-03 JST**, but the article content and `publish_time_iso` for these 10 posts are mostly **2026-05-01 JST**.
- The reclassification below uses the content age, not only the latest queue timestamp.

## Step 1: per-id recheck

Broad D-6 labels like `general` / `notice` were rescue-lane groupings. The current evaluator snapshot narrows them further as shown below.

| post_id | latest guarded entry | title | current subtype | source_url / source family | class for this turn | duplicate signal | outcome bucket |
|---|---|---|---|---|---|---|---|
| `64167` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=created_at` | `巨人スタメン 岡本和真 第3打席は三ゴロ 13連戦7戦目も4戦連` | `lineup` | exact URL not recoverable from local mirrors; cleanup heading indicates `スポニチ` article family | old lineup / in-game carryover | no guarded duplicate row; no `duplicate_of_post_id` | 別扱い |
| `64169` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=created_at` | `巨人スタメン 岡本和真 第4打席は左飛 13連戦7戦目も4戦連続` | `lineup` | exact URL not recoverable from local mirrors; cleanup heading indicates `スポニチ` article family | old lineup / in-game carryover | no guarded duplicate row; no `duplicate_of_post_id` | 別扱い |
| `64177` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=created_at` | `【三軍】巨人 vs 全足利クラブ HARD OFF ECOスタジアム新潟🏟…` | `farm` | exact URL not recoverable; local mirrors show official/social-style farm-game title and upstream `history_duplicate` sample | old farm game / in-game context | no guarded duplicate row; upstream `history_duplicate` sample exists for same title family | 別扱い |
| `64183` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=created_at` | `巨人スタメン 岡本和真 3戦連続V打なるか 13連戦7戦目ツイン` | `lineup` | exact URL not recoverable from local mirrors; cleanup heading indicates `スポニチ` article family | old lineup / pregame-lineup carryover | no guarded duplicate row; no `duplicate_of_post_id` | 別扱い |
| `64198` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=source_date` | `新イニング間イベント 「RINOKA's BEEEATS!」 を開催🎵 「R…` | `default` (broad family: official event/front) | recovered exact social anchor: `https://twitter.com/TokyoGiants/status/2050084227643814174` | official event/front item, but not new | no guarded duplicate row; upstream `history_duplicate` sample exists for this title family | 別扱い |
| `64201` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=source_date` | `RT 【公式】ジャイアンツタウンスタジアム: ／ 🆕カスタムグッズに新商品が…` | `off_field` | exact URL not recoverable; source family is official `ジャイアンツタウンスタジアム` social/RT | off-field / front item, old | no guarded duplicate row; upstream `history_duplicate` sample exists for same official-social family | 別扱い |
| `64212` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=source_date` | `巨人が6人入れ替え 阪神は西勇輝を抹消し及川雅貴を登録 西武はネビンを登録…` | `roster` | exact URL not recoverable from local mirrors; source family is roster/news notice | roster move, but now stale | no guarded duplicate row; no `duplicate_of_post_id` | 別扱い |
| `64214` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=source_date` | `阪神戦を前に大量６選手を入れ替え 高梨雄平、中山礼都、若林楽人を登録 北浦竜…` | `roster` | exact URL not recoverable from local mirrors; source family is Giants-specific roster/news notice | roster move, but now stale | no guarded duplicate row; no `duplicate_of_post_id` | 別扱い |
| `64218` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=source_date` | `（１日）巨人・中山礼都、西武・ネビンを登録 巨人・皆川岳飛、西武・児玉亮涼ら…` | `roster` | exact URL not recoverable from local mirrors; source family is roster transaction notice | 5/1 roster notice, explicitly old | no guarded duplicate row; no `duplicate_of_post_id` | 別扱い |
| `64242` | `2026-05-03T18:25:41+09:00` `skipped/backlog_only` `freshness_source=created_at` | `【🔥📷】 選手、1軍復帰戦で3番スタメン起用に応えるマルチヒット（撮影・中井…` | `lineup` | exact URL not recoverable; source family is photo/game article about a return game | old lineup-like return article | guarded latest row has no duplicate target, but publish-notice mirror logged `REVIEW_RECENT_DUPLICATE` suppression | 別扱い |

## Step 2: publish bucket extraction

User policy for this turn:

- candidate: newish `roster / injury-return / manager-comment / bench-comment / pregame`
- separate handling: old lineup速報, in-game-only info, `48h+` stale roster

### per-id age check against exact dates

| post_id | content anchor | age result in local evaluator | decision |
|---|---|---|---|
| `64167` | `publish_time_iso=2026-05-01T12:40:33+09:00` | lineup expiry gate; evaluator `age_hours=53.11` | separate |
| `64169` | `publish_time_iso=2026-05-01T12:40:44+09:00` | lineup expiry gate; evaluator `age_hours=53.10` | separate |
| `64177` | `publish_time_iso=2026-05-01T13:00:22+09:00` | stale farm-game context; evaluator `age_hours=52.78` | separate |
| `64183` | `publish_time_iso=2026-05-01T13:30:25+09:00` | lineup expiry gate; evaluator `age_hours=52.27` | separate |
| `64198` | `publish_time_iso=2026-05-01T14:30:34+09:00` | official event item; evaluator `content_date=2026-05-01`, `age_hours=51.27` | separate |
| `64201` | `publish_time_iso=2026-05-01T14:40:32+09:00` | off-field item; evaluator `content_date=2026-04-30`, `age_hours=89.78` | separate |
| `64212` | `publish_time_iso=2026-05-01T16:20:31+09:00` | roster, but evaluator `content_date=2026-05-01`, `age_hours=49.44` | separate |
| `64214` | `publish_time_iso=2026-05-01T16:30:32+09:00` | roster, but evaluator `content_date=2026-05-01`, `age_hours=49.27` | separate |
| `64218` | `publish_time_iso=2026-05-01T16:40:26+09:00` | roster, title itself says `（１日）`; evaluator `age_hours=49.11` | separate |
| `64242` | `publish_time_iso=2026-05-01T22:50:20+09:00` | lineup-like return article; evaluator `age_hours=42.94` + stale/duplicate-like mail suppression | separate |

### bucket result

- `publish 候補 A`: `0`
- `別扱い`: `10`

Why `64212 / 64214` were **not** promoted despite the earlier roster-return intuition:

- by the time of this re-eval, both are anchored to **2026-05-01** content
- the local evaluator already classifies them as `stale_for_breaking_board`
- user policy for this turn explicitly excludes `48h+ stale roster`

## Step 3: narrow re-eval + publish

Not executed.

### hard stop 1: no eligible bucket A posts

Because bucket A is empty, the Lane O-style mutation sequence must not start:

- no `24h dedupe` narrow deletion
- no `/tmp/lane_P_backup_<ts>/dedupe_pre.jsonl`
- no one-by-one live guarded re-eval
- no publish writes

Starting the mutation sequence with zero candidates would violate the narrow-scope contract.

### hard stop 2: current sandbox cannot reach WordPress REST

Direct probe from this session:

```text
{'ok': False, 'error_type': 'ConnectionError', 'error': 'HTTPSConnectionPool(host='yoshilover.com', port=443): Max retries exceeded with url: /wp-json/wp/v2/posts/64198 (Caused by NameResolutionError(... Failed to resolve ...))'}
```

Interpretation:

- even if bucket A had been non-empty, this sandbox cannot safely perform the live preflight / publish / verify path
- per the turn contract, that means `Step 3 plan only`

## Step 4: per-id outcome

No new publish happened in this execution.

| post_id | kept as draft / non-publishable in this turn because | latest notice mirror timestamp |
|---|---|---|
| `64167` | old lineup, in-game carryover, expired by `2026-05-03` | `2026-05-03T13:01:02.026768+09:00` suppressed |
| `64169` | old lineup, in-game carryover, expired by `2026-05-03` | `2026-05-03T13:01:02.029091+09:00` suppressed |
| `64177` | old farm game context, not a newish roster/manager/pregame candidate | `2026-05-03T13:06:06.142118+09:00` suppressed |
| `64183` | old lineup/pregame carryover, expired by `2026-05-03` | `2026-05-03T13:36:00.163748+09:00` suppressed |
| `64198` | official event/front item from `2026-05-01`, now stale | `2026-05-03T14:41:11.566480+09:00` suppressed |
| `64201` | off-field/front item with `content_date=2026-04-30`, clearly stale | `2026-05-03T15:01:10.074155+09:00` suppressed |
| `64212` | roster notice but `48h+` stale by policy | `2026-05-03T16:41:05.116369+09:00` suppressed |
| `64214` | roster notice but `48h+` stale by policy | `2026-05-03T16:41:05.128561+09:00` suppressed |
| `64218` | title explicitly points to `2026-05-01`; stale roster notice | `2026-05-03T16:56:02.853386+09:00` suppressed |
| `64242` | old lineup-like return article plus duplicate-like mail suppression signal | `2026-05-02T22:56:00.766991+09:00` suppressed |

### publish result

- newly published posts: none
- new public URLs from this execution: none
- new mail sent by this execution: none

## backup path

- created backup path: none
- reason: Step 3 never started, so no dedupe-row deletion was allowed

## rollback

This execution is a no-op, so rollback is also a no-op.

If a future live-capable rerun ever reclassifies a truly new candidate into bucket A and performs the Lane O mutation sequence, the rollback contract should be:

1. restore the deleted dedupe rows from that run's `/tmp/lane_P_backup_<ts>/dedupe_pre.jsonl`
2. revert any newly published post from `publish` back to `draft` in WordPress
3. record restore timestamp, restored row count, and reverted post IDs in a follow-up ops note

## final read

- The earlier intuition that `64212 / 64214` might still be publishable does **not** survive exact-date recheck on `2026-05-03 JST`.
- All 10 current targets are separate-handling items under the user policy now in force.
- Lane P therefore ends as `read-only only / publish 0 / rollback 0`.
