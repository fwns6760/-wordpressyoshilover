# 032 — 本文ブロック順の正規化と subtype 別 body contract 固定

**フェーズ：** 本文品質改善の第2優先  
**担当：** Codex B  
**依存：** 011, A4 `858bab9`, B3 `293d4a5`, B4 `ca643ab`, B5 `aa11a07`, B6 `50be9b7`, B7 `1a56138`, B8 `3acb49c`, 030

---

## why_now

- `current_focus` の修正優先順位 3 位。
- title 層を固定した後は、本文 block 順と required block 欠落を抑えないと `薄本文` と `title-body mismatch` が残る。

## purpose

- subtype ごとに本文の required block と block order を固定する。
- validator で欠落と順序崩れを検知し、reroll で本文の深さと一貫性を安定化する。

## scope

### live_update

- text block order: `【いま起きていること】` → `【流れが動いた場面】` → `【次にどこを見るか】`
- first block: `【いま起きていること】`
- source block は本文 heading とは別に、rendered HTML 側の source hero / source card を required block として持つ

### postgame

- text block order: `【試合結果】` → `【ハイライト】` → `【選手成績】` → `【試合展開】`
- first block: `【試合結果】`
- source block は本文 heading とは別に、rendered HTML 側の source hero / source card を required block として持つ

### pregame

- text block order: `【変更情報の要旨】` → `【具体的な変更内容】` → `【この変更が意味すること】`
- first block: `【変更情報の要旨】`
- source block は本文 heading とは別に、rendered HTML 側の source hero を required block として持つ

### farm

- text block order: `【二軍結果・活躍の要旨】` → `【ファームのハイライト】` → `【二軍個別選手成績】` → `【一軍への示唆】`
- first block: `【二軍結果・活躍の要旨】`
- source block は本文 heading とは別に、rendered HTML 側の source hero を required block として持つ

### fact_notice

- text block order: `【訂正の対象】` → `【訂正内容】` → `【訂正元】` → `【お詫び / ファン視点】`
- first block: `【訂正の対象】`
- source block は `【訂正元】` に加えて、rendered HTML 側の source hero を required block として持つ

### validator

- validator は body 層のみを責務に持ち、subtype は upstream classifier / 030 title validator の解決結果を受け取るだけにする。
- first block は summary hero を除いた本文最初の normalized heading を対象に固定する。
- required block 欠落時は `WARN + reroll`。
- block order が崩れた場合も `WARN + reroll`。
- source block 不在時は publish / draft status に関係なく fail 扱いにする。
- `030` の title validator と重なる prefix / subtype 逆判定 / title-body mismatch の再判定は行わない。body validator は title reroll を発火しない。

## non_goals

- subtype 境界の再設計
- routing 変更
- publish 経路追加
- 新 subtype 追加

## acceptance_check

- subtype ごとの body contract が ticket 本文で固定されている。
- validator 追加後、sample で required block 欠落と順序崩れを再現しない。
- `030` の title rule と矛盾しない。

## TODO

【×】`live_update / postgame / pregame / farm / fact_notice` の block order を固定する  
【×】各 subtype の first block を固定する  
【×】required block 欠落時の `WARN + reroll` を固定する  
【×】block order 崩れ時の `WARN + reroll` を固定する  
【×】source block 不在を fail 扱いに固定する  
【×】`030` title rule と整合する validator 境界を明記する  

## 成功条件

- required block 欠落と block order 崩れが observation window で有意に減る  
- title だけ強くて本文が薄い記事が sample で再現しない  
- Codex B が subtype 別 validator 実装へそのまま進める  
