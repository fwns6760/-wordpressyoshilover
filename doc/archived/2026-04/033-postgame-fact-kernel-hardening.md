# 033 — postgame fact kernel hardening

**フェーズ：** 本文品質改善の第3優先  
**担当：** Codex B  
**依存：** 011, B3 `293d4a5`, 032

---

## why_now

- `current_focus` の修正優先順位 4 位。
- `postgame` が抽象的で、何が起きたかが見えにくい fail pattern が残っている。

## purpose

- `postgame` を必ず事実核から始めるよう固定する。
- 抽象 lead と薄本文を抑え、試合結果記事の可読性を安定させる。

## scope

### fact kernel

- `【試合結果】` の first sentence で、`スコア / 勝敗 / 対戦相手 / 日付` を先に短く固定する。
- `【ハイライト】` に `決定的出来事` を 1 件以上入れる。
- コメント slot は fact kernel (`【試合結果】` + `【ハイライト】`) の後ろにだけ置く。
- コメントがなくても fact kernel だけで記事が成立する構造にする。

### abstract lead 禁止

- `激闘だった` や `悔しい敗戦となった` のような抽象 lead を first sentence に置かない。
- 先頭文は必ず具体的事実を含む。

### validator

- `【試合結果】` の first sentence が抽象 lead の場合は `WARN + reroll`。
- `【試合結果】` に `対戦相手 / 日付` が欠ける場合も `WARN + reroll`。
- comment slot が fact kernel より前に出た場合は `WARN + reroll`。
- `スコア / 勝敗 / 決定的出来事` のいずれか欠落で fail。

## non_goals

- `020` postgame revisit chain
- SEO / 文体最適化
- AI lane 拡張
- コメント量の増量

## acceptance_check

- `postgame` sample 群で fact-first lead が維持される。
- `何が起きたかが見えにくい` fail pattern が observation window で 0 件になる。
- `032` の body contract と矛盾しない。

## TODO

【×】postgame の fact kernel 必須項目を固定する  
【×】fact kernel の後ろにだけコメント slot を置くと固定する  
【×】抽象 lead 禁止を固定する  
【×】fact-first validator と reroll 条件を固定する  
【×】`スコア / 勝敗 / 決定的出来事` 欠落時の fail 条件を固定する  

## 成功条件

- `postgame` が抽象 lead ではなく fact-first になる  
- コメント有無に関係なく、事実核だけで記事が成立する  
- Codex B が `postgame` 専用 hardening 実装へそのまま進める  
