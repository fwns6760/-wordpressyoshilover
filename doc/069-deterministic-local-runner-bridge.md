# 069 deterministic local runner bridge

- owner: Codex A
- deps: 現行 Codex automations(draft-body-editor / quality-monitor / quality-gmail)
- status: READY
- priority: 本線の最優先(046 / 047 / 048 / 065 の runtime 由来遅延の解消先)
- fire 前提: user 手元作業に依存しない(automation.toml の shape 修正が本便の主体、user 手元作業は次 tick 発火時のみ)

## §1 目的

quality-monitor / draft-body-editor の実行形を Windows 側の安定起点から明示的に WSL へ橋渡しする deterministic shape に揃え、UNC cwd 由来の不安定を取り除く。runtime 由来で 046 first wave 実運用観測 / 047 派生 emit 実運用観測 / 048 HOLD 解除 trigger / 065 fire 条件がまとめて遅れている状況を先に閉じる。

## §2 背景(根因の切り分け)

- 現状の shape(`/mnt/c/Users/fwns6/.codex/automations/` を正とする):
  - **draft-body-editor**: `cwds = ["\\\\wsl.localhost\\Ubuntu\\home\\fwns6\\code\\wordpressyoshilover"]`(UNC cwd、不安定の主因)
  - **quality-monitor**: `cwds = ["C:\\Users\\fwns6"]` + prompt 内 `wsl.exe bash -lc "cd /home/... && python3 -m ..."`(既に deterministic 形に近い)
  - **quality-gmail**: `cwds = ["C:\\Users\\fwns6"]` + Windows UNC 読取のみ(`wsl.exe` を呼ばない、digest 現状形維持)
- `wsl.exe subprocess が Codex automation の user context で denied` 系の失敗は UNC cwd と暗黙 WSL 解決が絡む
- draft-body-editor だけ shape が違うため、pipeline 復帰可否の分岐を生む

## §3 採用する deterministic shape(quality-monitor の形に揃える)

| 項目 | 既定値 |
|---|---|
| Windows 側 cwd | `C:\Users\fwns6` |
| WSL 起動 | `C:\Windows\System32\wsl.exe`(絶対 path で明示) |
| WSL 内 cwd | `/home/fwns6/code/wordpressyoshilover`(cd で明示) |
| 実行 | `python3 -m <module> <args>`(module 相対) |
| shell | `bash -lc`(login shell、PATH / venv 既定の再現) |
| UNC cwd | 使わない(Windows 側 cwd は必ず `C:\Users\fwns6`) |

### shape 例(draft-body-editor)

```
wsl.exe bash -lc "cd /home/fwns6/code/wordpressyoshilover && python3 -m src.tools.run_draft_body_editor_lane --dry-run --max-posts 5"
```

### shape 例(quality-monitor、既存形の確認)

```
wsl.exe bash -lc "cd /home/fwns6/code/wordpressyoshilover && python3 -m src.tools.run_quality_monitor --target draft --page-limit 5"
```

## §4 heartbeat

- Windows 側に runner heartbeat を 1 つだけ残す
- 実装形(任意):
  - 各 run の冒頭で Windows 側 path(例: `C:\Users\fwns6\.codex\heartbeats\<automation_id>.txt`)に UTC / JST timestamp を 1 行書く
  - WSL 内 path のみで完結させない(Windows 側 process の稼働を Windows 側 artifact で確認可能にする)
- quality-gmail はこの heartbeat を fallback 読みできる形に整える(必須 path ではない、source tag は既存 `[src:qm]` / `[src:stale]` / `[src:none]` を維持)

## §5 quality-gmail(非破壊)

- digest 送信経路 / 4 行フォーマット / subject source tag / recipient / cadence は diff 0 で維持
- heartbeat fallback 読みは optional(`[src:none]` 時に heartbeat timestamp を短く 1 行添えるのは可、4 行本体は変えない)
- `wsl.exe` は quality-gmail では引き続き呼ばない(Windows UNC 読取のみ)

## §6 scope(本便で触るもの)

- `/mnt/c/Users/fwns6/.codex/automations/draft-body-editor/automation.toml`
  - `cwds` を `["C:\\Users\\fwns6"]` に変更(UNC cwd を廃止)
  - `prompt` を deterministic shape の exact command へ揃える(§3 shape 例参照)
  - `status` / `rrule` / `model` / `reasoning_effort` / `execution_environment` は diff 0
