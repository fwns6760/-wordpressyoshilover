# 044 — Codex app startup 登録と reboot smoke 確認

**フェーズ：** ローカル常駐運用の無人化 follow-up
**担当：** Claude Code
**依存：** 039, 042, 043, 現行 Codex automations(`quality-gmail` / `quality-monitor` / `draft-body-editor`)

---

## why_now

- 043 で reboot 後の auto recovery 設計は固まり、follow-up は `Codex app を Windows スタートアップフォルダへ配置する` 1 本に絞れた。
- ただし「誰がどう配置するか / 配置後に何を確認して復帰と判定するか」は 043 本文では運用手順として閉じていない。
- 044 は 043 の follow-up を **正本手順 1 本** に固定し、配置完了後の **reboot smoke(3 automation 次 tick 復帰確認)** までを 1 ticket で読めるようにする。
- 失敗時の routing を 039(delivery 切り分け) / 042(手動復旧)に閉じ、044 単体に新規 observation を抱え込まない。

## 042 / 043 / 044 の分離

- **042** = reboot 監査と **手動復旧** 手順(Codex を起動すれば何が戻るか / Claude は cron 必須 runtime ではない)
- **043** = 無人化に向けた **自動復帰設計**(OS / app / automation 3 層の復帰条件 / follow-up は Codex app スタートアップ配置 1 本)
- **044** = 043 follow-up の **正本実施手順 + reboot smoke**(配置 1 本 + 3 automation 次 tick 復帰判定 + 失敗時 routing)
- 044 は 043 scope を広げない。Codex app スタートアップ配置以外の auto-start 手段(タスクスケジューラ / Windows 自動ログイン / Claude auto-start)は非採用を継承。

## purpose

- Codex app の Windows スタートアップ登録を **user 手動 1 本** として正式化する。
- 登録後の **reboot smoke 手順** を固定し、`quality-gmail` / `quality-monitor` / `draft-body-editor` 3 本の次 tick 復帰を 1 ticket で判定できるようにする。
- smoke 失敗時の **routing** を 039 / 042 に閉じる(044 は新規観測を抱えない)。

## scope

### 実施対象(2 ブロック)

**A. Codex app の Windows スタートアップ登録(user 手動 1 本)**

- owner: user 手動(Claude は GUI 操作を持たない、Codex app 自身は OS 設定を触れない)
- 手段: Windows スタートアップフォルダへ Codex app の shortcut を配置する 1 本のみ
- 非採用(散らさない): タスクスケジューラ登録 / Windows 自動ログイン / WSL auto-start / Claude auto-start
- 配置後の可逆性: shortcut 削除で即座に原状復帰(可逆、コスト増なし)
- 配置対象の確認: 043 本文で推奨済の shortcut 配置 1 本のみ実施し、複数配置しない

**B. reboot smoke(Claude 管理の確認手順)**

- owner: Claude Code(観測 / 追認 / 判定)
- 実施タイミング: A 完了後、次の OS 再起動サイクルで 1 回、または意図的な再起動で 1 回
- 観測対象: 再起動後の次 tick 到達時に以下 3 点を順に確認

| automation | 確認 file / 経路 | 期待 | 次 tick 基準 |
|---|---|---|---|
| quality-monitor | `logs/quality_monitor/<JST date>.jsonl` | 新規行追加 | :45 |
| quality-gmail | Gmail inbox `fwns6760@gmail.com` | subject `[src:qm/stale/none]` で 1 通 | 10:00-23:59 JST 窓内の次 :00 |
| draft-body-editor | `logs/draft_body_editor/<JST date>.jsonl` | 新規行追加(dry-run) | 次 hourly tick |

- 3 automation すべてが次 tick で復帰すれば smoke pass と判定し、044 の acceptance_check を満たす。
- 1 本でも復帰しない場合は下節 **失敗時 routing** へ。

### 失敗時 routing(044 は抱えない)

