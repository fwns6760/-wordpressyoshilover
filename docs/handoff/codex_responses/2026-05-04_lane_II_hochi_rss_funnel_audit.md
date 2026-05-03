# 2026-05-04 Lane II hochi RSS funnel audit

## Scope

- target: `hochi_giants` RSS X funnel
- window: latest `24h`
- mode: `read-only audit + publish-forward decision`
- mutation result in this session: `none`

## Data Sources

- Cloud Logging: `resource.labels.service_name="yoshilover-fetcher"` latest `24h`
- Cloud Logging: targeted windows for `[WP] 記事draft`, `[下書き維持]`, `media_xpost_embedded`
- GCS: `gs://yoshilover-history/rss_history.json`
- GCS: `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
- GCS: `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
- probe execution: `guarded-publish-lane-zz-67lnl` (`MODE=probe`, read-only)
- prior related records used only where the current ledgers conflicted or were incomplete:
  - [2026-05-04_lane_HH_64421_publish_evaluation.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-04_lane_HH_64421_publish_evaluation.md)
  - [2026-05-04_lane_DD_publish_mail_suppression_audit.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-04_lane_DD_publish_mail_suppression_audit.md)
  - [2026-05-04_lane_GG_bug003_publish_revert_fix.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-04_lane_GG_bug003_publish_revert_fix.md)

## Inference Rules

- `social_too_weak (inferred)`:
  - latest run had `SOURCE` then `CLASSIFY_OBSERVE`, but no `HIT` and no later per-id event in the same `social_news` scan.
- `history_duplicate (latest rescan inferred)`:
  - URL already existed in `rss_history.json`, and the latest run showed `SOURCE` only with no downstream per-id event.
- `64416`:
  - durable guarded history says `refused / review_date_fact_mismatch_review`.
  - later publish-notice evidence is inconsistent with repo-visible publish logs, so Lane II treats it as `unsafe / not a publish-forward candidate`.

## Step 1: latest 20 hochi RSS entries

