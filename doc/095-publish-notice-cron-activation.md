# 095 Publish-notice cron activation

## meta

- owner: **Claude Code**(運用 / runbook ticket、Codex 実装便ではない)
- type: **ops/runbook**(088 手動 smoke 成功後の自動化展開)
- status: BLOCKED on 088 close(手動 1 通 smoke 成功 = 本 ticket fire 前提)
- created_at: 2026-04-25 00:30 JST
- deps: 088(publish-notice real-send smoke、本 ticket の前提条件)/ 076(publish-notice-email contract)/ 072(mail-delivery-bridge)/ 093(automation tick recovery、cron 化の前提として automation tick 自体が稼働している必要)
- renumber note: user 指示で 094 を意図していたが、094 は既に `creator-lineup-template-refactor`(in-flight)で使用中、本 ticket は 095 へ移動

## why_now

- 088 で publish-notice real-send 1 通の手動 smoke が成功した時点で、**「自動化に載せるか」は次の判断**
- 自動化なしだと user が毎回 publish のたびに手動 fire する必要 = relay 増加、運用負荷
- 076 は automation 設計済(`automation.toml` lane 定義可能)、ただし本番有効化は user 判断 8 類型
- 093 で automation tick が復旧していることが大前提(tick が止まっていれば cron 化しても動かない)

## purpose

- 088 成功を前提に、076 publish-notice-email を **cron / Codex Desktop automation** に載せる activation 手順を固定
- 必要な gate / env / recipient / `--send` 条件を 1 本に整理
- 失敗時の rollback / disable 手順を明記
- 073 / 074 / 075 への横展開順を固定

## non_goals

- 076 / 072 code 本体の実装変更
- editor / creator / front lane / X API
- 088 が未完了の状態で本 ticket を進める(stop 条件)
- 093 が未復旧の状態で本 ticket を進める(stop 条件)
- automation tick subsystem 自体の修復(093 の責務)

## 前提条件(本 ticket fire 前にチェック)

1. **088 close 確認**: publish-notice real-send smoke が成功(Gmail に `[publish] ...` 件名 1 通着信、`/tmp/option_e/publish_notice_queue.jsonl` に `sent` 行)
2. **093 cron tick 復旧確認**: `/mnt/c/Users/fwns6/.codex/heartbeats/` dir 存在 + `quality-monitor.txt` 等が hourly 更新
3. **既存 3 automation 健全**: draft-body-editor / quality-monitor / quality-gmail が hourly tick で発火
4. **.env credential 維持**: `MAIL_BRIDGE_GMAIL_APP_PASSWORD` + `MAIL_BRIDGE_TO` が .env に残っている

→ 4 条件全 hit で本 ticket Phase 1 へ。1 つでも未達なら **stop して該当 ticket(088 / 093)へ戻る**。

## ticket で固定する runbook の骨子

### Phase 1: automation.toml 定義作成(私が即実行可能、新規 file 追加のみ)

`/mnt/c/Users/fwns6/.codex/automations/publish-notice-email/automation.toml` を新規作成:

```toml
version = 1
id = "publish-notice-email"
kind = "cron"
name = "Publish Notice Email"
prompt = """Use Asia/Tokyo local time. Use Windows local shell only, and run the runner through WSL. In shell, run exactly: cmd /c "mkdir C:\\Users\\fwns6\\.codex\\heartbeats 2>nul && echo %DATE% %TIME% > C:\\Users\\fwns6\\.codex\\heartbeats\\publish-notice-email.txt" && wsl.exe bash -lc "cd /home/fwns6/code/wordpressyoshilover && PUBLISH_NOTICE_EMAIL_ENABLED=1 python3 -m src.tools.run_publish_notice_email_dry_run --scan --send --cursor-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_cursor.txt --history-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_history.json --queue-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_queue.jsonl". Do not modify code, env, secrets, scheduler, traffic, or any automation files. Report only the single-line summary from stdout. If the command exits non-zero or status is suppressed unexpectedly, report the exact failure briefly and stop."""
status = "ACTIVE"
rrule = "FREQ=HOURLY;INTERVAL=1;BYMINUTE=15"
model = "gpt-5.4-mini"
reasoning_effort = "low"
execution_environment = "local"
cwds = ["C:\\Users\\fwns6"]
```

設定 point:
- `id = "publish-notice-email"` 固有
- `cwds = ["C:\\Users\\fwns6"]`(069 deterministic shape 準拠、UNC cwd 不使用)
- `wsl.exe bash -lc "cd ... && PUBLISH_NOTICE_EMAIL_ENABLED=1 python3 -m ..."` で送信 gate を inline env で渡す
- `--send` flag で real-send 経路
- log paths を WSL 内 `/home/fwns6/.../logs/` に固定(automation 起動時にも cursor / history が共有される)
- `BYMINUTE=15` で他 automation(draft-body-editor=毎時 / quality-monitor=:45 / quality-gmail=毎時)と被らない時刻
- `model = "gpt-5.4-mini"` + `reasoning_effort = "low"`(quality-monitor と同じ軽量、prompt 通りの 1 行 stdout だけなので)

