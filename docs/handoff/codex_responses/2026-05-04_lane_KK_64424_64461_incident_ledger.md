# 2026-05-04 Lane KK 64424-64461 incident ledger

作成: 2026-05-04 JST  
scope: live ops / incident audit / read-only evidence + doc-only ledger  
write scope used: `docs/handoff/codex_responses/2026-05-04_lane_KK_64424_64461_incident_ledger.md`, `doc/active/assignments.md` only

## meta

- incident start basis: user fire `2026-05-04 JST`, scope fixed to `64424-64461`
- policy lock: individual mail arrival does not equal pipeline healthy
- live mutation decision: only `C` type rescue was eligible for consideration; no safe mutation was executed because both `C` rows are STOP-locked by state inconsistency
- direct WordPress REST/public re-check from this sandbox later became unavailable because outbound DNS to `yoshilover.com` failed; WP/public status fields below preserve the earlier Claude WSL sweep plus the earlier successful shell checks already captured during this session

## Step 1-2 consolidated ledger

| post_id | source | raw → rewritten | subtype / category | WP status | public URL | guarded-publish | publish-notice | duplicate_of | 種別 | 救出可否 / 方法 | 本文品質 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `64424` | 報知新聞 / スポーツ報知巨人班X<br>@hochi_giants<br>https://twitter.com/hochi_giants/status/2051067520736702585 | raw: RT スポーツ報知 レイアウト担当: 5/4付 選手 投手 きょう1軍合流！！！ さぁヤクルト3連戦 ベスト布陣秒読みで仕切り直し...<br>rewritten: RT スポーツ報知 レイアウト担当: 5/4付 選手 投手 きょう1軍合流！… | general / コラム | draft | 404<br>https://yoshilover.com/?p=64424 | draft `2026-05-03 22:35:41.641251 JST` / hold `2026-05-04T07:40:40.111663+09:00` / `review_date_fact_mismatch_review` | suppressed `2026-05-04T07:46:03.745834+09:00` / `PUBLISH_ONLY_FILTER` / publish_ref `2026-05-04T07:35:41+09:00` | - | `B` | 不可<br>narrow re-eval 不可 | yes: RT/レイアウト担当題材 + 日付ミスマッチ review |
| `64425` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64426` | スポニチ / スポニチ野球記者X<br>@SponichiYakyu<br>https://twitter.com/SponichiYakyu/status/2051074252976398667 | raw: 【記事全文】巨人 降雨コールドで今季3度目零敗 好機生かせず守備ミスも…阿部監督「あと一本が先に出ていれば」 - スポニチ Sponichi Annex 野球<br>rewritten: 阿部監督「あと一本が先に出ていれば」 ベンチ関連発言 | manager / 首脳陣 | publish | 200<br>https://yoshilover.com/64426 | draft `2026-05-03 23:02:28.291669 JST` / publish `2026-05-04T08:06:10.637441+09:00` / cleanup ok / cleanup_ts `2026-05-04T08:06:10.637441+09:00` | sent `2026-05-04T08:11:17.799760+09:00` / `-` / publish_ref `2026-05-04T08:06:14+09:00` | - | `D` | 該当なし<br>- | no |
| `64427` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64428` | スポニチ / スポニチ野球記者X<br>@SponichiYakyu<br>https://twitter.com/SponichiYakyu/status/2051074112806871321 | raw: 【記事全文】巨人・山崎伊織 2軍・広島戦に先発も右肩の違和感で2球で降板…泉口は4日に1軍合流へ - スポニチ Sponichi Annex 野球<br>rewritten: 巨人・山崎伊織 2軍・広島戦に先発も右肩の違和感で2球で降板…泉口は4日に1… | farm / ドラフト・育成 | draft | 404<br>https://yoshilover.com/?p=64428 | draft `2026-05-03 23:02:35.319904 JST` / hold `2026-05-04T08:06:10.637441+09:00` / `hard_stop_farm_result_placeholder_body` | - | - | `B` | 不可<br>narrow re-eval 不可 | yes: placeholder/hard-stop body |
| `64429` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64429 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64430` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64430 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64431` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64432` | サンスポ / サンスポ巨人X<br>@sanspo_giants<br>https://twitter.com/sanspo_giants/status/2051101291485733322 | raw: 右アキレス腱炎からの復帰を目指す 投手がブルペン投球を実施<br>rewritten: 実施選手、昇格・復帰 関連情報 | player / 選手情報 | publish | 200<br>https://yoshilover.com/64432 | draft `2026-05-04 00:51:07.519967 JST` / publish `2026-05-04T09:55:37.318944+09:00` / cleanup ok / cleanup_ts `2026-05-04T09:55:37.318944+09:00` | sent `2026-05-04T10:01:17.270981+09:00` / `-` / publish_ref `2026-05-04T09:55:41+09:00` | - | `F` | 該当なし<br>- | yes: rewritten title が「実施選手」で主体欠落 |
| `64433` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64433 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64434` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64435` | 報知新聞 / スポーツ報知巨人班X<br>@hochi_giants<br>https://twitter.com/hochi_giants/status/2051075133427618165 | raw: 【ハヤテ】巨人から育成派遣中の左腕・代木大和が４回３失点「チャンスをいただいている。辛抱強くやっていきたい」…ファーム・リーグ<br>rewritten: 二軍 巨人から育成派遣中の左腕・代木大和が３失点「チャンスをいただいている… | farm / ドラフト・育成 | draft | 404<br>https://yoshilover.com/?p=64435 | draft `2026-05-04 00:55:45.164729 JST` / hold `2026-05-04T10:00:48.685264+09:00` / `hard_stop_farm_result_placeholder_body` | - | - | `B` | 不可<br>narrow re-eval 不可 | yes: placeholder/hard-stop body |
| `64436` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64437` | 報知新聞 / スポーツ報知巨人班X<br>@hochi_giants<br>https://twitter.com/hochi_giants/status/2051067937851891869 | raw: 「菅野智之さん 安否ヨシッ！」元巨人・宮国椋丞さんがデンバーへ遠征応援 小林誠司も「いいね！」…「２人の関係大好き」の声<br>rewritten: 「菅野智之さん 安否ヨシッ！」元巨人・宮国椋丞さんがデンバーへ遠征応援 小林… | general / OB・解説者 | draft | 404<br>https://yoshilover.com/?p=64437 | draft `2026-05-04 00:55:49.098001 JST` / skip replay `2026-05-04T10:00:48.685264+09:00`→`2026-05-04T10:25:36.196891+09:00` / `backlog_only` | suppressed `2026-05-04T10:06:36.373219+09:00` / `DUPLICATE_WITHIN_REPLAY_WINDOW` / publish_ref `2026-05-04T09:55:49+09:00` | - | `C` | 不可 (STOP lock)<br>WP status mutation / narrow re-eval 停止 | no: state inconsistency main issue |
| `64438` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64439` | 報知新聞 / スポーツ報知巨人班X<br>@hochi_giants<br>https://twitter.com/hochi_giants/status/2051031133790380168 | raw: あえて巨人戦はチェックせず 泉口友汰が明かした負傷離脱中の心境<br>rewritten: あえて巨人戦はチェックせず 泉口友汰が明かした負傷離脱中の心境 | general / コラム | publish | 200<br>https://yoshilover.com/64439 | draft `2026-05-04 00:56:05.820753 JST` / publish `2026-05-04T10:00:48.685264+09:00` / cleanup ok / cleanup_ts `2026-05-04T10:00:48.685264+09:00` | sent `2026-05-04T10:06:33.591091+09:00` / `-` / publish_ref `2026-05-04T10:00:56+09:00` | - | `D` | 該当なし<br>- | no |
| `64440` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64441` | 報知新聞 / スポーツ報知巨人班X (RT: 報知プロ野球チャンネル)<br>@hochi_giants<br>https://twitter.com/hochi_giants/status/2050908686688899531 | raw: RT 報知プロ野球チャンネル: 【動画】昨年とは別人！？ 西川歩が今季２軍初昇格…新たな投球術で先発ローテをつかめ！【ファーム報知】<br>rewritten: RT 報知プロ野球チャンネル: 【動画】昨年とは別人！？ 西川歩が今季２軍初… | farm / ドラフト・育成 | draft | 404<br>https://yoshilover.com/?p=64441 | draft `2026-05-04 00:56:17.195477 JST` / hold `2026-05-04T10:00:48.685264+09:00` / `hard_stop_farm_result_placeholder_body` | - | - | `B` | 不可<br>narrow re-eval 不可 | yes: RT動画題材 + placeholder/hard-stop body |
| `64442` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64443` | 報知新聞 / スポーツ報知巨人班X<br>@hochi_giants<br>https://twitter.com/hochi_giants/status/2050891541141483536 | raw: 【巨人】ドラ２・田和廉が球団新を更新する１２試合連続無失点 ７回２死満塁→中断→降雨コールドで記録継続<br>rewritten: ドラ２・田和廉が球団新を更新する１２試合連続無失点 ７回２死満塁→中断→降雨… | general / 球団情報 | publish | 200<br>https://yoshilover.com/64443 | draft `2026-05-04 00:56:22.726020 JST` / publish `2026-05-04T10:00:48.685264+09:00` / cleanup ok / cleanup_ts `2026-05-04T10:00:48.685264+09:00` | sent `2026-05-04T10:06:27.579840+09:00` / `-` / publish_ref `2026-05-04T10:00:55+09:00` | - | `D` | 該当なし<br>- | no |
| `64444` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64445` | 報知新聞 / スポーツ報知巨人班X<br>@hochi_giants<br>https://twitter.com/hochi_giants/status/2050885171277099230 | raw: 【巨人】松浦慶斗が初回から緊急リリーフ 大慌てで準備した舞台裏は… 先発・山崎伊織が２球で交代<br>rewritten: 【巨人】松浦慶斗が初回から緊急リリーフ 大慌てで準備した舞台裏は… 先発・山… | pregame / 試合速報 | publish | 200<br>https://yoshilover.com/64445 | draft `2026-05-04 00:56:31.037999 JST` / publish `2026-05-04T10:00:48.685264+09:00` / cleanup ok / cleanup_ts `2026-05-04T10:00:48.685264+09:00` | sent `2026-05-04T10:06:30.618885+09:00` / `-` / publish_ref `2026-05-04T10:00:55+09:00` | - | `D` | 該当なし<br>- | no |
| `64446` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64447` | サンスポ / サンスポ巨人X<br>@sanspo_giants<br>https://twitter.com/sanspo_giants/status/2050861454233059811 | raw: 巨人D2位 の球団新記録が〝首の皮一枚〟つながる 満塁ピンチで降雨コールドとなり無失点<br>rewritten: 巨人D2位 の球団新記録が〝首の皮一枚〟つながる 満塁ピンチで降雨コールドと… | general / 球団情報 | draft | 404<br>https://yoshilover.com/?p=64447 | draft `2026-05-04 00:56:44.048964 JST` / skip replay `2026-05-04T10:00:48.685264+09:00`→`2026-05-04T10:30:47.857437+09:00` / `backlog_only` | suppressed `2026-05-04T10:06:39.201959+09:00` / `DUPLICATE_WITHIN_REPLAY_WINDOW` / publish_ref `2026-05-04T09:56:43+09:00` | - | `C` | 不可 (STOP lock)<br>WP status mutation / narrow re-eval 停止 | no: state inconsistency main issue |
| `64448` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64449` | サンスポ / サンスポ巨人X<br>@sanspo_giants<br>https://twitter.com/sanspo_giants/status/2050832871234187694 | raw: 投手の降板理由は右肩の違和感<br>rewritten: 投手の降板理由は右肩の違和感 | pregame / 試合速報 | publish | 200<br>https://yoshilover.com/64449 | draft `2026-05-04 00:57:09.405538 JST` / publish `2026-05-04T10:00:48.685264+09:00` / cleanup ok / cleanup_ts `2026-05-04T10:00:48.685264+09:00` | sent `2026-05-04T10:06:21.146932+09:00` / `-` / publish_ref `2026-05-04T10:00:54+09:00` | - | `D` | 該当なし<br>- | no |
| `64450` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64451` | 日刊スポーツ 巨人<br>-<br>https://www.nikkansports.com/baseball/news/202605030001845.html | raw: 【巨人】泉口友汰は４日ヤクルト戦で１軍合流、登録は未定　リチャードは「まだです」橋上コーチ<br>rewritten: 橋上コーチ「まだです」 ベンチ関連発言 | manager / 首脳陣 | publish | 200<br>https://yoshilover.com/64451 | draft `2026-05-04 00:57:26.766730 JST` / publish `2026-05-04T10:00:48.685264+09:00` / cleanup ok / cleanup_ts `2026-05-04T10:00:48.685264+09:00` | sent `2026-05-04T10:06:24.052801+09:00` / `-` / publish_ref `2026-05-04T10:00:54+09:00` | - | `D` | 該当なし<br>- | no |
| `64452` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64453` | 日刊スポーツ 巨人<br>-<br>https://www.nikkansports.com/baseball/news/202605030000454.html | raw: 元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘れるくらい」<br>rewritten: 元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘… | general / OB・解説者 | publish | 200<br>https://yoshilover.com/64453 | draft `2026-05-04 00:57:41.889870 JST` / publish `2026-05-04T10:00:48.685264+09:00` / cleanup ok / cleanup_ts `2026-05-04T10:00:48.685264+09:00` | sent `2026-05-04T10:06:18.303030+09:00` / `-` / publish_ref `2026-05-04T10:00:53+09:00` | - | `F` | 該当なし<br>- | yes: 巨人現役情報ではなく relevance 弱い |
| `64454` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64454 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64455` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64455 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64456` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64456 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64457` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64457 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64458` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64458 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64459` | - | - | - / - | invalid_id (gap) | 404<br>https://yoshilover.com/?p=64459 | - | - | - | `E` | 該当なし<br>- | no: no article trace |
| `64460` | - | - | - / - | invalid_id (attachment) | 200(upload)<br>upload asset | - | - | - | `E` | 該当なし<br>- | no: attachment id |
| `64461` | ベースボールキング<br>- (embedded xpost: @hochi_baseball)<br>https://baseballking.jp/ns/694662/ | raw: ブルージェイズ・岡本和真が3戦連発の9号2ラン　9回に反撃の一発放つも及ばず、勝率5割復帰お預け<br>rewritten: 岡本和真、昇格・復帰 関連情報 | player / 選手情報 | publish | 200<br>https://yoshilover.com/64461 | draft `2026-05-04 01:02:23.062171 JST` / publish `2026-05-04T10:05:44.505730+09:00` / cleanup ok / cleanup_ts `2026-05-04T10:05:44.505730+09:00` | sent `2026-05-04T10:11:12.202828+09:00` / `-` / publish_ref `2026-05-04T10:05:47+09:00` | - | `F` | 該当なし<br>- | yes: Blue Jays/岡本和真の entity mismatch |

## Step 2 classification summary

- `A`: `0`件 - 本物重複
- `B`: `4`件 - 本文崩壊・事実破綻 stop 正解
- `C`: `2`件 - fan-important だが救出 STOP lock
- `D`: `6`件 - publish 済み確認のみ
- `E`: `23`件 - ID 不在/attachment/gap
- `F`: `3`件 - publish 済みだが本文品質 NG 候補

### rescue execution outcome

- executed publish-forward mutations: `0`
- rescue success: `0`
- rescue failed after mutation: `0`
- blocked before mutation: `2` (`64437`, `64447`)
- reason: both rows are fan-important enough for `C`, but current evidence is inconsistent: `publish_notice_history/queue` says published while `guarded_publish_history` never records `sent` and current WP status is draft/forbidden. This hit the user STOP condition for pipeline state inconsistency, so no narrow re-eval or WP status mutation was attempted from this sandbox.

## Step 3 rescue plan that would have run if state were coherent

1. `64437` - fan-important OB/遠征応援ネタ。candidate method would be narrow re-eval or explicit publish mutation, but STOP locked until notice/history drift is explained.
2. `64447` - fan-important record-survival / game-context item。candidate method would be narrow re-eval or explicit publish mutation, but STOP locked until notice/history drift is explained.

## Step 5 forbidden 6 deep audit

| post_id | current state | publish trace | revert actor judgment | BUG-003/GG hardening implication |
| --- | --- | --- | --- | --- |
| `64424` | draft / public 404 | no guarded `sent`, no cleanup, notice only `PUBLISH_ONLY_FILTER` suppress | no revert observed; draft-only review stop | not a GG hardening miss; correct hold on `review_date_fact_mismatch_review` |
| `64428` | draft / public 404 | no guarded `sent`, no cleanup, no notice | no revert observed; draft-only hard stop | not a GG hardening miss; correct stop on `farm_result_placeholder_body` |
| `64435` | draft / public 404 | no guarded `sent`, no cleanup, no notice | no revert observed; draft-only hard stop | not a GG hardening miss; correct stop on `farm_result_placeholder_body` |
| `64437` | draft / public 404 | guarded only `skipped backlog_only`; notice queue/history stamped it as published at `2026-05-04T10:05:40-10:06:36+09:00` | no confirmed publish→draft revert; evidence points to publish-notice phantom publish marker / history seeding drift rather than WP revert actor | GG hardening does not cover this. Needs a separate narrow audit on publish-notice history seeding and direct-publish replay interaction. Treat as BUG-003 family candidate until disproved. |
| `64441` | draft / public 404 | no guarded `sent`, no cleanup, no notice | no revert observed; draft-only hard stop | not a GG hardening miss; correct stop on `farm_result_placeholder_body` |
| `64447` | draft / public 404 | guarded only `skipped backlog_only`; notice queue/history stamped it as published at `2026-05-04T10:05:40-10:06:39+09:00` | no confirmed publish→draft revert; evidence points to publish-notice phantom publish marker / history seeding drift rather than WP revert actor | GG hardening does not cover this. Needs a separate narrow audit on publish-notice history seeding and direct-publish replay interaction. Treat as BUG-003 family candidate until disproved. |

## Step 6 invalid_id 23 cause audit

- guarded-publish trace count for invalid `23`: `0`
- publish-notice queue/history trace count for invalid `23`: `0`
- interpretation: these are not “vanished article posts” from the guarded pipeline.

| cause bucket | count | ids | judgment |
| --- | --- | --- | --- |
| attachment IDs resolving to `wp-content/uploads/...` | `14` | `64425, 64427, 64431, 64434, 64436, 64438, 64440, 64442, 64444, 64446, 64448, 64450, 64452, 64460` | expected WP/media allocation, not a publish pipeline failure |
| true gaps / no public article / no guarded trace | `9` | `64429, 64430, 64433, 64454, 64455, 64456, 64457, 64458, 64459` | likely unallocated or non-post IDs; no evidence of cleanup/trash or mid-flight guarded failure |

## quality backlog (`F` rows + additional quality flags)

- primary `F` rows:
  - `64432`: rewritten title lost the player subject and became `実施選手、昇格・復帰 関連情報`
  - `64453`: published but giant relevance is weak (`上原浩治` x boxing comment)
  - `64461`: published with strong entity mismatch (`ブルージェイズ・岡本和真` → Giants return title)
- additional blocked quality rows:
  - `64424`: RT / レイアウト担当 / date mismatch review stop
  - `64428`, `64435`, `64441`: placeholder-body family, stop was correct

## public URLs + mail sent timestamps

- `64426`: https://yoshilover.com/64426 / mail `2026-05-04T08:11:17.799760+09:00`
- `64432`: https://yoshilover.com/64432 / mail `2026-05-04T10:01:17.270981+09:00`
- `64439`: https://yoshilover.com/64439 / mail `2026-05-04T10:06:33.591091+09:00`
- `64443`: https://yoshilover.com/64443 / mail `2026-05-04T10:06:27.579840+09:00`
- `64445`: https://yoshilover.com/64445 / mail `2026-05-04T10:06:30.618885+09:00`
- `64449`: https://yoshilover.com/64449 / mail `2026-05-04T10:06:21.146932+09:00`
- `64451`: https://yoshilover.com/64451 / mail `2026-05-04T10:06:24.052801+09:00`
- `64453`: https://yoshilover.com/64453 / mail `2026-05-04T10:06:18.303030+09:00`
- `64461`: https://yoshilover.com/64461 / mail `2026-05-04T10:11:12.202828+09:00`

## conclusion

- lane KK did **not** find a broad pipeline collapse across all 38 IDs.
- it did find two concrete classes of incident evidence:
  - `64437` / `64447`: publish-notice state drift against guarded/WP reality
  - `64432` / `64453` / `64461`: published quality acceptance problems that should remain on the backlog even though mail/public URL exist
- safe publish-forward rescue count for this cycle is `0`, because the only candidate `C` rows are exactly the ones that hit the state-inconsistency STOP rule.
