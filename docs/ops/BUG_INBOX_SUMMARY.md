# BUG_INBOX_SUMMARY — 2026-05-02 デグレ・改修メモ棚卸し

## 入力元

- `C:/Users/fwns6/Downloads/yoshilover_degre_kaishu_memo_format.xlsm`
- 対象sheet: `メモ`, `チケット`
- 本summaryはdoc-only。Excelだけに閉じず、repo内の正本メモとして保持する。

## 結論

今回のメモは、正式ticket番号を振り直さず、まずBUG_INBOXに受ける。

## P1候補

| inbox_id | P1理由 | 既存ticket候補 |
|---|---|---|
| BUG-003 | 公開状態が勝手に変わる疑い | 298-Phase3 / guarded-publish / WP status mutation audit候補 |
| BUG-004 | silent skipで候補がuserから見えない | 289 / 291 / 292 / 293 / 288 Phase 1/2 |
| BUG-005 | HOLD中ticketのコード混入 | 294-PROCESS |
| BUG-006 | 作業ゴミdeploy混入 | 294-PROCESS / POLICY / Pack template |
| BUG-007 | build context汚染 | 294-PROCESS |
| BUG-008 | mail送信pathでLLM費用増の疑い | 229 / 293 / publish-notice no-LLM invariant候補 |
| BUG-009 | rollback不能リスク | POLICY / ACCEPTANCE_PACK_TEMPLATE / 294 |
| BUG-010 | cache steady誤認で費用雪崩 | 229 / 293 / 改修 #1/#2 |
| BUG-012 | cache miss自動ブレーキ | 改修 #2 |
| BUG-013 | post単位Gemini上限 | 改修 #3 |
| BUG-014 | prompt/cache key変更のcost review | 改修 #4 / 294 |
| BUG-016 | mail cap class別最低保証 | 改修 #6 / 289 |

## 既存ticketに吸収できるもの

| inbox_id | 吸収先 |
|---|---|
| BUG-001 | 234 / 234-impl-* / 283-MKT |
| BUG-004 | 289 / 291 / 292 / 293 / 288 Phase 1/2 |
| BUG-005 | 294-PROCESS |
| BUG-006 | 294-PROCESS / ACCEPTANCE_PACK_TEMPLATE |
| BUG-007 | 294-PROCESS |
| BUG-009 | POLICY / ACCEPTANCE_PACK_TEMPLATE / 294 |
| BUG-010 | 229 / 293 / 改修 #1/#2 |
| BUG-011 | 改修 #1 |
| BUG-012 | 改修 #2 |
| BUG-013 | 改修 #3 |
| BUG-014 | 改修 #4 |
| BUG-015 | 改修 #5 |
| BUG-016 | 改修 #6 |
| BUG-018 | 299-QA / 275-QA |

## 新規ticket候補

正式番号はまだ切らない。必要なら後で採番する。

| candidate | 元BUG | 理由 | まずやること |
|---|---|---|---|
| WP status mutation audit | BUG-003 | 「mailが来たら全公開が非公開化」は既存ticketだけでは説明不能の可能性 | 該当時刻・WP status mutation・guarded-publish・cleanup logをread-only照合 |
| publish-notice no-LLM invariant | BUG-008 | mail pathがLLMを呼ぶと費用増と通知遅延に直結 | grep/read-onlyでLLM import/call 0を証拠化 |
| GCP log retention review | BUG-017 | 証拠保持と費用の両面。既存230/205へ吸収できなければ新規 | 現状retentionと費用影響のread-only確認 |
| mail body link hygiene | BUG-002 | Twitter/Xリンクが運用上ノイズなら別mail本文品質ticketが必要 | 該当mail fieldと除去範囲を確認 |

## HOLDでよいもの

| inbox_id | 理由 |
|---|---|
| BUG-001 | 具体post_id / fixtureなしではP2品質改善。既存234系に吸収が自然 |
| BUG-002 | GPTs運用との整合確認が先。P2 |
| BUG-015 | TTL pruneはcleanup mutationを伴う可能性があり、default OFF / Pack必須 |
| BUG-017 | 費用影響が小さい可能性あり。read-only確認が先 |
| BUG-018 | CI/pytest baseline整理としてP2。299/275へ吸収 |

## DONE扱いでよいもの

現時点ではBUG_INBOXとしてDONE扱いにするものはない。

理由:

- メモは違和感の受け皿であり、close evidenceが必要。
- 改修 #1/#2/#3/#6 等は実装済みでも、flag ON / deploy / observeが別段階のものがあるため、BUG側では吸収扱いに留める。

## user判断が必要なもの

現時点では正式ticket化や本番変更のuser判断は不要。

user判断が必要になるのは以下だけ。

- WP status mutation auditで実際の公開/非公開操作が必要になった時
- env/flag/source/Gemini増/mail量増/cleanup mutationが必要になった時
- 新規ticket候補を正式採番して実装する時

## userが次に見るべきもの 5件以内

1. BUG-003: 公開状態が勝手に変わった疑いの時刻・メール件名が残っているか。
2. BUG-004: silent skip候補が今後メール/ledgerで見えるか。
3. BUG-005/006/007: deploy前gateにHOLD code混入・dirty・build context確認が入っているか。
4. BUG-008: publish-notice/mail送信pathにLLM callが無いか。
5. BUG-010/012/013/014: Gemini費用雪崩系が改修 #1-#4に吸収されているか。

## 推奨

- GO: BUG_INBOX三文書 + TICKET_OPERATION_RULES作成とcommit/push。
- HOLD: 新規ticket正式採番、本番deploy、env/flag変更、GCP変更、Scheduler変更、SEO変更、Gemini/mail/source変更。
- REJECT: チケット番号の振り直し、Excelだけ管理、BUG_INBOXからの大量ticket乱立。