### Phase 2: gate 確認 + automation 登録(私が file 配置、user 操作 1 手で reload)

1. 上記 toml を `/mnt/c/Users/fwns6/.codex/automations/publish-notice-email/automation.toml` に配置(私が WSL 経由で `cp` または `cat > ` で作成)
2. `/mnt/c/Users/fwns6/.codex/automations/publish-notice-email/memory.md` を空 file or 1 行で作成(他 automation と同形式)
3. user 操作: Codex Desktop app で **automation 一覧を refresh**(workspace switcher で C:\Users\fwns6 を再 attach、または app 再起動)
4. 登録確認: `/mnt/c/Users/fwns6/.codex/automations/publish-notice-email/` dir が認識され、Codex Desktop UI に `Publish Notice Email` 名で表示される

### Phase 3: 初回 tick 観測(~ 1 時間以内、自動)

最初の `:15` ターン到来時に tick 発火。以下を観測:

1. `/mnt/c/Users/fwns6/.codex/heartbeats/publish-notice-email.txt` 出現 + 直近 timestamp
2. WSL 内 `/home/fwns6/code/wordpressyoshilover/logs/publish_notice_queue.jsonl` に `sent` または `dry_run` 行追加(emit 0 なら何も追加されない)
3. `[publish] ...` 件名のメールが `MAIL_BRIDGE_TO` recipient に届く(対象 publish が 1 時間以内にあった場合のみ)

→ 3 条件 全 hit = activation 成功 → 本 ticket close。

### Phase 4: 失敗 routing

| 観測 | 含意 | next |
|---|---|---|
| heartbeats/publish-notice-email.txt 出現せず 1 時間後 | automation registry reload 失敗、または cron tick subsystem 不調 | 093 cron tick recovery を再実行、または app 再起動 |
| heartbeats 出るが queue.jsonl に行追加なし | runner は走ったが publish event が 0(対象 publish が無い時間帯) | 正常、次 tick 待ち |
| queue.jsonl に `suppressed` 多発 | gate 設定不足、または env 不在 | 088 で確認した env 状態を automation prompt 内 `PUBLISH_NOTICE_EMAIL_ENABLED=1` 経路で再注入確認 |
| queue.jsonl に `sent` 行あるが Gmail 着信なし | spam / filter / SMTP 一時失敗 | smtp_response エラー詳細確認、088 失敗 routing 7 pattern を流用 |
| `RECENT_DUPLICATE` 連発 | 24h dedup hit、運用上は OK | 様子見 1 日 |

## 073 / 074 / 075 への横展開順(本 ticket close 後)

076 cron 化が安定運用 1 週間 + 失敗 0 件 を確認後、同 pattern で:

1. **095-A: morning-analyst-email-send (073) cron activation** — 朝 1 回固定、`ANALYST_EMAIL_TO` env 設定 + `--send` flag
2. **095-B: x-draft-email-send (074) cron activation** — 1 日 2 便(昼 / 夜)、`X_DRAFT_EMAIL_TO` env、065-B1 出力ベース
3. **095-C: ops-status-email-send (075) cron activation** — state change 時のみ送る設計、まず手動 smoke で挙動確認後

各 sub-ticket は独立 narrow、本 ticket close 後に user 判断で起票。

## acceptance(本 ticket、runbook ticket)

1. 076 cron activation の前提と手順が **本 doc に 1 本固定**(Phase 1-3)
2. 088 未完了 / 093 未復旧の状態では **Stop 条件で進めない**ことが明記
3. 073 / 074 / 075 への展開順が **095-A/B/C として記述**(本 ticket では起票しない、横展開トリガ条件後)
4. failure routing が 5 pattern で固定
5. 追加実装が必要な場合は 095-A/B/C 候補のみ(本 ticket では起票しない)

## 不可触

- 076 code(既存実装で動く、変更不要)
- 072 mail bridge code
- automation.toml の他 3 lane(draft-body-editor / quality-monitor / quality-gmail)
- editor / creator / 086 / 091 / 092 / 094 contract
- baseballwordpress repo / front lane

## stop 条件

- 088 が未 close → 本 ticket fire 不可、088 完了待ち
- 093 が未 close → cron tick 自体が稼働していない、本 ticket の effort が無駄、093 完了待ち
- Phase 1 で `automation.toml` 配置時に既存 lane 衝突 → user 判断、別 id で再試行
- Phase 2 で Codex Desktop が新 automation を認識せず → 093 routing(workspace reattach)
- Phase 3 で 1 時間後も heartbeats 出ず → 093 失敗 routing と合流

## 関連 file

- `/home/fwns6/code/wordpressyoshilover/doc/088-publish-notice-real-send-smoke-and-mail-gate-activation.md`(本 ticket の前提)
- `/home/fwns6/code/wordpressyoshilover/doc/093-automation-tick-recovery-and-workspace-reattach.md`(cron tick 復旧の前提 ticket)
- `/home/fwns6/code/wordpressyoshilover/doc/076-publish-notice-email.md`(gate / suppress rule 正本)
- `/mnt/c/Users/fwns6/.codex/automations/quality-monitor/automation.toml`(automation.toml 形式の reference)
