# 093 Automation tick recovery and workspace reattach

## meta

- owner: **Claude Code**(運用 / runbook ticket、Codex 実装便ではない)
- type: **ops/runbook**(現象整理 + 診断手順 + recovery path、新規実装なし)
- status: OPEN(現在 進行中の問題、再現可能)
- created_at: 2026-04-25 00:25 JST
- deps: 042 / 043 / 044(reboot 系 ticket、本 ticket は app 起動中の別現象)/ 069(deterministic local runner bridge、heartbeat 機構の正本)
- non_blocker_for: 088 手動 smoke / 094 lineup refactor / 095 publish-notice cron activation / editor lane / creator lane

## why_now

- Codex Desktop app は **active**(本 chat session が動いている、`/mnt/c/Users/fwns6/.codex/logs_2.sqlite` が今この瞬間も書き込まれている)
- automation 定義 3 本 全て `status = "ACTIVE"` + `rrule = "FREQ=HOURLY;INTERVAL=1"`(`/mnt/c/Users/fwns6/.codex/automations/{draft-body-editor,quality-monitor,quality-gmail}/automation.toml` で確認)
- ただし `/mnt/c/Users/fwns6/.codex/heartbeats/` dir が **存在しない**(prompt 冒頭の `cmd /c "mkdir ... heartbeats"` が 1 度も実行されていない = tick が 0 回)
- 各 automation の WSL 内 runner(`run_quality_monitor` / `run_draft_body_editor_lane` / quality-gmail prompt)は **手動 WSL fire で完全動作**(本 session の私が実証、scanned_count: 48 / draft 376 件 / 39+ candidates)
- 044(startup 登録 + reboot smoke)/ 042(reboot recovery)/ 043(auto recovery)は **reboot 前提**の ticket、現状(app 起動中だが tick 不発火)は cover 範囲外
- → **「app 起動中だが Codex Desktop の cron runner が tick を発火していない」現象の独立 ticket が必要**

## purpose

- 「app 起動中 / automation 定義 ACTIVE / runner 健全 / heartbeat 0」という固有現象を再現条件 + recovery path 付きで固定
- runbook 化、user 1 手ずつ追える形に
- 手動 smoke(088)は別 ticket で機能、本 ticket は cron 化継続価値の確保

## non_goals

- runner code 改修(WSL 内 Python 経路は健全、touch 不要)
- automation.toml の rrule / prompt / cwds 改修(069 で deterministic shape 確定済、touch 不要)
- 044 / 042 / 043 の置き換え(reboot 系は今後も維持、本 ticket は別現象)
- WP write / mail real-send / X API
- baseballwordpress repo / front lane / 070-092 contract

## ticket で固定する runbook の骨子

### Phase 0: 現象整理 + 再現確認(私が即実行可能、read-only)

確認チェックリスト:
- [ ] Codex Desktop app process が active(`logs_2.sqlite` 直近 5 分以内に更新がある)
- [ ] 3 automation の `automation.toml` が全て `status = "ACTIVE"` + `rrule = "FREQ=HOURLY;INTERVAL=1"`(`cat /mnt/c/Users/fwns6/.codex/automations/{draft-body-editor,quality-monitor,quality-gmail}/automation.toml` で確認)
- [ ] `/mnt/c/Users/fwns6/.codex/heartbeats/` dir が存在しない、または存在しても 24h 以内の `*.txt` が無い
- [ ] WSL から runner 直接 fire で `scanned_count > 0` 等の正常 stdout が返る(runner 健全確認)
- [ ] `/home/fwns6/code/wordpressyoshilover/logs/quality_monitor/<today>.jsonl` が **存在しない or 24h 以内の line が無い**

→ 全 5 条件 hit で **本 ticket の現象 = 確定**。

### Phase 1: 最短診断(私が即実行可能、read-only、~5 分)

```bash
# Step 1: app process 生存確認
ls -la /mnt/c/Users/fwns6/.codex/logs_2.sqlite

# Step 2: automation 定義一括確認
for id in draft-body-editor quality-monitor quality-gmail; do
  echo "=== $id ==="
  grep -E "^(status|rrule|model|cwds)" /mnt/c/Users/fwns6/.codex/automations/$id/automation.toml
done

# Step 3: heartbeat dir 確認
ls -la /mnt/c/Users/fwns6/.codex/heartbeats/ 2>&1 || echo "DIR NOT FOUND"

# Step 4: runner 手動 fire test
cd /home/fwns6/code/wordpressyoshilover && \
  python3 -m src.tools.run_quality_monitor --target draft --page-limit 5 2>&1 | tail -3

# Step 5: log dir freshness 確認
ls -lt /home/fwns6/code/wordpressyoshilover/logs/quality_monitor/ 2>&1 | head -5
ls -lt /home/fwns6/code/wordpressyoshilover/logs/draft_body_editor/ 2>&1 | head -5

# Step 6: cap_sid workspace bind 確認
cat /mnt/c/Users/fwns6/.codex/cap_sid 2>&1
```

期待:
- Step 1: 直近 mtime
- Step 2: 全 ACTIVE / FREQ=HOURLY
- Step 3: `DIR NOT FOUND` または stale
- Step 4: 正常 stdout JSON
- Step 5: stale log(数日前)
- Step 6: workspace SID list、`c:/users/fwns6` 含むか確認

→ 診断 OK = 本 ticket 現象、Phase 2 へ。
→ 診断異常(runner fail 等) = 別 root cause、043/044 へ routing。

### Phase 2: workspace reattach / runner recovery(user 操作、~3 分)

Codex Desktop app 内で次の 1 手ずつ試行:

#### Step A: 同 app session で workspace の明示再 attach(最小手)

