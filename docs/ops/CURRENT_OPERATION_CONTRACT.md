# CURRENT_OPERATION_CONTRACT — 現在の運用契約

最終更新: 2026-05-03 JST

この1枚を、日々の現場運用で最初に読む正本にする。
詳細規程は `POLICY.md`、チケット細則は `TICKET_OPERATION_RULES.md` に残すが、役割・報告・HOLD・自動GO判断で迷ったらこの契約を優先する。

目的はチケット消化ではなく、userがチケット管理者・現場監督・整理係へ戻らないこと。

## Pre-work sync rule (2026-05-03 user lock)

### 作業開始前に必ず読む (省略禁止)

- `docs/ops/CURRENT_OPERATION_CONTRACT.md` (本ファイル)
- `docs/ops/OPS_BOARD.yaml`
- `docs/ops/BUG_INBOX.md`
- `doc/README.md` + `doc/active/assignments.md`
- 該当 ticket 本体
- 会議室 Codex / ChatGPT から渡された Ticket Sync Packet (もしあれば)

### 作業前 ACK (短く 6 点のみ)

- 読み込んだ commit (HEAD hash)
- ACTIVE (現在の 1-2 件)
- OBSERVE (観察中の state)
- `USER_DECISION_REQUIRED` (上げる予定があれば)
- 今回やること
- 今回やらないこと

### ズレ時 (repo 正本 / Ticket Sync Packet / 現場認識の不一致)

- user に確認を戻さない
- 作業を止めて短く HOLD
- 返答 template: `正本と現場認識が不一致のため HOLD。Codex reconcile 必要。`

### 禁止

- user にチケット認識の確認を戻す
- 古いチャット記憶で作業する
- 正本を読まずに ACTIVE 判断する
- Claude / Codex 間のズレを user に説明させる
- 正常系の長文報告
- `USER_DECISION_REQUIRED` でないものを user 判断に戻す

## A. 絶対原則

- userは上司ではなく、クライアント / 発注者。
- userの役割は、初期要件定義、受け入れ条件の提示、最終 `OK / HOLD / REJECT`、違和感や現場ログの共有だけ。
- userに、次候補選定、通常ログ確認、チケット整理、worker dispatch、実装手順管理、Claude/Codex間の仲介を戻さない。
- `USER_DECISION_REQUIRED` は、`OK / HOLD / REJECT` で返せる形に圧縮する。
- ChatGPTは外部コンサル。通常の現場判断、ACTIVE管理、dispatch、evidence収集、rollback一次判断はClaudeが持つ。

## B. 自動で進めてよい条件

以下は `CLAUDE_AUTO_GO` 候補。Claude/Codex側で証拠を確認し、userへ細切れ確認を戻さない。

- read-only
- doc-only
- preview-only
- deployなし
- flag / env / Scheduler / SEO / source変更なし
- Gemini call増加なし
- mail通知条件変更なし
- WP本文変更なし
- publish状態変更なし
- rollback target明確
- 同一deploy対象の衝突なし

HOLDする場合は、具体 blocker を1つだけ書く。

- `ROLLBACK_BLOCKED`: 戻せない変更、または rollback target / restore手順なし
- `VERIFY_BLOCKED`: 検証できない変更、または必要evidenceが取れない
- `USER_AUTH_REQUIRED`: user権限が必要

どれにも該当しない場合は、HOLDではなく小さくGO候補にする。

## C. user判断が必要な条件

以下は `USER_DECISION_REQUIRED`。ClaudeはAcceptance Packまたは短い判断文へ圧縮し、userには `OK / HOLD / REJECT` だけを求める。

- deploy
- flag / env変更
- Scheduler変更
- SEO / noindex / canonical / 301変更
- source追加
- Gemini call増加
- mail通知条件の大改修
- WP本文変更
- publish状態変更
- rollback不能変更
- WP plugin upload

## D. 現在のチケット運用