| # | rss_id | source_url | fetched_at JST | title |
| --- | --- | --- | --- | --- |
| 1 | `2050872338510704861` | `https://twitter.com/hochi_giants/status/2050872338510704861` | `2026-05-04 07:55:07` | `RT 小林泰斗📷スポーツ報知: 5/3 📣` |
| 2 | `2050872467724669124` | `https://twitter.com/hochi_giants/status/2050872467724669124` | `2026-05-04 07:55:07` | `【番記者Ｇ戦記】巨人バッテリーが大ピンチで佐藤輝明と真っ向勝負 見逃し三振の完璧配球 悔しい敗戦を次への糧に` |
| 3 | `2050875183099953299` | `https://twitter.com/hochi_giants/status/2050875183099953299` | `2026-05-04 07:55:07` | `【番記者Ｇ戦記】巨人打線が苦戦した阪神・才木の変身投球 ... 橋上コーチ「イメージを変えるような投...」` |
| 4 | `2050877658838220900` | `https://twitter.com/hochi_giants/status/2050877658838220900` | `2026-05-04 07:55:07` | `【巨人】西舘勇陽がパワーアップ ２か月ぶり復帰で快投「投げられたことがまず良かった」ＭＡＸ１５１キロ` |
| 5 | `2050885170111074767` | `https://twitter.com/hochi_giants/status/2050885170111074767` | `2026-05-04 07:55:07` | `【巨人】中田歩夢がサヨナラ打！ ２安打２打点で「最高です！」...` |
| 6 | `2050885171277099230` | `https://twitter.com/hochi_giants/status/2050885171277099230` | `2026-05-04 07:55:07` | `【巨人】松浦慶斗が初回から緊急リリーフ 大慌てで準備した舞台裏は… 先発・山崎伊織が２球で交代` |
| 7 | `2050891541141483536` | `https://twitter.com/hochi_giants/status/2050891541141483536` | `2026-05-04 07:55:07` | `【巨人】ドラ２・田和廉が球団新を更新する１２試合連続無失点 ...` |
| 8 | `2050892644889326062` | `https://twitter.com/hochi_giants/status/2050892644889326062` | `2026-05-04 07:55:07` | `【巨人】井上温大、力投８Ｋも今季３敗目 杉内投手チーフコーチ「球自体は本当によかった。それは継続してもらえたら」` |
| 9 | `2050908686688899531` | `https://twitter.com/hochi_giants/status/2050908686688899531` | `2026-05-04 07:55:07` | `RT 報知プロ野球チャンネル: 【動画】昨年とは別人！？ 西川歩が今季２軍初昇格` |
| 10 | `2050938460278788254` | `https://twitter.com/hochi_giants/status/2050938460278788254` | `2026-05-04 07:55:07` | `２戦連発の岡本和真を支える元日ハム戦士 日米を知る加藤豪将氏が果たす役割 野球談` |
| 11 | `2051029788702187840` | `https://twitter.com/hochi_giants/status/2051029788702187840` | `2026-05-04 07:55:07` | `巨人打線が陥った天敵右腕の“ギャップ” ４安打１１奪三振０封負けの要因…大勢＆泉口きょう合流で反撃へ` |
| 12 | `2051031133790380168` | `https://twitter.com/hochi_giants/status/2051031133790380168` | `2026-05-04 07:55:07` | `あえて巨人戦はチェックせず 泉口友汰が明かした負傷離脱中の心境` |
| 13 | `2051033632886653412` | `https://twitter.com/hochi_giants/status/2051033632886653412` | `2026-05-04 07:55:07` | `巨人・井上温大、先制打許した虎の最強打者から“リベンジＫ”…雨の甲子園で６回８Ｋ` |
| 14 | `2051033634635649152` | `https://twitter.com/hochi_giants/status/2051033634635649152` | `2026-05-04 07:55:07` | `【巨人記録室】才木に対虎投ワースト８連敗 巨人から移籍のレジェンドら通算４人目の屈辱` |
| 15 | `2051034863562637654` | `https://twitter.com/hochi_giants/status/2051034863562637654` | `2026-05-04 07:55:07` | `巨人・井上温大の１球で光が見えた今後の佐藤輝明対策…金村義明氏「才木を上回るほど...」` |
| 16 | `2051036146163929091` | `https://twitter.com/hochi_giants/status/2051036146163929091` | `2026-05-04 07:55:07` | `巨人・山崎伊織、復帰戦でまさか わずか２球で緊急降板 右肩違和感…詳細は「僕もまだ分からない」` |
| 17 | `2051037501184167955` | `https://twitter.com/hochi_giants/status/2051037501184167955` | `2026-05-04 07:55:07` | `巨人・戸郷翔征「遅くなりましたけど」今季初登板 「ゼロにこだわりたい」４日ヤクルト戦で復活勝利誓う` |
| 18 | `2051067520736702585` | `https://twitter.com/hochi_giants/status/2051067520736702585` | `2026-05-04 07:55:07` | `RT スポーツ報知 レイアウト担当: 5/4付 選手 投手 きょう1軍合流！！！ さぁヤクルト3連戦 ベスト布陣秒読みで仕切り直し...` |
| 19 | `2051067937851891869` | `https://twitter.com/hochi_giants/status/2051067937851891869` | `2026-05-04 07:55:07` | `「菅野智之さん 安否ヨシッ！」元巨人・宮国椋丞さんがデンバーへ遠征応援 小林誠司` |
| 20 | `2051068170069533177` | `https://twitter.com/hochi_giants/status/2051068170069533177` | `2026-05-04 07:55:07` | `岡本和真が圧巻３戦連発９号２ラン 日米通じて初の２番で９回に意地のアーチで４２・...` |

## Step 2: per-id funnel

