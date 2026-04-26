# 103 publish-notice cron health check (dry-run)

## meta

- owner: Claude Code(設計 + 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / health check / dry-run only
- status: READY(102 board 連番、Codex slot 開放時 fire 候補)
- priority: P1(95-D close 後の 095 cron 安定運用補完)
- parent: 095 / 095-D
- created: 2026-04-26

## 目的

publish-notice 経路の health を **切り分ける** dry-run health check。
「メールが飛んでいない」=「壊れた」と誤断しないために、以下 4 つの状態を区別する:

| 切り分け | 意味 | 期待挙動 |
|---|---|---|
| **(a) cron 停止** | WSL cron daemon が止まっている / crontab line 消失 | 即 escalate(復旧手順 = `sudo service cron start` + crontab 復元) |
| **(b) 新規 publish なし** | cron は動いているが scan emit=0 が連続(publish 候補が無い)| 正常 idle(publish なしなら mail なし、当然)|
| **(c) SMTP 失敗** | scan emit > 0 だが send で `RuntimeError` / `NO_RECIPIENT` / 認証失敗 | env / secret / SMTP path 確認 |
| **(d) duplicate history 誤判定** | scan emit > 0 だが history.json が既存 entry で全 `RECENT_DUPLICATE` skip | history.json reset 判断 |

**「メールが届かない = cron 壊れた」ではなく、上記 (a)〜(d) のどれかを判定する**ツール。

## 重要制約

- **実メール送信 一切なし**(dry-run のみ、scan は `--scan` だが `--send` 付けない)
- **secret 表示禁止**(MAIL_BRIDGE_GMAIL_APP_PASSWORD / MAIL_BRIDGE_TO 値は出力 / log に出さない、env が set されているか / 値の長さや first 3 chars 等で間接判定のみ)
- **ログから secret 漏洩防止**(出力 sanitize)
- 既存 `src/tools/run_publish_notice_email_dry_run.py` は **改変禁止**(本 ticket は別 tool として運用)
- 既存 `logs/publish_notice_*` は read-only 利用、改変禁止

## 不可触

- 095 既設 cron line(crontab 改変禁止、判定のみ)
- `.env` 内容
- `MAIL_BRIDGE_*` env 値の表示
- WP write
- X / SNS POST
- `RUN_DRAFT_ONLY` flip
- Cloud Run env
- automation.toml
- baseballwordpress repo
- front / plugin
- `git add -A`
- `git push`(NEW RULE: Claude が push)

## 実装範囲(Codex 便、推奨設計)

### 新規 file

- 新規 module: `src/publish_notice_cron_health.py`
- 新規 CLI: `src/tools/run_publish_notice_cron_health_check.py`
- tests: `tests/test_publish_notice_cron_health.py`

### 検査軸(4 項目)

```python
def check_cron_health() -> dict:
    return {
        "ts": "<JST ISO>",
        "cron_daemon": {  # (a) cron 停止 検出
            "active": True/False,  # systemctl is-active cron
            "crontab_line_present": True/False,  # `# 095-WSL-CRON-FALLBACK` marker grep
            "verdict": "ok" / "stopped" / "crontab_missing"
        },
        "publish_recent": {  # (b) 新規 publish 状況
            "publishes_last_24h": <int>,  # WP REST GET status=publish, after=24h ago
            "verdict": "active" / "idle"
        },
        "cron_log_recent": {  # log 直近 tick 観察
            "last_tick_ts": "<JST ISO>",
            "last_tick_age_min": <int>,
            "last_emit_count": <int>,
            "last_send_count": <int>,
            "last_skip_count": <int>,
            "verdict": "ok" / "stale_log" / "no_log"
        },
        "smtp_send_health": {  # (c) SMTP 失敗 検出
            "sent_24h": <int>,
            "suppressed_24h": <int>,
            "suppressed_reasons": {"NO_RECIPIENT": <int>, "RECENT_DUPLICATE": <int>, ...},
            "smtp_error_24h": <int>,
            "verdict": "ok" / "smtp_error" / "no_recipient" / "credential_missing"
        },
        "history_dedup_health": {  # (d) duplicate history 誤判定
            "history_entries_total": <int>,
            "history_oldest_ts": "<JST ISO>",
            "history_age_days": <int>,
            "duplicate_skip_24h": <int>,
            "duplicate_skip_share": <0.0..1.0>,  # duplicate / (emit + duplicate)
            "verdict": "ok" / "history_too_long" / "all_duplicate_skip"
        },
        "env_presence_only": {  # secret 値表示せず、set 状態だけ
            "MAIL_BRIDGE_TO_set": True/False,
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD_set": True/False,
            "MAIL_BRIDGE_SMTP_USERNAME_set": True/False,
            "MAIL_BRIDGE_FROM_set": True/False,
            # 値は絶対に出さない、None vs not None だけ
        },
        "overall_verdict": "healthy" / "stopped" / "no_publish" / "smtp_failure" / "dedup_misjudgment" / "investigate"
    }
