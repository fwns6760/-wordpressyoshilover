---
session_date: 2026-04-30
topic: P0 公開復旧観察 + CI 緑化 + 229-COST 観察 + 275-QA push
participants: Claude Code (management), user (final judge)
status: IN_PROGRESS
---

# 2026-04-30 P0 公開復旧観察 session log

## 目的

OS 再起動で /tmp 上の前 session handoff を喪失。
本 session は (1) P0 公開復旧観察 (2) CI 緑化確認 (3) 229-COST 本番効果 read-only 観察 (4) 205-COST は HOLD 維持 を進める。
今後 handoff は /tmp ではなく **本ファイル series**(`docs/handoff/session_logs/<date>_<topic>.md`)に永続化する。

## 起点状態 (recover from repo / git / GCP)

### git / commit
- yoshilover repo HEAD = `856c01d` (275-QA test mock 追加)
- session 開始時点 origin/master = `22bc09b` (205-COST publish-notice incremental scan)
- session 内で 856c01d を push → origin = 856c01d に同期
- 直前の publish 復旧 chain:
  - dc02d61 267-QA publish-notice review/hold notification
  - 7667658 263-QA guarded-publish duplicate guard
  - d58941b 269-QA 263-same-source-url duplicate guard narrow relax
  - d7c7b07 270-QA+271-QA backlog-only narrow relax
  - a175f24 273-QA subtype resolution narrow + unresolved fallback
  - 453ee24 229-COST fetcher Gemini dedupe + cooldown
  - 22bc09b 205-COST publish-notice incremental scan
  - 856c01d 275-QA SyntheticDraftWPClient.list_posts test mock

### GCP image / 本番反映 (read-only describe)
- **yoshilover-fetcher** service: `:453ee24` (rev `yoshilover-fetcher-00172-brl`、100% traffic) → **229-COST 本番反映済**
- **publish-notice** job: `:dc02d61` (267-QA 時点) → **205-COST 未反映**(4 commit 遅れ)
- **guarded-publish** job: `:a175f24` (273-QA 時点) → **269/270/271/273 全部入り、本番反映済**
- **draft-body-editor** job: `:cf8ecb9` (244-B-followup 時点、本日 scope 外)

### Scheduler (read-only)
- giants-realtime-trigger */5 ENABLED 直近 03:26Z
- guarded-publish-trigger */5 ENABLED 直近 03:25Z
- publish-notice-trigger */5 ENABLED 直近 03:25Z
- giants-postgame / lineup / pre / weekend 系 ENABLED
- audit-notify-6x PAUSED(明示停止維持)
- yoshilover-fetcher-job PAUSED(旧 monolith、設計通り)

## P0 観察結果 (read-only logging read)

### guarded-publish (image `:a175f24`)
- 04-30 01:46Z (10:46 JST) に 2 件 `backlog_narrow_publish_eligible`:
  - post_id=63922 subtype=comment
  - post_id=64075 subtype=off_field
- これが user 報告「10:46頃に 3件 publish」の元(ログ上 2 件捕捉、3 件目は別 lane の可能性、要追跡)
- 269/270/271/273 narrow relax + 263-QA duplicate guard が live で動いている

### publish-notice (image `:dc02d61`)
- cursor-based scan log 形式は出ている(`cursor_before` / `cursor_after`)
- ただし skip=27000+ で実質 full-scan 挙動 = **205-COST incremental は未反映**(image label 通り)
- emit 実績(04-30):
  - 02:55Z 11:55 JST: emitted=1 post_id=64081「巨人二軍スタメン 当日カード試合前情報」review/hold mail
  - 03:20Z 12:20 JST: emitted=1 post_id=64087「橋上コーチ "新しいつば九郎じゃないの" ベンチ関連発言」review/hold mail
  - 他 trigger は emitted=0(候補なし、正常)
- mail 経路 = Team Shiny From、267-QA review/hold notification 機能稼働中

## 229-COST 観察結果 (fetcher rev `:453ee24`)

- 直近 04-30 00:00Z 以降の `gemini_cache_lookup` 44 件サンプル
  - **cache_hit=true: 33 件 (75%)** すべて `content_hash_exact`、`gemini_call_made=false`
  - cache_hit=false: 11 件 (25%) `cache_miss`、`gemini_call=true`
- effective に Gemini API call 削減中
- 削減効果は明日以降の Gemini cost log で集計する

## 275-QA push 効果 (CI 緑化)

