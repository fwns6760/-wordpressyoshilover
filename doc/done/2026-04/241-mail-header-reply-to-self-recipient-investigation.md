# 241 mail-header reply-to self-recipient investigation and minimal fix

- number: 241
- type: investigation + minimal impl
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 240
- related: 240-followup, 219, 222
- owner: Codex B
- lane: B
- created: 2026-04-28

## background

240 で publish-notice の SMTP login user / visible From を `y.sebata@shiny-lab.org` に切り替え、smoke 1 通実送信成功。ところが user 側で **mail は届くが Gmail 通知が鳴らない** 状態が継続。

GCP 側の env / IAM / SMTP 認証は完全に正しく構成されている(read-only verify 済み):

- `MAIL_BRIDGE_SMTP_USERNAME=y.sebata@shiny-lab.org`
- `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org`
- `MAIL_BRIDGE_TO=fwns6760@gmail.com`
- `MAIL_BRIDGE_REPLY_TO=fwns6760@gmail.com` ← **suspect**
- `MAIL_BRIDGE_GMAIL_APP_PASSWORD` ← secret-backed (`yoshilover-shiny-lab-gmail-app-password:latest`)
- ERROR log 0、`status=sent` で配信成功

つまり残る変数は **mail header の semantics** のみ。特に `Reply-To` が **受信者自身 (`fwns6760@gmail.com`)** を指している点が、Gmail の「自分とのやり取り thread」判定で通知抑制の trigger になっている疑い。

## current header build (read-only audit, do not modify here)

`src/mail_delivery_bridge.py` の現状仕様:

| header | 現挙動 | source |
|---|---|---|
| `From` | `MAIL_BRIDGE_FROM` env(または `NOTIFY_FROM` / `FACT_CHECK_EMAIL_FROM` / SMTP login user の順) | `_resolve_sender()` (line 199-203) |
| `To` | `request.to` を comma 結合 | `_build_message()` (line 217) |
| `Reply-To` | `MAIL_BRIDGE_REPLY_TO` env(または `NOTIFY_REPLY_TO`)、空なら header 省略。resolved address が recipient と一致する場合も header 省略 | `_resolve_reply_to()` / `_reply_to_matches_recipient()` / `_build_message()` (line 220-234) |
| `Sender` | **set されていない** | - |
| envelope sender / Return-Path | `smtplib.SMTP.send_message(message)` を `from_addr=` 指定なしで呼び、Python が `From` ヘッダから自動抽出 | `send()` (line 271) |
| `Message-ID` | `make_msgid(domain="yoshilover.com")` | `_build_message()` (line 221) |

## hypothesis

主仮説: **`Reply-To` が受信者自身を指している** ため Gmail が thread 主と認識し通知を抑制している。

副仮説:
- `Sender` header が無く `From` のみで Gmail が会話 thread 判定を強めている
- `Message-ID` の domain (`yoshilover.com`) と SMTP login domain (`shiny-lab.org`) の不一致が二次的影響
- envelope sender (Return-Path) を明示指定していないことで SPF/DKIM alignment に副作用

## smoke probe(241 起票と並行で Claude/auth executor が実施、結果を本 ticket に追記する)

probe 内容:
- env `MAIL_BRIDGE_REPLY_TO` を **削除** して再 smoke 1 通
- code 変更なし、env-only、可逆
- 結果(通知が鳴った / 鳴らない)を本 ticket の **probe result** section に user 報告 + Claude 観測として追記

probe 結果の使い方:
- **鳴った** → 主仮説確定 → 最小修正案 1(Reply-To が recipient self を指すとき header 省略)
- **鳴らない** → 副仮説へ調査拡大 → `Sender` header / `Message-ID` domain / envelope sender 明示

## scope (Codex B work)

### investigation
1. `src/mail_delivery_bridge.py` の header build logic を doc 化(本 ticket の `current header build` section を更新)
2. probe 結果(Claude/auth executor から本 ticket に追記される)を入力として、最小修正案を 1 本に絞る
3. Gmail の self-thread / muted-conversation 判定に影響しうる header の組み合わせを文献ベースで整理

### minimal implementation
probe 結果次第:
- **Reply-To = recipient self なら header 省略**(if `Reply-To` resolved value matches any of recipient list, omit header)
- もしくは `Sender` header を `MAIL_BRIDGE_SMTP_USERNAME` から明示注入
- もしくは envelope sender を `smtplib.send_message(message, from_addr=smtp_username)` で明示

複数案が並ぶ場合は、code diff 最小 / 既存 tests 影響最小 / 副作用最小 の優先順で 1 案へ絞る。

### tests
- `tests/test_mail_delivery_bridge.py` に追加:
  - `Reply-To` resolved value が recipient list と一致したら header 省略される(該当修正を採用した場合)
  - `Reply-To` env 未設定時は header 省略(既存挙動の regression test)
  - `Reply-To` env が recipient と異なる場合は header 残る
  - 既存 publish-notice mail flow / subject prefix / manual_x_post_candidates が影響を受けない smoke

## acceptance (3 点 contract per memory)

