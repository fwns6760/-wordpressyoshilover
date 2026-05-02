# ACTIVE_LANE_POLICY — ACTIVEとworker lane運用

最終更新: 2026-05-02 JST

## 目的

ACTIVE ticket と Codex worker lane を絞り、userを時計係にせず、現場Claudeが安全に作業を流せる状態にする。

## ACTIVEルール

- ACTIVEは最大2件。
- ACTIVE最大2件はuserが選ぶ2件ではなく、現場Claudeが同時実行する作業上限。
- ACTIVEは、いま実装・accept・deploy判断に使うものだけ。
- P1候補を一括ACTIVE化しない。
- `P1_REVIEW` はACTIVEではない。
- `OBSERVE` / `HOLD` / `DONE` の正常報告をACTIVE扱いしない。
- ACTIVE化する前に、既存ticketへ吸収できるか確認する。
- userに「次どれにしますか？」と聞かない。

## READY_NEXTルール

- ACTIVEとは別に、READY_NEXTを最大3件だけ並べる。
- ACTIVEが完了 / OBSERVE / HOLD になったら、USER_DECISION_REQUIREDでない限りREADY_NEXTから現場Claudeが自動昇格する。
- READY_NEXTは「次に現場Claudeが流す候補」であり、userへの選択肢リストではない。
- READY_NEXT昇格時も、新規ticket乱立は禁止。既存ticket / BUG_INBOX / NEW_CANDIDATEから吸収して流す。
- READY_NEXTが空なら、現場Claudeが低リスクsubtask / read-only / Pack補強 / test plan を探す。
- READY_NEXTがUSER_DECISION_REQUIREDだけの場合は、Acceptance Packを完成させてからuserへ `OK / HOLD / REJECT` の1行判断で出す。

## Codex workerルール

- Codex workerは最大2本。
- Lane A / Lane B は現場Claudeが管理する。
- Codexはworkerでありmanagerではない。
- 同一deploy対象を2 workerで同時編集しない。
- 同一ファイルを2 workerで競合編集しない。
- Codex生回答をuserへ直送しない。

## idle運用

- 待ちstateのticketを理由にCodexをidleにしない。
- 既存ticket内に低リスクsubtaskがある場合、現場Claudeが自律fireする。
- ただし、Codexをbusyにするだけの無意味fireは禁止。
- 無理に新規ticketを増やさない。
- 新規ticket乱立は禁止。既存ticketのsubtaskへ吸収する。

idle維持が許される条件:

1. 消化順内の低リスクsubtaskが本当にない。
2. 既存Pack / read-only / test plan / rollback plan / evidence が完了済み。
3. Lane Aやobserveと重複する作業しか残っていない。
4. deploy / flag / source / Gemini増などuser GO必須作業しか残っていない。

idle維持する場合はHOLD理由を明記する。

## 報告ルール

- OBSERVE中の正常報告は禁止。
- cycle silent / 正常系ログ報告は禁止。
- state到達、異常、rollback、USER_DECISION_REQUIREDだけ報告する。
- userが見るべきものは最大5件以内。
- user返答は原則 `OK` / `HOLD` / `REJECT` の1行。

## deploy判断との関係

- deploy済み、flag ON、effect observed、closeを分ける。
- deployしただけでDONEにしない。
- post-deploy verify と本番safe regression evidence が揃って初めて `OBSERVED_OK` / DONE候補。
- `flag OFF deploy` / `live-inert deploy` は条件を満たせば `CLAUDE_AUTO_GO` だが、verify必須。
- `flag ON` / env挙動変更 / Gemini増 / mail増 / source追加 / Scheduler変更 / SEO変更は `USER_DECISION_REQUIRED`。

## 禁止

- userを全チケットOWNERにする。
- userにExcel入力を求める。
- userに仕分けを戻す。
- チケット番号を振り直す。
- 新規ticketを大量発行する。
- Codex生回答をuserへ直送する。
- 正常系ログを延々報告する。
- doc更新だけで実行した扱いにする。
- 本番deploy / env / flag / GCP / Scheduler / SEO / Gemini / mail / source変更をこのpolicy更新だけで実施した扱いにする。
