# 461 DATA-SITE 既存 advanced_metric_snapshots の SABR 指標表示

- **種別**: 実装 / **priority**: P3 / **effort**: S(表示)〜M
- **親**: 443 / 設計: `455...md` §12-1(B に深さで負け)/ §13-5 / GH: #125
- **status**: READY(whitelist 確認先行)

## 背景(深掘り 1次source)

- baseballdata.jp は SABR 20指標(NOI/GPA/Iso/SecA/TA/RC/XR系/FIP/DIPS/RSAA/LOB% 等)を個別ランキング化。yoshilover pillar は **OPS 止まり**で B に深さで負け。
- insight.db に `advanced_metric_snapshots` table が**既存**(17指標 BABIP/wOBA/ISO/BB%/K%/OBP/SLG/OPS/FIP/xFIP/WHIP 等 + 9 scope + league_rank/position_rank、設計資料 §B3/data-insight-metric-whitelist より)。**既にある指標は表示するだけ=一部 S**。

## ゴール

pillar に **既存 snapshot の whitelist 指標**を追加表示(打者: OPS+/wOBA/ISO/BB%/K% 等、投手: FIP/WHIP/K9 等)。`doc/reference/data-insight-metric-whitelist.md` の ◯/× と `project_data_insight_final_whitelist` に**厳密準拠**(サバメ NG line を超えない)。

## 対象

- `src/data_site_query.py`: `advanced_metric_snapshots` から whitelist 指標を fetch(`fetch_team_leaders` L1110 が既に `team_code='g'` で参照)。
- `src/data_site_template_pillar.py`: 「指標(大手未掲載)」section 追加。

## やる / やらない

- やる: whitelist 内の既存 snapshot 指標表示、用語ツールチップ、test。
- やらない: **whitelist 外のサバメ追加(NG)**、新規指標計算、pitch-level、HR-WPO 等の独自指標新設(別検討)。

## 成功条件

- pillar に whitelist 準拠の SABR 指標が数値入り表示。
- metric-whitelist doc の × 指標が出ていないことを確認。
- targeted pytest green。

## 依存

`data-insight-metric-whitelist.md` の最終確認先行。snapshot に無い指標は本 ticket 対象外(計算は別)。