1. **着地**: 仮説確定後、code 修正(または「修正不要」結論)+ tests + 本 ticket の probe result / decision section が landed
2. **挙動**: 修正後の smoke で Gmail 通知が鳴る、または鳴らない場合の次手 (`Sender` 追加 / Message-ID domain 等) が次 ticket に分離されている
3. **境界**: publish-notice の subject prefix / mail classification / manual_x_post_candidates / scan logic に影響ゼロ、env / secret 触らない

## write_scope

- `src/mail_delivery_bridge.py`
- `tests/test_mail_delivery_bridge.py`
- `doc/active/241-mail-header-reply-to-self-recipient-investigation.md`(本 file、probe 結果と decision を追記)
- `doc/README.md`(241 row 追加)
- `doc/active/assignments.md`(241 row 追加)

## non-goals

- env mutation(env は Claude/auth executor 側で probe + 最終適用)
- secret 触る / 表示する
- WP publish / X live post / publish gate / RUN_DRAFT_ONLY
- 他 sender (`x_draft_email_sender.py` / `ops_status_email_sender.py` / `morning_analyst_email_sender.py`) の同経路展開(別 ticket)
- subject prefix / mail classification / manual_x_post_candidates / scan logic の変更
- Cloud Run / Scheduler の cadence 変更
- `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` 経路の例外握り潰し bug 修正(別 narrow ticket 候補、240 で secret-backed env injection に切替済で運用は通っている)

## probe result(Claude/auth executor 追記、2026-04-28 JST)

- env mutation: `MAIL_BRIDGE_REPLY_TO` を一時 remove(他 mail env 維持、code 不変)
- smoke execution: `publish-notice-6k4vt`、`status=sent reason=None`、ERROR log 0
- subject: `[smoke 240 v4 noReplyTo] From=y.sebata@shiny-lab.org`
- user 報告: **PC の Gmail 通知が鳴った**(`v3` Reply-To あり = 通知鳴らず、`v4` Reply-To なし = PC 通知 success、mobile 通知は未確認)
- restore: command/args は default に restore 済、`MAIL_BRIDGE_REPLY_TO` env は削除のまま(本 ticket landed まで暫定維持)

→ **主仮説確定**: `Reply-To` が **受信者自身 (`fwns6760@gmail.com`)** を指していたことが Gmail 通知抑制の主因。

## decision(2026-04-28 JST、user 方針 lock)

- **採用案**: `_resolve_reply_to()` で resolved value が recipient list 内のいずれかと一致する場合、`Reply-To` header を omit する
- 採用しない案(本 ticket scope 外):
  - `Sender` header 明示注入(副仮説、現 probe で不要)
  - envelope sender 明示指定(副仮説、現 probe で不要)
  - `Message-ID` domain 整合(副仮説、現 probe で不要)
- 修正範囲: `src/mail_delivery_bridge.py` + `tests/test_mail_delivery_bridge.py` の最小差分
- publish-notice 既存挙動 / 他 mail sender / subject prefix / mail classification / manual_x_post_candidates / scan logic 不変
- repo 修正: `_reply_to_matches_recipient()` を追加し、`EmailMessage` 生成時に Reply-To address と recipient address を `email.utils.getaddresses()` + casefold で比較。self-recipient 一致時は `Reply-To` header を omit
- tests: `tests/test_mail_delivery_bridge.py` に env Reply-To self omit / request Reply-To self omit を追加し、異なる Reply-To 維持・未設定 omit の既存 flow を維持
- 修正 landed 後、Claude/auth executor が `MAIL_BRIDGE_REPLY_TO=fwns6760@gmail.com` を env に戻して動作 verify(Reply-To header が omit されることを smoke で確認)

## live verify + close evidence(2026-04-28 JST)

- repo commit: `894db98` 241: omit self-recipient reply-to mail header(+228/-5、5 path)
- image rebuild: `publish-notice:25f176b` (rebuild commit base = 242-D2 着地後の `25f176b`、Cloud Build success)
- Cloud Run Job update: `gcloud run jobs update publish-notice --image=...:25f176b` 完了
- env restore: `MAIL_BRIDGE_REPLY_TO=fwns6760@gmail.com` 復元
- smoke v5 execution: `publish-notice-9t59j` exit(0)、`status=sent reason=None`
- subject: `[smoke 240 v5 post-rebuild] From=y.sebata@shiny-lab.org Reply-To=self omit test`
- user 報告: **PC 通知 yes / モバイル通知 yes**(両方発火、Reply-To header omit が live で動作確認)

→ **241 CLOSED**(2026-04-28 JST)。close gate(env restore smoke + PC/mobile 通知確認)全部 pass。

横展開候補(別 ticket):
- 他 mail sender(`x_draft_email_sender.py` / `ops_status_email_sender.py` / `morning_analyst_email_sender.py`)も同 `mail_delivery_bridge.py` 経由 = 修正自動適用済み、ただし各 sender 固有の reply_to override の有無は未 grep。run-time で問題が出たら narrow ticket で起票
- `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` 経路の例外握り潰し bug は別 narrow ticket 候補(現状 secret-backed env injection 経路で運用は通っている)
