# BUG-004+291 publish=0原因分解 + narrow publish-path unlock prompt

現場Claudeへ。

BUG-004+291 の中で、`publish=0原因分解 + narrow publish-path unlock` を実施してください。
これは新規ticketではありません。
BUG-004+291 のACTIVE内サブタスクとして扱ってください。

## 目的

現状の問題は、publish gate を緩めるか維持するかの二択ではありません。
公開ゼロの原因を分解し、高信頼条件を満たす候補だけを狭く publish path に戻すことです。

旧状態も正常ではありませんでした。
したがって rollback や現状維持を最終正解にせず、候補が見える状態を保ちながら品質条件を満たす記事だけ公開候補へ戻してください。

## まず read-only で分解する原因

- `277` title quality
- `289` post_gen_validate
- `290` weak title rescue 不発
- 4-tier分類の strict 判定
- duplicate / backlog / freshness
- body_contract
- subtype misclassify
- numeric guard
- placeholder
- source facts 不足

## publish候補に戻してよい最小条件

- YOSHILOVER対象
- source_urlあり
- subtype / template_key high confidence
- numeric guard pass
- body_contract pass
- placeholderなし
- silent skipなし
- titleが最低限「何の記事か分かる」
- review / hold 理由なし

## やってよいこと

- read-only 原因分解
- ledger / log / state row 確認
- candidate terminal state 確認
- fixture / test plan / Acceptance Pack 補強
- narrow unlock 設計
- rollback plan / stop condition 明文化

## やってはいけないこと

- publish gate 全体緩和
- 悪い記事を後で消す前提の大量公開
- noindex解除
- review thresholdを上げるだけのmail隠し
- user判断なしのSEO変更
- source追加
- Gemini call増加
- mail量増加
- WP本文変更
- publish状態変更
- env / flag / Scheduler変更

## 報告trigger

報告してよいのは以下だけです。

- publish=0原因分解完了
- narrow unlock設計完了
- P1相当の異常
- rollback必要
- USER_DECISION_REQUIRED
- 新たにP0/P1へ昇格すべき証拠

正常系の定期報告、cycle silent、長いlog貼り付け、user返答不要の実況は不要です。

## 完了条件

- publish=0 の主因が ticket / guard / reason 単位で分解されている
- 高信頼候補だけ publish path に戻す条件が明文化されている
- 全体緩和をしていない
- noindex / SEO に触っていない
- silent skip を増やしていない
- Gemini call / mail量を増やしていない
- rollback target と stop condition が明確

