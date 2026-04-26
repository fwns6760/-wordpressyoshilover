# 034 — 公式 X / 公式媒体 X 付与ルール正式化

**フェーズ：** 本文品質改善の第4優先  
**担当：** Codex B  
**依存：** 014, B8 `3acb49c`, 032

---

## why_now

- `current_focus` の修正優先順位 5 位。
- 公式 X / 公式媒体 X が必要な記事なのに attribution が欠ける fail pattern が残っている。

## purpose

- どの subtype / source 条件で公式 X attribution を必須にするかを固定する。
- source block から attribution 漏れを早段で検知し、欠落時に reroll できるようにする。

## scope

### attribution 必須条件

- primary 事実 source が `公式 X / 公式媒体 X` で、同等の T1 Web source が bundle に無い場合は必須。
- `live_update / lineup / fact_notice / pregame` で、最初の assertion が `公式 X / 公式媒体 X` 由来なら必須。
- `postgame / farm` は T1 Web source が先にある場合は任意、X が唯一の一次ソースなら必須。

### attribution 任意条件

- 同等内容の T1 Web source があり、X が補強だけの時は任意。
- 任意時も source block 内にまとめてよく、タイトルや lead に出す必要はない。

### 表示位置

- attribution は source block に置く。
- source block は本文末尾の required block として扱う。
- 表記は `出典: 読売ジャイアンツ公式X / 公式媒体X` のように source 種別が分かる形に固定する。

### validator

- 必須条件で attribution が無い場合は `WARN + reroll`。
- source block があっても source 種別が曖昧なら fail 扱いにする。

## non_goals

- source expansion
- X API 実装
- 新 source trust tier 追加
- SNS 文面の自動生成

## acceptance_check

- attribution 必須ケースが一覧化されている。
- validator で未付与ケースを拾える。
- `032` の source block 契約と矛盾しない。

## TODO

【×】attribution 必須条件を固定する  
【×】attribution 任意条件を固定する  
【×】source block での表示位置を固定する  
【×】source 種別の表記ルールを固定する  
【×】欠落時の `WARN + reroll` を固定する  
【×】source 種別が曖昧な時は fail と明記する  

## 成功条件

- 必要記事での X attribution 欠落が observation window で 0 件になる  
- source block を見れば official X 由来かどうかが分かる  
- Codex B が attribution validator 実装へそのまま進める  