- ACTIVEは最大2件。
- `SIDE_READONLY` は1件まで。ACTIVE扱いではなく、衝突しないread-only棚卸しだけ。
- READY_NEXT自動昇格は `CLAUDE_AUTO_GO` 条件を満たす場合のみ。
- 条件外は長文説明せず、短いHOLD理由だけ返す。
- 正常系の長文報告、一覧再掲、途中経過だけの報告は禁止。
- userへ報告するのは、P0/P1異常、rollback、不可逆変更、重要なstate到達、受け入れ判断が必要なものだけ。
- NEW_CANDIDATEは最大3件。超える場合は `ABSORB` / `HOLD` / `OBSOLETE` へ圧縮する。

HOLDには必ず以下を書く。

- `HOLD_REASON`
- `UNBLOCK_CONDITION`
- `NEXT_OWNER`
- `EXPIRY`
- `USER_DECISION_REQUIRED` かどうか

解除条件が書けないHOLDは、`OBSOLETE` / `ABSORBED` / `FROZEN` 候補にする。

## E. 現在のチケット固有ルール

- `BUG-004+291` をACTIVE中心にする。
- `292 body_contract_fail durable ledger` は独立ACTIVEにせず、`BUG-004+291` の解除条件・必須サブタスクに吸収する。
- `282-COST` / `298` はOBSERVE。正常系の細かい報告は不要。
- `245 WP plugin upload` だけ `USER_DECISION_REQUIRED`。
- `GCP Codex WP本文修正preview v0` はpreview-only。WP本文変更、publish状態変更、Gemini call、deployは禁止。
- `288-INGEST Phase0` はSIDE_READONLYで並走可。source追加、本線接続、Scheduler、deploy/env、Gemini/mail増は禁止。

## 現場Claudeへ毎回渡す短縮版

```text
userは上司ではなくクライアント。userへ戻すのはUSER_DECISION_REQUIRED、P0/P1異常、rollback、不可逆変更、重要state到達、受け入れ判断だけ。ACTIVEは最大2件、SIDE_READONLYは1件まで。READY_NEXT昇格はCLAUDE_AUTO_GO条件を満たす場合のみ。read-only/doc-only/preview-only/deployなし/flag-env-Scheduler-SEO-source変更なし/Gemini-mail増なし/WP本文変更なし/publish状態変更なし/rollback明確/衝突なしなら小さくGO候補。HOLDするならROLLBACK_BLOCKED/VERIFY_BLOCKED/USER_AUTH_REQUIREDの1つに分類し、HOLD_REASON/UNBLOCK_CONDITION/NEXT_OWNER/EXPIRY/USER_DECISION_REQUIREDを書く。BUG-004+291をACTIVE中心、292はそのサブタスク、282/298はOBSERVE、245だけUSER_DECISION_REQUIRED。
```

## 削除・統合した/削除候補の重複ルール一覧

| 既存箇所 | 扱い | 理由 |
|---|---|---|
| `POLICY.md` §2 Roles のuser/Claude/ChatGPT境界 | 本契約へ統合。POLICY側は詳細規程として残す | 同じ役割定義が複数箇所に増えている |
| `POLICY.md` §3 / §14 / §22 | 本契約へ統合。§22は短い参照節へ圧縮済み | HOLD、小さくGO、Codex C、ChatGPT境界が長文化 |
| `CLAUDE_FIELD_RULES.md` 全体 | 本契約の現場向け抜粋へ圧縮済み | 同じ短縮版を別ファイルでも持っている |
| `TICKET_OPERATION_RULES.md` user確認を減らすルール | 本契約へ統合。ticket固有細則だけ残す | user境界と報告条件が重複 |
| `NEXT_SESSION_RUNBOOK.md` Weak HOLD Prevention節 | 本契約への参照へ圧縮済み | 再開時ルールと現場契約が重複 |
| `OPS_BOARD.yaml` `codex_c_pmo` / `chatgpt_meeting_room` | `board_rules` の機械可読最小キーへ圧縮済み | 自然文の重複が増えやすい |

## 今後ルールを増やす時の基準

新ルール追加は禁止ではないが、追加前に必ず以下を満たす。

1. 既存ルールに吸収できない。
2. user介入回数を減らす効果がある。
3. `CLAUDE_AUTO_GO` / `USER_DECISION_REQUIRED` / `HOLD` のどれに効くか明確。
4. HOLDを増やすだけのルールではない。
5. 正常系報告や一覧再掲を増やさない。
6. 追加するなら、この契約に1行追加し、古い重複行を削る。
