# 345-INSIGHT — 守備指標の追加と 3 area 配分均等化

status: PARKED(NPB box score 守備項目 audit が prerequisite)
priority: P2(本日 LIVE の DATA-INSIGHT-continuous 拡張、急がない)
owner: Claude
ready_for: audit only(実装は別 session)
blocked_by: NPB 公式 box score の守備項目 source 確認

## 背景

2026-05-14 EVENING、user から指摘:

> 守備率とかもだしたりして。安打だけでなく。守備も打撃も投手も全てが同じ割合を記録かな。

現状の DATA-INSIGHT-continuous(同日 LIVE):
- 打撃: OPS / 打率 / HR / BABIP_DIVERGENCE 等
- 投手: ERA / WHIP / FIP / K9 / BB9 / HR9 / FIP_ERA_DIVERGENCE 等
- 守備: **ゼロ**(欠落)

scheduler 7 trigger(02/07/12/15/17/20/21 JST)で出る記事の area 配分も、打撃 + 投手で偏っている。

## ゴール

1. 守備指標を 1〜3 軸追加(候補: 守備率 FP% / 失策 E / 守備機会 TC)
2. scheduler trigger 配分を 打撃 / 投手 / 守備 で **概ね均等**(各 area が同じ頻度で出る)

## prerequisite audit

実装前に 1 次 source 確認:

1. NPB 公式 box score に守備項目があるか(失策 / 補殺 / 刺殺 / 守備機会)
2. 既存 ETL(`src/analysis/insight_etl.py`)で守備データを保存しているか
   - `batting_logs` / `pitching_logs` はあるが `fielding_logs` table は **無さそう**
3. もし無ければ scrape 拡張が必要 → 343-INSIGHT-007 と同じ手順

## 実装 path 候補

### A. NPB box score に守備項目あり

- 1 session で `fielding_logs` table 新設
- `compute_advanced_metric_snapshots()` に守備 metric 追加
- `ranking_article_publisher.py` で守備 ranking 記事 type 追加
- scheduler rotation を 3 area 均等化
- 想定: 24h 以内 LIVE 可能

### B. NPB box score に守備項目なし

- 別 source 必要(Yahoo NPB stats / Sportsnavi 等)
- scope 大、user 判断要(著作権 / コスト境界)

## 配分均等化の設計

候補:
- trigger 7 本を area で round-robin: 朝=打撃 / 昼=投手 / 午後=守備 / 夕方=打撃 / 夜=投手 / 試合中=守備 / 試合後=打撃
- もしくは各 trigger で 3 area から 1 記事ずつ並走

## 守備指標の注意点

- **失策ランキング**は negative 強調(選手不評を招く可能性)→ 大手も控えめ。出すなら「守備率上位」優先、失策は背景の参考値に留める
- 守備率は出場機会で揺れる(代打中心の選手は分母小)→ サンプルサイズ 50 機会以上の閾値を入れる

## ticket 着手判断

- 着手前に user に audit 結果(A or B path)を上げる
- A path なら自律実装 GO
- B path なら user 判断待ち

## 関連

- 親 system: DATA-INSIGHT-continuous(2026-05-14 LIVE、doc/done/2026-05/342-INSIGHT-data-driven-ranking-auto-publish.md)
- handoff: `docs/handoff/session_logs/2026-05-14_session_handoff_DATA_INSIGHT_continuous_LIVE.md`
- work_log: `docs/work_logs/2026-05-14_continuous-db-insight-articles.md`
