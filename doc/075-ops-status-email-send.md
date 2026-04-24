# 075 ops status email send

- owner: Codex A
- deps: 070(`src/ops_secretary_status.py` renderer)、072(`src/mail_delivery_bridge.py` bridge)
- status: IMPLEMENTING
- scope: snapshot JSON を受けて 070 renderer を通し、072 bridge に渡す薄い adapter を追加する

## purpose

- 070 の fixed 5-line digest renderer を mail delivery bridge に接続する
- caller(automation / Claude chat / future state-change detector) は snapshot JSON を作るだけに留める
- 075 は state change 検出 / snapshot 生成 / scheduling を持たない

## interface

- module: `src/ops_status_email_sender.py`
- CLI: `src/tools/run_ops_status_email_send_dry_run.py`
- default behavior: `dry_run`
- actual send: `--send` opt-in

## input contract

- `--snapshot-path <path>`
  - required group の 1 つ
  - JSON object を読む
- `--stdin`
  - required group の 1 つ
  - stdin の JSON object を読む
- `--subject-datetime '2026-04-24 11:30'`
  - optional
  - subject timestamp override
- `--to a@example.com,b@example.com`
  - optional
  - comma-separated recipients
- `--strict`
  - optional
  - 070 renderer に `strict=True` を渡す
  - forbidden field は reject 扱いで suppress する
- `--body-html-path <path>`
  - optional
  - HTML body を別添する
- `--send`
  - optional
  - 未指定時は dry-run

## subject rule

- prefix は 070 doc の通り `[ops]`
- format:
  - `[ops] Giants ops status YYYY-MM-DD HH:mm`
- datetime source:
  - default は送信時刻の JST `%Y-%m-%d %H:%M`
  - `--subject-datetime` 指定時はそれを優先

## recipient rule

- priority:
  - `--to`
  - `OPS_EMAIL_TO`
  - `MAIL_BRIDGE_TO`
- recipient が空なら suppress `NO_RECIPIENT`

## suppress rule

- `MISSING_SNAPSHOT`
  - `--snapshot-path` 指定で file 不在
- `INVALID_SNAPSHOT`
  - JSON decode error
  - JSON が object ではない
- `RENDERER_ERROR`
  - 070 renderer 実行時の例外
  - strict reject marker も 075 wrapper で例外化して reason に含める
- `EMPTY_BODY`
  - render 後の body が strip して空
- `NO_RECIPIENT`
  - recipient 解決結果が空

## non_goals

- state change 検出
- snapshot 生成
- 070 renderer の field / format / defaults 変更
- `automation.toml`
- scheduler / cron / systemd
- env key の新設
- 実メール送信 runtime の改造
- LLM / X API / WP published
- 039 quality-gmail 経路改造
- 072 bridge / 073 / 074 adapter 変更

## acceptance_check

- import は 070 module と 072 bridge のみ
- suppress 5 path が固定される
- subject rule が `[ops] Giants ops status YYYY-MM-DD HH:mm`
- recipient priority が `--to -> OPS_EMAIL_TO -> MAIL_BRIDGE_TO`
- CLI dry-run が `--snapshot-path` と `--stdin` の両方で動く
