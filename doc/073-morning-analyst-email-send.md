# 073 morning analyst digest email sender

## purpose

- seo-analyzer 側が出力する朝 digest JSON と、Claude analyst が手書きした 5 ブロック本文 text を入力に、072 bridge 経由で analyst digest mail を送る thin adapter を固定する。
- 073 自体は本文生成を持たない。subject 決定、recipient 解決、suppress 判定、072 bridge への `MailRequest` 生成だけを責務にする。

## interface

### input

- `digest_json_path: str` 必須
- `body_text_path: str` 必須
- `body_html_path: str | None` optional
- `override_subject_date: str | None` optional
- `override_recipient: list[str] | None` optional

### public API

- `load_digest_meta(path: str) -> AnalystDigestMeta`
- `build_subject(meta: AnalystDigestMeta, override_date: str | None) -> str`
- `resolve_recipients(override: list[str] | None) -> list[str]`
- `send(request: AnalystEmailRequest, *, dry_run: bool = True, bridge_send=src.mail_delivery_bridge.send) -> AnalystEmailResult`

### CLI

- `python3 src/tools/run_morning_analyst_dry_run.py --digest-path <json> --body-text-path <txt>`
- dry-run default
- `--send` のときだけ 072 bridge の real send path を使う

## input contract

### digest JSON

- seo-analyzer 側 contract の `window` を必須とする
- 073 が参照するのは `window.latest_date`, `window.comparison_ready`, `window.status` のみ
- 他 key (`kpis`, `winners`, `losers`, `query_moves`, `opportunities`, `next_action_candidates`, `revenue`, `social_x`) は read-only contract 前提で、073 では解釈しない

### body text

- Claude analyst が 5 ブロック contract に従って手書きした本文を UTF-8 text file で渡す
- 073 は block 構造を再検証しない
- empty / whitespace-only は suppress 対象

### body html

- optional
- 渡された場合だけ UTF-8 file として読んで `MailRequest.html_body` にそのまま流す
- sender / reply-to は 073 では独自解決しない。`MailRequest.sender=None`, `reply_to=None` のまま 072 bridge に渡し、072 側の env 解決を流用する

## subject rule

- 既定:
  - `[analyst] Giants morning digest YYYY-MM-DD`
- `YYYY-MM-DD` は digest JSON `window.latest_date`
- `override_subject_date` が渡された場合は `window.latest_date` より優先
- `window.comparison_ready = false` のときも suppress しない
  - subject は `[analyst][蓄積中] Giants morning digest YYYY-MM-DD`

## recipient rule

- recipient override があれば最優先
- override が無ければ `ANALYST_EMAIL_TO`
- `ANALYST_EMAIL_TO` が空なら `MAIL_BRIDGE_TO`
- 複数 recipient は comma separator

## suppress rule

- digest JSON not found -> `MISSING_DIGEST`
- digest JSON parse error -> `MISSING_DIGEST`
- digest JSON に `window` key が無い -> `INVALID_DIGEST`
- body text not found -> `EMPTY_BODY`
- body text empty / whitespace-only -> `EMPTY_BODY`
- recipient 解決結果が空 -> `NO_RECIPIENT`

## non_goals

- LLM call / AI 生成
- X API / AdSense / BigQuery / Secret Manager / Google API の新規 call
- 074 X draft / 075 ops status との共通 renderer 化
- `automation.toml`, scheduler, cron, systemd unit, env provisioning の変更
- WordPress 側の書き込み
- 実メール送信の smoke 実行
- `src/mail_delivery_bridge.py` の signature / credential fallback / SMTP host fallback の変更

## acceptance_check

- 073 の実装は新規 4 file に閉じ、072 bridge は import only
- `dry_run=True` が既定で、dry-run では bridge send を呼ばない
- `comparison_ready=false` は suppress せず、subject prefix だけ変える
- recipient precedence は `override -> ANALYST_EMAIL_TO -> MAIL_BRIDGE_TO`
- suppress code は `MISSING_DIGEST / INVALID_DIGEST / EMPTY_BODY / NO_RECIPIENT` の 4 系統に閉じる
- CLI は `[request]`, `[meta]`, `[subject]`, `[result]` の順で stdout を出す
