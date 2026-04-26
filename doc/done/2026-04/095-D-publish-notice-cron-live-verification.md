# 095-D publish-notice-cron-live-verification

## meta

- owner: Claude Code
- type: ops / cron live verification
- status: in_progress (2026-04-25 fire 20:15 tick で 1st observation)
- parent: 095 publish-notice cron activation
- deps: 088(close 候補)/ 093(Codex Desktop tick down → WSL cron fallback 採用)/ DOTENV-LOAD-088(c974fda)

## purpose

WSL cron に登録した publish-notice (`076 + DOTENV-LOAD-088 fixed runner`) が、新規 publish で自動メールを送り、次回 tick で重複送信しないことを実機検証する。

## 実装状況(2026-04-25 19:44 JST)

- crontab に WSL cron line 配備済(marker comment `# 095-WSL-CRON-FALLBACK` 付き、可逆)
  - `15 * * * * MAIL_BRIDGE_SMTP_USERNAME=fwns6760@gmail.com PUBLISH_NOTICE_EMAIL_ENABLED=1 cd /home/fwns6/code/wordpressyoshilover && python3 -m src.tools.run_publish_notice_email_dry_run --scan --send --cursor-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_cursor.txt --history-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_history.json --queue-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_queue.jsonl >> /home/fwns6/code/wordpressyoshilover/logs/publish_notice_cron.log 2>&1`
- production cursor seeded 19:36:35 (manual dry-run x2)
- production history.json = `{}` 初期状態
- production cron daemon = active (10h+ since 08:59 JST)

## 検証 staging publish (4 件、cursor seed 後)

cursor 19:36:35 < publish 19:44 → 全 4 件が次 :15 tick で emit 対象

| post_id | title 抜粋 | game scope | publish 時刻 | URL |
|---|---|---|---|---|
| 63335 | 山田龍聖 4安打完封 138球 劇勝 | 二軍 西武 Apr 23 | 2026-04-25 19:44:0X | https://yoshilover.com/63335 |
| 63381 | 丸佳浩 マルチ安打 4戦連続 .429 | 二軍 中日 Apr 24 | 2026-04-25 19:44:0X | https://yoshilover.com/63381 |
| 63307 | 石塚裕惺 緊急昇格 翌日「3番・遊撃」プロ | 一軍 Apr 23 lineup | 2026-04-25 19:44:0X | https://yoshilover.com/63307 |
| 63280 | ドラ１竹丸和幸 5回1失点 (4月22日) | 一軍 Apr 22 postgame | 2026-04-25 19:44:0X | https://yoshilover.com/63280 |

backup: `/home/fwns6/code/wordpressyoshilover/backups/wp_publish/2026-04-25/post_<id>_<UTCISO>.json`(各 7-10 KB)

## 検証手順

### Phase 1: 20:15 tick(cron 経路 alive 確認 + 1st send)
- 期待: cron が `15 * * * *` rule で fire、`logs/publish_notice_cron.log` 行追加
- 期待: scanner emit=4(staging publish 全件)、send 4 通(Gmail 着信 4 通)
- 期待: history.json に 4 post_id entry 追加

### Phase 2: 21:15 tick(dedup 確認)
- 期待: scanner emit=0(cursor 進行 + history dedup の両方)
- 期待: send 0 通(再送なし)

## 成功条件

1. cron log に 20:15 + 21:15 の実行記録あり
2. 20:15 queue.jsonl に 4 行 status=sent 追加
3. Gmail 着信 4 通(`[公開通知] Giants <title>...`)
4. 21:15 で同 post_id 再送なし(emit=0 or RECENT_DUPLICATE)

## 安全装置

- mail burst cap: 5 通 / cron tick(stop 条件、6 通以上で escalate)
- noindex 維持(REST publish は status flip のみ、noindex 設定不変)
- X 投稿なし(WP REST publish は X auto-tweet 配線なし、AUTO_TWEET は fetcher /run 経由のみ)
- App Password / secret 実値非表示

## 不可触

- `.env` 本体
- automation.toml / scheduler / Codex Desktop 側
- src/ tests/ requirements*.txt
- front dirty / build / logs (cron log のみ append OK)
- baseballwordpress repo
- WP plugin 設定 / X API / Cloud Run

## stop 条件

- 20:15 tick で cron fire せず → cron daemon 状態再確認 + crontab 構文 verify
- 20:15 で send > 5 通 → 緊急 disable(`crontab -l | grep -v 095-WSL-CRON-FALLBACK | crontab -`)+ user escalate
- Gmail 着信ゼロ → status=sent でも mail blocked = SMTP / Gmail 側問題、088 失敗 routing 7 pattern を流用
- 21:15 で 同 post_id 再送発生 → cursor 進行 + history.json dedup logic 不整合、緊急 disable + 088-A narrow 候補

## 関連 file

- /home/fwns6/code/wordpressyoshilover/doc/088-publish-notice-real-send-smoke-and-mail-gate-activation.md
- /home/fwns6/code/wordpressyoshilover/doc/093-automation-tick-recovery-and-workspace-reattach.md
- /home/fwns6/code/wordpressyoshilover/doc/095-publish-notice-cron-activation.md
- /home/fwns6/code/wordpressyoshilover/doc/PUB-002-launch-small-manual-publish-and-quality-improvement.md
- crontab line(WSL cron, marker `# 095-WSL-CRON-FALLBACK`)
