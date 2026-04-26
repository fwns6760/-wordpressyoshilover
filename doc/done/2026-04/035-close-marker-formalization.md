# 035 — close_marker 判定正式化

**フェーズ：** 条件付き reserve  
**担当：** Codex B  
**依存：** 032, 033, 034

---

## why_now

- `current_focus` の修正優先順位 6 位は `必要なら close_marker 判定`。
- 今は本線ではないが、残課題だった場合に user を経由せず即 fire できるよう dormant ticket として在庫化しておく。

## purpose

- close_marker が本当に残課題だった場合だけ、最小改修で閉じる条件を固定する。
- 先行 fire を防ぎつつ、必要時の判断待ちを減らす。

## scope

### dormant 条件

- `030-034` 完了前は fire しない。
- `030-034` 完了後の 7 日 observation で close_marker 系 fail が 0〜1 件なら fire しない。

### fire 条件

- 7 日 observation で close_marker 系 fail が 2 件以上。
- または sampled post の 10% 以上で close_marker 系 fail が再現する。

### formalization 対象

- close_marker が必要なのは `live_update / live_anchor` の終端だけ。
- `lineup / pregame / fact_notice / farm / postgame` では close_marker を付けない。
- 終端条件が未確定の live 系記事では premature close を禁止する。

## non_goals

- 先行 fire
- 他 fail pattern との混在修正
- close_marker を全 subtype 共通ルールに広げること
- published 修正

## acceptance_check

- dormant 条件と fire 条件が ticket だけで読める。
- close_marker が必要な subtype と不要な subtype が分かれている。
- 条件を満たさない限り queue に積まれても fire されない。

## TODO

【】dormant 条件を固定する  
【】fire 条件を固定する  
【】close_marker 必須 subtype を固定する  
【】close_marker 禁止 subtype を固定する  
【】premature close 禁止条件を固定する  

## 成功条件

- close_marker 系 fail が残った時だけ即 fire できる  
- 条件を満たさない限り dormant のまま維持される  
- Codex B が必要時だけ最小改修へ進める  
