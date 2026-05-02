---
ticket: 253-QA
title: mail summary 内 source 断片の fact contains check(現状 truncation のみ、実例待ち)
status: NOT_NOW
owner: Codex B(後段)
priority: P3
lane: B
ready_for: 解除条件達成後判断
created: 2026-04-29
related: 234-impl-1〜4 mail UX / 244 numeric guard / publish_notice_email_sender
---

## 状態: NOT_NOW

## 背景

mail 通知で送られる summary は内部編集者確認用、現状 `WhitespaceRE truncate` のみで fact check なし。
`raw_summary` に source 断片(誤情報含む)があれば mail に残る可能性。

ただし mail = 編集者宛 内部運用、外部公開ではない → 公開事故 risk は低め。

## なぜ今やらないか

1. **mail summary は内部運用、公開事故 risk 低**
   - 編集者が mail で気づける設計
   - 外部読者には届かない(mail = `fwns6760@gmail.com` 1 通)
2. **contains check は false positive 増 risk**
   - source に類似文字列がある場合「contains」判定で誤一致しがち
   - mail 全件に `【要確認】` prefix 強制になる risk
3. **234-impl-1〜4 review prefix が既存防衛**
   - subtype 別 review fallback が mail UX 側で実装済(`【要確認】` prefix)
   - 247-QA-amend で strict 失敗も review 倒し
4. **実例検出ベースで判断する方が精度高い**
   - speculative 実装より、実 mail で「summary 由来の編集判断ミス」検出後に narrow fix

## 解除条件(GO trigger)

以下 1 つ以上 検出された場合:
- mail summary 由来で **編集者が誤った publish/draft 判断をした実例**(post_id + 内容明示)
- mail 受信者(編集者)から「summary 内に明らかな source 違反 fact」報告
- 247-QA flag ON 観察で「strict success 記事の mail summary に source にない数字 / 選手名」検出
- 234-impl-1〜4 review prefix が hit しないが mail summary は誤情報を残す pattern が判明

## 解除時の scope (narrow)

- src/publish_notice_email_sender.py に `_validate_summary_against_source(summary, source_text)` narrow check 追加
- 失敗 → review prefix 強制 + log
- false positive 抑制のため contains 判定は **数字 / 選手名 token のみ**(自由文字列は対象外)
- tests narrow

## owner

- 起票: Claude(本日 2026-04-29)
- 実装: Codex B(後段)
- accept: Claude
- live judgment: user GO

## 次確認タイミング

- 254-QA 完了後(2-3 日後)
- 247-QA flag 試合日 ON 観察後
- 編集者から実例報告があった時(即)

## 関連 file

- src/publish_notice_email_sender.py(target file)
- src/baseball_numeric_fact_consistency.py(reuse 候補)
- tests/test_publish_notice_email_sender.py(fixture 追加先)

## コスト影響

- Gemini call: 0
- X API: 不要
- Cloud Run / Scheduler: 不変
- 運用コスト: 中(false positive 増えると mail 全件 `【要確認】` 化 risk、editor 負担)
- 実装工数: 小-中

## non-goals

- mail body 全体の fact check(本 ticket は summary 部分のみ)
- LLM での summary 再生成(prompt 改修 / Gemini call 増、user 制約違反)
- 編集者 mail 自動振り分け(別 ticket)

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
