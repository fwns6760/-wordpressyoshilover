# T-007 Post Fix Recheck - 2026-04-18

- generated_at: `2026-04-18`
- scope: `62518, 62527, 62540, 62044, 61981, 61886, 61802, 61770, 61598`
- before_logic: `git commit 10fa214 の acceptance_fact_check.py`
- after_logic: `working tree の T-007 修正版 acceptance_fact_check.py`

## サマリ

| post_id | subtype | before | after | 変化 |
|---|---|---:|---:|---|
| 62518 | postgame | 🔴 | ✅ | `venue=PayPay` / `score=25-97` 疑陽性が解消 |
| 62527 | postgame | 🔴 | 🔴 | 真の opponent mismatch が残存、evidence URL が source へ改善 |
| 62540 | postgame | ✅ | ✅ | 変化なし |
| 62044 | lineup | 🔴 | ✅ | venue 疑陽性が解消 |
| 61981 | postgame | 🔴 | 🔴 | venue 疑陽性は解消、opponent mismatch は残存 |
| 61886 | pregame | 🔴 | ✅ | venue 疑陽性が解消 |
| 61802 | lineup | 🔴 | ✅ | venue 疑陽性が解消 |
| 61770 | lineup | 🔴 | 🟡 | venue 疑陽性が解消、`source_reference_missing` のみ残存 |
| 61598 | postgame | 🔴 | 🟡 | venue 疑陽性が解消、`source_reference_missing` のみ残存 |

## post_id 62518

- title: `巨人8-2 勝利の分岐点はどこだったか`
- category/subtype: `試合速報 / postgame`
- before: `🔴`
  - `venue`: `神宮` vs `PayPay`
  - `score`: `8-2` vs `25-97`
- after: `✅`
  - findings なし
- 差分:
  - UUID断片由来の `25-97` 誤抽出が消えた
  - NPB 月間日程の venue 誤取得も消えた

## post_id 62527

- title: `巨人DeNA戦 大城卓三は何を見せたか`
- category/subtype: `試合速報 / postgame`
- before: `🔴`
  - `opponent`: `DeNA` vs `ヤクルト`
  - evidence: `https://npb.jp/games/2026/schedule_04_detail.html`
- after: `🔴`
  - `opponent`: `DeNA` vs `ヤクルト`
  - evidence: `https://www.nikkansports.com/baseball/news/202604170001523.html`
- 差分:
  - 判定自体は残存
  - root cause は parser ではなく `title_rewrite_mismatch`
  - evidence URL が正しく source origin に切り替わった

## post_id 62540

- title: `巨人ヤクルト戦 フォレスト・ウィットリーは何を見せたか`
- category/subtype: `試合速報 / postgame`
- before: `✅`
- after: `✅`
- 差分:
  - 変化なし
  - `source_facts.score=19-4` の潜在誤抽出は消えたが、表面判定は元から green

## post_id 62044

- title: `巨人スタメン 阿部監督賞賛、大城の同点弾に「自分たちに流れを」決勝打の松本に…`
- category/subtype: `試合速報 / lineup`
- before: `🔴`
  - `venue`: `甲子園` vs `PayPay`
- after: `✅`
- 差分:
  - venue fallback 疑陽性が解消

## post_id 61981

- title: `巨人阪神戦 試合の流れを分けたポイント`
- category/subtype: `試合速報 / postgame`
- before: `🔴`
  - `opponent`: `阪神` vs `楽天`
  - `venue`: `甲子園` vs `PayPay`
- after: `🔴`
  - `opponent`: `阪神` vs `楽天`
  - evidence: `https://www.nikkansports.com/baseball/news/202604140001354.html`
- 差分:
  - venue 疑陽性は解消
  - `opponent` の mismatch は残存
  - 真の誤記候補として個別対応継続

## post_id 61886

- title: `【巨人】則本昂大、甲子園で12年ぶり先発「極力聞かないように」虎党ならではの独特な注意事項`
- category/subtype: `試合速報 / pregame`
- before: `🔴`
  - `venue`: `甲子園` vs `PayPay`
- after: `✅`
- 差分:
  - venue fallback 疑陽性が解消

## post_id 61802

- title: `【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待`
- category/subtype: `試合速報 / lineup`
- before: `🔴`
  - `venue`: `東京ドーム` vs `PayPay`
- after: `✅`
- 差分:
  - venue fallback 疑陽性が解消

## post_id 61770

- title: `【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待`
- category/subtype: `試合速報 / lineup`
- before: `🔴`
  - `venue`: `東京ドーム` vs `PayPay`
  - `source_reference_missing`
- after: `🟡`
  - `source_reference_missing` のみ
- 差分:
  - venue 疑陽性が解消
  - source 参照欠落の yellow だけが残った

## post_id 61598

- title: `解説陣が巨人・坂本勇人にエール「背中でチームを引っ張って」`
- category/subtype: `試合速報 / postgame`
- before: `🔴`
  - `venue`: `東京ドーム` vs `PayPay`
  - `source_reference_missing`
- after: `🟡`
  - `source_reference_missing` のみ
- 差分:
  - venue 疑陽性が解消
  - source 参照欠落の yellow だけが残った

## 結論

- T-007 修正で、`62518` と T-002 venue 系の疑陽性は解消した
- 依然 red のまま残るのは `62527`, `61981`
- `61770`, `61598` は parser バグ由来の red ではなく、参照元欠落による yellow として扱うのが妥当
