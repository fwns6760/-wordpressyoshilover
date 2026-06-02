# 464 DATA-ARTICLE 眠っている角度の再活性化(空固定 detector)

- **種別**: 実装 / **priority**: P2(差別化A・幅) / **effort**: S〜M
- **親**: 443 / 設計: `455...md` §16 / §17 Phase2A / GH: #128
- **status**: CLOSED / LIVE(2026-06-02、commit `ecc6eb0e`、image `insight-nightly:hero-reactivate-ecc6eb0`)

## 着地(2026-06-02、選別基準 = user「読者にわかりやすい角度を優先」)

検証で判明: 眠り角度は**事故ではなく全て日付つき user 明示指示で OFF**(サバメいらない / マニアック drop / issue#44 hero off / 変化率わかりにくい)。よって「わかりやすさ」基準で**選別再活性化**した。

**再活性化(読者にわかりやすい・全て whitelist◯ counting 系):**
- 今日のヒーロー打者 — gate 厳格化(H>=3 / HR+RBI2 / RBI3 / マルチHR のみ。旧 H>=2&RBI1 / 単発HR / RBI2単独 を撤去 = issue#44 乱発源を遮断)
- 今日の好投 — 真 QS(IP>=6 ER<=2)/ 救援無失点 S/H/勝 のみ(旧 IP>=5 準QS と不調を撤去)
- 本塁打ペース(このペースで○本)
- 連続マルチ安打(○試合連続)

**据え置き(わかりにくい = whitelist×):** BABIP乖離 / FIP-ERA乖離 / 変化率(stat_delta)/ 規定外好調(規定打席の説明要)。

**bug fix(read-only prod 検証で露呈):** 本塁打ペース / 連続多安打 detector は作成以来 dormant で `_resolve_team_code_from_name` 未 import の NameError が顕在化しておらず、再活性化で初発火。12球団網羅の `insight_defense_proxy._resolve_team_code` を alias import で配線。

**prod 実検証(snapshot 2026-06-01、read-only):** pace_hr 巨人publish=**1**(キャベッジ HR換算26本)/ multi_hit 2(巨人0)/ hero・好投 0(当日該当者なし=gate正常)。非巨人(priority=3)は publish の `priority<=2` gate で除外 = **乱発なし**。renderer は `anomaly_article_publisher` に既登録。test: off-lock を reactivated-lock へ書換 + NameError 回帰防止、insight/anomaly/nomotoke 917 pass / regression 0。

次回 insight-nightly 自然発火(12/17/20/21 JST)で記事化。

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
