# CODEX_APP_TICKET_VIEW — user向けチケット見える化

最終更新: 2026-05-02 JST

## 目的

Codex App上で、userが今日見るべきチケットだけを確認できるようにする。

このファイルは全チケット一覧ではない。user向けの入口であり、詳細な仕分けは以下の正本で管理する。

- `docs/ops/ヨシラバーチケット管理.xlsx`
- `docs/ops/BUG_INBOX.md`
- `docs/ops/TICKET_OPERATION_RULES.md`

## userが見るもの

原則、userが見るのは最大5件だけ。

1. ACTIVE最大2件
2. 次候補最大3件
3. USER_DECISION_REQUIRED があれば最大1件

DONE / OBSERVE / HOLD の正常報告はここに載せない。

## 今日のACTIVE候補

| 優先 | ID | 内容 | user作業 |
|---|---|---|---|
| 1 | BUG-003 | WP status mutation audit。公開状態が勝手に変わった疑いをread-onlyで確認する。 | なし |
| 2 | BUG-004 | silent skip / 候補消失の可視化確認。候補がpublish/review/hold/skipのどこかで見えるか確認する。 | なし |

## 次候補

| 優先 | ID | 内容 | 扱い |
|---|---|---|---|
| 1 | BUG-008 | mail送信pathにLLM呼び出しが混入していないかread-only確認。 | ACTIVE空き後 |
| 2 | 245 | frontに内部カテゴリ「自動投稿」がまだ出るか確認。出なければDONE候補。 | 整理候補 |
| 3 | 297 | codex-shadow-trigger pause済みならDONE候補。 | 整理候補 |

## HOLD / 不要寄りメモ

| ID | 扱い | 理由 |
|---|---|---|
| 240 | DONE維持 | Gmail From / Reply-To / 通知改善は完了済み。 |
| 251 | HOLD深め | SEO/noindex解放は今触ると危険。 |
| 252 | OBSOLETE候補 | XはGPTs手動運用へ寄せたため優先度低。 |
| 274 | OBSOLETE候補 | Gmailフィルタであり、GitHub Actions赤の根本対応ではない。 |
| 275 | KEEP | CI赤が残るなら必要。緑ならDONE候補。 |

## 報告ルール

Codex / Claude は、以下だけをuserへ出す。

- ACTIVE完了
- P1相当の異常
- rollback必要
- USER_DECISION_REQUIRED
- 新たにP0/P1へ昇格すべき証拠

以下は出さない。

- cycle silent
- 異常なしの定期報告
- 次wake予定
- monitorなし
- user返答不要の正常系報告
- 長いlog貼り付け
- HOLD / OBSERVE / DONE の正常報告

## 現場Claudeへ渡す1文

```text
BUG_INBOX初回棚卸しでは、ACTIVE候補は BUG-003 WP status mutation audit と BUG-004 silent skip / 候補消失の可視化確認 の2件だけです。他のP1候補は一括ACTIVE化せず、BUG-008は次候補、245/297は整理候補、240/251/252/274/275は上記分類のまま扱ってください。
```

## 更新ルール

- このファイルはuser向けビュー。
- 正本は `ヨシラバーチケット管理.xlsx` と `BUG_INBOX.md`。
- 新しい違和感は、userがチャットに貼るだけ。
- CodexがBUG_INBOXへ反映し、このviewには最大5件だけ載せる。
