# USER_INPUT_FORMAT — user入力を最小化する定型

最終更新: 2026-05-02 JST

## 目的

userがExcelやチケット番号を触らず、現場報告・違和感・ログをチャットへ貼るだけで、会議室CodexがBUG_INBOXへ載せられるようにする。

## userが投げる文

userは以下だけでよい。

```text
会議室Codexへ。
以下をチケット運用に載せて。

【貼り付け内容】
現場報告・違和感・ログをそのまま貼る
```

## userがしないこと

- Excelを編集しない
- 仕分けしない
- 優先度分類をしない
- ticket番号を作らない
- ACTIVE候補を考えない
- 長い一覧を読む前提にしない

## 会議室Codexの処理

会議室Codexは、貼られた内容から必要なBUG_INBOX行を抽出し、以下へ反映する。

- `docs/ops/ヨシラバーチケット管理.xlsx` の `01_BUG_INBOX`
- `docs/ops/BUG_INBOX.md` 必要時
- 既存ticketへの関連付け

分類は以下に限定する。

- `P1_REVIEW`
- `ABSORB_EXISTING`
- `NEW_CANDIDATE`
- `HOLD`
- `DONE`
- `OBSERVE`
- `REJECT`

新規ticket候補は番号を振らず、候補のまま保持する。

## Codex側の返答形式

1. BUG_INBOXに追加/更新するもの
2. 既存ticketに吸収するもの
3. 新規ticket候補
4. HOLD / DONE / OBSERVE
5. ACTIVE候補 最大2件
6. user判断が必要なもの
7. 現場Claudeへ渡す1文

## 返答制約

- userに見せる一覧は最大5件。
- DONE / OBSERVE / HOLD の正常報告は不要。
- 長い棚卸しを返さない。
- userに仕分けを戻さない。
- `USER_DECISION_REQUIRED` 以外の技術判断をuserへ戻さない。

## 現場Claudeへ渡す1文の例

```text
Claudeへ。BUG_INBOX正本では、次にACTIVE候補へ上げるのは BUG-003 WP status mutation audit と BUG-004 silent skip / 候補消失の可視化確認 の2件だけです。他のP1候補はP1_REVIEWのまま保持し、ACTIVE化しないでください。
```