- push 後 GH Actions run `25145944864` = **failure**
- ただし内訳: `Ran 1820 tests in 41.522s / FAILED (failures=1)`
- 改善: **5 errors → 1 fail**(SyntheticDraftWPClient AttributeError 5 件は完全解消)
- 残る 1 件: `test_fact_conflict_guard.test_body_validator_escalates_hard_fail_tags_without_repair`
  - actual `pregame_score_fabrication` ≠ expected `NO_GAME_BUT_RESULT`
  - 275-QA ticket doc で「ambient 既存問題、276-QA で後回し」と明記済
- CI 完全 green には 276-QA narrow fix が必要

## user 判断 (本 session 内)

- A: **275-QA push** → **go**(実施済、22bc09b..856c01d、03:33Z run)
- B: **205-COST publish-notice rebuild + job update** → **HOLD**(明日以降、P0 観察を壊さないため)
- C: **276-QA narrow fix 起票** → 推奨 **HOLD**、user 判断待ち

## HOLD 継続(本日変更なし)

- live_update ON
- ENABLE_LIVE_UPDATE_ARTICLES=1
- noindex 解放 / canonical / 301 / SEO 系
- Gemini call 増加
- X 自動投稿
- duplicate guard 全解除
- default/other 無制限公開
- Scheduler 頻度変更
- prosports 修正

## 次 session への引き継ぎ事項

1. **P0 観察継続**: publish/mail が継続して届くか、silent draft / silent backlog が出ないか
2. **229-COST cost 効果集計**: 24h 単位で `cache_hit` / `gemini_call_made` 比率と推定 cost 削減
3. **276-QA narrow fix**: user GO 後 Codex 便で起票(`tests/test_fact_conflict_guard.py:159` の expected_tag 修正 or src 側 stop_reason 文字列復元)
4. **205-COST 本番反映**: P0 安定確認後、image rebuild + publish-notice job update を別便で(deploy 判断は user)
5. **メール件名・記事タイトル・summary 改善**: チケット化のみ(CI と費用の後)
6. **GH Actions 連続 red 履歴**: 04-29 以降 8 連続 failure → 856c01d で 1 fail へ。次回 commit で完全 green 確認可

## session 進行ログ

- 12:40 JST | fire | 276-QA | codex_exec_276_qa | wait commit
  - target: tests/test_fact_conflict_guard.py:159 周辺の stop_reason 文字列差 narrow fix
  - 本番 src 変更必要時は停止して open_questions