| rss_id | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| `2050872338510704861` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2050872467724669124` | passed | passed | blocked: `post_gen_validate` / `postgame_strict_review` | not created | n/a |
| `2050875183099953299` | passed | passed; latest rescan=`history_duplicate` inferred | passed (earlier run) | passed: `post_id=64394` draft `2026-05-03 09:55:46 JST` | passed: `sent` `2026-05-03 19:34:16 JST` |
| `2050877658838220900` | passed | passed; latest rescan=`history_duplicate` inferred | passed (earlier run) | passed: `post_id=64396` draft `2026-05-03 10:00:50 JST` | passed: `sent` `2026-05-03 19:05:39 JST` |
| `2050885170111074767` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2050885171277099230` | passed | passed | blocked: `pregame_started` | not created | n/a |
| `2050891541141483536` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2050892644889326062` | passed | passed; latest rescan=`history_duplicate` inferred | passed (earlier run) | passed: `post_id=64405` draft `2026-05-03 11:02:33 JST` | passed: `sent` `2026-05-03 20:05:39 JST` |
| `2050908686688899531` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2050938460278788254` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2051029788702187840` | passed | passed; latest rescan=`history_duplicate` inferred | passed (earlier run) | passed: `post_id=64416` draft `2026-05-04 05:10:40 JST` | blocked: `review_date_fact_mismatch_review` (`guarded_publish_history` durable row); later notify evidence conflicted, so not treated as safe publish |
| `2051031133790380168` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2051033632886653412` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2051033634635649152` | passed | passed; latest rescan=`history_duplicate` inferred | passed (earlier run) | passed: `post_id=64418` draft `2026-05-04 05:20:39 JST` | passed: `sent` `2026-05-04 05:25:36 JST` |
| `2051034863562637654` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2051036146163929091` | passed | passed; latest rescan=`history_duplicate` inferred | passed (earlier run) | passed: `post_id=64421` draft `2026-05-04 05:30:40 JST` | blocked: `hard_stop_lineup_duplicate_excessive` |
| `2051037501184167955` | passed | passed | blocked: `post_gen_validate` / `postgame_strict_review` | not created | n/a |
| `2051067520736702585` | passed | passed; latest rescan=`history_duplicate` inferred | passed (earlier run) | passed: `post_id=64424` draft `2026-05-04 07:35:41 JST` | blocked: `review_date_fact_mismatch_review` |
| `2051067937851891869` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |
| `2051068170069533177` | passed | passed | blocked: `social_too_weak` inferred | not created | n/a |

## Step 3: blocked reason summary

### A -> B

| reason | count | ids |
| --- | --- | --- |
| `history_duplicate` latest rescan inferred | `7` | `2050875183099953299`, `2050877658838220900`, `2050892644889326062`, `2051029788702187840`, `2051033634635649152`, `2051036146163929091`, `2051067520736702585` |
| `not_giants_related` | `0` | `-` |

### B -> C

| reason | count | ids |
| --- | --- | --- |
| `social_too_weak` inferred | `10` | `2050872338510704861`, `2050885170111074767`, `2050891541141483536`, `2050908686688899531`, `2050938460278788254`, `2051031133790380168`, `2051033632886653412`, `2051034863562637654`, `2051067937851891869`, `2051068170069533177` |
| `post_gen_validate` / `postgame_strict_review` | `2` | `2050872467724669124`, `2051037501184167955` |
| `pregame_started` | `1` | `2050885171277099230` |

### C -> D

| reason | count | ids |
| --- | --- | --- |
| draft created | `7` | `2050875183099953299`, `2050877658838220900`, `2050892644889326062`, `2051029788702187840`, `2051033634635649152`, `2051036146163929091`, `2051067520736702585` |
| draft creation fail | `0` | `-` |

### D -> E

| reason | count | ids |
| --- | --- | --- |
| `sent` | `4` | `64394`, `64396`, `64405`, `64418` |
| `review_date_fact_mismatch_review` | `2` | `64416`, `64424` |
| `hard_stop_lineup_duplicate_excessive` | `1` | `64421` |

## Step 4: publish candidates

- publish-forward candidate count: `0`
- reason:
  - `64394 / 64396 / 64405 / 64418` are already `sent`
  - `64416` is blocked by fact/date review and has conflicting downstream evidence
  - `64421` is a real duplicate-family hard stop
  - `64424` is blocked by date-fact review
  - all other RSS entries never reached draft creation, so Lane ZZ narrow delete + rerun is not applicable without broader mutation

## Step 5-6: outcome and verify

- live publish-forward executed in this session: `NO`
- backup create: `NO`
- refused-row delete: `NO`
- `run_guarded_publish --live`: `NO`
- WordPress mutation: `NO`
- mail side effect from this session: `NO`

### already-published rows

