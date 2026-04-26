# 030 — title assembly のルール固定と subtype-aware 生成

**フェーズ：** 本文品質改善の第1優先  
**担当：** Codex B  
**依存：** 010, 011, 014, A4 `858bab9`, B2 `177aa86`

---

## why_now

- `current_focus` の修正優先順位 1 位が `title assembly`。
- `027 canary DNS blocker` と独立に前進できる。
- fail pattern の `巨人スタメン` 接頭漏れ / `title-body mismatch` / `速報感だけ強くて本文が薄い` を title 層で早段に止める必要がある。

## purpose

- subtype × category から title を決定論的に構築する。
- title から逆に subtype を判定できる状態にし、本文との不整合を `WARN / reroll` で遮断する。

## scope

### title prefix table

- `lineup = 巨人スタメン`
- `postgame = 試合結果`
- `live_update = 接頭なし`
- `pregame = 先発情報`
- `farm = 二軍`
- `fact_notice = 訂正・告知系`

### title validator

- title から subtype を逆判定する。
- 逆判定は以下で固定する。
  - `巨人スタメン` 接頭 → `lineup`
  - `試合結果` 接頭、または score + 勝敗/分岐点/試合結果語彙 → `postgame`
  - `速報` 接頭、`途中経過`、`X回表/裏` などの live signal → `live_update`
  - `先発情報` 接頭、`予告先発` / `先発` / `試合前` → `pregame`
  - `二軍` / `ファーム` 系の接頭・主要語彙 → `farm`
  - `訂正` / `告知` / `お知らせ` / `お詫び` / `公示` / `取り下げ` → `fact_notice`
- 逆判定 subtype と classifier subtype が不一致なら `WARN + reroll`。
- `速報` 接頭は `live_update` 以外で禁止する。
- `巨人スタメン` 接頭は `lineup` 以外で禁止する。
- title が強い速報調でも、本文先頭 block が required fact block で始まらない場合は `WARN + reroll`。

### pipeline 挿入位置

- lane 切替直後、body render 前の validator として入れる。
- B1 / B2 の subtype 境界ガードと衝突する場合は、`030` は title 層だけを責務に持つ。

## non_goals

- `published` 既存記事の書き換え
- SEO 最適化
- 文体改善全般
- 新 subtype 追加
- `027 canary` 実走や DNS blocker 解消

## acceptance_check

- rule 固定 → Codex B 実装 → tests pass の 2 段で閉じられる。
- `巨人スタメン` 接頭漏れ、`速報` 接頭誤用、`title-body mismatch` を sample で再現できない。
- `git log --stat` / `git status --short` / 追加 test で追認できる。

## TODO

【×】subtype 別 title prefix 一覧を固定する  
【×】title からの subtype 逆判定条件を固定する  
【×】`巨人スタメン` 接頭の許可 subtype を `lineup` のみに固定する  
【×】`速報` 接頭の許可 subtype を `live_update` のみに固定する  
【×】mismatch 時の `WARN / reroll` を固定する  
【×】validator の挿入位置を lane 切替直後に固定する  
【×】B1 / B2 と責務が重なる時は title 層のみ担当と明記する  

## 成功条件

- subtype 別 title prefix 一覧が ticket 本文で固定されている  
- validator が `live_update` 以外の `巨人スタメン` 接頭と、`live_update` 以外の `速報` 接頭を `WARN + reroll` する  
- `title-body mismatch` が 1 週間の observation window で 0 件になる  
- Codex B がこの ticket だけで bounded 実装へ進める  
