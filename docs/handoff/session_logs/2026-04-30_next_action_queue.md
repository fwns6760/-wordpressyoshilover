---
session_date: 2026-04-30
topic: 次セッション再開順 永続記録(2026-04-30 PM 確定 queue)
participants: Claude Code(管理), user(最終判断), Codex(impl), ChatGPT(方針)
status: ACTIVE_QUEUE
purpose: 次セッション開始時に Claude/Codex/ChatGPT が迷わず再開できる、具体的 queue + HOLD 理由 + 解除条件
---

# 2026-04-30 PM 確定 次アクション queue

**次セッション開始時の最初の指示**: 本ファイル → `docs/handoff/session_logs/2026-04-30_p0_publish_recovery_observation.md` の順で読み、active / observe / hold / done を 5 点で要約してから再開。

---

## 0. 「明日朝」「後で」禁止、依存関係 + 解除条件で記述

本 queue は時間軸ではなく **依存関係と条件管理**。各 step の前提が満たされた時点で着手、なければ HOLD 維持。

---

## 1. 現在の本番状態(2026-04-30 18:00 JST 時点)

### git / repo
- HEAD = `4be818d`(290-QA REVIEW_NEEDED status doc 更新あり、Codex `bw2q618tt` は impl 完了通知後に commit)
- origin = `4be818d`(289-OBSERVE 通知化 + 282-COST preflight 仕込み + 281-QA farm_result allowlist + 277-QA title backfill + 283-MKT design)

### 本番 image / live state

| service / job | image | env flag |
|---|---|---|
| **yoshilover-fetcher** service | `:4be818d` rev `00175-c8c` 100% traffic | `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` / `ENABLE_GEMINI_PREFLIGHT` 未設定(default OFF) / `ENABLE_LIVE_UPDATE_ARTICLES=0` |
| **publish-notice** job | `:4be818d` | `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` / Team Shiny From `y.sebata@shiny-lab.org` |
| **guarded-publish** job | `:6df049c`(281-QA farm_result allowlist live) | - |
| **draft-body-editor** job | `:cf8ecb9`(244-B-followup) | - |
| **codex-shadow** job | 不変 | - |

### Scheduler

全部 ENABLED + 直近 attempt 5min 以内:
- giants-realtime-trigger / guarded-publish-trigger / publish-notice-trigger 全て */5
- giants-weekday-* / giants-postgame-catchup-am / fact-check-morning-report
- audit-notify-6x PAUSED(維持) / yoshilover-fetcher-job PAUSED(旧 monolith、設計通り)

### P0 publish/mail 状態

- **本日の publish 5 件**(WP REST 確認):10:46 (3 件) / 11:50 (id=64081) / 12:15 (id=64087) / 17:10 review/hold mail (id=64104)
- **publish-notice 17:10 sent=1**(本日 12:20 以来 50min ぶりの review/hold mail、deploy 後の既存導線維持確認)
- **289 post_gen_validate mail emit 達成**:16:55+17:00 sent=10 each、cap=10/run + dedup 動作、subject「【要review｜post_gen_validate】コーチが早出練習で 選手に直々にトス上げ」等
- silent skip 解消、cursor scan 動作、errors=0

### 各 ticket 状態

