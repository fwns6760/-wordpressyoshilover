# 464 DATA-ARTICLE 眠っている角度の再活性化(空固定 detector)

- **種別**: 実装 / **priority**: P2(差別化A・幅) / **effort**: S〜M
- **親**: 443 / 設計: `455...md` §16 / §17 Phase2A / GH: #128
- **status**: READY

## 背景(深掘り 1次source・コメントとコードの矛盾)

`insight_anomaly_detector.py` の `_RENDERERS`(L2248)に15種登録だが、**detector が `[]` ハードコードで実生成されない角度が約半数**(コメントは「2026-05-27 全部復活」と書くがコードは空):
- BABIP乖離 / FIP-ERA乖離 = `[]`固定(L1824-1825)
- giants_top% = `_GIANTS_TOP_METRICS = ()` 空ループ(L1757)
- HRペース / 規定外好調 / 連続多安打 = `[]`固定(L1841-1844)
- 1試合 hero打者 / 好投投手 = `[]`固定(issue#44 Bで off, L1861-1862)
- stat_delta(変化率)= `[]`固定(L1916)

= **「幅」が見かけより狭い**。renderer はあるのに供給が止まっている。

## ゴール

whitelist(`data-insight-metric-whitelist.md` / `project_data_insight_final_whitelist`)準拠の角度を**1つずつ精査して再活性化**。サバメ NG line(BABIP/FIP/wOBA 等の×指標)は**起こさない**。連続多安打 / 1試合 hero / HRペース 等の◯角度を優先。

## 対象

- `src/analysis/insight_anomaly_detector.py`(空固定の解除、whitelist gate 経由)。
- 各角度の閾値・dedup・quality gate 通過を確認。

## やる / やらない

- やる: whitelist◯角度の再活性化(1角度ずつ verify)、test、誤検知防止。
- やらない: **whitelist×角度(サバメ NG)を起こす**、閾値だけ緩めて乱発、publish直書き。

## 成功条件

- 再活性化した各角度が production データで適切に発火(乱発でない、dedup効く)。
- whitelist× が混入していないことを確認。
- targeted pytest green。

## 依存

issue#44 B(1試合hero off)の経緯を確認してから hero 系は判断(user 方針確認要の可能性)。
