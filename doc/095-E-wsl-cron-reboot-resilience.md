# 095-E WSL cron reboot resilience

## meta

- owner: Claude Code(手順 + 自動復帰判断)
- type: ops / runbook / reboot resilience
- status: READY(現状の WSL2 systemd 設定で auto-start 期待、reboot 検証は user op)
- priority: P2(095-D 完了後、095 cron 安定化の補完)
- parent: 095 / 095-D
- created: 2026-04-25

## purpose

PC 再起動後も publish-notice cron が自動復帰するか確認し、必要なら復旧手順を固定する。
WSL2 + Windows shutdown / sleep / log-off / WSL session 終了で cron daemon が消える可能性があり、復帰経路を 1 枚にする。

## 現状把握(2026-04-25)

- cron daemon = `cron.service` (systemd unit、active running、since `2026-04-25 08:59:23 JST` = 10h+ 稼働)
- WSL2 distro = Ubuntu(`/usr/lib/systemd/system/cron.service` が `enabled` + `preset: enabled`)
- WSL session を **明示的に Terminate / Windows shutdown / sleep** すると cron daemon は止まる
- 通常の Windows ログオフ + 再ログイン は WSL session が persist する場合あり(WSL2 仕様 + ユーザー設定依存)

## 不可触

- `.env` / secrets / App Password の表示
- automation.toml(Codex Desktop 側、093 territory)
- crontab の publish-notice 行(本 ticket は確認のみ、改変は別 ticket)
- src / tests / requirements*.txt
- baseballwordpress repo
- WP / X / Cloud Run

## 復帰確認手順(再起動後、user 1 回 + Claude が自動 verify)

### Step 1: WSL 内 cron daemon の状態確認

```bash
systemctl is-active cron
# expected: active
```

または:

```bash
service cron status
# expected: ● cron.service - Regular background program processing daemon
#           Active: active (running) since ...
```

### Step 2: cron が止まっている場合の手動 start

```bash
sudo service cron start
# or:
sudo systemctl start cron
```

確認:

```bash
systemctl is-active cron
# expected: active
```

### Step 3: crontab の publish_notice 行が残っているか確認

```bash
crontab -l | grep -E "publish_notice|095-WSL-CRON-FALLBACK"
# expected: 2 行 (marker comment + cron 行)
```

期待される 2 行:

```
# 095-WSL-CRON-FALLBACK: 暫定運用。Codex Desktop automation tick 復旧時はこの 2 行を削除して /mnt/c/Users/fwns6/.codex/automations/publish-notice-email/automation.toml に切替
15 * * * * cd /home/fwns6/code/wordpressyoshilover && MAIL_BRIDGE_SMTP_USERNAME=fwns6760@gmail.com MAIL_BRIDGE_FROM=fwns6760@gmail.com PUBLISH_NOTICE_EMAIL_ENABLED=1 /usr/bin/python3 -m src.tools.run_publish_notice_email_dry_run --scan --send --cursor-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_cursor.txt --history-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_history.json --queue-path /home/fwns6/code/wordpressyoshilover/logs/publish_notice_queue.jsonl >> /home/fwns6/code/wordpressyoshilover/logs/publish_notice_cron.log 2>&1
```

crontab が空になっていた場合:
- `crontab -l` で空 / no crontab → user に bash で復元 line を投入する小手順を escalate
- 復元 line は本 doc 内に保管(secret なし、recipient address のみ)

### Step 4: 次の :15 tick で `publish_notice_cron.log` が更新されるか確認

```bash
log=/home/fwns6/code/wordpressyoshilover/logs/publish_notice_cron.log
ls -la "$log"
# 直近 mtime が 65 min 以内なら直前 tick が動いた
# 65 min 超なら次 :15 を待って 5 min 後に再確認
```

watch 形式(Claude 自動 verify):

```bash
end_ts=$(date -d "+70 minutes" +%s)
prev_size=$(stat -c%s "$log" 2>/dev/null || echo 0)
while [ $(date +%s) -lt $end_ts ]; do
  cur_size=$(stat -c%s "$log" 2>/dev/null || echo 0)
  if [ $cur_size -gt $prev_size ]; then
    echo "095E_TICK_RECOVERED $(date '+%H:%M:%S')"
    tail -5 "$log"
    exit 0
  fi
  sleep 60
done
echo "095E_TIMEOUT after 70min, cron 復帰失敗"
```

### Step 5: WSL 起動時に cron を auto-start する選択肢

#### option A: systemd の自動起動(現状想定)

WSL2 で systemd が有効な場合、`cron.service` が `enabled` であれば WSL 起動と同時に cron daemon も起動する。

verify:

```bash
systemctl is-enabled cron
# expected: enabled
```

`enabled` になっていない場合:

```bash
sudo systemctl enable cron
```

#### option B: `/etc/wsl.conf` での boot command(systemd 不使用 / 補完)

`/etc/wsl.conf` に以下を追記:

```ini
[boot]
command = "service cron start"
```

これで WSL distro が起動するたびに cron daemon が start する。

#### option C: `~/.bashrc` 起動時に cron start(対話 shell 限定)

```bash
# ~/.bashrc 末尾
service cron status > /dev/null 2>&1 || sudo service cron start
```

ただし WSL bash session を **開かない限り** cron は start しないため、cron トリガが session 開始に依存。option A / B より弱い。

#### 推奨

- **第 1 推奨: option A**(systemd `enabled` 維持。WSL2 systemd OK の現代的設定)
- 第 2 推奨: option B(systemd 不使用環境 / 念のための保険)
- option C は autonomous には不向き(session 開始 trigger 依存)

## reboot 検証手順(user op + Claude 自動 verify)

1. user: PC 再起動 / WSL Terminate → restart
2. user: 「rebooted」1 ワード返信
3. Claude: Step 1 で systemctl is-active cron 確認
4. Claude: Step 3 で crontab 残存確認
5. Claude: Step 4 で次 :15 tick の log 更新を 70 min watch
6. 全 OK なら 095-E close 候補
7. 失敗時 routing:
   - cron daemon 停止 → Step 2 の手動 start を user に提示
   - crontab 消失 → 復元 line 投入手順を提示
   - 次 tick で log 更新なし → 095-D Phase 4 失敗 routing(PATH / dotenv / 権限) と合流

## 完了条件

1. 再起動後 cron daemon active を確認できる
2. crontab に publish_notice 行が残存
3. 次 :15 tick で `publish_notice_cron.log` が更新される
4. 上記 3 点が満たされない場合の復旧手順が本 doc 内に固定される
5. WSL auto-start 設定が option A / B のどちらで稼働しているか確定

## 関連 file

- `/home/fwns6/code/wordpressyoshilover/doc/095-publish-notice-cron-activation.md`(parent、cron 化判断)
- `/home/fwns6/code/wordpressyoshilover/doc/095-D-publish-notice-cron-live-verification.md`(WSL cron 実機検証、本 ticket は reboot 後の同検証)
- `/home/fwns6/code/wordpressyoshilover/doc/093-automation-tick-recovery-and-workspace-reattach.md`(Codex Desktop tick 復旧、本 ticket は WSL cron 側)
- `/etc/wsl.conf`(option B 設定対象)
- `~/.bashrc`(option C 設定対象、推奨せず)

## stop 条件

- crontab 復元手順実施で secret を表示する必要が出たら → 別 user op、絶対に表示しない
- option B / C を導入したいが `/etc/wsl.conf` / `~/.bashrc` を改変する必要 → user 判断 8 類型(local env 変更)
- WSL2 systemd 設定そのものを変更する必要 → user 判断