| ticket | 状態 | 最終 action |
|---|---|---|
| **289-OBSERVE post_gen_validate notification** | LIVE(flag ON 17:00 JST) | 24h 安定観察中 |
| **290-QA weak title rescue** | REVIEW_NEEDED(Codex `bw2q618tt` 完了通知待ち) | impl 完了直前、push 未 / deploy 未 |
| **281-QA farm_result backlog allowlist** | LIVE(guarded-publish `:6df049c`) | farm_result <24h positive case 観察待ち |
| **282-COST gemini preflight gate** | LIVE flag OFF(コードあり挙動なし) | flag ON は 293 完遂後 |
| **277-QA title player-name backfill** | LIVE(fetcher `:27166c5`→`:4be818d` carry) | 効果は 290 救済込みで観察 |
| **205-COST publish-notice incremental scan** | LIVE retroactive accept | cursor 動作中、process violation 記録 |
| **283-MKT unique article requirements** | DOC LIVE(commit `a2777f9`) | 子 ticket 284-287 HOLD |
| **288-INGEST source coverage expansion** | DESIGN_DRAFTED + HOLD(5 条件管理) | impl 起票 HOLD |
| **291-OBSERVE candidate terminal outcome** | DESIGN_DRAFTED + HOLD | impl 起票 HOLD |
| **292-OBSERVE body_contract_fail notification** | DESIGN_DRAFTED + HOLD | impl 起票 HOLD |
| **293-COST preflight skip visible notification** | DESIGN_DRAFTED + HOLD | **次セッション最優先 fire 候補** |
| **294-PROCESS release composition gate** | DESIGN_DRAFTED + HOLD | user GO 後 impl |
| **295-QA subtype evaluator misclassify fix** | DESIGN_DRAFTED + HOLD | 289 安定 + 290 整理後 |

---

## 2. 次にやる順番(依存関係つき queue)

### Step 1(次セッション開始直後)= **観察まとめ**

依存:本 file 読了 + session log 読了 + git fetch
着手判断:無条件で着手

タスク:
- 289 post_gen_validate mail 24h 集計(emit 件数 / dedup 件数 / 既存 publish/review/hold 件数)
- 290-QA Codex `bw2q618tt` 完了確認 + 3 点 contract 追認 + push判断
- 281-QA farm_result <24h positive case 観察(発火しているか)
- 277-QA title backfill 効果(本日 publish 候補で人名補完が効いたか目視)
- silent skip 0 維持 verify
- cap=10/run 維持、通知爆発 0 維持

### Step 2 = **290-QA push + GH Actions verify**

依存:Step 1 観察まとめで「既存導線維持」確認
着手判断:Codex `bw2q618tt` impl 完了 + 3 点 contract 追認 OK + pytest baseline 1851/7 維持
deploy:fetcher rebuild + flag ON は別判断(290-QA deploy は次セッションで user GO 後)
fire コマンド:`git push origin master`

### Step 3 = **293-COST preflight skip visible notification 起票 + Codex fire**

依存:Step 2 完了 + 289 24h 安定確認(silent skip 0、通知爆発 0、Team Shiny From 維持)
着手判断:本日 user 明示 GO 済(2026-04-30 PM)
fire 内容:
- ticket 起票:`doc/active/293-COST-preflight-skip-visible-notification.md`(既存 design draft あり、impl 仕様 finalize)
- Codex impl prompt fire(282-COST + 289 と同 pattern)
- env flag `ENABLE_PREFLIGHT_SKIP_NOTIFICATION` default OFF
- 新 ledger or 289 ledger 流用判断は impl 時 Codex audit 後

### Step 4 = **293-COST commit + push + deploy + flag ON**

依存:Step 3 commit 完了 + 3 点 contract 追認 + pytest baseline 維持
着手判断:user 明示 GO(deploy + flag ON は user 判断)
deploy 順:
1. fetcher rebuild(`yoshilover-fetcher:<293 commit>`)
2. publish-notice rebuild(同上)
3. 両方 `--update-env-vars ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1`

### Step 5 = **293 24h 安定観察**

依存:Step 4 完了 + 自然発火 trigger 後 24h
着手判断:無条件で 24h 観察
verify:
- preflight skip 件数 = 0(282-COST flag OFF なので skip 自体起きない、通知経路だけ稼働確認)
- 既存 publish/review/hold + 289 post_gen_validate 通知不変
- 通知爆発 0、Team Shiny From 維持、Gemini call 増加 0
- mail attempt / success / error log

### Step 6 = **282-COST flag ON 判断**

依存:Step 5 完了 + user 明示 GO
着手判断:user 判断(本 step で Claude が autonomous 進めない)
fire 内容:
- `gcloud run services update yoshilover-fetcher --update-env-vars ENABLE_GEMINI_PREFLIGHT=1`
- 24h 観察(Step 7)

### Step 7 = **282-COST flag ON 後の 24h 観察**

