# 072 — Gmail SMTP shared mail delivery bridge

## purpose

- 073 morning analyst / 074 X draft / 075 ops status が共通で使える Gmail SMTP bridge を追加する。
- `src/fact_check_notifier.py` の env key / secret name / default host 互換は維持する。
- 既存 notifier は変更せず、新規 module の `send()` に配送責務を閉じる。

## interface

### `MailRequest`

- `to: list[str]`
- `subject: str`
- `text_body: str`
- `html_body: str | None = None`
- `sender: str | None = None`
- `reply_to: str | None = None`
- `metadata: dict[str, Any] = field(default_factory=dict)`

### `MailResult`

- `status: "sent" | "dry_run" | "suppressed"`
- `refused_recipients: dict[str, list[Any]]`
- `smtp_response: list[Any]`
- `reason: str | None = None`

### `BridgeCredentials`

- `app_password: str`
- `smtp_host: str`
- `smtp_port: int`

### functions

- `load_credentials_from_env() -> BridgeCredentials`
- `send(request: MailRequest, *, dry_run: bool = True, credentials: BridgeCredentials | None = None) -> MailResult`

## credential 取得順序

### Gmail app password

1. `MAIL_BRIDGE_GMAIL_APP_PASSWORD`
2. `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` が set されている場合のみ Secret Manager
3. `GMAIL_APP_PASSWORD`
4. `GMAIL_APP_PASSWORD_SECRET_NAME` または既定 secret `yoshilover-gmail-app-password` を Secret Manager
5. 上記がすべて失敗したら `RuntimeError("no Gmail app password configured")`

### SMTP host / port

1. `MAIL_BRIDGE_SMTP_HOST` / `MAIL_BRIDGE_SMTP_PORT`
2. `FACT_CHECK_SMTP_HOST` / `FACT_CHECK_SMTP_PORT`
3. `smtp.gmail.com` / `465`

### SMTP login username / sender

- login username:
  1. `MAIL_BRIDGE_SMTP_USERNAME`
  2. `FACT_CHECK_EMAIL_FROM`
  3. どちらも空なら raise
- sender header:
  1. `MailRequest.sender`
  2. `MAIL_BRIDGE_FROM`
  3. `FACT_CHECK_EMAIL_FROM`
  4. login username

## empty suppress rule

- `to == []` または `all(not addr.strip() for addr in to)`:
  `status="suppressed"` / `reason="NO_RECIPIENT"`
- `subject.strip() == ""`:
  `status="suppressed"` / `reason="EMPTY_SUBJECT"`
- `text_body.strip() == "" and not (html_body and html_body.strip())`:
  `status="suppressed"` / `reason="EMPTY_BODY"`
- suppress 判定が先。`dry_run=False` でも suppress 条件なら SMTP 接続しない。

## env key 一覧

| purpose | primary | fallback | default |
|---|---|---|---|
| Gmail app password direct | `MAIL_BRIDGE_GMAIL_APP_PASSWORD` | `GMAIL_APP_PASSWORD` | none |
| Gmail app password secret name | `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` | `GMAIL_APP_PASSWORD_SECRET_NAME` | `yoshilover-gmail-app-password` |
| SMTP host | `MAIL_BRIDGE_SMTP_HOST` | `FACT_CHECK_SMTP_HOST` | `smtp.gmail.com` |
| SMTP port | `MAIL_BRIDGE_SMTP_PORT` | `FACT_CHECK_SMTP_PORT` | `465` |
| SMTP login username | `MAIL_BRIDGE_SMTP_USERNAME` | `FACT_CHECK_EMAIL_FROM` | none |
| From header | `MAIL_BRIDGE_FROM` | `FACT_CHECK_EMAIL_FROM` | SMTP login username |
| Secret Manager project id | `GOOGLE_CLOUD_PROJECT` | `GCP_PROJECT`, `GCLOUD_PROJECT` | none |

## fact_check_notifier 互換

- 既存 notifier と shared bridge の共通互換点は `GMAIL_APP_PASSWORD`, `GMAIL_APP_PASSWORD_SECRET_NAME`, `FACT_CHECK_SMTP_HOST`, `FACT_CHECK_SMTP_PORT`, `FACT_CHECK_EMAIL_FROM`, default secret `yoshilover-gmail-app-password`, default host `smtp.gmail.com`, default port `465`。
- bridge は env key 互換だけを持ち、`src/fact_check_notifier.py` の import・signature・内部 helper には依存しない。

## non_goals

- `src/fact_check_notifier.py` / `src/audit_notify.py` の変更
- automation / scheduler / cron wiring
- WP / X API / published 記事への書き込み
- real send の smoke 実行
- 073 / 074 / 075 の sender 実装

## acceptance_check

- `MailRequest` / `MailResult` / `BridgeCredentials` / `send` / `load_credentials_from_env` が doc と実装で 1:1 になっている。
- `dry_run=True` が既定で、SMTP 接続前に suppress 判定を行う。
- env key 順序が `MAIL_BRIDGE_*` → `fact_check_notifier` 互換 key → default になっている。
- Secret Manager は optional で、未 install でも module import 自体は成功する。
- `src/fact_check_notifier.py` と `src/audit_notify.py` は diff 0 のまま。
