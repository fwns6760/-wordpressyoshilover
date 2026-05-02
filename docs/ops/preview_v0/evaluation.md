# preview_v0 evaluation

`GCP Codex WP本文修正プレビュー v0` の既存 5 サンプルを、preview-only 前提で評価したメモ。

## 評価前提

- 対象 sample:
  - `sample_postgame_1.md`
  - `sample_postgame_2.md`
  - `sample_postgame_3.md`
  - `sample_farm_result_1.md`
  - `sample_farm_result_2.md`
- 参照元:
  - `docs/ops/preview_v0/README.md`
  - `logs/cleanup_backup/*.json`
- 実施していないこと:
  - `WP write`
  - `publish status change`
  - `Gemini call`
  - `deploy`

## スコア定義

| axis | 1 | 5 |
|---|---|---|
| 元本文の劣化深刻度 | 軽微 | 深刻 |
| 修正文候補の improvement 効果 | 限定的 | 大きい |
| source/meta facts 完備度 | facts が乏しい | facts が十分ある |
| 捏造リスク | 低い | 高い |
| deterministic 純度 | ルール依存が弱い | ルール化しやすい |

## 5 sample scorecard

| sample | subtype | 劣化深刻度 | improvement 効果 | facts 完備度 | 捏造リスク | deterministic 純度 | short note |
|---|---|---:|---:|---:|---:|---:|---|
| `sample_postgame_1` | `postgame` | 5 | 5 | 2 | 1 | 5 | `score=-` と `相手=相手`、破損断片、unsupported section が多く、削除中心で大きく改善できる |
| `sample_postgame_2` | `postgame` | 4 | 4 | 4 | 2 | 4 | source が「記念グッズ発売」で game-summary に寄り切れておらず、短文化は効くが解釈の余地が少し残る |
| `sample_postgame_3` | `postgame` | 4 | 5 | 3 | 1 | 5 | `結果確認中` と hero-name placeholder、fan voice 過積載を切るだけで見た目が大きく改善する |
| `sample_farm_result_1` | `farm_result` | 4 | 5 | 5 | 1 | 5 | source/meta facts が十分あり、空 section と一般論フィラーを落とすだけで成立する |
| `sample_farm_result_2` | `farm_result` | 3 | 4 | 4 | 1 | 5 | title restatement loop と empty section が中心で、低リスクに圧縮できる |

## subtype summary

| subtype | samples | avg 劣化深刻度 | avg improvement | avg facts 完備度 | avg 捏造リスク | avg deterministic 純度 | summary |
|---|---:|---:|---:|---:|---:|---:|---|
| `postgame` | 3 | 4.3 | 4.7 | 3.0 | 1.3 | 4.7 | 劣化は重いが、placeholder 削除と optional section 切り落としだけでも改善幅が大きい |
| `farm_result` | 2 | 3.5 | 4.5 | 4.5 | 1.0 | 5.0 | facts が濃く、delete-first ルールとの相性が最も良い。安全に広げやすい |

## 共通課題

- 本文に `CTA / fan voice / related posts / poll` が混入し、core facts に対して本文が長すぎる
- `source/meta` にない一般論や将来予想が `【試合展開】` `【一軍への示唆】` として増殖する
- 空見出し、または見出しに対して本文が title restatement だけの section が残る
- facts の密度より section 数が多く、見出しを増やすほど捏造リスクが上がる構造になっている

## subtype 固有課題

### `postgame`

- `結果確認中`、`スコア=-`、`相手=相手`、`選手` のような placeholder が残りやすい
- source が hero note や goods note でも、強引に full game-summary テンプレへ押し込まれている
- fan voice と関連記事が本文面積を圧迫し、試合 facts より補助要素が目立つ
- 2 source 記事でも、preview 時点で見えている source/meta facts は意外に薄く、unknown slot は明示的に空欄化ではなく「書かない」判断が必要

### `farm_result`

- `【二軍結果・活躍の要旨】` はあるが、その下が empty / title restatement / generic filler のまま終わりやすい
- `【一軍への示唆】` が source 非依存の一般論に流れやすい
- score はあるが player facts が薄いケースでは、試合サマリーを膨らませるより roster/move note に落とした方が安全

## backup volume メモ

- `logs/cleanup_backup` 内の `GIANTS GAME NOTE`: `59`
- `logs/cleanup_backup` 内の `GIANTS FARM WATCH`: `44`

母数は `postgame` の方がやや大きい。volume 差は極端ではないが、preview を広げた時の観測件数は `postgame` が取りやすい。

## どちらを先に広げるか

推奨: `postgame`

理由:

- 平均 `improvement 効果` が `4.7` と高く、5 sample 中でもっとも「削除と短文化だけで見た目が戻る」余地が大きい
- backup 母数が `59` あり、`farm_result` (`44`) より preview 観測を早く溜めやすい
- `postgame` の劣化は `placeholder / fan voice 過積載 / 推測展開 / hero-name omission` に集中しており、v0 の deterministic rule と噛み合う
- facts 完備度は `farm_result` より低いが、v0 は unknown fact を補完せず「書かない」方針なので、strict omission を守れば hallucination risk は低く抑えられる

補足:

- `farm_result` は `facts 完備度 4.5 / deterministic 純度 5.0` で、低リスクな第 2 波として非常に良い
- 先に安全率を優先するなら `farm_result` canary も成立するが、preview v0 の価値検証という観点では `postgame` の方が impact が大きい