verify:
- preflight skip 件数 > 0(8 skip_reason 別 count)
- preflight skip mail / digest 配信
- Gemini call 数 deploy 前後比較(削減効果測定、本 step が 282-COST 投資の回収開始)
- false-positive 検出(本来 publish 価値ある candidate が誤 skip されていないか mail 目視)
- publish 数 deploy 前後で減っていない確認

### Step 8 = **229-COST C prompt compression 起票検討**

依存:Step 7 完了 + 282-COST 効果確定 + user 明示 GO
着手判断:282-COST 効果が想定範囲(-10〜30% Gemini call)で安定後
fire 内容:
- 既存 fixed_lane prompt の冗長 instruction 圧縮
- A/B test 設計(同 source で旧 prompt vs 新 prompt 結果比較)
- env flag で OFF/ON 切替

### Step 9 = **291-OBSERVE candidate terminal outcome contract 設計確定 + 起票**

依存:Step 8 完了(or 並走)+ 289 / 290 / 293 24h 安定 + user 明示 GO
着手判断:複数 ledger を統一 outcome ledger に集約する設計確定後

### Step 10 = **292-OBSERVE body_contract_fail notification**

依存:Step 9(統一 outcome ledger)完遂後、その上に乗せる

### Step 11 = **295-QA subtype evaluator misclassify fix**

依存:Step 5 完了 + Step 8 着手 + user 明示 GO
内容:live_update 誤判定の narrow 化、浦田俊輔 type の通常 notice/recovery を救済

### Step 12 = **288-INGEST source coverage expansion**

依存(全部達成):
1. 289 silent skip 通知化済(達成)
2. 290 weak title rescue 方針確定(Step 2 で達成見込み)
3. 295 live_update 誤判定整理(Step 11)
4. 候補が必ず terminal state に落ちる契約(291、Step 9)
5. Gemini call 増加抑制 preflight/dedupe(282-COST flag ON、Step 6-7)
+ user 明示 GO

### Step 13 以降 = **278/279/280-QA 品質改善 + 284-287-MKT 系**

依存:Step 12 までの安定 + 277/290 効果確認
内容:RT title cleanup / mail subject clarity / summary excerpt cleanup / マニアック記事系

---

## 3. HOLD 中のもの + 理由 + 解除条件

| 項目 | HOLD 理由 | 解除条件 |
|---|---|---|
| **282-COST flag ON** | 293 未着地で flag ON すると preflight skip が完全 silent | 293-COST impl + deploy + flag ON + 24h 安定 + user 明示 GO |
| **229-COST C prompt compression** | 282-COST 効果確定前に prompt 触ると効果分離不能 | 282-COST flag ON + 24h 観察完了 + user 明示 GO |
| **cache TTL 延長**(229 既存 24h → 48-72h) | 古い cache でズレた記事 risk | 個別検証 ticket 起票 + A/B test + user 明示 GO |
| **lower-cost model 部分採用**(flash → flash-lite) | 品質劣化 risk、現フェーズ noindex 検証中 | 個別検証 ticket 起票 + A/B test + user 明示 GO |
| **Scheduler 頻度変更** | candidate 取りこぼし risk、user explicit hold | user 明示 GO 必須(本 ticket では HOLD 維持) |
| **source 追加(288-INGEST)** | silent skip / outcome 契約が固まる前に source 増やすと候補消失 path 拡大 | Step 12 の 5 条件 + user 明示 GO |
| **205-COST 追加作業** | P0 mail 安定確認まで | mail 24h 安定 + user 明示 GO |
| **278/279/280-QA 品質改善** | 277/290 効果確認後 | 277/290 24h 安定 + user 判断 |
| **284-287-MKT 系** | 283-MKT 確認後 | user 明示 GO + 子 ticket 個別判断 |
| **live_update ON / ENABLE_LIVE_UPDATE_ARTICLES=1** | 試合中実況解禁、運用負荷大 | user 明示 GO 必須(現フェーズ NEVER) |
| **SEO / noindex 解放 / canonical / 301** | 公開影響大、フェーズ変更 | user 明示 GO 必須(品質検証フェーズ完了後) |
| **X 自動投稿 ON** | 法務 / 著作権境界 | user 明示 GO 必須 |
| **duplicate guard 全解除** | 重複公開 risk | NEVER(narrow 緩和のみ可、過去 269/270/271 で narrow 緩和済) |
| **default/other 無制限公開** | 品質低下 risk | NEVER(273-QA で 24h cap narrow 化済) |
| **Team Shiny From 変更** | mail 受信側設定影響 | user 明示 GO 必須 |
| **Gemini call 増加 prompt 拡張** | コスト増 | user 明示 GO 必須 |
| **新 subtype 追加** | VALID_ARTICLE_SUBTYPES 拡張は影響大 | user 明示 GO + 283-MKT contract 維持 |

