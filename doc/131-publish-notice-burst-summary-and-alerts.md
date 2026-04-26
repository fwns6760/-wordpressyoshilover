# 131 publish-notice-burst-summary-and-alerts

## meta

- number: 131
- alias: -
- owner: Claude Code(設計)/ Codex A(実装、130 land 後)
- type: ops / publish-notice mail layering
- status: READY(130 land 後に fire)
- priority: P0.5
- lane: A
- created: 2026-04-26
- supersedes_filename: `131-publish-notice-batch-suppress.md`(旧 file 名、本 file が正)
- parent: 088 / 095-D / 130

## 目的

publish-notice mail を **suppress しない**。
20 件 burst / 100 件 daily の状態でも、user が事故・hard_stop・X/SNS 発火兆候・postcheck 失敗を **見逃さない** mail layering を作る。

## layer 設計

### layer 1: per-post 通常通知(維持)

- 既設の publish-notice mail を維持
- 20 件 burst 内でも 1 件 1 通の per-post 通知は **送る**(suppress しない)

### layer 2: 10 本ごと summary mail

- burst 内で 10 件 publish するたびに summary mail を送る
- summary 内容:
  - 直近 10 件の post_id / title 概要 / category / publishable / cleanup_required / cleanup_success
  - hard_stop 件数(その 10 件 batch 内で hold された数)
  - hold 件数(cleanup 失敗 / verify 失敗で hold された数)
  - daily cap 残数

### layer 3: 即時 alert mail

以下のイベントで **即時 alert** mail を送る:

- publish 失敗(WP REST POST/PUT 4xx/5xx)
- hard_stop 検出
- postcheck 失敗(WP REST GET で status=publish 不一致)
- cleanup 失敗 / verify 失敗 → hold
- X / SNS 発火兆候(`x_sns_auto_post_risk` flag 検出 + WP plugin auto-tweet 痕跡)

alert mail subject に `[ALERT]` prefix。

### layer 4: emergency mail(最高優先)

- X / SNS 実発火を log で検出した場合(後付け検出)
- WP plugin が tweet を投げた tracelog
- subject に `[EMERGENCY]` prefix
- このレイヤーは 130 ticket scope 外、131 では hook 設計のみ

### layer 5: duplicate 抑止

- 同一 post_id の per-post 通知が 30 分以内に 2 回送られる場合のみ suppress
- それ以外の suppress なし

## 不可触

- 既存 publish-notice mail flow 自体の停止
- per-post 通知の suppress(layer 5 例外のみ)
- mail real-send は test では mock(SMTPテストは smtplib mock 使用)
- `.env` / secret(MAIL_BRIDGE_SMTP_* は load_dotenv 経由)
- automation / scheduler 既設変更
- baseballwordpress repo
- WP write / live publish(本 ticket は notification 層のみ、publish 自体は 130 runner 担当)
- `git add -A`
- **git push**

## acceptance

1. layer 1 維持(per-post mail 送る)
2. layer 2 実装(10 件ごと summary mail)
3. layer 3 実装(失敗 / hold / X兆候 即 alert)
4. layer 4 hook 設計のみ(実装は別 ticket)
5. layer 5 duplicate 抑止(30 分内 同 post_id のみ)
6. mail subject prefix で alert / emergency 識別可能
7. test は mock SMTP で全 layer 検証

## verify

- `python3 -m pytest tests/test_publish_notice_*.py -v`
- mock SMTP で送信内容を assert(subject prefix / body 概要)
- 既存 publish-notice tests pass

## next

- 130 実装 land 後に fire
- 131 land 後に 105 autonomous live ramp 開始