| rss_id | post_id | guarded-publish outcome | public URL | publish-notice mail timestamps JST | backup path |
| --- | --- | --- | --- | --- | --- |
| `2050875183099953299` | `64394` | `sent` at `2026-05-03 19:34:16` | `https://yoshilover.com/64394` | `2026-05-03 19:36:31.963` and `19:37:39.164` | `/tmp/pub004d/cleanup_backup/64394_20260503T103416.json` |
| `2050877658838220900` | `64396` | `sent` at `2026-05-03 19:05:39` | `https://yoshilover.com/64396` | `2026-05-03 19:11:09.067` | `/tmp/pub004d/cleanup_backup/64396_20260503T100539.json` |
| `2050892644889326062` | `64405` | `sent` at `2026-05-03 20:05:39` | `https://yoshilover.com/64405` | `2026-05-03 20:11:02.087` | `/tmp/pub004d/cleanup_backup/64405_20260503T110539.json` |
| `2051033634635649152` | `64418` | `sent` at `2026-05-04 05:25:36` | `https://yoshilover.com/64418` | `2026-05-04 05:31:06.096` | `/tmp/pub004d/cleanup_backup/64418_20260503T202536.json` |

### held rows

| rss_id | post_id | current terminal state | public URL verify | mail evidence |
| --- | --- | --- | --- | --- |
| `2051029788702187840` | `64416` | `refused / review_date_fact_mismatch_review` in durable guarded history; later notify evidence conflicted | not treated as verified public in Lane II | `2026-05-04 05:21:07.430` `suppressed / BACKLOG_SUMMARY_ONLY`; later replay-side mail exists in separate lane docs |
| `2051036146163929091` | `64421` | `refused / hard_stop_lineup_duplicate_excessive` | none; [lane_HH_64421_publish_evaluation](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-04_lane_HH_64421_publish_evaluation.md) concluded `https://yoshilover.com/64421` is not public | none |
| `2051067520736702585` | `64424` | `refused / review_date_fact_mismatch_review` | none confirmed | `2026-05-04 07:46:03.746` `suppressed / PUBLISH_ONLY_FILTER` |

## Mail delta actual

| post_id | publish time JST | first/retained mail timestamp JST | delta |
| --- | --- | --- | --- |
| `64394` | `2026-05-03 19:34:19` | `19:36:31.963` and `19:37:39.164` | `+2m12.963` and `+3m20.164` |
| `64396` | `2026-05-03 19:05:43` | `19:11:09.067` | `+5m26.067` |
| `64405` | `2026-05-03 20:05:42` | `20:11:02.087` | `+5m20.087` |
| `64418` | `2026-05-04 05:25:40` | `05:31:06.096` | `+5m26.096` |

## Per-id rollback

| post_id / rss_id | rollback requirement | rollback path |
| --- | --- | --- |
| `64394` | only if user wants the already-public post reverted | use WP-capable environment to move post back to draft or unpublish; cleanup backup exists at `/tmp/pub004d/cleanup_backup/64394_20260503T103416.json` |
| `64396` | only if user wants the already-public post reverted | use WP-capable environment to move post back to draft or unpublish; cleanup backup exists at `/tmp/pub004d/cleanup_backup/64396_20260503T100539.json` |
| `64405` | only if user wants the already-public post reverted | use WP-capable environment to move post back to draft or unpublish; cleanup backup exists at `/tmp/pub004d/cleanup_backup/64405_20260503T110539.json` |
| `64418` | only if user wants the already-public post reverted | use WP-capable environment to move post back to draft or unpublish; cleanup backup exists at `/tmp/pub004d/cleanup_backup/64418_20260503T202536.json` |
| `64416` | no rollback from this session | no Lane II mutation performed; keep stopped unless a separate editorial / actor-trace decision is made |
| `64421` | no rollback from this session | no Lane II mutation performed; keep stopped unless manual editorial differentiation is approved |
| `64424` | no rollback from this session | no Lane II mutation performed; keep stopped unless date-fact mismatch is manually repaired first |
| all non-draft rows | none | they never reached a mutable draft/publish stage in this audit window |

## Final outcome

- RSS 20 extracted: `20/20`
- draft-backed rows among the 20: `7`
- already-published rows among the 20: `4`
- unpublished safe candidates requiring Lane ZZ live publish now: `0`
- Lane II live mutation this session: `no-op`
- stop-condition violations in this session: `0`