---

## 4. 各 ticket の再開条件

### 290-QA(REVIEW_NEEDED、Codex 完了通知待ち)
- **解除条件**: Codex `bw2q618tt` 完了 + 3 点 contract 追認 + pytest baseline 1851/7 維持
- **owner**: Claude(accept) → push
- **deploy 要否**: fetcher rebuild + flag ON 必要(別 fire、user GO 後)
- **user GO 必須か**: deploy + flag ON で必須、push のみは autonomous OK
- **rollback 条件**: env flag remove で即時、image revert で完全戻し

### 293-COST(DESIGN_DRAFTED、HOLD)
- **解除条件**: 290-QA push + 289 24h 安定(silent 0、通知爆発 0、Team Shiny From 維持)
- **owner**: Claude(設計 finalize)→ Codex(impl)
- **deploy 要否**: fetcher + publish-notice rebuild + flag ON 必要
- **user GO 必須か**: deploy + flag ON で必須、impl + push のみは本日 user 明示 GO 済
- **rollback 条件**: env flag remove で即時(`ENABLE_PREFLIGHT_SKIP_NOTIFICATION`)

### 282-COST flag ON(コード live、flag OFF)
- **解除条件**: 293 完遂 + 24h 安定
- **owner**: user 判断
- **deploy 要否**: env 変更のみ、image rebuild 不要
- **user GO 必須か**: **YES、必須**
- **rollback 条件**: `--remove-env-vars=ENABLE_GEMINI_PREFLIGHT` 即時

### 291 / 292 / 295 / 288 / 229-C / 278/279/280 / 284-287
- 各 ticket doc 内 HOLD 解除条件参照
- 共通:**user 明示 GO 必須**

---

## 5. 必須デグレ試験(全 next action 共通)

各 next action(impl / deploy / flag ON)で以下 9 項目を **必ず** 含める:

1. **publish/mail が止まらない**(deploy 前後で publish/mail count 比較、減っていない)
2. **review/hold/skip 通知が届く**(267-QA / 289 / 293 通知導線維持)
3. **silent skip を作らない**(全 skip event が ledger or mail で見える、追加 logger emit OK)
4. **Team Shiny From `y.sebata@shiny-lab.org` 維持**(SMTP env 不変 assert)
5. **Gemini call 増加なし**(削減方向のみ、増えるなら bug)
6. **ENABLE_LIVE_UPDATE_ARTICLES=0 維持**(env 不変 assert)
7. **SEO/noindex/canonical/301 変更なし**(token 不在 assert)
8. **X 自動投稿なし**(`ENABLE_X_POST_FOR_*=0` 維持、X 自動投稿 path 不変)
9. **新 subtype 追加なし**(`VALID_ARTICLE_SUBTYPES` set 不変 assert)

加えて各 ticket 個別の test:
- 該当 ticket doc の「必須デグレ試験」section 全項目

---

## 6. 次セッション開始時の指示(必読 sequence)

### 起動直後の必須 sequence

1. **本 file 読了**(`docs/handoff/session_logs/2026-04-30_next_action_queue.md`)
2. **session log 読了**(`docs/handoff/session_logs/2026-04-30_p0_publish_recovery_observation.md`、最後の方の進行ログ重点)
3. `git fetch && git log -5 --oneline` で repo 状態確認
4. `gh run list --workflow=tests.yml --limit 3` で CI 状態確認
5. live image 確認:
   - `gcloud run services describe yoshilover-fetcher --region=asia-northeast1 --project=baseballsite --format='value(spec.template.spec.containers[0].image)'`
   - `gcloud run jobs describe publish-notice --region=asia-northeast1 --project=baseballsite --format='value(spec.template.spec.template.spec.containers[0].image)'`