- `/mnt/c/Users/fwns6/.codex/automations/quality-monitor/automation.toml`
  - 既に deterministic 形に近いが、§3 shape に exact 準拠する差分があれば最小修正(cwds 確認 / wsl.exe の絶対 path 化確認 / exact command 文字列確認)
  - 挙動非破壊、shape の冗長性除去のみ
- heartbeat 実装
  - 実装形は自由度を持たせる(WSL 内 runner 側で stdout 印字するだけでは不十分。Windows 側 path に artifact を残す形が必須)
  - 最小実装: `wsl.exe bash -lc "cd ... && python3 -m ..."` の前段に `cmd /c echo %DATE% %TIME% > C:\Users\fwns6\.codex\heartbeats\<id>.txt` を挟む、もしくは runner 側で Windows path を書く mechanism を選ぶ
  - 実装先は Codex A の判断で選んでよい(最小 diff 優先)
- `/mnt/c/Users/fwns6/.codex/automations/quality-gmail/automation.toml`
  - heartbeat fallback 読みを optional で追加(prompt に 1 文追加程度、4 行本体と subject tag は diff 0)
  - heartbeat を読むかどうかは判断に任せる(fallback 優先度は `[src:none]` 時のみ)

## §7 non-goals(§31-B Hard constraints)

以下は本便で触らない:

- route / intake / pickup / fixed lane の判定層(`src/tools/run_notice_fixed_lane.py` / `src/source_trust.py` / `src/source_id.py` / `src/postgame_revisit_chain.py`) — diff 0
- category / ledger schema(`docs/handoff/ledger/` schema)— diff 0
- quality contract 全般(036 / 040 / 067 / 068 の prompt / validator / repair)— diff 0
- `published` 書き込み経路 — Phase 4 まで禁止
- secret / env / external API の追加・変更 — 無し
- worker 追加 / cloud 化 — 無し
- quality-gmail の digest 本体 / cadence / recipient / subject source tag の仕様 — diff 0
- Codex B 領域(067 / 068 の実装) — diff 0
- Windows 自動ログイン / Claude auto-start / タスクスケジューラ連携 — 無し

## §8 acceptance_check

1. draft-body-editor automation.toml の cwds が `C:\Users\fwns6` に修正されている(UNC cwd 廃止)
2. draft-body-editor prompt が `wsl.exe bash -lc "cd /home/fwns6/code/wordpressyoshilover && python3 -m src.tools.run_draft_body_editor_lane --dry-run --max-posts 5"` に準拠している
3. quality-monitor automation.toml が §3 shape に exact 準拠している(必要なら shape を最小修正)
4. Windows 側 heartbeat artifact path が確定している(`C:\Users\fwns6\.codex\heartbeats\` 配下推奨、path は Codex A の判断でよい)
5. quality-gmail の digest 本体 / cadence / recipient / subject source tag が diff 0 で維持されている
6. `src/` 配下の挙動変更が無い(runner の引数 / 出力仕様は非破壊)
7. 次 tick で heartbeat または log の新規 evidence が Windows 側 path から確認できる shape になっている(実走は別)

## §9 runtime 依存

- 本便の実装(automation.toml の shape 修正)自体は runtime 非依存
- 効果測定は次 tick の automation 発火時(Codex app が起動していれば自動、そうでなければ user 手元の再起動で発火)

## §10 TODO

- 【×】 draft-body-editor automation.toml shape 修正(UNC cwd 廃止、Windows cwd=`C:\Users\fwns6` + `wsl.exe bash -lc "cd /home/fwns6/code/wordpressyoshilover && python3 -m src.tools.run_draft_body_editor_lane --dry-run --max-posts 5"` へ統一)
- 【×】 quality-monitor automation.toml shape exact 準拠確認 / 最小修正(`C:\Users\fwns6` 維持、runner 前段に Windows heartbeat wrapper を追加)
- 【×】 Windows 側 heartbeat 機構 1 本(path 確定: `C:\Users\fwns6\.codex\heartbeats\<automation_id>.txt`、prompt wrapper で書き込み)
- 【】 quality-gmail heartbeat fallback 読み optional 追加(digest 本体 diff 0 優先のため本便では未実施)
- 【×】 §8 acceptance_check 7 項目自己追認(quality-gmail は digest 本体 / cadence / recipient / subject source tag diff 0、`src/` 配下 diff 0)
