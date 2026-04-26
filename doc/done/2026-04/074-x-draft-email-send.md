# 074 X draft digest email sender

## purpose

- 065-B1 が出力する X 下書き digest body text を入力に、072 bridge 経由で 1 通送る thin adapter を固定する。
- 074 自体は rendering / validation / dedup / LLM call / X API / 自動投稿を持たない。
- 責務は subject 決定、recipient 解決、item count 判定、suppress 判定、072 bridge への `MailRequest` 組み立てだけに閉じる。

## interface

### input

- `body_text_path: str` 必須
- `body_html_path: str | None` optional
- `override_subject_datetime: str | None` optional
- `override_recipient: list[str] | None` optional
- `item_count_override: int | None` optional

### public API

- `build_subject(now_jst: str | None, override: str | None) -> str`
- `resolve_recipients(override: list[str] | None) -> list[str]`
- `count_items(body_text: str) -> int`
- `send(request: XDraftEmailRequest, *, dry_run: bool = True, bridge_send=src.mail_delivery_bridge.send, now_provider=None) -> XDraftEmailResult`

### CLI

- `python3 src/tools/run_x_draft_email_send_dry_run.py --body-text-path <txt>`
- dry-run default
- `--send` のときだけ 072 bridge の real send path を使う

## input contract

### body text

- `--body-text-path` は必須
- 想定入力は 065-B1 `src/tools/run_x_draft_email_dry_run.py --format human` の stdout を保存した UTF-8 text file
- 074 は本文の 8 欄構造を再生成しない
- body text が file 不在なら `MISSING_BODY`
- body text が strip 後 empty なら `EMPTY_BODY`

### item count

- `--item-count` は optional
- 明示された場合は body text 推定より優先する
- 省略時は B1 human format の item separator から推定する
- 074 の推定は `candidate N` 行の個数に依存する
- item 数が 0 なら空メール禁止で suppress する

### body html

- `--body-html-path` は optional
- 渡された場合だけ UTF-8 file として読んで `MailRequest.html_body` にそのまま流す
- sender / reply-to は 074 では独自解決しない

## subject rule

- 固定文言:
  - `[X下書き] Giants news drafts YYYY-MM-DD HH:mm`
- `YYYY-MM-DD HH:mm` は JST
- 既定は送信時刻の JST `%Y-%m-%d %H:%M`
- `--subject-datetime '2026-04-24 08:00'` が渡された場合は送信時刻より優先する
- 073 の `[蓄積中]` prefix は付けない

## recipient rule

- recipient override があれば最優先
- override が無ければ `X_DRAFT_EMAIL_TO`
- `X_DRAFT_EMAIL_TO` が空なら `MAIL_BRIDGE_TO`
- 両方空なら suppress
- 複数 recipient は comma separator

## suppress rule

- body text path 未指定 / file 不在 -> `MISSING_BODY`
- body text empty / whitespace-only -> `EMPTY_BODY`
- `item_count_override=0` 明示 or body text に item marker が 0 個 -> `NO_ITEMS`
- recipient 解決結果が空 -> `NO_RECIPIENT`

## non_goals

- 065-B1 renderer / validator / digest / dry-run CLI の変更
- LLM call / AI 生成
- dedup / X API / 自動投稿 / cadence 制御
- 060 / 061 / 072 / 073 / `automation.toml` / scheduler / cron / systemd unit の変更
- WordPress 側の書き込み
- 実メール送信の smoke 実行
- env key の追加
- 075 ops status の先食い

## acceptance_check

- 074 の実装は新規 4 file に閉じ、072 bridge は import only
- 065-B1 module は diff 0 のまま read-only 参照に留める
- suppress code は `MISSING_BODY / EMPTY_BODY / NO_ITEMS / NO_RECIPIENT` の 4 系統に閉じる
- subject は `[X下書き] Giants news drafts YYYY-MM-DD HH:mm` を守る
- recipient precedence は `override -> X_DRAFT_EMAIL_TO -> MAIL_BRIDGE_TO`
- `--item-count` 未指定時の item count 推定は B1 human format の `candidate N` 行に一致する
- CLI dry-run は通常 path と suppress path の 2 系統を確認する
