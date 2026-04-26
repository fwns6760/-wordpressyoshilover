# 088 Publish notice real-send smoke and mail gate activation

## meta

- owner: **Claude Code**(運用 / 接続 ticket、Codex 実装便ではない)
- type: **runbook + checklist**(既存 072-076 実装済を運用接続するだけ、新規実装なし)
- status: OPEN(option E Phase 2 = 63405 publish 待ち)
- created_at: 2026-04-25 00:00 JST
- deps: 072(mail-delivery-bridge)/ 076(publish-notice-email)/ option E playbook(`docs/handoff/runbooks/option_e_publish_chain_smoke.md`)
- non_blocker_for: editor lane / creator lane / 086 contract / 087 front / 091 audit / 092 creator refactor

## why_now

- backend lane に **072-076 mail chain** は完全実装済(全 push、suite green)
- ただし **「仕組みはあるがメールが 1 通も届いていない」**状態
- 真因: 076 publish-notice-email の **real-send 二重 gate** が ON されていない
  - `--send` flag(CLI)
  - `PUBLISH_NOTICE_EMAIL_ENABLED=1` env(または `--send-enabled`)
  - **両方揃って** はじめて `dry_run=False` で 072 bridge を呼ぶ
- さらに 072 bridge の credential(`MAIL_BRIDGE_GMAIL_APP_PASSWORD` / `MAIL_BRIDGE_TO`)も .env 未 set
- 結果: 376 drafts 蓄積 + Yoshilover Exclude Old Articles plugin 復旧 + editor lane 健全化が揃っても、**publish-notice mail だけ最後の運用 gate で止まっている**
- 実装不足ではなく、**運用 gate を開ける 1 操作**が決定打

## purpose

- 「publish-notice mail が 1 通も届いていない」状態を終わらせる
- 1 通だけ real-send smoke で 072 bridge → Gmail 着信までの end-to-end を管理対象にする
- 076 の gate ON 手順を runbook 化、user 判断 8 類型を最小化
- 大量送信は本 ticket scope 外、smoke 1 通のみ

## non_goals

- 073 morning-analyst-email-send / 074 x-draft-email-send / 075 ops-status-email-send の real-send 化(別 ticket、本 ticket で 076 が成功してから段階展開)
- 076 / 072 の code 実装変更(既存 contract のままで動くはず、code 改修は必要時 narrow ticket 化)
- automation.toml への 076 lane 登録(本 ticket は手動 1 通 smoke のみ、cron は別判断)
- bulk publish / mass-send / digest 化
- option D(`RUN_DRAFT_ONLY=False` flip)= 別 user 判断
- 376 drafts 全件の遡及 publish 化
- editor / creator / 086 contract 関連改修

## ticket で固定する runbook の骨子

### Phase 0: 前提確認(私が即実行可能、read-only)

- 072 doc / 076 doc の env precedence + suppress rule を再確認(本 ticket §環境変数 precedence 節に転記済)
- option E Phase 1-2 が完了している(63405 publish 済)
- editor lane が健全(083/084/089/090 land 済)
- WP REST `_yoshilover_source_url` plugin 問題は disabled で通る状態維持

### Phase 1: scanner dry-run preview(私が即実行可能、read-only WP GET のみ)

```bash
mkdir -p /tmp/option_e
cd /home/fwns6/code/wordpressyoshilover && \
python3 -m src.tools.run_publish_notice_email_dry_run --scan \
  --cursor-path /tmp/option_e/publish_notice_cursor.txt \
  --history-path /tmp/option_e/publish_notice_history.json \
  --queue-path /tmp/option_e/publish_notice_queue.jsonl
```

初回は cursor backfill 防止で emit 0、即同じ command を 2 回目 fire → 63405 を検知。

stdout の preview 確認項目(私が user に 1 行で要約):
- `subject`: `[publish] ...` 形になっているか
- `body_text`: 5 行固定で記事タイトル + canonical URL + 発行時刻 + tier(if any)+ source(if any)
- `to`: empty(env 未 set)or `MAIL_BRIDGE_TO` 値
- `status`: `dry_run` 期待
- `suppressed` でないこと

### Phase 2: real-send 必要 env の最終 checklist(user 操作 1 手、user 判断 8 類型)

