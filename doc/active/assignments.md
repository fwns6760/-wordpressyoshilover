# assignments — 現場担当と次アクション

最終更新: 2026-05-19 JST

## 2026-05-19 session update

| ticket | status | 内容 |
|---|---|---|
| `doc/active/383-INGEST-youtube-source-articleize-fix.md` (GH #58) | LIVE_DEPLOYED_OBSERVE | 344 の YouTube 記事が出ない件。live では `youtube_channel` 取得は出ていたが、`media_quote_only` で articleize path に進まず、`youtube_caption_section_appended` / `youtube_title_filter_skip` が 0 件だった。repo fix: YouTube channel scraper だけ `media_quote_only` でも記事化 path へ進め、`youtube_ob_sources.json` の confirmed / candidate ch を runtime 展開。tests: 344/YouTube suite 68 OK、rss_fetcher + tag_page + YouTube integration 57 OK、compileall / AST / diff-check OK。Cloud Build `7ed5103a` SUCCESS、fetcher rev `yoshilover-fetcher-00436-7zq` 100%、`/health` OK、新 revision ERROR 0。次は自然 fire で YouTube path log / draft evidence 待ち。Scheduler / env / Secret / WP既存記事 / X / frontend は未変更。 |
| `doc/active/384-INGEST-source-expansion-with-publish-time-fallback.md` (GH #59) | DESIGN_LOCKED / READY_FOR_IMPL | user 要望「ソースをふやしたい、ガードに引っかからない」(2026-05-19 chat lock)。chat verify 結果: 5/19 9 時 cycle で 52 件 `source_time_missing_review` review 落ち = 既存 381 16 family にも meta なし媒体が混在している evidence (Full-Count / 週刊女性PRIME / 読売新聞は meta あり、朝日 / 毎日 / FRIDAY 等は root では meta なし)。新規候補 verify: 産経 (`<meta name="article:published_time">` あり、5/19 朝記事 age 4h) ✓、日刊SPA (`<meta property=...>` あり、search 最新 sort 要 verify) ✓、中日新聞・中日スポーツ (meta なし、SPA 構造) ✗、THE ANSWER (search SPA で article href 抽出不能) ✗。Phase 1 = 産経 + 日刊SPA 追加 (`config/rss_sources.json` + `source_trust.py` SourceProfile + `rss_fetcher.py` `_POST_GEN_VALIDATE_TOPIC_SOURCE_FAMILIES`)、Phase 2 = `tag_page_scraper.py` に publish-time fallback chain (property/name/modified_time/URL date/body 日付表記)、Phase 3 = 中日系追加 (Phase 2 effect ベース判断)、Phase 4 = THE ANSWER (SPA、別 ticket)。デグレ試験: 既存 16 family 挙動不変 + `STRICT_BREAKING_NEWS_THRESHOLDS` 閾値不変 + scraper `_is_ymd_within_window` で古い記事 2 重 guard。`_POST_GEN_VALIDATE_TRUSTED_FAMILIES` (full bypass) / numeric fact validator / close_marker / placeholder_body / hard-stop は不可触、env / Secret / Scheduler / X / SNS / WP既存記事も不可触。 |
| `doc/active/385-INGEST-youtube-caption-short-quote-summary.md` (GH #60) | LIVE_DEPLOYED_OBSERVE | user GO。YouTube 字幕を長い 600 字 1 block ではなく、LLM なし / 推測なしで短い引用 + 要点表示に寄せる。実装: caption text を deterministic に文分割し、最大2 quote + 最大3要点 bullet に整形。推測補完なし、HTML escape、出典 / embed 維持。follow-up: 取得材料 window を 600→1500 chars に拡大、表示 cap は維持。tests: YouTube caption/title/integration 63 OK、compileall / py_compile / AST / diff-check OK。Cloud Build `82719b1a` SUCCESS、image `385-youtube-caption-1500-6904c98` digest `sha256:2d696966...`、fetcher rev `yoshilover-fetcher-00441-xj8` 100%、`/health` OK、新 revision ERROR 0。次は自然 fire で quote_count / summary_count evidence 待ち。env / Secret / Scheduler / RUN_DRAFT_ONLY / WP既存記事 / X / frontend は不可触。 |
| `doc/done/2026-05/386-INSIGHT-no-game-day-normal-exit.md` (GH #61) | CLOSED | 2026-05-18(月) 試合なしで `insight-nightly` が `auto_resolve_all_failed` / exit 2 になった件。NPB日程HTMLが読めて parse できるが対象日 slug 0 件なら `status=no_game_day` / exit 0 に分岐し、日程取得失敗は従来通り blocked / exit 2 のままにする修正を deploy / live verify 済み。commit `a852abf`、image `insight-nightly:386-no-game-a852abf`、Job generation `67`、execution `insight-nightly-mf69g` 成功、log `status=no_game_day` / reason `no scheduled NPB games for 2026-05-18`。Scheduler / env / Secret / WP既存記事 / X / frontend は未変更。 |

## 2026-05-18 session summary

### 着地 (Cloud Scheduler 3 jobs 追加、 repo code 不変)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/378-evening-peak-fetch-15min.md` (GH #52) | CLOSED (2026-05-19) | 試合後ピーク (20:00-22:00 JST) の `yoshilover-fetcher /run` fetch を 15min cadence 化、 22-23 時を 30min cadence 補強。 既存 `giants-realtime-trigger 0,30 17-21` `giants-postgame-catchup-am 0 22` は不変 (gcloud list で verify 済)、 新規 3 jobs ENABLED で着地 (`giants-realtime-peak-15min 15,45 20-21`, `giants-realtime-2230 30 22`, `giants-realtime-2300 0 23`)。 auth は既存 trigger と同じ `seo-web-runtime@baseballsite.iam.gserviceaccount.com` + oidcToken (5/16 x-post-mail 403 事故回避)。 guarded-publish-trigger `*/30` / publish-notice-trigger-evening `5,35 16-22` / WP / X / SNS / env / Secret 不変、 mail 仕様も不変。 cost +$0.30/月、 user confirm 済。 23:00 fetch の mail は翌朝 (`publish-notice-trigger 5 6-15`)、 判断サイクル完全 15min 化は別 ticket (guarded-publish + publish-notice 連動 15min 化、 +$0.30/月)。 |

### 起票 (DESIGN 段階、 377-OPS Phase 1C / Phase 2 完了後着手)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/377-OPS-...md` Phase 1C (GH #51) | CLOSED (2026-05-19) | mail に body_excerpt + admin_edit_url を populate。 commits `11128d5` (helper module + 39 tests) → `cb5b477` (scanner wiring + 15 tests) → `0467180` (dry-run tool + e2e integration 2 tests)。 Cloud Build `1aa5e4f2` SUCCESS、 image `publish-notice:377-phase1c-0467180` digest `sha256:e01bccd9e503...`、 Cloud Run Job update Ready=True (旧 image `classification-316cb03` rollback 用に保持)。 env (RUN_DRAFT_ONLY=0 維持) / Secret / Scheduler / WP / X / SNS 全て不変、 手動 execute は追加 mail 回避のため未実行。 publish_notice 系 12 files 340 tests pass、 regression 0。 次回自然 fire = 10:05 JST (publish-notice-trigger)。 本文 / admin link 目視 verify 待ち。 |
| `doc/done/2026-05/377-OPS-...md` Phase 2 (GH #51) | CLOSED (2026-05-19) | `RUN_DRAFT_ONLY=True` env apply。 yoshilover-fetcher service rev `00424-sc8` で全 subtype draft 化稼働開始。 既存 publish 済記事は touch せず forward-only、 rollback は env=False で 1 toggle。 |
| `doc/done/2026-05/379-mail-publish-x-intent-button.md` (GH #53) | CLOSED (2026-05-19) | 当日 10 commit fix chain (9fdbeca→38bfedc→be1cc62→4a85a8a→585a208→b9281a3→f3a961f→b998f0a→3c1612d→feb27e3)。 最終 deploy: fetcher `fix-team-label-3c1612d` (rev `00429-m9h` 100%) + publish-notice `dedup-24h-feb27e3`。 env final: RUN_DRAFT_ONLY=True / DRAFT_ONLY_SCAN_MODE=1 / ENABLE_POST_GEN_VALIDATE_NOTIFICATION=0 / ENABLE_PREFLIGHT_SKIP_NOTIFICATION=0 / ENABLE_PUBLISH_ONLY_MAIL_FILTER=0 / DEFAULT_DUPLICATE_WINDOW=24h。 **end-to-end first 完全動作確認 (15:05 fire)**: user が 69348/69349/69350 を 15:11-15:12 JST に mail 緑 button click → caller=mail_publish_and_tweet_endpoint で publish 化 (Cloud Logging `publish_button_publish_success` × 3 evidence)。 当日 事故 root cause = (1) 13:00 fetcher 0 件 = 「巨人」「ジャイアンツ」 を generic title block list に入れた、 commit `3c1612d` で除外修正、 (2) 14:05 fire 30 通中 20 通 再送 = dedup 30 分 default 短すぎ、 `feb27e3` で 24h に拡大。 様子見 point = 16:05 以降の自然 fire mail 量 baseline (5-10 通安定) / 再送 0 / 21:00-22:00 試合後ピーク fetch 15min cadence (378) / title 弱 case 別 ticket / 13:05 で STALE filter 効かなかった root cause (DRAFT_ONLY_SCAN_MODE 回避策で代用、 コード trace 未) は次 session 案件。 ticket 内に詳細記録 (10 fix log / 様子見 point / コスト試算 / 別 ticket 候補) 追記済。 |
| `doc/done/2026-05/380-x-post-mail-player-diversity-cap.md` (GH #54) | CLOSED (2026-05-19) | 2026-05-18 07:00 JST mail は `マルティネス` 3 件 / `岸田 行倫` 2 件、12:01 JST mail は浦田俊輔 3 件 / マルティネス 3 件、13:07 手動 mail でも浦田俊輔が再登場したため、user-visible acceptance は未達。follow-up 実装: GCS dedup JSONL に `focus_player / metric / period_label` を記録し、直近24h player history から既出 player を避ける。ranking 内に別の巨人 player があれば差し替え、無ければ `player_history_skip` を log して news/opinion fallback で別 player を補充する。tests: py_compile / compileall / AST PASS、pytest `94 passed, 3 warnings`、unittest `Ran 94 tests OK`。deploy: commit `157b26b` clean archive、Cloud Build `8dad3a83` SUCCESS、image `x-post-mail-lane:380-player-history-157b26b` digest `sha256:15cd067...`、Cloud Run Job generation `21` Ready=True。手動 execute は追加 real mail 回避で未実行、post-update user-visible acceptance は次回自然 fire 待ち。Scheduler / env / Secret / WP / X / SNS / production DB は変更しない。 |
| `doc/active/381-INGEST-giants-general-source-expansion.md` (GH #55) | LIVE_DEPLOYED_OBSERVE | user 要望「巨人だけ総合」「データがなければニュース記事の意見」「読売新聞/朝日新聞/毎日新聞/週刊ベースボール/一般誌」。追加/修正 source: Full-Count 巨人 category feed、ベースボールチャンネル、朝日スポーツRSS、毎日スポーツRSS、週刊ベースボールONLINE、読売新聞オンライン プロ野球、日テレNEWS NNN、FRIDAY、Smart FLASH、週刊女性PRIME、文春、NEWSポストセブン、デイリー新潮、現代ビジネス、アサ芸。root cause: x-post-mail news/opinion fallback が tag_scrape を読まず、source limit 4 で新ソースまで届かなかった。修正後 evidence: fallback default limit 32 / loaded article sources 32 / positions 23-32 に読売・日テレ・一般誌まで到達。live scraper evidence: 読売3、日テレ5、Smart FLASH5、週刊女性PRIME5、NEWSポストセブン2、アサ芸3、FRIDAY0、文春0、デイリー新潮0、現代ビジネス0。ガード: tag_scrape は title/summary に `巨人`/`読売ジャイアンツ`/`ジャイアンツ` 必須、一般誌/新聞は limited topic bypass のみで full bypass / numeric fact / hard stop は不変。tests: unittest 170 OK、pytest 203 passed。deploy: commit `c791f52`、x-post-mail build `a8a5ea80` SUCCESS / image `x-post-mail-lane:381-general-sources-c791f52` / digest `sha256:a39a741...` / Job generation `22` Ready=True、fetcher build `2b60df25` SUCCESS / image `yoshilover-fetcher:381-general-sources-c791f52` / digest `sha256:ad8fd151...` / revision `yoshilover-fetcher-00431-vl9` 100% / `GET /health` OK。manual-intake-service も source 候補 tab + `/source-candidates` を追加 deploy 済み: build `9329593b` SUCCESS / image `manual-intake-service:source-candidates-202605181726` / digest `sha256:994eb392...` / revision `manual-intake-service-00084-bzv` 100% / live 読売 endpoint `count=3` / ERROR log 0。Scheduler / env / Secret / WP / X は未変更。追加 real mail 回避のため manual execute は未実行、post-update mail acceptance は次回自然 fire 待ち。 |
| `doc/done/2026-05/382-MKT-yoshilover-branding-post-planning-mail.md` (GH #56) | CLOSED | 既存 x-post-mail lane 内でブランディングXポスト案を実装 / deploy / 自然実行 verify 済み。commit `4507257` + full regression follow-up `1013716`、Cloud Build `1629e082` SUCCESS、image `x-post-mail-lane:382-branding-4507257`、Cloud Run Job generation 23 Ready=True、2026-05-19 07:00 JST 自然実行 `x-post-mail-lane-psp2s` SUCCESS / mail sent / ERROR 0。URLなし / hashtagなし / サイト誘導なし、未照合数値は本文から除外、DB照合済み数値のみ許可。Scheduler / env / Secret / WP / X live post は不変。git push は repo lock により未実施。GH #57 は user request により canceled close 済み。 |

## チケット管理方針(2026-05-14 EVENING lock)

- **正本 = repo doc 一本**(`doc/README.md` + 本 `doc/active/assignments.md`)
- **2026-05-16 user lock: 新規/修正 ticket は GitHub Issue も作る**
- GitHub Issue は日本語で、人間が読んで分かる題名・原因・直す内容・完了条件を書く
- Issue は作っただけで完了にしない。変更 diff、テスト、deploy / log 証跡、受け入れ条件の一致が揃った後に close する
- repo doc は引き続き正本。GitHub Issue は user が追いやすい外部台帳として同期する

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`
- `doc/active/assignments.md`
- **2026-05-14 最新 handoff (本日 3 session)**:
  - `docs/handoff/session_logs/2026-05-14_pm_336qa_chain_handoff.md` (PM、336-QA chain LIVE)
  - `docs/handoff/session_logs/2026-05-14_session_handoff_343_INSIGHT_007_LIVE.md` (PM 並走、343-INSIGHT-007 chain LIVE + 342 unblock)
  - `docs/handoff/session_logs/2026-05-14_session_handoff_DATA_INSIGHT_continuous_LIVE.md` (EVENING、342 LIVE 公開 + DATA-INSIGHT-continuous system 稼働 + SVG fix)
- **2026-05-08 緊急対応 (close 済)**: `doc/done/2026-05/RESTORE-2026-05-08-MORNING-RELIABILITY.md` + `docs/handoff/HANDOFF-2026-05-08-NEXT-SESSION.md`

## 2026-05-14 PM session summary

### close 済 (13 GH Issue、1 commit chain)

| 区分 | Issue | commit | 備考 |
|---|---|---|---|
| impl | #17 / 338-QA | `ef204c5` | 「無失点」を「失点」誤判定 fix |
| audit→fix | #19 / 340-OBSERVE → #22 / 341-FIX | `4487e77` | digest 不発 audit → schema adapter |
| impl | #8 / 335-QA Phase 3 | `ace4b64` | event token 重複圧縮 |
| impl | #16 / 337-INGEST Phase 3 | `21e4502` | sanspo balanced div extractor |
| impl | #18 / 339-INGEST | `6dd55f2` | X+Web 同 family dedup (default OFF) |
| impl | #10/#11/#12 / 336-QA Phase 1+2+3 | `e7a33bd` | 報知優先 parent + 600字 excerpt block |
| ops 移行 | #5 / 334-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| ops 移行 | #9 / 335-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| ops 移行 | #13 / 336-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| 並走 | #23 / 343-INSIGHT-007 | (並走 session) | Phase 1+2 LIVE deploy 完了で close |

deploy: yoshilover-fetcher rev 00380-dx7 → 00381-n9d → 00382-hqj → 00383-vtd → 00384-c2s → 00385-5xb (6 deploy、build digest = revision sha256 一致全件 verify)

## 2026-05-15 session summary

### close 済(本 session、 348 chain)

| 区分 | ticket | commit | image digest |
|---|---|---|---|
| impl + deploy | 348 step 1: × whitelist gate + config JSON | `86d4724` | `sha256:43aeb2b5...` |
| impl + deploy | 348 step 2: 勝率/守備率 + publisher 日本語 label | `bf010ba` | `sha256:e26ac26d...` |
| impl + deploy | 348 step 3 part 1: scope 拡張 (last_5/10_games / monthly / weekly) | `8b962e5` | `sha256:16129274...` |
| impl + deploy | 348 step 3 part 2: record detector + team ranking + counting helper | `7a10c6e` | `sha256:6e633c8b...` |

test: 382 passed (= 302 baseline + 35 step1 + 18 step2 + 14 step3p1 + 13 step3p2)、regression 0、schema migration 0

### 起票(本 session 発見、 user 確認後 着手判断)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/352-postgame-auto-thin-body-false-positive.md` | REVIEW_NEEDED | 2026-05-17 user GO で repo fix 完了。Yahoo minimal postgame は勝敗投手 table を本文に出し `【試合結果】` title へ補正、scorecard-only STOP は維持。朝 catchup は前日配信 postgame に当日朝の `見どころ` state を当てない。targeted tests green、live deploy 未実行 |

### user 判断 残

| 件 | 内容 |
|---|---|
| 既存 wOBA 5 件 post (68064-68068) | × metric が title 流出、 §11 GATE。 削除/書き換え/放置 のどれか |
| 352 着手 GO 判断 | 済。repo fix 完了、live deploy / 自然 fire 観察待ち |

### 翌日の verify gap

- 明朝 07:00 JST insight-nightly 自然 fire 後、 348 step 3 で導入した新 scope (last_5_games / last_10_games / monthly / weekly) で実 publish が出るか確認
- 「奪三振率 / 与四球率 / 被本塁打率」「勝率 / 守備率」の日本語 label が新規 publish title に反映されているか

## 2026-05-16 session summary

### repo 実装済、push は repo lock により未実行、deploy 状態は ticket ごとに記録

| ticket | status | 内容 |
|---|---|---|
| `348-INSIGHT` follow-up | LIVE_DEPLOYED_OBSERVE | `BABIP` / `FIP` が detector bypass や direct renderer から再流出しないよう二重防御。UZR は user 指示通り許可側維持 |
| `349-INSIGHT-dedup-cooldown-cascade` | LIVE_DEPLOYED_OBSERVE | 同じ subject + metric を期間違いでも 7 日 cooldown。例外は 5% 以上の値変化または順位 band 変化。title 期間 runtime guard も deploy 済み。schema migration なし、既存 `article_candidates` を ledger として利用 |
| `356-INSIGHT-data-quality-publish-gate` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #31 起票済み。sample不足 / ranking coverage不足 / stale snapshot / 本文根拠不足を publish 直前に止める data quality gate を `insight-nightly:ca03019` へ本番 deploy 済み。Cloud Build `19c2e97d-f4f9-48e9-8db4-7a303003892e` SUCCESS、digest `sha256:a71bbe0f...`、Job generation `46`。env / Scheduler / Secret / X / SNS は未変更、手動 execute 未実行 |
| `362-INSIGHT-queue-cleanup-and-metric-run-cap` | LIVE_DEPLOYED_OBSERVE | anomaly auto publish を 1 run 同一 metric 1 本までに制限し、古い NEW / 対象外 signal / metric cap 余剰を status 変更で掃除する実装を `insight-nightly:362-queue-80b87ea` へ deploy 済み。production DB copy smoke では `NEW 15938 -> 822`、UZR 3 件は 1 件 draft candidate + 2 件 cap drop。Scheduler / env / Secret / X / SNS は未変更、手動 execute 未実行 |
| `363-QA-same-fire-cross-source-title-duplicate-stop` | CLOSED | 68478/68480 型の別 source URL・同 generated title の連続 draft を、lineup / pregame / postgame / player quote など高確度 family に限って same-fire で止める。generic title collision は従来通り observe-only。py_compile PASS、lineup 周辺込み targeted pytest 79 passed / 3 xfailed。Cloud Build SUCCESS、`yoshilover-fetcher-00400-f29` へ deploy、`/health` OK。Scheduler / env / Secret / WP既存記事 / X / SNS は未変更。GitHub Issue #32 は日本語化して close |
| `364-QA-cross-family-same-event-dedup` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #33。報知 / スポニチ / デイリー等が同じ巨人ニュースを別タイトルで出す穴を、literal `phase + subject + player + event + day` key で止める repo 実装完了。X+雑誌/Web も対象、別主体コメントは保持、`cross_family_same_event_duplicate_skip` 構造化ログあり。targeted tests PASS。Cloud Build `440b7747-e8f4-4ca7-adc2-f0299ab3ddd5` SUCCESS、image `364-cross-family-4929278`、digest `sha256:c2f85e1a4bb2...`、revision `yoshilover-fetcher-00401-dxs` 100%、`/health` OK。Scheduler / env / Secret / WP既存記事 / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `365-QA-social-x-related-post-specificity` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #34。68489 型。SNS記事の「関連ポスト」が同一選手名だけで別話題Xを束ねる穴を、literal detail overlap 必須にして恒久修正。記憶再構成 / silent skip / 自己評価OKは禁止。`topic_detail_mismatch` を返す。py_compile / compileall / AST PASS。pytest: media selector 24 passed、media selector + build block 83 passed、duplicate guard 13 passed。Cloud Build `a46132b5-d25a-4bf0-b44f-6bb92b39fbff` SUCCESS、image `365-social-x-7440089`、digest `sha256:6161a8b640e5...`、revision `yoshilover-fetcher-00402-4vc` 100%、`/health` OK。Scheduler / env / Secret / WP既存記事 / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `366-QA-source-excerpt-placement` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #35。68321 / 68622 型。引用記事（本文抜粋）が関連ポストから離れたり参照元付近まで下がる穴を、生成済み HTML の relocation で恒久修正。関連ポストありならポスト直後、ポストなしなら最初の本文見出し前へ移動。記憶再構成 / silent skip / 自己評価OKは禁止。py_compile / compileall / AST PASS。pytest: source excerpt 9 passed、source excerpt + build block 68 passed。Cloud Build `593207f8-ad5d-4ddd-a5ea-cc56bb436772` SUCCESS、image `366-excerpt-placement-4021792`、digest `sha256:e4bf5f00d105...`、revision `yoshilover-fetcher-00403-ssj` 100%、`/health` OK。draft 68622 は status=draft 確認後に本文抜粋位置のみ修正済み。published 68321 は未更新。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `367-QA-farm-third-postgame-first-team-box-guard` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #36。68610 型。三軍 / 二軍の試合結果記事が `first` 誤判定で当日の一軍 NPB / Yahoo boxscore を取りに行く穴を、postgame 抽出器と rss_fetcher の二層 guard で止める。`三軍` は `league_level=third`、二軍 / ファームは `farm`。parser が first と誤返却しても farm / third marker・subtype・カテゴリで fetch を止め、fallback 表示は `巨人3軍` / `巨人2軍` にする。py_compile / compileall / AST PASS。pytest: postgame extractor + postgame table 33 passed、関連 build block 込み 92 passed。commit `6664e16`、Cloud Build `f321dc67-1491-49a3-87b3-077abf922a20` SUCCESS、image `367-farm-box-6664e16`、digest `sha256:9c6dcd9294d5...`、revision `yoshilover-fetcher-00404-kds` 100%、`/health` OK。published 68610 は未更新。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `368-QA-x-web-post-quote-dedupe-title` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #37。68628 / 68633 型。Xポスト + 引用記事を残し、Web-only duplicate を消費する方向へ修正。WP既存 post は 68628 / 68619 を publish のまま title + 本文構成補正、68633 は draft duplicate として trash。関連記事は X記事では literal detail overlap 必須にする。py_compile / compileall / AST PASS。関連 pytest 103 passed。commit `8b0b420`、Cloud Build `26d505cd-8fe3-43cd-a99b-aceb93cf7766` SUCCESS、image `368-x-web-8b0b420`、digest `sha256:d8414f326603...`、revision `yoshilover-fetcher-00405-t9l` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `369-QA-short-player-event-title-quality` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #38。68539 / 68608 型に加え、68795 型の短すぎる引用 title `菅野智之「阿部さん」` を追補。`選手名 + 薄いイベント語` / `選手名 + 短い引用` title を、同じX source本文内の literal な `2回適時打` / `3安打1打点猛打賞` / `日米通算150勝` などで補強する。68795 は title + JSON-LD headline を `菅野智之が日米通算１５０勝 ... 歴代捕手に感謝` に補正済み。follow-up commit `d3e2e9b`、Cloud Build `192a645c-1460-4d89-ba5d-b2a37845765a` SUCCESS、image `369-milestone-title-d3e2e9b`、digest `sha256:5873728c...`、revision `yoshilover-fetcher-00411-4xl` 100%、`/health` OK、新 revision ERROR logs 0。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `370-QA-staff-x-web-dedupe` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #39。68649 / 68653 型。368 の `player_name` 前提から漏れた杉内投手コーチなどの staff/manager/coach quote X+Web 重複を、staff subject + quote/event token で同 fire 消費する。WP既存 post は 68649 publish を X embed + source excerpt のまま title/headline 補正、68653 duplicate は trash 済み。py_compile / compileall / AST PASS、関連 pytest 104 passed。commit `e98bb8c`、Cloud Build `3df7fcf2-b845-46d4-84f5-a56e9bf307d1` SUCCESS、image `370-staff-x-web-e98bb8c`、digest `sha256:6189023b74d9...`、revision `yoshilover-fetcher-00407-h9v` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `371-QA-disable-game-live-source-policy` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #40。user 方針「絞らないでいい。重複だけがいや」。試合あり 17:00-21:30 JST の `game_live_source_policy` をデフォルト解除し、サンスポX/Webなど通常sourceも流す。重複は既存 same-fire / cross-family / X+Web dedupe gates で止める。py_compile / compileall / AST PASS、関連 pytest 41 passed。commit `639040e`、Cloud Build `dec33608-4335-40fe-8b63-9867d3e5f79d` SUCCESS、image `371-source-unlock-639040e`、digest `sha256:86370ac5b7e6...`、revision `yoshilover-fetcher-00408-l7b` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更、追加 publish/mail 回避のため手動 `/run` は未実行。自然 fire / log evidence 後に Issue close |
| `372-QA-human-readable-title-context-repair` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #41。68537 / 68622 型。`内海哲也投手コーチ、先発` / `井上温大「ミスドの券」` / `関連情報` / generic `選手「...」` のように人間に記事の核が伝わらない title を、source title / summary の literal context で恒久補正する。WP既存 post は 41 件の title + schema headline を status 確認後に補正済み、検証 `headline_mismatches=0`。py_compile / compileall / AST PASS、関連 pytest 104 passed + 3 xfailed + 16 subtests。commit `097c4c8`、Cloud Build `9faa589c-fa6d-40c9-930b-3c80e80fd076` SUCCESS、image `372-title-context-097c4c8`、digest `sha256:1f557f4c...`、revision `yoshilover-fetcher-00409-jkg` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更、手動 `/run` は未実行。自然 fire / log evidence 後に Issue close |
| `373-INSIGHT-defense-player-comparison-table` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #42。68665 型。守備系データ記事で title が選手主語なのに本文が球団順位表になる穴を、UZR / 守備率 article renderer で同ポジションの選手別比較へ変更。セ・リーグ選手名が十分なら `セ・リーグ選手別`、他球団 player rows が薄い場合も球団順位へ戻さず `巨人選手別` fallback。WP既存 post 68665 は status `publish` 確認後、title/content のみ更新済み、status 維持。py_compile / compileall / AST PASS、関連 pytest 103 passed。commit `3260e7a`、Cloud Build `afc27377-94d5-4756-9694-16daae910588` SUCCESS、image `insight-nightly:373-defense-player-3260e7a`、digest `sha256:7a3f569b...`、Cloud Run Job generation `52`。Scheduler / env / Secret / X / SNS / mail 条件は未変更、executionCount `40` 維持で手動 insight execute は未実行 |
| `374-x-post-mail-dedup-starvation-fallback` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #43。353〜355 の手動確認 mail が 24h dedup ledger を埋め、15:00 は 1 件、17:30 は 0 件で自然 mail が枯れた問題を修正。dedup は維持しつつ、dedup 後候補が default 3 件未満なら dedup-safe 候補を先頭に残して dedup なし候補で backfill。py_compile / compileall / AST PASS、x-post-mail 関連 pytest 107 passed。commit `c939b77`、Cloud Build `7a6ae843-f49c-4a23-90ed-af1d57831f30` SUCCESS、image `x-post-mail-lane:374-dedup-starvation-c939b77`、digest `sha256:739e16042fbb...`、Cloud Run Job generation `11`。Scheduler / env / Secret / WP / X / SNS は未変更、追加 mail 回避のため手動 execute は未実行。22:30 自然 fire は更新直前の旧 image で候補0件、次回 2026-05-17 07:00 JST 自然 fire で観察 |
| `375-QA-paper-layout-social-promo-skip` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #46。68812 型。`RT スポーツ報知 レイアウト担当: 5/17付 スポーツ報知` の紙面告知RTが `5連勝` / 選手語で social_news rescue され、半端な本文の記事になる穴を修正。`レイアウト担当` / `紙面レイアウト` / 日付付き新聞紙面告知は trusted social rescue / weak social rescue / template v2 / main intake で hard stop し、`paper_layout_social_promo_skip` を出す。py_compile / compileall / AST PASS、関連 pytest 113 passed。commit `ed237ea`、Cloud Build `3daeb97b-9252-4fb6-82d8-bc546ae46403` SUCCESS、image `375-paper-layout-ed237ea`、digest `sha256:3f2aff2f...`、revision `yoshilover-fetcher-00412-4kg` 100%、`/health` OK、新 revision ERROR logs 0。Scheduler / env / Secret / X / SNS / mail 条件は未変更 |
| `376-QA-person-tag-routing-and-noindex` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #49。選手・首脳陣・OBの人物タグを事前作成し、RSS記事作成時は既存 WP tag ID にだけ自動付与する。2選手記事は2タグ、runtime tag新規作成なし、missing / ambiguous / no hit は log 化。py_compile PASS、person tag / WP tag / noindex / RSS integration 16 passed、WP client 66 passed、RSS related 41 passed / 3 xfailed。WP tag sync `ok_count=173` / `missing_count=0`、commit `a995071`、deploy source HEAD `242aab2` includes `a995071`、Cloud Build `43fb75f9-4f92-4b79-a204-08cc8d343d3d` SUCCESS、image digest `sha256:52ac886e...`、revision `yoshilover-fetcher-00421-vzd` 100%、`/health` OK、新 revision ERROR logs 0。WP plugin upload 後、tag archive `吉川尚輝` で `x-robots-tag: noindex, follow` と HTML robots noindex を確認。Scheduler / env / Secret / X / SNS は未変更。自然 RSS fire で実記事 tag 付与 evidence 待ち |

deploy: `insight-nightly:ca03019` / digest `sha256:a71bbe0f943c969349a61413da3a6addb016f8286e506229e0b3a3a0a76bc41f`。Cloud Build `19c2e97d-f4f9-48e9-8db4-7a303003892e` SUCCESS。Scheduler / env / Secret は未変更、手動 execute 未実行。

test: deploy 前 data-insight 関連 pytest 231 passed。full unittest は既存の `manual_intake_service` socket PermissionError、`manual_intake_service_x_post` 403 expectation、`duplicate_prevention_golden` logger call-count で赤のまま。

様子見リスク: 記事減りすぎ / まだ多い / mail過多 / 既存投稿 backfill 未実装 / title期間必須 runtime guard の live 観察待ち。次 action は次回 Scheduler 自然 fire のログ観察。

### x-post-mail scheduler 403 fix (2026-05-16 13:40 JST)

353〜355 の X投稿候補 mail lane は code / manual execute / mail send / GCS dedup write は成功していたが、07:00 / 12:00 の自然 Scheduler fire が HTTP 403 `PERMISSION_DENIED` で失敗。原因は `x-post-mail-*` Scheduler jobs の OAuth service account が `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com` になっていたこと。正常稼働中の `data-insight-*` と同じ `487178857517-compute@developer.gserviceaccount.com` へ 5 jobs だけ更新済み。schedule / env / Secret / Job image / mail body は未変更。手動 execute は追加 mail 回避のため未実行、次回自然 fire は 15:00 JST。

### 357 x-post-mail period 表示 tuning (2026-05-16 JST)

user 指示「日付だけでは分かりにくい」「直近5試合 / 直近10試合を前面」「7月成績のような月別は分かりやすい」「大手が出す全期間はいらない」を受け、`doc/active/357-x-post-mail-human-period-labels.md` を起票。repo 実装 + targeted tests 完了、status `REVIEW_NEEDED`。2026-05-16 follow-up で production GCS DB 更新状況を確認し、all-NPB DB 化後の直近5/10試合 window を `batting_logs` 巨人 row で絞る修正と、DB最新試合日が2日超古い場合に X 投稿候補 mail を候補生成前に止める freshness guard を追加。2026-05-16 14:35 JST `x-post-mail-lane:357-db-freshness-15ff032` deploy 済み、Job generation `9`。X / SNS live post、Scheduler、env、Secret、WP publish は未変更、手動 execute は追加 mail 回避のため未実行。

### insight-nightly same-day DB + no-season auto publish fix (2026-05-16 14:49 JST)

user 指示「DB当日更新はやらないの？」を受け、`--auto` target を 15:00 JST 以降は当日、朝/昼は前日に切替。auto publish に残っていた `season` split / vs opponent 経路を `weekly` / `last_7d` へ変更。commit `2949f98`、Cloud Build `a9574fbf-f26c-4a17-b977-cb56f7e94f72` SUCCESS、image `insight-nightly:358-sameday-auto-2949f98`、digest `sha256:3afff4dfe4e80791e833c149a41d3f973e9f005365f4033b599042feba8b707a`、Cloud Run Job generation `47`。Scheduler / env / Secret は未変更、手動 execute は追加 publish/mail 回避のため未実行。

### 358 local production DB pull tool (2026-05-16 JST)

DB 同士の「同期」はしない方針で決定。production source of truth は GCS `insight.db`、local `data/insight/insight.db` は生成物として扱う。ローカルが古いことによる誤判断だけを防ぐため、`src/tools/pull_insight_db_from_gcs.py` を追加し、default `/tmp/yoshilover-insight-latest.db` へ download-only pull + 最新試合日 / 巨人最新試合日 / row count を JSON 表示する。local Python に `google-cloud-storage` が無い場合は `gcloud storage cp` fallback。targeted pytest `34 passed`、production GCS read-only smoke は latest `2026-05-16` / Giants latest `2026-05-16` / staleness `0`。Cloud Run / Scheduler / env / Secret / GCS upload / WP publish / mail / X / SNS は未変更。

### 359 x-post-mail subject visibility (2026-05-16 JST)

user 指示「他の自動通知も来るから分からない」を受け、X 投稿候補 mail の件名を `📮【要確認：巨人データX投稿候補 N件】午後 2026-05-16 15:00 JST` 形式へ変更。本文冒頭にも「公開通知ではない」ことを明記。commit `902689c`、Cloud Build `a89b7e8e-b565-4c3f-aaab-40da89ec6611` SUCCESS、image `x-post-mail-lane:359-subject-902689c`、digest `sha256:b5c6aa968959351a691337c256f1d14671be4b539894c91db61ebd600824d120`、Job generation `10`。targeted pytest `69 passed`、関連 `105 passed`。候補生成 / DB / GCS dedup / SMTP 宛先 / Scheduler / env / Secret / WP publish / X / SNS は変更しない。手動 execute は追加 mail 回避のため未実行。

### 360 INSIGHT defense table comparison format (2026-05-16 JST)

user 指示「UZR は出したいが球団ごとの表形式比較が欲しい」「方針として全てが表形式」を受け、`doc/active/360-INSIGHT-defense-table-comparison-format.md` を起票。未来生成分の `anomaly_article_publisher` で、UZR / 守備率記事をセ・リーグ球団別 table 主体に変更。シンプルデータ記事の `## データ` も箇条書きから table 化。「全てが表形式」は数値・比較・根拠を table に寄せる方針として記録。production DB copy preview では `泉口友汰 / 遊撃守備` が `セ・リーグ球団別 遊撃守備の簡易UZR、巨人 6/6位 -0.088（直近30日）` と6球団表で出ることを確認。commit `269fd37`、Cloud Build `7cf61309-f315-4fb9-9a2f-5ec130c26c23` SUCCESS、image digest `sha256:0e2abc58b2704a03eb8f49481dae1f3a858986b068cd087854b38a1594af72c7`、Job generation `48`。関連 pytest `100 passed`。既存公開 post / WP update / Scheduler / env / Secret / X / SNS は触らない。手動 execute は追加 publish/mail 回避のため未実行。

### 361 INSIGHT permanent table body and title contract (2026-05-16 JST)

user 指示「恒久対応」「title は巨人の選手の名前と指数と何位と期間」「巨人サイトだから」を受け、`doc/active/361-INSIGHT-permanent-table-body-and-title-contract.md` を起票。UZR / 守備率 title を `泉口友汰の遊撃守備、巨人は簡易UZR -0.088でセ・リーグ6/6位（直近30日）` 型へ変更し、本文のセ・リーグ球団別表は維持。`insight_quality_gate` に table contract を追加し、`## データ` / `## このデータについて` / ranking / 比較 section が table でない記事、または `## データ` が bullet list に戻った記事を publish/draft 投入前に止める。py_compile / compileall / AST PASS、関連 pytest `102 passed`、production DB copy preview PASS。commit `a9b208e`、Cloud Build `b027f92a-b3f7-4aed-b448-cdded17740fb` SUCCESS、image digest `sha256:b2fb813a542a0ce7b79ea8c395f939fa3027001ce88f97bca123c2c65877ff69`、Job generation `50`。既存公開 post / WP update / Scheduler / env / Secret / X / SNS は触らない。手動 execute は追加 publish/mail 回避のため未実行。

## 2026-05-14 EVENING session summary

### close 済(本 session)

| 区分 | ticket | commit | 備考 |
|---|---|---|---|
| impl | 342-INSIGHT(=旧 GH #21) | 多数 | data-driven ranking 自動 publish 基盤 LIVE。本日 Giants 12 件 + 球団 5 件 + 異常値 5 件 publish |
| impl | DATA-INSIGHT-continuous(=旧 GH #25) | 多数 | 継続改善 system 稼働。異常値検出 8 種 + ランキング 4 軸 + 球団ランキング 7 軸 |
| ops | Cloud Scheduler 7 trigger 配備 | 設定 | 02/07/12/15/17/20/21 JST、`ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1` で Giants のみ auto publish |
| fix | SVG inline-style fix | `7da3956` | WP wpautop で `<style>` が `</p><p>` 分割していた bug、既存 17 記事一括 patch も済 |
| ci | xfail 4 pre-existing | `578a598` | baseline 一致 fail を unblock、regression 検知力は xfail で保持 |

### 残 open(別 actor lane)

| ticket | status | blocker |
|---|---|---|
| 344-INGEST(=GH #24、別 actor lane) | YouTube 字幕 + ch 拡充進行中 | 触らない、別 actor の lane |

### waiting(park、別 session 着手)

| ticket | status | next action |
|---|---|---|
| `doc/waiting/345-INSIGHT-fielding-and-equal-area-ratio.md` | PARKED | NPB box score の守備項目 audit、A path なら自律実装、B path なら user 判断 |

### close 済(旧)

| # | ticket | status | blocker |
|---|---|---|---|
| #21 | 342-INSIGHT | Phase 0 audit + Phase 1 spec done、impl 未着手 | last_30d batter snapshot 12 球団分 (各 5+ 選手) 蓄積待ち、想定 7-21 日後 |

next session: 朝 06:00 自然 fire 後の log 観察 (silent gap §5 in handoff doc) + #21 着手判断 (data 充足後)

## folder cleanup note(2026-05-02)

- Active folderから、明確な HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY / READY_FOR_AUTH_EXECUTOR を waiting へ移動。
- `205-COST` は done/2026-05 へ移動。
- READY / REVIEW_NEEDED で現場が拾う可能性のある ticket は勝手に close していない。

## いま active に残すもの(2026-05-13 lock)

| ticket | status | 判定 | 次 action |
|---|---|---|---|
| **303-rollback-2026-05-08-frontend-rich-body** | LIVE_VERIFIED (Tier 1+2 audit pass) | manual-intake-service / yoshilover-fetcher 両方 `d34072a` 反映済み | manual-intake の rich body 装飾を 5/8 朝 audit Tier 1+2 で 5 件 fix 反映済み。Tier 3 (49 件 doc-only) は別便、現場は live 観察のみ |
| **MANUAL-INTAKE-QUALITY-PARITY-2026-05-08** | DESIGN_REQUIRED | **user 判断待ち**: 「手動 vs 自動」のどの軸(本文長 / 装飾 / 自動化)を直すか | 5/8 PM session 調査済、apply_rss_pipeline_enrichment の nomotoke marker gate を発見、現状 RSS auto は marker 付与なしで装飾 skip。user に A/B/C/D 軸を提示済み、回答待ち |
| **FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08** | READY_FOR_AUDIT | 5/7 enrichment 装飾(ToC / 順位表 / share / tag chip / AI badge / JSON-LD 等)が live で 0% / 100% gap。¥0、デグレ 0 の audit + narrow fix | Phase A 受動 audit から開始、root cause 特定 → narrow fix → unit test。3 auto jobs の redeploy は別 ticket |
| **H3-STRUCTURE-UNIFY-2026-05-08** | READY_FOR_IMPL | H3 が 30+ 種類混在 → 12 set に統一、「📣 関連投稿」3 形式を「💬 ファンの声」に統一、Gemini prompt 自由生成禁止 | ¥0、4-6h、Phase A nomotoke renderer 統一から |
| **DIGEST-DAILY-MORNING-2026-05-08** | READY_FOR_IMPL | 朝まとめ 1 日 1 本(前日 + 翌日 + 順位 + ファン声 を集約)。既存 block 再利用 | ¥0、4-6h、giants-morning-catchup 内に組み込み |
| **SIDEBAR-WIDGETS-2026-05-08** | READY_FOR_IMPL | sidebar 5 widget(直近5試合 / 順位 / streak / 次戦 / 1年前の今日)。WP plugin 側 | ¥0、6-8h、phase 分割で順次 |
| **305-QA featured media source priority** | LIVE_DEPLOYED, USER_ACCEPTANCE_PENDING | source eyecatch を最優先し、同一 source image の WP media reuse を優先。source 不在時は東京ドーム写真 fallback。legacy Ichiro mixed media `36062` は unsafe として除外 | Codex B が repo-only で impl/test/deploy 完了。revision `00293-7lc`、`guarded-publish` / `publish-notice` success、deploy 後新規記事 0 件。次の自動生成 window で user が受け入れ判断。publish / mail / scheduler / env / Cloud Run 設定は追加変更なし |
| **319-QA fetcher topic dedup and slot fill** | REVIEW_NEEDED | 自動起動時に同じ話題の重複記事が10枠を消費する問題を narrow 修正する ticket。head/bat contact 事故の再現テスト赤→緑、related/full pytest green | diff review + commit 判断待ち。publish / mail / scheduler / env / Cloud Run / SEO / source追加は不可触 |
| **CATEGORY-RESTRUCTURE-2026-05-08** | DESIGN_REQUIRED | 「コラム」catch-all 解消、「試合中継」新 category 抽出、巨人 tag 化 | user 判断必要(WP admin で新 category 作成)、Claude は設計 + automation script |
| **EXTERNAL-MONITOR-APPS-SCRIPT** | READY_FOR_USER_SETUP | user 作業 10 分(GAS で完全独立 ping) | 明日朝 yoshilover infra 全死シナリオ用の独立 safety net、user 任意 |
| **334-QA-player-voice-multi-source-digest-subtype** | DESIGN_LOCKED / READY_FOR_PHASE_0_AUDIT | 2026-05-14 user chat lock。のもとけ風 multi-source digest subtype。title 3-token literal assembly(player「セリフ20-40字」event)、AI 禁止、player-agnostic、forward-only、複数 web 媒体サイト集約 | Phase 0 read-only audit から開始。`title_template_assembler.py` 追加位置 + `rss_fetcher.py` clustering hook + source extractor coverage を audit、結果 doc 追記。memory lock: `feedback_title_no_ai` / `project_multi_source_digest_subtype` |
| **OPERATING_LOCK** | ACTIVE_LOCK | **必要。常時参照** | 事故防止ルール。変更は慎重に、src 実装とは混ぜない |
| **assignments** | ACTIVE_BOARD | **必要。現在地** | 本ファイル。active を増やしすぎない |

## 認識しているが今 session 触らないもの(明日朝 06:00 検証 window 関与)

| 項目 | 状態 | 触らない理由 |
|---|---|---|
| **`guarded-publish:eb38006-job`** (job) | 5/8 朝 06:40 JST build、scheduler `*/30 * * * *` ENABLED、明朝 06:00/06:30 fire | 5/8 朝 emergency 10 commit 未反映で draft 昇格挙動が古い可能性。redeploy が必要だが scheduler / image 変更は user 同意境界(autonomous_scope_v2)。明日朝検証で挙動異常があれば次便で扱う |
| **3 auto jobs(broadcast / lineup / postgame)** | `manual-intake-service:b432801`、5/8 0bf8900 / d34072a 未反映 | 明日朝 06:00 検証 window 範囲外(11:30 / 17-18 / 22:30 fire)、検証直後の判断で OK |
| **`draft-body-editor:c796c77`** (job) | 5/2 build、scheduler `0 */3 * * *` 06:00 fire | 5/8 emergency 範囲外、観察のみ |

## done へ送ったもの

仕様変更後も役割は残るが、実装と live 反映が済んだため active から外した。

| ticket | close 判定 |
|---|---|
| **234-impl-1** farm_result / farm_lineup mail UX | `75d9407` で実装済み、後続 234-impl-6 で本文側も補強済み |
| **234-impl-2** first-team postgame / lineup mail UX | `9e98c96` で実装済み |
| **234-impl-3** program / roster notice mail UX | `dd158fb` で実装済み |
| **234-impl-4** injury_recovery / default_review mail UX | `ac23529` で実装済み |
| **234-impl-5** first-team postgame body hardening | `bc3b771` で実装済み、live image `cf8ecb9` へ反映済み |
| **234-impl-6** farm_result / farm_lineup body hardening | `7567e6f` で実装済み、live image `cf8ecb9` へ反映済み |
| **242 parent / 242-B** auto-publish incident + entity contamination | 子 ticket 実装済み。63844 型は `16304f2` + `cf8ecb9` で detector live |
| **243 emit observability** | `499966d` で実装済み、draft-body-editor / fetcher 系の observability lane に反映済み |
| **244 numeric guard** | `f2cc8a3` で実装済み、guarded-publish / X suppress の本線に反映済み |
| **244-B repair anchor** | `e04eee1` で実装済み、後続 wire 完了 |
| **244-followup subtype-aware severity** | `9074c8a` で実装済み |
| **244-B-followup stub to module wire** | `cf8ecb9` で実装済み、draft-body-editor image へ反映済み |
| **278-QA RT title cleanup** | `5a253a2` (TITLE-SEO-POLISH-001) で RT prefix 除去 + 末尾 filler trim 実装。yoshilover-fetcher / manual-intake-service / 3 auto jobs に live 反映済み |
| **279-QA mail subject clarity** | `6349995` (MAIL-SUBJECT-DETAIL-001) で件名 prefix を 公開済｜subtype / 要review｜reason / hold｜reason / 要確認(古い候補)｜subtype に拡張。publish-notice job 後段 rebuild(`b816f06-job`)に live 反映済み(2026-05-08 close) |
| **280-QA summary excerpt cleanup** | `74b0cec` (MAIL-MINIMAL-BODY-001) で本文を title+URL のみに簡素化したため summary を磨く意味なし。publish-notice job に live 反映済み |
| **304-QA player / manager common quality guard** | `6fb818a` で player / manager 共通品質 guard を実装し、Cloud Run revision `yoshilover-fetcher-00285-5bg` へ deploy 済み。post-deploy `/run` 完走、`guarded-publish` / `publish-notice` manual trigger success、運用継続可 |
| **246-viral-topic-detection** | 8 日 parked。SNS バズ検出 → 既存 RSS 裏取り → routing 構想は良いが、現フェーズ(noindex 検証 + 本文品質 + cost)と競合。再着手したくなれば doc/done/2026-05/ から復元 |
| **247-QA-postgame-strict-slot-fill-poc** | 8 日 parked。LLM JSON 抽出 + slot-fill POC は野心的だが LLM 本文生成に踏み込む変更で、現 policy(LLM 本文補完禁止)と衝突。再着手時は scope 再設計必要 |
| **254-QA-starter-innings-normalization** | 8 日 parked。投手回数表記揺れ統一 helper 構想。fact_consistency false negative の対策だが、現状観察で具体被害が顕在化していない。被害が見えたら再起 |
| **245 front hide auto-post category label** | 2026-05-07 audit で実装済 verify 完了。`yoshilover_063_is_internal_auto_post_category` helper + 11 callsite で sidebar/article-card/related に適用済 |
| **277-QA title player name backfill** | `src/title_player_name_backfiller.py` + rss_fetcher 統合済、prod live。tests pass |
| **229 Gemini cost governor + LLM call reduction** | `ENABLE_PER_POST_24H_GEMINI_BUDGET=1` + preflight gate ON 等、主要 sub 全部 prod 反映済 |
| **250-QA-1 manager_quote_zero_review** | rss_fetcher の `MANAGER_QUOTE_REVIEW_SUBTYPES` + event emit 実装済 |
| **250-QA-3 fetcher weak generated title** | `is_weak_generated_title` (title_validator.py) + 「前日コメント整理」「ベンチ関連の発言ポイント」phrase 入り |
| **275-QA github-actions tests failed audit** | CI 直近 3 run 全 SUCCESS、回復済 |
| **281-QA farm_result backlog allowlist** | guarded_publish_runner の `BACKLOG_NARROW_FARM_RESULT_SUBTYPES` + 24h cap 実装済 |
| **282-COST gemini preflight article gate** | `ENABLE_GEMINI_PREFLIGHT=1` prod env で ON 済(memory 282 CONDITIONAL_USER_GO 達成) |
| **289-OBSERVE post_gen_validate mail notification** | `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` ON、silent skip 解消済 |
| **290-QA weak title rescue backfill** | `weak_title_rescue.py` + `ENABLE_TITLE_GENERIC_COMPOUND_GUARD` 等 5 関連 ENABLE_* flag prod ON |
| **293-COST preflight skip visible notification** | `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1` ON |
| **297-OPS pause codex-shadow-trigger** | scheduler state = PAUSED、実行済 |
| **248-MKT-2/3a same-game articles linking + display matrix** | parked、現在の運用ループ閉鎖 priority より外。再開時は doc/done/2026-05/ から復元 |

## waiting へ送ったもの

| ticket | 理由 | 戻す条件 |
|---|---|---|
| **205 GCP runtime drift audit** | 必要だが、今の本文ハルシネ対策の実装ではない。定期監査として待機 | Cloud Run image / Scheduler / logs に不整合が疑われた時 |
| **238 night-draft-only + morning report** | 必要だが、まず 234/244 の本文品質を安定させる。夜間運用は次の運用改善 | 本文品質が落ち着き、夜間 publish/mail 抑制を入れる段階 |
| **246-MKT today giants fan guide** | HOLD。247-QA amend と postgame strict 試合日観察が先。現場に投げない | 246-MKT 判断後に、必要なら実装 ticket として個別に戻す |
| **255-MKT fan guide expansion + comment badge** | HOLD。248 系の既存 ticket と採番衝突しないよう 255 に採番 | 246-MKT 観戦ガイドが成立し、コメント/反応導線を検討してよい時 |
| **249-INGEST live game ingestion expansion** | HOLD。Cloud Run / Scheduler 影響が大きい構想 | user が live ingestion の負荷とリスクを理解して明示 GO した時 |
| **256-QA manager/player quote strict subset** | HOLD。250 系の既存 ticket と採番衝突しないよう 256 に採番 | 247-QA の試合日観察後、コメント系を短い事実記事として分ける価値がある時 |
| **260-MKT fan-original article types and templates** | HOLD / design only。RC / T1 / 262-QA / 263-QA observation 完了 + user 明示 GO 後に 261-MKT-PILOT 起動判断 | 大手新聞の後追いではない巨人ファン向け独自記事型 6 型のテンプレ設計、実装しない |
| **261-MKT-PILOT (予約)** | HOLD / 261-PILOT 起動条件 達成後 RESUMABLE | 260-MKT で設計した 6 型から手動/半自動で 3 型 pilot、3-5 本評価、実装ではない |
| **234-impl-7 probable_starter / pregame body hardening** | READY_FOR_AUTH_EXECUTOR。repo実装済みだが残りは live handoff / observation 判断のため waiting へ移動 | live反映が必要な時だけ、Acceptance Pack と rollback target を確認して戻す |
| **291-OBSERVE candidate terminal outcome contract** | WAITING_PARENT / subtask-9 + subtask-10b live apply 完了。fetcher image `e0a58bb` / revision `00186-9cl` へ更新し、`ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE=1` と `ENABLE_POSTGAME_STRICT_FACT_RECOVERY=1` を反映、既存 narrow flags 維持確認済み | 30-60min verify。Scheduler 次回 fire 以降で `weak_title_subtype_aware` / `postgame_strict_fact_recovery` event と scope-eligible postgame candidate の publish/review outcome を観測する。親 ticket 自体は waiting 維持、global gate 緩和はしない |
| **318-A..E social video full connect** | 318-C REVIEW_NEEDED / 318-A,B,D,E READY_DOC_ONLY。YouTube / Instagram / OB動画の完全接続を5本に分割。初期はreview/draft優先、publish/mail/scheduler/env/deploy/X/SEO不可触 | 318-C safe title fallback は repo実装 + full pytest PASS。次に進めるなら 318-A YouTube registry intake を小さく実装GO。 |
| **319-QA fetcher topic dedup and slot fill** | REVIEW_NEEDED。次の記事公開から重複話題で10枠を消費しないための narrow fix ticket | 再現テスト赤→緑、`src/rss_fetcher.py` 候補選別のみ修正済み。diff review + commit 判断待ち。deployは別GO |
| **320-FRONT scroll ads UIUX AdSense slot control** | READY_FOR_IMPL_AFTER_USER_GO。のもとけ型の scroll / sticky AdSense slot UIUX。dummy-only ではなく、既存または user 確認済み AdSense slot 前提 | まず Phase 0 read-only audit で repo / live DOM / WP 実設定を確認。記憶から再構成 / silent skip / 自己評価OKは禁止。publish/mail/scheduler/env/Cloud Run/GitHub Actions/SEO は不可触 |
| **323-QA source body excerpt clean truncation** | BLOCKED_USER_DIFF_REVIEW。`314-QA-rss-source-body-excerpt-followup` 関連。ブログ本文の `📖 本文抜粋` が600文字化後も途中切れ / UI・関連記事混入に見える問題を狭く扱う | repo local 実装 + 回帰テスト + full unittest OK。diff review と commit 判断待ち。publish / mail / scheduler / env / Cloud Run / X / SEO / featured_media は不可触 |
| **251/252/253/264/274/283/288/294/295/296** | HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY 系。active から waiting へ整理 | 各 ticket の解除条件または user GO が来た時 |

## いま動かす指示(2026-05-13 lock)

### close 済 (2026-05-13)

- **RESTORE-2026-05-08-MORNING-RELIABILITY**: LIVE_VERIFIED → `doc/done/2026-05/` 移動。5/13 朝 (06:01 / 07:01 / 08:01 JST) で投稿=9 / 2 / エラー=0、cron 安定稼働確認
- **2026-05-12 evening P0 UnboundLocalError incident**: hotfix `802511f` + `b8a7f01` 復旧確認済 (revision `00417-wuw` 100%、5/13 朝 publish 投稿=9/2 / エラー=0)。incident log は `docs/handoff/session_logs/2026-05-12_evening_INCIDENT_publish_unbound_local.md` (verify note 追記済)

### user 任意作業

- B 案 GAS 独立 ping 設定(10分): `doc/active/EXTERNAL-MONITOR-APPS-SCRIPT.md`
- 重複記事削除判断: 山野5勝 4本(64878/64879/64882/64883) / 5/6試合結果 2本(64983/64985) / 三塚二軍 2本(64861/64945)
- 若手 17人 eyecatch upload(WP media に upload で fallback 解消)

### 現場 (Claude / Codex) の不可触

- すでに deploy 済の 4 image を勝手に rollback しない
- 5/8 設定済 5 env flag を user 確認なしに変更しない
- `PUBLISH_NOTICE_BURST_THRESHOLD=-1` は user 同意済、変更しない
- 04-06時 publish-notice silence は user 同意済、戻さない
- giants-morning-catchup 04:30 schedule は user 同意済、戻さない

## 役割

| 略号 | 役割 | やること |
|---|---|---|
| **Claude** | 現場管理 / accept / push / live監視 | 開発しない。src/tests編集しない。commitしない |
| **Codex A** | ops / GCP / WP / mail / build / scheduler infra | live mutation は authenticated executor 境界を守る |
| **Codex B** | evaluator / validator / article quality / numeric / template | 234-impl-7 など品質系を narrow に実装 |
| **User** | 最終判断 | 重要な live mutation / WP記事判断 / scope拡張だけ判断 |

Codex C / Codex-M は使わない。

## ad hoc live ops

| lane / scope | status | 次 action |
|---|---|---|
| **Lane FF / BUG-004+291 replay-window dedup (Task 37)** | LIVE_APPLIED | `publish-notice` image `4231805` + `ENABLE_REPLAY_WINDOW_DEDUP=1` を反映済み。次の manual replay / scheduler overlap で `DUPLICATE_WITHIN_REPLAY_WINDOW` 観測を確認する |
| **Lane JJ / BUG-004+291 fetcher fan-important narrow exempt** | REPO_IMPL_READY | code commit `1ccda1b` 済み。次は authenticated executor が `yoshilover-fetcher` image `:1ccda1b` build/update + `ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT=1` apply、その後 5-15 分 fetcher cycle で `fetcher_fan_important_narrow_exempt` event と rescued draft/publish terminal state を観測する |
| **Lane KK / 64424-64461 incident ledger + publish-forward audit** | LEDGER_READY | 38件棚卸し完了。分類 `B4 / C2 / D6 / E23 / F3`、safe rescue `0`。`64437` / `64447` は publish-notice state drift で STOP lock、次は Claude が ledger review / push / follow-up 起票 |
| **Lane MM / 64437 publish-notice phantom publish marker narrow fix** | REPO_IMPL_READY | repo audit + strict-stamp fix + tests 完了。次は authenticated executor が `publish-notice` image build/update と `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP=1` apply、その後 `64437` / `64447` 再発有無と new history stamp を観測する |
| **Lane LL / BUG-003 64424 revert actor + WP revert guard** | REPO_IMPL_READY | `64424` は repo-visible evidence 上 true revert ではなく、`publish_notice` direct-publish seed による phantom publish marker。`src/wp_client.py` に `ENABLE_WP_REVERT_AUDIT_LEDGER` / `ENABLE_WP_PUBLISHED_REVERT_GUARD` を追加し、publish 済みから `draft/private` への repo-owned mutation を audit/block できる状態にした。`tests.test_wp_client` と `tests.test_guarded_publish_runner` pass。次は Claude が doc review / commit review / 必要なら authenticated executor へ build+env plan を handoff |
| **Lane NN / 64432-64461 quality NG 3件 audit + ticket assignment** | REPO_DOC_READY | `64432` は 277 insufficiency + 290未live、`64453` は元巨人OBの非野球 relevance 漏れ、`64461` は Blue Jays→Giants entity contamination と判定。次は Claude が ledger review / push / per-id live judgment(A/B/C) と follow-up ticket 起票 |
| **Lane PP / article body quality v1 active repair + per-id preview** | REPO_IMPL_READY | Lane OO guard維持のまま `ENABLE_H3_COUNT_GUARD` / `ENABLE_ENTITY_MISMATCH_REPAIR` を追加。preview runner と 5 candidate dry-run ledger を作成し、full pytest は `2246 pass / 4 pre-existing fail` で据え置き。次は Claude が preview ledger review / commit review / user preview judgment を進める |
| **Lane QQ / body template v2 narrow tune (related-post H4 + social tone cleanup)** | REVIEW_NEEDED | rollback 後の narrow fix として、v2 ON 時だけ `📌 関連ポスト` を `<h4>` へ降格し、`social_v2` fallback の「目を引きます」を除去。新規 preview test で live踏襲 3 sample の `H3<=2` / forbidden phrase 0 hit を確認済み。次は Claude が commit review / push / user preview judgment を進め、reflip は別便で扱う |
| **Lane B / RSS type classification narrow fixes (5 flags)** | REVIEW_NEEDED | `src/rss_fetcher.py` に 5 本の default-OFF flag を追加し、RSS 型 drift 修正を narrow 実装。`tests/test_rss_fetcher_type_routing_flags.py` を追加し、full pytest は `2315 pass / 4 pre-existing fail` で据え置き。次は Claude が commit review / push judgment を行う |
