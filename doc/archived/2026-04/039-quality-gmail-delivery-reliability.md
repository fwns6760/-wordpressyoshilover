# 039 — quality-gmail cron delivery reliability の切り分けと復旧

**フェーズ：** 通知 delivery の信頼性確保  
**担当：** Claude Code(運用管理 ticket、必要時のみ Codex に最小修正便を切る)  
**依存：** 015, 現行 `quality-gmail` automation / `logs/quality_monitor/` / `docs/handoff/session_logs/*quality_gmail*`

---

## 概要

- `quality-gmail` は cron automation として `fwns6760@gmail.com` に 4 行メールを送る正本通知フロントである。
- 2026-04-21 の UNC 読取差し替え(`session_logs/2026-04-21_quality_gmail_unc_fallback_fix.md`)で WSL 依存は外したが、cron fire → 送信まで全経路の delivery 信頼性は未検証。
- 本 ticket は delivery が止まった / 届かない時の切り分けフローと最小復旧手順を固定し、user を relay に使わず現場で閉じる運用台帳を作る。

## 029 との分離

- `029` = `quality-gmail` の 4 行の**意味と閾値**を正式化する ticket(品質推移 / 公開準備 / 主因 / 次改善、良化 / 横ばい / 悪化)。内容の contract。
- `039` = `quality-gmail` の**配信経路(cron fire → log read → mail send → 着信)の信頼性**を管理する ticket。delivery の contract。
- 両者は独立で、どちらかが未達でも他方は進める(意味は正しくても届かなければ見えない / 届いても意味が 4 行でなければ運用にならない)。

## 決定事項

### 切り分けの 4 段階

1. **cron fire** — Codex automation として hourly 10:00-23:59 JST で起動しているか(Codex Cloud の run 履歴 / Codex automation の log で確認)
2. **log read** — `\\\\wsl.localhost\\Ubuntu\\home\\fwns6\\code\\wordpressyoshilover\\logs\\quality_monitor\\<today-JST>.jsonl` が Windows 側から読めるか(fresh / stale / none の判定)
3. **mail send** — GPT 側 Gmail 統合が `fwns6760@gmail.com` 宛に送信 call を出したか(automation の run 結果 / GPT 側記録)
4. **着信** — Gmail 受信トレイに `[src:qm] / [src:stale] / [src:none]` の subject が届いたか

### 切り分けの既定 artifact

- 段階 1: Codex Cloud automation run history
- 段階 2: `/home/fwns6/code/wordpressyoshilover/logs/quality_monitor/<date>.jsonl` の最終更新時刻と行数
- 段階 3: automation の run 通知 / GPT 側 log(返答本文に 4 行が出ているか)
- 段階 4: `fwns6760@gmail.com` の実 inbox(user 手元、Claude は観測不可 → user に 1 行報告で済ませる)

### 復旧の最小経路

- **段階 1 失敗**(cron 未 fire): automation schedule の確認 → user 判断で resume / 修正
- **段階 2 失敗**(log 読めず `[src:none]` が連続): `quality-monitor` 側の run 状態確認 → 必要なら `quality-monitor` の cron 確認 ticket に分岐
- **段階 3 失敗**(run はしているが mail 送信 call が出ない): automation prompt の minimum 修正便を Codex に 1 commit で依頼(ここだけ Codex に渡す)
- **段階 4 失敗**(送信 call は出ているが届かない): spam / filter / Gmail 側 API エラーを user 手元で確認 → user 判断

### 不可触

- `quality-gmail` の cadence / recipient / model / 4 行意味は触らない(029 / 本 ticket いずれも意味は scope 外)
- `quality-monitor` 本体は触らない(読み先として扱うだけ)
- 新しい mail channel / 新しい通知先 / 新しい env / 新しい secret は追加しない
- `published` への書き込みは発生させない

### 再発防止の観測ループ

- 1 日 1 回 Claude が段階 2 の log 最終更新時刻を軽く確認し、`[src:none]` が 6h 以上連続していれば本 ticket を再 open する
- 1 週に 1 回、Claude が `docs/handoff/session_logs/` に delivery 観測 1 行を残す(`[src:qm] 継続` / `[src:stale] 発生あり` / `[src:none] 連続` のどれか)
- user から「届いてない」報告があった時だけ段階 1 → 4 の切り分けに入る(平時は静かに維持)

---

## TODO

【】切り分け 4 段階(cron fire / log read / mail send / 着信)を固定する  
【】各段階の既定 artifact 置き場を明記する  
【】段階ごとの最小復旧経路を固定する  
【】`quality-gmail` の cadence / recipient / model / 4 行意味は不可触と明記する  
【】`quality-monitor` 本体は scope 外と明記する  
【】029 との分離(意味 vs 配信)を明記する  
【】delivery 観測ループ(1 日 1 回 / 1 週 1 回)を明記する  
【】user から「届いてない」報告があった時の入口を明記する  
【】Codex への最小修正便が必要になるのは段階 3 の mail send 経路だけであると明記する  

---

## 成功条件

- delivery が止まった時に切り分け手順で原因段階が 1 つに絞れる
- 平時は user が delivery 状態を気にせずに済む
- 029 の 4 行意味が正しく維持されたまま、配信経路の信頼性が独立に管理できる
- 復旧に user を relay として使わない(user 判断が必要なのは段階 1 resume / 段階 4 Gmail 側のみ)
- 既存 mail / automation / cron に副作用を出さない