- 12:46 JST | commit | 276-QA | 470dd9f | wait Claude push
- 13:05 JST | push | 276-QA | 856c01d..abbf212 | GH Actions run 25146349669 success
- 13:08 JST | draft | 277-280-QA quality series | doc/active/277-280-*.md (untracked) | 4 ticket draft
- 13:12 JST | fire | 277-QA impl | bvpiytqib | wait commits A (doc-only) + B (impl)
- 13:02 JST | commit | 277-280 ticket draft | 8313bc266fab351625ce5a26a20aa2e17cd785fd | doc-only
- 13:15 JST | commit | 277-QA impl | 8e9f5d826dff81a7328d0044a343971067bd996e | wait Claude push
- 13:50 JST | accept | 277-QA | full audit, REJECT 条件 8 項目 全部 NOT triggered | 中間 transient state での誤報告は plumbing fallback 由来
- 13:55 JST | verify | 277-QA pre-push | targeted test 6/6 pass + env/SEO/X/Team Shiny tokens diff 内 doc only | full pytest 1826 tests / 7 fails = abbf212 baseline で pre-existing local env 差 (CI green)
- 14:00 JST | push | 277-QA series 3 commits | abbf212..27166c5 | wait GH Actions
- 14:05 JST | verify | GH Actions run 25147379845 | success | 1820 tests / OK
- 14:10 JST | fire | 277-QA deploy (fetcher rebuild) | b4t5p3knc | yoshilover-fetcher:453ee24 → :27166c5
- 14:47 JST | deploy success | 277-QA fetcher | rev 00172-brl → 00173-2f9, traffic 100%, build sha256:5437e1d5 | wait giants-realtime-trigger 14:50
- 15:10 JST | draft | 281-QA farm_result backlog allowlist | doc/active/281-QA-*.md (untracked) | farm_result 24h age cap 設計
- 15:15 JST | fire | 281-QA impl | bn5afe7nw | wait commit (src + test + doc)
- 15:30 JST | commit | 281-QA impl | 6df049ca1ad76affbe2aa52487a3a8d469e3b947 | wait Claude push
- 15:55 JST | accept | 281-QA | 3 file scope clean, targeted 11/11, baseline 1837/7 maintained | full audit, REJECT 0
- 15:56 JST | push | 281-QA | 27166c5..6df049c | wait GH Actions
- 15:56 JST | draft | 282-COST gemini preflight gate | doc/active/282-COST-*.md (untracked) | env flag default OFF
- 15:57 JST | fire | 282-COST impl (parallel) | bjxqxwx7r | wait commit (flag OFF)
- 16:05 JST | draft | 283-MKT unique article requirements | doc/active/283-MKT-*.md (untracked) | design only、12 deliverables 全包含、子 ticket 284-287 設計込み
- 16:06 JST | commit | 282-COST impl | 325b47f3d3c81810d2dd5979198b718a7d8541c8 | wait Claude push
- 15:51 JST | diagnose | P0 source 不足 (not regression) | last 90min publish 0 / mail 0 / fresh candidate 0 / cache_hit 100% / silent 0 / Scheduler 動作中 | 16:50 lineup-a window 待ち
- 15:53 JST | accept | 282-COST | 3 file scope clean (src/gemini_preflight_gate.py 300+ / src/rss_fetcher.py +133 / tests +389), pytest 1845/7 baseline 維持, env flag default OFF | 281-QA deploy と同時 deploy しない
- 15:55 JST | push | 282-COST impl | a2777f9..325b47f | wait GH Actions
- 15:56 JST | fire | 281-QA deploy (guarded-publish rebuild) | bjuy1sqhq | guarded-publish:a175f24 → :6df049c
- 16:30 JST | diagnose | source 不足 誤診撤回 | post_gen_validate silent skip 真因(本日 22 件/trigger 全部 silent) | NNN/スポニチweb/サンスポweb 未登録 + hochi RSS error も並走原因
- 16:35 JST | draft | 289-OBSERVE post_gen_validate mail notification | doc/active/289-OBSERVE-*.md (untracked) | P0 equivalent silent skip 解消、env flag default OFF
- 16:36 JST | fire | 289-OBSERVE impl | bbqz20ubm | wait commit (flag OFF、ledger + publish-notice scan 拡張)
- 16:37 JST | commit | 289-OBSERVE impl | <see final report for commit hash> | wait Claude push (flag default OFF)
- 16:50 JST | deploy success | 281-QA guarded-publish | image :a175f24 → :6df049c, exec guarded-publish-cd9n6 success, silent hold 0, sent=0/skipped=97/refused=97 | farm_result <24h positive case 観察待ち
- 16:55 JST | fire | 282-COST flag OFF deploy | brjl03dmt | yoshilover-fetcher:27166c5 → :325b47f, ENABLE_GEMINI_PREFLIGHT 未設定維持(default OFF)
- 17:00 JST | deploy success | 289-OBSERVE flag ON | bm91l6f7o | fetcher :325b47f → :4be818d (rev 00175-c8c) + publish-notice :dc02d61 → :4be818d, ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1 両方、cap=10 dedup OK
- 17:10 JST | retroactive accept | 205-COST publish-notice incremental scan carried | commit 22bc09b → live image :4be818d | rollback せず、process violation 記録、release composition gate 追加(294-PROCESS) | live verify: cursor scan 動作、id=64104 review/hold mail sent=1、Team Shiny From 維持
- 17:11 JST | doc | 205-COST retroactive accept ticket | doc/active/205-COST-*-retroactive-accept.md (untracked)
- 17:12 JST | doc | 294-PROCESS release composition gate ticket | doc/active/294-PROCESS-*.md (untracked) | impl 別便、user GO 後
- 17:20 JST | doc | 288-INGEST HOLD 解除条件 修正 | 時間軸撤回、5 条件管理 (289 通知 / 290 救済 / 295 誤判定 / 候補終端契約 / Gemini call 抑制)
- 17:21 JST | doc | 295-QA subtype evaluator misclassify fix ticket | doc/active/295-QA-*.md (untracked) | live_update 誤判定救済、env 不変 contract 強調、impl HOLD until 289 安定 + 290 整理
- 17:35 JST | quality audit | 21 候補分類 | A=1 / B=6 / C=6 / D=4 / E=4 | LLM 不要救済対象 7 件特定
- 17:40 JST | draft | 290-QA weak title rescue backfill | doc/active/290-QA-*.md (untracked) | A/B 7 候補対象、env flag default OFF、人名+イベント AND narrow 例外
- 17:42 JST | fire | 290-QA impl | bw2q618tt | wait commit (regex/metadata only、Gemini 0 増、env 不変)
- 17:55 JST | commit | 290-QA impl | c14e269f5701715fd2b40d522b5e71c2faca04e8 | wait Claude push (flag default OFF)