| 必要事項 | 状態 | 設定方法 | user 判断 |
|---|---|---|---|
| Gmail App Password 16 char | **未取得** | Google Account → セキュリティ → 2 段階認証 → アプリパスワード(`yoshilover` 名で生成)| user only |
| `.env` に `MAIL_BRIDGE_GMAIL_APP_PASSWORD=<16char>` 追加 | **未 set** | `.env` 末尾 1 行追加 | user only(secret 実値投入) |
| `.env` に `MAIL_BRIDGE_TO=fwns6760@gmail.com` 追加 | **未 set** | `.env` 末尾 1 行追加 | user only(recipient 確定) |
| `PUBLISH_NOTICE_EMAIL_ENABLED=1` env(send 時のみ環境変数で渡す) | **未 set** | smoke command 1 行に prefix で付与 | 私が command に含める |
| 076 CLI に `--send` flag 付与 | **未 set** | smoke command の引数 | 私が command に含める |

→ user の 1 手 = **「Gmail App Password 16 char を生成、`.env` に 2 行追加」**(2-3 分)

完了後、user は **「env set」** の 1 ワード返答。

### Phase 3: real-send smoke 1 通 fire(私が実行、user 判断 8 類型 後)

```bash
cd /home/fwns6/code/wordpressyoshilover && \
PUBLISH_NOTICE_EMAIL_ENABLED=1 \
python3 -m src.tools.run_publish_notice_email_dry_run --scan --send \
  --cursor-path /tmp/option_e/publish_notice_cursor.txt \
  --history-path /tmp/option_e/publish_notice_history.json \
  --queue-path /tmp/option_e/publish_notice_queue.jsonl
```

注:
- `PUBLISH_NOTICE_EMAIL_ENABLED=1` を inline で渡す(.env に書かない、shell 一時 env)
- `--send` で dry_run=False
- cursor は Phase 1 で advance 済、再度 63405 を拾うには history reset 必要(下記)
- もしくは Phase 1 で 63405 を拾った直後に同じ session で `--send` 実行(cursor 未 commit 状態を利用)

### Phase 4: 結果確認(私が実行、~1 分以内)

stdout 確認項目:
- `status: sent`(成功)
- `status: suppressed` + `reason: ...`(失敗、下記 routing)
- `MailResult.smtp_response`(Gmail SMTP の応答)
- `/tmp/option_e/publish_notice_queue.jsonl` に `sent` 行追加されたか

user 確認項目(2-3 分以内):
- Gmail に `[publish] ...` 件名のメール 1 通着信
- 本文 5 行が読める
- canonical URL クリックで site の該当 publish に飛ぶ

## user が最後にやる 1 操作

**Gmail App Password 16 char を生成、`.env` 末尾に以下 2 行を追加して保存、私に「env set」と 1 ワード返答**

```
MAIL_BRIDGE_GMAIL_APP_PASSWORD=<16char-app-password>
MAIL_BRIDGE_TO=fwns6760@gmail.com
```

(option E Phase 2 = 63405 publish が未完了の場合、まず WP admin で 63405 publish → 「published: 63405」報告、その後に env set でも順序 OK)

## smoke 成功時の次手(自動連鎖)

- 私が session_log + master_backlog に成功 record 1 行追加
- 088 close(本 ticket、runbook 起動条件達成)
- 後続: **073 morning-analyst-email-send** real-send smoke を同 pattern で展開(別 narrow ticket、088-A 等)→ **074 x-draft-email-send** → **075 ops-status-email-send**(段階展開、各 ticket 1 通 smoke + 個別 env / recipient 設定)
- automation.toml への 076 lane 登録判断は別 user 判断(cron 化 = bulk send 開始 = 別段階)

## smoke 失敗時の切り分け順(私が判定 + routing)