### 起動後 5 点要約(user 報告 format)

```
1. active(進行中): <ticket list>
2. observe(24h 観察中): <ticket list、観察開始時刻>
3. hold(待機中): <ticket list、解除条件>
4. done(完了): <ticket list、本日着地分>
5. 次の 1 手: <next action queue Step N>
```

### 5 点要約後の最初の確認
- 290-QA Codex `bw2q618tt` 状態(commit landed か / push 必要か)
- 289 mail emit 24h 集計(silent 0 / 通知爆発 0 維持確認)
- 281-QA farm_result <24h positive case 発火確認
- user 体感問題(publish/mail 異常 / 通知爆発 / 既存導線崩れ)有無

### 起動後の追加 fire 判断
- **Step 3(293-COST 起票 + Codex fire)が次の最優先**
- ただし Step 1-2 観察まとめで silent skip 0 / 通知爆発 0 / 既存導線維持を確認できなければ、**Step 3 の fire は HOLD**
- 異常検出時は rollback 判断を user に上げる

---

## 7. 不変条項(全 step 継承、user 明示 GO で初めて触れる)

- ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- Team Shiny From `y.sebata@shiny-lab.org` 維持
- SEO/noindex/canonical/301 不変
- X 自動投稿 OFF
- duplicate guard 全解除なし(narrow 緩和のみ可)
- default/other 無制限公開なし
- 新 subtype 追加なし
- Scheduler 頻度変更なし
- prosports 修正なし
- 既存 fixed_lane prompt text 不変(283-MKT 7-1 contract)

---

## 8. 本日 incident / 学び(永続記録)

| incident | 学び |
|---|---|
| 205-COST 暗黙 carry(289 deploy で publish-notice :dc02d61 → :4be818d、間の commit 22bc09b carry) | 294-PROCESS で release composition gate 確立、deploy 前 commit 一覧 verify を boilerplate に |
| 282-COST deploy 時の dirty worktree 警告(Codex open question) | clean export 経由 build を deploy 便標準化(294-PROCESS と統合) |
| pytest local 7 fails が CI green と乖離 | feedback memory `feedback_local_pytest_ci_env_mismatch.md` で baseline 比較判定 fix |
| Codex prompt の cloudbuild substitution 名 mismatch(`_IMAGE_TAG` vs `_TAG`) | feedback memory `feedback_codex_prompt_filenames_real_repo.md` でファイル名/変数名 ls 確認標準化 |
| 「source 不足」と誤診断 → 真因は post_gen_validate silent skip | 候補消失の真因は coverage gap < silent skip(設計上の盲点)、可視化を最優先 |
| build context 汚染 verify 未実施で連続 deploy | 294-PROCESS で git stash + clean export 経由 deploy を標準化 |
| KPI 計測 doc 不在で「削減した」検証経路なし | 282-COST flag ON 時に Gemini call 数 deploy 前後比較必須、KPI doc 起票候補 |

---

## 9. 自律進行ポリシー(本 queue 範囲内、user 明示 GO 不要で進めて良い)