1. Codex Desktop app の sidebar / workspace switcher を開く
2. 現在 attach されている workspace 一覧を確認
3. `C:\Users\fwns6` または `c:/users/fwns6` に対応する workspace が **active / online** 表示か確認
4. もし「sleeping」「detached」「offline」等の状態なら、明示的に **「activate」または「reconnect」**

→ 5 分待つ → Phase 3 確認

#### Step B: automation panel が UI 上に無い場合の代替

(本環境では確認済)Codex Desktop の Automations UI が見当たらない場合:
- app の Settings / Advanced / Beta features に「automations」「cron」「scheduled tasks」trigger があるか確認
- なければ Step C へ

#### Step C: app 完全再起動(WSL 影響なし、最後の手)

1. Codex Desktop app を完全 quit(System Tray icon → Quit、または Task Manager で `codex` 系 process を全 kill)
2. 30 秒待つ
3. Codex Desktop app を再起動
4. 起動後 5-10 分待つ(automation registry の reload 時間)
5. Phase 3 確認

→ Phase 3 で復旧確認。

### Phase 3: 成功判定(私が確認、Phase 2 後 5-10 分)

3 つの観測点で復旧判定:

| # | 観測点 | 期待 | 観測 method |
|---|---|---|---|
| 1 | `/mnt/c/Users/fwns6/.codex/heartbeats/` dir 出現 + `quality-monitor.txt` (or 同等)が存在 | dir + 1+ file | `ls -la /mnt/c/Users/fwns6/.codex/heartbeats/` |
| 2 | `/home/fwns6/code/wordpressyoshilover/logs/quality_monitor/<today>.jsonl` に新規 line | last_modified が 65 分以内 | `ls -lt logs/quality_monitor/` |
| 3 | Codex Desktop app UI で 3 automation の "next run" timestamp が future / sliding | 各 automation で next_run > now | UI 直接観察 |

→ **3 / 3 hit** = 復旧成功 → 本 ticket close
→ **1-2 / 3 hit** = 部分復旧、別 automation が個別問題、追加切り分け
→ **0 / 3 hit** = Phase 2 失敗、Phase 4 失敗 routing へ

## user が今やる 1 操作

**Codex Desktop app で workspace switcher を開き、`C:\Users\fwns6` workspace の状態を確認 → sleeping / detached / offline なら activate**

(UI に該当機能が無い場合 = Phase 2 Step C = app 完全再起動 → 5-10 分待ち)

完了したら私に **「reattached」または「restarted」** + 1 行報告。

私が即 Phase 3 観測 → 成功 / 失敗判定 → 1 行で次手 routing。

## 失敗時 routing

| 観測 | 含意 | next |
|---|---|---|
| Phase 2 Step A 後も heartbeats 無し | workspace bind は正常、別所で詰まり | Step B(automation panel 探索) → Step C(再起動) |
| Phase 2 Step C(再起動)後も heartbeats 無し | app 内部 cron runner subsystem が破損 | 093-A narrow ticket(automation 定義削除 + 再登録)を起票 / または Codex CLI 経由の手動 trigger 模索 |
| heartbeat 出るが log freshness 戻らず | runner 経路は通るが内部 fail | runner 単体エラー確認(Phase 1 Step 4 stderr) |
| heartbeat 1 automation だけ出る | 部分復旧、特定 automation の再登録 | 該当 automation だけ disable → enable で個別 reset |

## 追加実装が必要な場合の narrow ticket 提案

本 ticket runbook 内では実装不足を発見していない。下記は Phase 4 失敗時の **可能性のある** narrow ticket 候補:

| 候補 | 条件 | scope |
|---|---|---|
| **093-A**: automation 定義 backup + 再登録 script | Phase 2 Step C 後も heartbeats 0 | shell script で `automation.toml` を backup → delete → 再 cp、Codex Desktop に再登録させる手順 |
| **093-B**: WSL `cron` 代替経路 fallback | Codex Desktop subsystem が長期 broken | WSL crontab で 3 runner を hourly fire、Codex Desktop と独立、user 判断 8 類型(crontab 設定変更) |
| **093-C**: heartbeats 監視 alert | automatic detection + alert | Cron task で heartbeats freshness 監視 + Gmail alert(072 bridge 流用)、055 / 088 と同じ手法 |

これらは **Phase 2 失敗で必要判明時のみ** narrow 起票。

## acceptance(本 ticket、runbook ticket)

1. 現象整理が **本 doc に固定**(Phase 0 チェックリスト 5 条件)
2. 最短診断手順が **本 doc に固定**(Phase 1 6 step、~5 分)
3. workspace reattach / runner recovery 手順が **user 1 手ずつ追える形**(Phase 2 Step A/B/C)
4. 成功判定 3 観測点が **明確**(Phase 3、3 / 3 hit で復旧)
5. 失敗 routing 4 pattern が **整理**(Phase 4)
6. 追加実装は 093-A/B/C の **narrow 候補のみ**(本 ticket では起票しない、Phase 失敗時のみ)

## 不可触

- runner code(WSL 内 Python 健全、touch 不要)
- `automation.toml`(069 で確定 shape、touch 不要、本 ticket は環境側の問題)
- 044 / 042 / 043(reboot 系で完全別 ticket)
- 088 手動 smoke / 095 publish-notice cron activation(独立 ticket、依存しない)
- editor / creator / 086 / 091 / 092 / 094 contract
- baseballwordpress repo / front lane

## stop 条件

- Phase 0 チェックリストで 5 条件 hit しない → 別 root cause、043/044/041 等へ routing
- Phase 2 全試行後も Phase 3 観測 0/3 → 093-A/B/C narrow 候補から **1 本選択**(user 判断 8 類型 = 環境変更の踏み込み)
- WSL `cron` 代替(093-B)選択時 → user 判断必要(crontab 設定 = local env 変更)