| stdout / 観測 | 含意 | next |
|---|---|---|
| `MISSING_DIGEST` / `INVALID_DIGEST` | 076 入力問題、cursor / history 状態確認 | `/tmp/option_e/` reset → Phase 1 再実行 |
| `EMPTY_TITLE` / `MISSING_URL` | 63405 の post_title / canonical URL が空 | WP admin で 63405 状態確認、必要なら別 publish_id で smoke 再試行 |
| `NO_RECIPIENT` | recipient env 不足 | `.env` の `MAIL_BRIDGE_TO` 確認、または `--to` flag で override 試行 |
| `GATE_OFF` | `PUBLISH_NOTICE_EMAIL_ENABLED=1` 不足 | command の env prefix 確認、再実行 |
| `RuntimeError("no Gmail app password configured")` | 072 credential 不足 | `.env` の `MAIL_BRIDGE_GMAIL_APP_PASSWORD` 確認、Secret Manager fallback 経路は使わない(GOOGLE_CLOUD_PROJECT 未 set) |
| `status: sent` / smtp_response 200 / Gmail 着信なし | Gmail 側 spam filter / 受信トレイ別 tab | Gmail 全フォルダ検索 `from:fwns6760@gmail.com subject:[publish]`、必要なら recipient 別アドレス試行 |
| `status: sent` / smtp_response 失敗 | App Password 期限切れ / 2 段階認証 OFF | App Password 再生成、Google Account 2 段階認証確認 |
| `RECENT_DUPLICATE` | history.json に 24h 以内の同 post_id | `/tmp/option_e/publish_notice_history.json` reset、再実行 |

routing は私が即判定 → user に `失敗 + 次手` を 1 行で返す。user は次手を実行 or 別判断。

## 追加実装が必要な場合の narrow ticket 提案

本 ticket runbook 内では実装不足を発見していない。下記は smoke 失敗時の **可能性のある** narrow ticket 候補:

| 候補 | 条件 | scope |
|---|---|---|
| **088-A**: 076 retry / backoff 強化 | smoke で SMTP 接続 transient 失敗が観測された場合 | 076 sender に retry loop 追加(stdlib 範囲) |
| **088-B**: 076 fixture-input mode | scanner cursor 操作が複雑な場合、`--input <fixture.json>` で固定 payload 送信 path 整備 | 076 sender input mode 強化(既に `--input` あれば不要、現状確認要) |
| **088-C**: Secret Manager 経路 alive 化 | .env 直接設定を避けたい場合、Secret Manager(`yoshilover-gmail-app-password`)経路を WSL 環境で使えるようにする | gcloud auth + GOOGLE_CLOUD_PROJECT 設定、user 判断(prod 接続) |

これらは **smoke 失敗で必要と判明した時のみ** narrow 起票、本 ticket では先回り起票しない。

## acceptance(本 ticket、runbook ticket)

1. publish-notice real-send smoke の手順が **本 doc に 1 本固定**(Phase 0-4 + 失敗 routing 表)
2. user がやる操作は **最小 1 手**(Gmail App Password 生成 + .env 2 行追加)
3. 成功時の次手 = 088 close + 073/074/075 段階展開 ticket(088-D, 088-E, 088-F として後続)
4. 失敗時の切り分け順 = 上記 routing 表で 7 patterns 固定
5. 追加実装が必要な場合は 088-A/B/C を narrow 提案(本 ticket では起票しない)

## 不可触

- 072 / 076 code 本体(既存実装で動くはず、変更不要)
- automation.toml(本 ticket は手動 1 通 smoke のみ、cron 化は別判断)
- editor lane / creator lane / 086 contract / 087 front / 091 audit / 092 creator refactor
- baseballwordpress repo の handoff doc 本体(session_log 1 行追記は OK)
- front lane 全部
- X API / 061-P1 live post(別 ticket scope)

## stop 条件

- option E Phase 2(63405 publish)が未完了 → user に「Phase 2 が必要、WP admin で 63405 publish」と escalation
- Phase 2 完了後 Phase 1 scanner dry-run で 63405 を拾えない → cursor / history 状態確認、reset で再実行
- Phase 3 で `RuntimeError("no Gmail app password configured")` → user に「.env credential 確認」escalation
- smoke 成功後に「次は 073 から real-send 化したい」と user 指示 → 088-D 起票、本 ticket は close 維持

## 関連 file

- `/home/fwns6/code/baseballwordpress/docs/handoff/runbooks/option_e_publish_chain_smoke.md`(option E 本体 playbook、本 ticket は Phase 3-4 を細部化した extension)
- `/home/fwns6/code/wordpressyoshilover/doc/072-mail-delivery-bridge.md`(env precedence 正本)
- `/home/fwns6/code/wordpressyoshilover/doc/076-publish-notice-email.md`(gate / suppress rule 正本)