```

### CLI

```
python3 -m src.tools.run_publish_notice_cron_health_check \
  --cron-log /home/fwns6/code/wordpressyoshilover/logs/publish_notice_cron.log \
  --queue /home/fwns6/code/wordpressyoshilover/logs/publish_notice_queue.jsonl \
  --history /home/fwns6/code/wordpressyoshilover/logs/publish_notice_history.json \
  --crontab-marker "# 095-WSL-CRON-FALLBACK" \
  --format json|human \
  [--output PATH]
```

dry-run のみ:
- `--scan` / `--send` は持たない(本 tool は判定だけ、scan は別 tool 095 cron が実行済み)
- WP REST は read-only(`status=publish` after=24h で publish 数 count、本文取得しない)

### 出力例(human)

```
publish-notice cron health check  ts=2026-04-26T22:30:00+09:00

(a) cron daemon:        ok        (systemd active, crontab marker present)
(b) publish recent:     idle      (publishes_last_24h=0)
(c) cron log recent:    ok        (last tick 23:15:36, age 14 min)
(d) smtp send health:   ok        (sent_24h=0, suppressed_24h=0, smtp_error_24h=0)
(e) history dedup:      ok        (entries=6, age=1d, duplicate_skip_share=0.00)
(f) env presence:       MAIL_BRIDGE_TO=set / GMAIL_APP_PASSWORD=set / SMTP_USERNAME=set / FROM=set
                        (実値は表示しない)

overall_verdict: healthy / no_publish (cron 動作中、publish 候補なし、正常 idle)
```

### 受け入れ条件

1. cron daemon 状態を判定(active / stopped / crontab_missing)
2. 直近 24h の publish 件数を WP REST で取得(read-only)
3. 直近 cron tick からの経過時間を判定(stale_log / no_log)
4. SMTP send 結果を集計(sent / suppressed reasons / smtp_error)
5. history.json の dedup 健全性を判定(too_long / all_duplicate_skip)
6. env 4 つの **set 状態のみ** 出力(値は絶対表示しない)
7. overall_verdict で「壊れている / 正常 idle / 投資要」を 1 行判定
8. WP write / 実 mail send 一切なし
9. tests pass(env 値を mock で stub、secret 漏洩しない smoke check)

### tests

- cron daemon active / stopped / crontab missing の各 case
- publish 24h ありなし
- SMTP 失敗(NO_RECIPIENT / credential_missing)
- history 過大(>1000 entry)
- duplicate skip share 高(0.95+)
- env unset(各 4 つの組み合わせ)
- secret 値が stdout / log / JSON に出ないことを mock test で verify(MAIL_BRIDGE_GMAIL_APP_PASSWORD="abc123" を設定し、出力に "abc123" が含まれないこと)
- overall_verdict の各分岐

### 運用想定(本 ticket scope 外)

- 安定運用後、本 health check を WSL cron に hourly 登録(別 ticket、PUB-004-C / 095-C 並行)
- overall_verdict が `stopped` / `smtp_failure` / `dedup_misjudgment` の場合のみ Gmail alert(別 ticket)
- 本 ticket = dry-run 単発実行のみ、cron 化と alert 配線は別 ticket

## commit

- explicit paths(3 file):
  - src/publish_notice_cron_health.py
  - src/tools/run_publish_notice_cron_health_check.py
  - tests/test_publish_notice_cron_health.py
- 既存 doc は触らない
- commit message:
  ```
  103 publish-notice cron health check (dry-run)

  - 4 軸 health check: cron daemon / publish recent / cron log / SMTP / history dedup
  - secret 値非表示 (env presence のみ)
  - 実メール送信なし、WP read-only
  - overall_verdict で 壊れている / 正常 idle / 投資要 を 1 行判定
  ```
- plumbing 3-step fallback if .git/index.lock blocks
- **No git push**(Claude pushes after verification)

## 関連 file

- `doc/095-publish-notice-cron-activation.md`
- `doc/095-D-publish-notice-cron-live-verification.md`
- `doc/095-E-wsl-cron-reboot-resilience.md`
- `doc/088-publish-notice-real-send-smoke-and-mail-gate-activation.md`
- `doc/102-ticket-index-and-priority-board.md`
- `src/tools/run_publish_notice_email_dry_run.py`(参照のみ、改変禁止)
- `src/mail_delivery_bridge.py`(参照のみ、改変禁止)

## stop 条件

- 本 tool 実行で実メール飛ぶ(設計違反、即停止 + escalate)
- secret 値が出力 / log に出る(設計違反、即停止 + escalate)
- 既存 095 cron line を改変したくなる(本 ticket scope 外、別 ticket)
- WP write が必要になる(設計違反、本 ticket は read-only)
