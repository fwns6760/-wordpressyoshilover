# 029 — quality-gmail の progress digest を正式化

**フェーズ：** 品質監視通知の意味固定  
**担当：** Codex B  
**依存：** 015, 027

---

## 概要

- `quality-gmail` を件数通知ではなく、`品質推移 / 公開準備 / 主因 / 次改善` の progress digest として正式化する。
- 既存の mail path / cadence / recipient / fallback は変えず、4 行の意味と判定基準だけを固定する。
- `027` canary success 後に fire し、fixed lane の新 Draft 流入を含む品質の変化が読める状態を目指す。

## 決定事項

### 4 行の正本

- 1 行目: `品質推移`
- 2 行目: `公開準備`
- 3 行目: `主因`
- 4 行目: `次改善`

### 比較軸

- `品質推移` は `quality-monitor` の `flagged / scanned` と、利用可能なら `ready / review / hold` の割合を比較する。
- 基本比較窓は `直近24h vs 前24h` とする。
- 補助比較として、急なノイズをならすため `3日移動中央値` を参照してよい。

### 良化 / 横ばい / 悪化

- `良化`
  - `scanned_count` が前窓の 80% 以上を維持しつつ `ready_share` が +10pt 以上
- `悪化`
  - `ready_share` が -10pt 以上
  - または同一主因が 2 窓連続で最上位
- 上記以外は `横ばい`

### 公開準備

- `公開準備` は `ready / review / hold` の比率または件数を 1 行で出す。
- ここでの `ready` は publish を意味せず、`user が見に行く価値のある Draft` を意味する安全側の表現とする。

### 主因 / 次改善

- `主因` は `quality-monitor.reason_counts` と `draft-body-editor.skip_reason_counts` から最大 1 件だけ出す。
- `次改善` は次の 1 テーマだけを書く。ticket 名か prompt/theme 名のどちらか一方に固定する。

### fallback

- log は Windows 側から `\\\\wsl.localhost\\Ubuntu\\...\\logs\\quality_monitor\\` を直接読む前提にする。
- stale log 時は `[src:stale]`、usable log 不在時は `[src:none]` を使う。
- fallback 中でも 4 行の順番と意味は変えない。

### 不可触

- `quality-gmail` の送信先、時間帯、主系位置づけは変えない。
- 新しい mail channel や monitor は追加しない。
- `quality-monitor` 本体の大改修は scope 外とする。

---

## TODO

【×】4 行の正本を `品質推移 / 公開準備 / 主因 / 次改善` に固定する  
【×】`直近24h vs 前24h` の比較軸を固定する  
【×】`良化 / 横ばい / 悪化` の閾値を固定する  
【×】`公開準備` の安全側表現を固定する  
【×】`主因` は 1 件、`次改善` は 1 テーマだけと明記する  
【×】`[src:stale]` / `[src:none]` fallback 時も 4 行の意味を変えないことを明記する  
【×】送信先・時間帯・主系位置づけを不変と明記する  
【×】`027 canary success 後に fire` する前提を明記する  

---

## 成功条件

- user が 4 行だけ見て `良化 / 横ばい / 悪化` を理解できる  
- 件数ではなく改善方向と詰まりが読める  
- `主因` は 1 件だけ、`次改善` も 1 テーマだけに収まる  
- 既存通知経路を壊さない  
- `027` canary success 後にそのまま bounded 実装へ進める粒度になっている  
