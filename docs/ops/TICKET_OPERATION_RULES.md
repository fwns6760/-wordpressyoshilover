# TICKET_OPERATION_RULES — チケット運用ルール

最終更新: 2026-05-02 JST

## 目的

チケット番号・状態・フォルダ・観察・BUG_INBOX昇格を、次回Claude/Codexが迷わない形で扱う。

## 関連正本

- AIチーム体制: `docs/ops/AI_TEAM_OPERATION_MODEL.md`
- user入力形式: `docs/ops/USER_INPUT_FORMAT.md`
- ACTIVE / worker lane: `docs/ops/ACTIVE_LANE_POLICY.md`
- BUG_INBOX: `docs/ops/BUG_INBOX.md`
- BUG_INBOX管理Excel: `docs/ops/ヨシラバーチケット管理.xlsx`

## 番号ルール

- チケット番号の破壊的な振り直しは禁止。
- 既に使われた番号は履歴として残す。
- 衝突・名称変更が必要な場合は、aliasを付ける。
- 新規ticketは、既存ticketへ吸収できないことを確認してから採番する。
- BUG_INBOX項目には、正式ticket化まで番号を振らない。

## ACTIVEルール

- ACTIVEは最大2件を目安にする。
- ACTIVEは「いま実装・accept・deploy判断に使うもの」だけ。
- HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY / READY_FOR_AUTH_EXECUTOR は原則 waiting。
- DONE / CLOSED / OBSERVED_OK evidenceありは done/YYYY-MM。
- activeを増やして忙しく見せる運用は禁止。

## OBSERVEルール

- OBSERVEは複数可。
- 正常系の細かい報告は禁止。
- 異常、状態到達、USER_DECISION_REQUIRED、HOLD解除条件到達だけ報告する。
- userを時計係にしない。

## HOLDルール

HOLDは作業停止ではない。

HOLD中に進めてよいもの:

- read-only確認
- doc-only整理
- evidence収集
- test plan
- rollback plan
- Acceptance Pack補強
- BUG_INBOX整理

HOLD中に進めてはいけないもの:

- flag ON
- env変更
- deployで挙動変更
- Scheduler変更
- SEO/noindex/canonical/301変更
- source追加
- Gemini call増加
- mail量増加
- cleanup mutation

## DONEルール

DONEはevidenceありのみ。

DONEに必要なもの:

- 実装済み、または明確に不要化された証拠
- test / read-only evidence / post-deploy verifyのどれか
- rollback targetまたは「rollback不要」の理由
- 残課題が別ticketまたはBUG_INBOXへ移っている

禁止:

- deploy済みだけでDONEにする。
- image反映済みだけでDONEにする。
- flag OFF deployだけで効果確認済み扱いにする。

## deploy状態の分解

deploy済みと効果確認済みを分ける。

| 状態 | 意味 | DONE可否 |
|---|---|---|
| flag OFF deploy | codeは本番imageにあるが挙動は無効 | DONE不可。live-inert evidenceのみ |
| live-inert deploy | 起動しても挙動不変 | DONE不可。post-deploy verify必要 |
| flag ON | 挙動変更が有効 | USER_DECISION_REQUIRED |
| effect observed | 想定効果がlog/mail/ledgerで観測済み | DONE候補 |
| OBSERVED_OK_SHORT | 短時間verifyは通過、機能exercise未完 | DONE不可 |
| OBSERVED_OK | post-deploy verifyとsafe regression evidenceあり | DONE候補 |

## Claude / Codex laneルール

- Claudeは現場責任者。
- Codexはworkerでありmanagerではない。
- 会議室Codexはチケット運用PMOとしてBUG_INBOX仕分けとACTIVE候補圧縮を担う。
- 現場ClaudeはACTIVE最大2件を実行管理し、開発Codex A/Bをdispatchする。
- ClaudeがCodex lane A/Bを管理する。
- Codex lane idleをuserに発見させない。
- idle時は、既存ticket内の低リスクsubtaskを探す。
- ただし、Codexをbusyにするだけの無意味fireは禁止。
- 新規ticket乱立は禁止。既存ticketのsubtaskへ吸収する。

## BUG_INBOXから正式ticketへ昇格する流れ

1. BUG_INBOXに受ける。
2. 既存ticketに吸収できるか確認。
3. 影響、再現性、evidence、close条件を書く。
4. 既存ticketに吸収できない場合だけ新規ticket候補にする。
5. user判断が必要な変更はAcceptance Packを作る。
6. 番号採番は最後。

## Excel運用

- BUG_INBOXの人間向け管理ファイルは `docs/ops/ヨシラバーチケット管理.xlsx`。
- userは現場報告・違和感・ログをチャットにそのまま貼るだけ。
- userはExcelを編集しない。仕分けしない。優先度を細かく考えない。ticket番号を作らない。
- Codexはuserが貼った現場報告から必要なBUG_INBOX行を抽出し、Excelの `01_BUG_INBOX` に追記する。
- CodexはBUG_INBOXの新規行を仕分ける。
- 既存ticketに吸収できるものは吸収する。
- 新規ticket候補は番号を振らず、候補のまま保持する。
- `02_P1` / `03_Absorb` / `04_NewCandidate` / `05_HOLD` / `06_DONE` / `00_Summary` は仕分けビュー。
- userに一覧を長く返さない。userが見るべきものは最大5件以内。
- DONE / OBSERVE / HOLD の正常報告は不要。
- 次にACTIVEへ上げる候補は最大2件。
- 現時点のACTIVE候補は `BUG-003 WP status mutation audit` と `BUG-004 silent skip / 候補消失の可視化確認`。
- 他のP1候補は `P1_REVIEW` のまま保持し、ACTIVEに上げない。
- 現場ClaudeはACTIVE最大2件だけ実行する。
- 現場ClaudeはOBSERVE / HOLD / DONEの正常報告をしない。
- 現場Claudeはstate到達、異常、rollback、USER_DECISION_REQUIREDだけ報告する。
- doc更新だけで実行した扱いにしない。

毎回のBUG_INBOX報告形式:

1. BUG_INBOXへ追加したもの
2. 既存ticketに吸収したもの
3. ACTIVE候補 最大2件
4. user判断が必要なもの
5. 現場Claudeへ渡す1文

## user確認を減らすルール

userに投げる前にClaudeが潰すもの:

- test不明
- rollback不明
- cost impact不明
- Gemini call delta不明
- mail volume impact不明
- candidate disappearance risk不明
- stop condition不明
- blast radius不明

userに出す時は、推奨GO/HOLD/REJECT、理由、最大リスク、rollback可否、返すべき一言だけにする。

## 禁止

- チケット番号の振り直し
- 過去ticketの大規模再設計
- Excelだけ正本
- 状態遷移の無報告
- deploy済みとDONEの混同
- UNKNOWNのuser丸投げ
- BUG_INBOXからの大量ticket乱立