## 後便 follow-up メモ

- runbook 追記: tagged traffic が既存 rev pinned の service は `gcloud run services update --image` 後に `gcloud run services update-traffic --to-revisions=<new>=100` が必要(本日 deploy で発覚、open_questions_for_claude より)

## デグレ試験 — Live 観察 checklist (deploy 後 5-10 min)

各 ticket deploy 後、image rebuild + job/service update 直後に以下を read-only 観察。
1 つでも fail なら rollback 判断 → 前 image (`yoshilover-fetcher:453ee24` / `publish-notice:dc02d61`) に戻す。

### 277-QA deploy 観察 (fetcher / draft-body-editor 系)

公開・通知導線(P0 死守):
- [ ] publish 候補があるのに publish 0 が継続しない (前 5 trigger と比較、前回 emit > 0 なら今回も > 0 期待)
- [ ] publish 後 publish-notice mail が届く (post_id 一致確認)
- [ ] review/hold mail も届く (267-QA notification 維持確認)
- [ ] silent draft / silent backlog / silent hold が増えない (前 24h 比較)

タイトル品質(本 ticket 主目的):
- [ ] WP draft の title pattern サンプル 5 本: 「選手」「投手」「チーム」だけで終わるものが消えているか
- [ ] 「巨人スタメン が〜」のような主語抜けが消えているか
- [ ] 補完できなかった候補は review_reason=`title_player_name_unresolved` で notification に上がっているか
- [ ] 人名捏造が起きていないか (source body に無い人名が title に出ていないか、5 サンプル目視)

安全系(回帰禁止):
- [ ] hard_stop 死亡/重傷/救急搬送/意識不明 不変 (24h log で hard_stop trigger 件数比較)
- [ ] duplicate guard 不変 (263-QA dedup ratio 維持)

コスト系(回帰禁止):
- [ ] Gemini call 増加なし (229-COST cache_hit ratio 75% 維持)
- [ ] log 爆発なし (24h log 行数比較、前日 ±20% 以内)

不変系(env / SEO / X):
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] Team Shiny From 維持 (mail header 確認)
- [ ] noindex / canonical / 301 不変
- [ ] X 自動投稿無し (X_POST_DAILY_LIMIT log 確認)

rollback 条件 trip:
- 候補有りで publish 0 が 30 min 継続
- review_reason=title_player_name_unresolved が全候補に出る (helper bug)
- mail 0 が 30 min 継続
- WP draft に source body に無い人名が出る (捏造)
- pytest 既存 test の failure
- GH Actions red

### 279-QA / 280-QA deploy 観察 (publish-notice 系)

公開・通知導線:
- [ ] mail subject prefix 5 種(公開済/要review/hold/古い候補/X見送り) が分類通り出るか
- [ ] subject 固有 token 「| YOSHILOVER」維持 (GitHub noreply 混入分離)
- [ ] Team Shiny From 維持
- [ ] 同一 post_id の通知爆発なし (267-QA dedup 維持)
- [ ] 古い候補通知が age > 24h で 「(古い候補)」prefix 付き

summary 品質 (280):
- [ ] summary: (なし) が 0 件
- [ ] review reason 具体化 (mapping 5 種 出現確認)
- [ ] 絵文字 1 個まで
- [ ] source 名/subtype/age/URL/reason 5 要素揃う

回帰禁止: 277 と同じ + 205-COST incremental との衝突なし(image bundle 時)

### 278-QA deploy 観察 (RT title cleanup)

- [ ] WP draft title に「RT 」prefix が無い
- [ ] グッズ系 title が商品名先頭
- [ ] 巨人無関係 RT が off_field 判定 or review fallback
- [ ] 既存 X source title 系 candidate の publish 経路に regression なし

回帰禁止: 277 と同じ

## 不変ルール再確認

- Claude = 監査 / queue / prompt 起票 / read-only 観測 / push のみ
- Codex = 実装 / テスト / commit 担当
- user = 最終判断(deploy / publish / scheduler / env / secret / X live)
- handoff の永続化は **本 file series**、/tmp 禁止