- **quality-gmail が届かない** → 039(delivery reliability)の 4 段階(cron fire / log read / mail send / 着信)へ routing
- **quality-monitor / draft-body-editor が復帰しない**(WSL 経路 fail / Codex app 再起動失敗 / automation 非 ACTIVE) → 042(手動復旧 6 ステップ)へ routing
- **Codex app 自体が OS 起動後に立ち上がらない** → 043 follow-up(スタートアップ配置の再確認)へ戻し、shortcut の実在 / target path / 実行権限を user 手動で見直す
- 044 は smoke 判定と routing のハブだけを持ち、個別復旧手順は **042 / 039 / 043** 側の既存本文に閉じる

### Claude の位置づけ(042 / 043 継承)

- Claude は cron 実行の必須 runtime ではない。044 でも auto-start 対象にしない。
- smoke 判定は Claude セッションを user が開いた時に 1 回だけ確認すればよい(常駐不要)。
- handoff 更新 / ticket 管理 / accept 追認 / 失敗 routing 判定は Claude 側で手動実施(044 scope)。

### 不可触

- Claude 対話セッションの auto-start
- Windows 自動ログイン設定
- クラウド移行
- `quality-gmail` の内容変更(029 scope)
- `quality-gmail` の配信経路 contract(039 scope)
- automation cadence / model / env / secret の変更
- mail recipient の変更
- 既存 ticket の fire 順
- 042 / 043 の決定事項(Claude は cron 必須 runtime ではない / missed run は次 tick から再開 / follow-up はスタートアップ配置 1 本)

## success_criteria

- Codex app のスタートアップ登録が **user 手動 1 本** の正本手順として 044 本文で読める。
- reboot smoke の判定項目が **3 automation × 確認 file × 次 tick 基準** の表で 1 ticket から読める。
- smoke 失敗時の routing 先が **039 / 042 / 043** に閉じており、044 は新規復旧手順を抱えない。
- 「配置したか / 次 tick で戻ったか」を user が Claude に 1 回報告すれば 044 は accept に進められる。

## non_goals

- Claude 対話セッションの auto-start
- Windows 自動ログイン実装
- タスクスケジューラ登録
- クラウド移行
- `quality-gmail` の内容変更
- automation cadence / model / env / secret の変更
- mail recipient 変更
- 既存 ticket の fire 順変更

## acceptance_check

- Codex app のスタートアップ配置手順が user 手動 1 本で明記されている
- reboot smoke の 3 automation 判定表が本文に存在する(file / 期待 / 次 tick 基準)
- 失敗時 routing が 039 / 042 / 043 に閉じていることが明記されている
- 044 が新規 observation / 新規復旧手順を抱えていない(ハブに徹している)
- 042 / 043 の決定事項(Claude は cron 必須 runtime ではない / missed run は次 tick から再開 / follow-up 1 本)が継承されている
- 既存 ticket の fire 順を変更しない旨が明記されている

## TODO

【】042 / 043 との分離を明記する(手動復旧 / 自動復帰設計 / 正本手順 + smoke)
【】Codex app のスタートアップ配置を user 手動 1 本として固定する
【】非採用手段(タスクスケジューラ / 自動ログイン / Claude auto-start / WSL auto-start)を明記する
【】reboot smoke の 3 automation 判定表(file / 期待 / 次 tick 基準)を固定する
【】smoke 失敗時 routing を 039 / 042 / 043 に閉じる
【】Claude は cron 必須 runtime ではない境界を 042 / 043 から継承する
【】missed run は次 tick から再開を 042 / 043 から継承する
【】既存 fire 順を変更しないことを明記する
【】044 は新規 observation / 新規復旧手順を抱えないことを明記する

## 成功条件

- reboot 後、user が「Codex app を起動する」以外の手を動かさず、次 tick で 3 automation が復帰する状態を 044 単体で判定できる
- 失敗が出た時に、044 本文を見れば 039 / 042 / 043 のどこへ戻せばよいかが即分かる
- 本線 fire 順(`036 ✓ → [038 + 040 並走] → 029 → 028 impl → 037`)を止めず、044 は独立並走の補助 ticket として消化できる