- ticket 起票(doc/active/* に新規 doc 作成、untracked)
- Codex impl 便 fire(env / Scheduler / 公開 publish 触らない範囲、cleanup-disjoint scope)
- Codex commit 後の 3 点 contract 追認 + push
- pytest baseline 維持 verify
- read-only 観察(gcloud describe / logging read / WP REST GET)
- session log 追記
- memory 更新(feedback_*.md / project_*.md)

### 自律進行禁止(user 明示 GO 必須)
- 本番 deploy(image rebuild + service/job update)
- env flag 値変更(default 値変更 + 本番 env 変更両方)
- traffic 切替(canary 含む)
- Scheduler 変更(enable / disable / 頻度)
- secret 変更
- WP publish / X 自動投稿 / mail 経路変更
- rollback / 炎上対応
- MVP scope 拡張 / 縮小
- 法務 / 著作権 / プライバシー境界

---

## 9.5. 2026-05-01 朝 snapshot 追記(混線を止める日の盤面整理結果)

本 section は 2026-04-30 PM queue を上書きせず、5/1 朝時点の状態 snapshot を **追記**(doc-only、impl/deploy 0)。

### DONE(OBSERVED_OK evidence あり、通知品質 DONE ではない)

- **276-QA test mock fix**:CI run 25146349669 success / 1820 tests
- **281-QA farm_result allowlist deploy(execution success のみ)**:execution `guarded-publish-cd9n6` exit 0 / silent hold 0(97/97 records)— **farm_result <24h positive case 観察例 0、partial DONE**
- **283-MKT 要件定義 doc**:commit a2777f9 push、user 確認済
- **289-OBSERVE deploy + flag ON(通知導線 LIVE のみ)**:24h sent=172 errors=0 / silent skip 0(2808 records)/ Gmail sample 実到達確認(10+ thread)/ Team Shiny From 維持 — **通知品質 DONE ではない**(URL 表示・公開済 vs 未公開混在の見分けにくさ等は 279-QA 系で別便)
- **297-OPS codex-shadow PAUSE**:scheduler state=PAUSED / 24h publish-mail trigger 維持

### OBSERVE(LIVE deploy 済、効果未確認、DONE 扱い禁止)

- **282-COST gemini preflight gate(deploy 済 / flag OFF)**:image `:325b47f`(後 `:4be818d` carry)/ `ENABLE_GEMINI_PREFLIGHT` 未設定維持 / preflight skip event 0 — **flag OFF で本番挙動変えていない、効果あり扱い禁止**、flag ON 後の効果は未測定
- **205-COST publish-notice incremental scan(retroactive accept)**:cursor scan 動作確認、ただし cost 削減効果の数値計測なし
- **cost observe: cache_hit 99%**(498/500、24h、昨日 75% から急上昇)— 真の削減 / source 量 / 時間帯偏り未確定、**成功扱い禁止、OBSERVE 継続**

### NOT DONE(evidence 不足、現 status)

- **277-QA title player-name backfill**:`DEPLOYED`(rescue 効果 OBSERVED_OK 待ち、290 救済 + deploy 後)
- **290-QA weak title rescue**:`CODE_DONE` + `PUSHED`(deploy 未、本日禁止)
- **281-QA farm_result <24h positive case 観察**:`partial DONE`(execution success 確認済、actual <24h candidate 観察例 0)

### RISK(明示管理、本日 fix 禁止、observation のみ)

- **未 deploy 差分**:repo HEAD `1b77e89` と本番 image `:4be818d` の間に 290-QA(c14e269)+ docs commit が存在、deploy しないと反映しない / リスク自体は publish-mail 経路に影響なし(flag OFF design)、ただし「repo 状態 vs 本番状態」のズレを認識
- **次 deploy 前 clean build 必須**:`?? src/gemini_preflight_gate.py` / `?? tests/test_gemini_preflight_gate.py` は HEAD と disk 一致だが、`gcloud builds submit .` で worktree 全体送信、disk が変更されると build context 汚染 risk / 294-PROCESS で `git stash -u` または `/tmp` clean export 標準化予定、**次 deploy 便 fire 前必須参照**
- **cache_hit 99% 真因不明**:24h sample で persisted、ただし真因解明前に「282-COST + 229-COST 効果あり」と断定禁止

### active 2 件

1. **289-OBSERVE 24h 観察**(LIVE_TRIGGERED + USER_VISIBLE)
2. **290-QA**(CODE_DONE + PUSHED、deploy 判断保留)

### observe 1 件

- **cost observe**:cache_hit 99%(498/500、24h、昨日 75% から急上昇)— 真の削減効果 / source 量 / 時間帯偏り未確定

### Ready for user GO 3 件

| # | ticket | user GO 後の action |
|---|---|---|
| 1 | **290-QA deploy + `ENABLE_WEAK_TITLE_RESCUE=1`** | fetcher rebuild + flag ON、A/B 7 候補 rescue 効果反映 |
| 2 | **293-COST 起票 + Codex fire** | impl 着手(282-COST flag ON の鍵) |
| 3 | **264-QA Phase 1 audit**(read-only、user GO 不要) | 既存 publish 重複ペア集計、cleanup 判断材料作成 |

### P0 / Safety 有無(限定表現)

**現時点で観測済みの P0 / Safety なし**(read-only verify 5 件 + horizontal audit 範囲)。
**安全宣言ではない**。未観測領域は依然不明、cache_hit 99% / 次 deploy 前 clean build / 通知品質 等は continued risk として残す。

### 5/1 朝 verify evidence(p0 observation log に永続記録済)

`docs/handoff/session_logs/2026-04-30_p0_publish_recovery_observation.md` の `## 2026-05-01 朝 read-only verify evidence` section 参照:
- Gmail 実到達(sample、search_threads 10+ 件)
- post_gen_validate_history silent 0(2808 records)
- 通知 LLM 呼出 0(publish-notice 24h gemini token 0 hit)
- flag/env 5 項目期待値通り(64 env 行 grep 検証済)
- rollback target image AR 全 4 tag 存在(digest 確認済)
- ?? src 正体:HEAD と完全一致(disk diff empty)、本番影響なし、ただし次 deploy 前 clean build 必須

### 通知 URL 問題の扱い(279-QA 系 HOLD として残す)

- 現時点 P0 ではない、通知表示設計の改善対象
- 公開済み記事 mail と未公開候補 mail の見分けにくさは user 体感影響あり
- 未公開候補 mail を **止めない** 方向、見分けやすくする方向(279-QA 系で別便)

### 表現修正(永続)

今後の報告で:
- 「壊れていない確定」 ❌
- 「確認範囲では P0 / Safety なし」 ✓

### 自律 GO 範囲(永続、user 明示)

ユーザー GO 必須:
- deploy / env-flag 変更 / Scheduler 変更 / SEO-noindex-canonical-301 変更 / Gemini call 増加 / mail 通知条件変更 / source 追加 / live_update 変更 / X 自動投稿 / cleanup mutation / rollback 不能な変更 / 公開基準の緩和

Claude 自律 GO 可能:
- read-only 確認 / 分類 / doc-only handoff 更新 / 状態整理 / evidence 追記
- 完了後は「自律 GO で実施しました」/「user GO が必要です」/「HOLD しました」のどれかで報告

## 9.6. 2026-05-01 ops reset 反映(OWNER 三軸化)

詳細は `docs/handoff/session_logs/2026-05-01_ops_reset.md` 参照(本 queue は単一 source ではなくなった、ops_reset.md の運用ルールが上位)。

### OWNER 三軸の永続ルール
- **DECISION_OWNER**:最終判断者(user / Claude / Codex / ChatGPT)
- **EXECUTION_OWNER**:準備・調査・整理・記録・impl の進行担当(Claude / Codex / none)
- **USER_GO_REQUIRED**:true / false

### user を DECISION_OWNER にしてよい範囲(永続限定)
- deploy / env-flag / Scheduler / SEO / Gemini call 増加 / source 追加 / live_update / mail 条件変更 / cleanup mutation / X 自動投稿 / rollback 不能 / 公開基準の緩和

これ以外で user OWNER にしない(設計 / impl + push / doc / 整理 / 統合 / 凍結 file move 等は Claude / Codex OWNER)。

### 本 queue の各 ticket OWNER は ops_reset.md の HOLD list に正本反映済

本 queue の Ready for user GO / HOLD list は ops_reset.md(OWNER 三軸化)を **正本** とする。差分があれば ops_reset.md が優先。

本 queue は **2026-04-30 PM 確定版**。次セッション開始時にここから再開、以下を厳守:
- 「明日朝」「後で」「落ち着いたら」禁止
- 各 step の依存関係 + 解除条件で判断
- 並走可能性は scope disjoint + commit便直列ルール準拠で個別判断
- user 明示 GO 必須項目は autonomous 進めず

session 終了時:本 queue を更新 + 次 session 用に 5 点要約を末尾追記。
