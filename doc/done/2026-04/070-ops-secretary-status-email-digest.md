# 070 ops secretary status email digest

- owner: Claude Code(contract owner、実装が必要なら Codex B)
- deps: 039(quality-gmail delivery reliability / SMTP 経路 reference)、044 / 069(runtime shape / heartbeat)、`docs/handoff/current_focus.md`、Codex task state(TaskList / session_logs)
- status: IMPLEMENTED(content renderer + dry-run、mail 送信 / automation は後続 scope)
- fire 前提: runtime 非依存(content 設計のみ)、automation.toml 登録は初回 ticket では触らない
- §31-C 一体化: 実装時は doc + impl + tests を 1 commit

## §1 目的

user が Codex Desktop の前にいなくても、開発 / runtime / 公開準備の状態をメールで把握できる **read-only 稼働報告メール** を作る。

065 は X 下書き content、quality-gmail(039)は記事品質 digest、070 は開発運用状態の秘書メール。役割を分離する。

## §2 背景

- user は常にアプリ前にいない
- X 投稿下書きは 065 でメール化、品質監視は 039 quality-gmail digest で既存
- 別線で「いま何が稼働中か / 何が完了したか / 何が blocked か / user action が必要か」もメールで知りたい

## §3 scope(state change 時だけ送る)

送信 trigger は以下の state change 観測時のみ(定期 cadence ではない):

- Codex A / B fire
- Codex A / B 完了通知
- accept / close
- failed / blocked
- user action 必要
- runtime 復旧 または parked 継続確定
- 公開準備状態の変化

state 変化が無い期間はメールを送らない。

## §4 メール本文(固定 5 行)

```
進行中: <in-flight / in_progress の Codex 便 / ticket>
完了: <直近 accept / close した ticket、複数なら併記>
blocked/parked: <runtime / push / external precondition parked / hard blocker>
user action: <1 件だけ明示、不要なら「なし」と明記>
next: <次の 1 手、Claude 判断で圧縮、未定なら「待機」>
```

### §4-A 記入ルール

- **1 行 1 目的**。dry-run stdout は固定 5 行を維持し、複数 event は同一 field 内で ` / ` 圧縮する(送信側で改行展開可)
- **user action は 1 件だけ**。複数候補があっても recommend を 1 件選んで残りは next に回す
- **user action なしの場合「なし」と明記**(空欄禁止)
- Claude / Codex A / Codex B / runtime / push blocker が混ざらず読める表記(prefix `A:` / `B:` / `runtime:` / `push:` を使って可)

### §4-B 例

```
進行中: B: 048 formatter in-flight (b82trkc9p)
完了: B: 065-B1 close / A: 041 close
blocked/parked: runtime evidence parked、push DNS blocker(local commit 3 本保持)
user action: なし
next: 048 close 後に 046-A1 fixture dry-run fire 判断
```

## §5 non_goals

- X 下書きメール(065)と content / subject / recipient を混ぜない
- quality-gmail(039)の 4 行品質メールを改造しない(subject source tag / cadence / recipient / format 全て diff 0)
- fire 判断 / ticket 設計 / 実装判断を秘書メールに渡さない(read-only、Claude の chat 経路維持)
- long log / diff 全文 / secret / Draft URL / preview URL / private URL をメールに入れない
- 061 自動投稿を前倒ししない(060 gate 4 条件まで停止維持)
- automation.toml / scheduler は **初回 ticket では触らない**(次弾で判断)

## §6 success_criteria

1. user がアプリ前にいなくても、state 変化をメールで把握できる
2. user action がある場合は 1 個だけ明示される
3. user action がない場合は「なし」と明記される
4. Claude / Codex A / Codex B / runtime / push blocker が混ざらず読める
5. **3 メールの役割分離**が明確:
   - 065 = X 下書き content(8 欄)
   - quality-gmail(039)= 記事品質 digest(4 行、subject source tag)
   - 070 = 開発運用状態秘書(5 行、state change trigger)

## §7 acceptance_check(ticket 本文で閉じる)

- ticket 本文だけで、**いつ送るか / 何を書くか / 何を書かないか** が分かる
- 065 / 039 / quality-gmail と competition しない(subject / recipient / cadence / body format 全て disjoint)
- **read-only 稼働報告**であり、実装 / fire / commit / accept / close 権限を持たないことが明記されている(Claude / Codex / user 既存の chat 経路を奪わない)
- 048 formatter in-flight を邪魔しない(070 起票は可、実装 fire は 048 close 後に判断)

## §8 実装境界(§31-B 不可触、実装 fire 時に準用)

- 039 quality-gmail 本体(cadence / recipient / subject source tag / 4 行 format)diff 0
- 065 X 下書きメール本体(8 欄 / validator / digest)diff 0
- automation.toml / scheduler / cron / env / secret の登録(初回 ticket では触らない)
- published 書込 Phase 4 まで禁止
- 外部 API / 新規依存 / subprocess 追加禁止(pure Python stdlib のみ、SMTP は `smtplib` 標準)
- Codex A 領域 / validator 本体 / ledger schema 全て diff 0
- user action 判定ロジックで「fire 判断 / accept 判断」を模倣しない(Claude の chat 経路を奪わない)

## §9 実装候補(実装 fire 時の参考、doc-only では確定しない)

- `src/ops_secretary_status.py`(state snapshot + 5 行 formatter)
- `src/tools/run_ops_secretary_dry_run.py`(stdout dry-run、CLI、初回 ticket では mail 送信なし)
- state source: `docs/handoff/current_focus.md` / session_logs / TaskList(pure Python で read-only 抽出)
- mail 送信経路は **次弾**(automation / cron 接続は別 ticket)

## §10 運用方針

- **048 formatter が close するまで実装 fire しない**
- 070 起票は doc-only で閉じる(本 ticket)
- 実装 fire が必要な時点で Codex B に最小実装として切る(content renderer + dry-run stdout で閉じる、mail 送信は後続)
- 070 と 065 は送信経路を分けても良いが、**subject prefix で識別可能にする**(例: `[ops]` vs `[x-draft]` vs `[quality]`)

## §11 TODO(起票時点)

- 【×】070 ticket 正本起票(本 doc)
- 【×】実装 fire 判断(048 formatter close 後)
- 【×】Codex B 向け最小実装 prompt 起草(content renderer + dry-run、mail 送信なし)
- 【×】content renderer 実装(`src/ops_secretary_status.py`)
- 【×】dry-run CLI 実装(`src/tools/run_ops_secretary_dry_run.py`)
- 【×】fixture / tests 実装(`tests/fixtures/ops_secretary/`、`tests/test_ops_secretary_status.py`、`tests/test_run_ops_secretary_dry_run.py`)
- 【】mail 送信経路接続(automation.toml 登録、後続 ticket)
- 【】state source の抽出 API 確定(current_focus / session_logs / TaskList のどれを使うか)
- 【】subject prefix 命名確定(`[ops]` / `[x-draft]` / `[quality]` の 3 系統分離)

## §12 本便の scope 外(混線防止)

- 048 formatter 実装(Codex B、本 ticket fire 前に close 済 / in-flight)
- 065-B2 mail delivery 接続(runtime evidence 復旧後、別ticket)
- 061 自動投稿(060 gate 停止維持)
- 039 quality-gmail 本体改造(disjoint)
- 046 / 047 実装(Codex A、runtime 観測 gate 絡み)
