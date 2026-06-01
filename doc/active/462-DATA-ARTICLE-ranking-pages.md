# 462 DATA-ARTICLE 球団内/リーグ ランキング面 新設

- **種別**: 実装 / **priority**: P2(parity) / **effort**: M
- **親**: 443 / 設計: `455...md` §17 Phase1 / GH: #126
- **status**: LIVE_DEPLOYED_VERIFIED (2026-06-01)
- **実績**: commit `b0dc60bf`、image `data-site-publisher:ranking-b0dc60bf`、execute SUCCESS。/data/ranking 新設(fetch_team_leaders の8カテゴリ leaderboard、各選手→pillar 回遊)。verify = page 76423 に「巨人 本塁打/防御率 ランキング」+ **pillar 回遊リンク64本**反映確認。data-site test 103 passed。
- **note**: 当初案の `/data/ranking/{metric}/` 個別面でなく、1 HUB に全カテゴリ集約(回遊と保守性優先)。指標別個別面は需要次第で follow-up。

## 背景(parity・実測)

A(my-favorite-giants)も B(baseballdata)も**指標別ランキング面**を持つ(B は SABR 指標別個別ページ ~60本、A は通算/シーズンランキング)。yoshilover は `/data/ranking` が **404**(§12-0 実測)。ランキング記事は nightly で生成済(`ranking_article_publisher.py`)だが、**恒久ランキング面(/data/ranking/)が無い**ため回遊先・SEO面が欠落。

## ゴール

`/data/ranking/`(HUB)+ `/data/ranking/{metric}/`(OPS/HR/防御率/直近5HOT 等)を新設。既存 `advanced_metric_snapshots`(team_code='g')+ ranking 集計を表示。各行から選手 pillar へリンク(回遊)。

## 対象

- `src/data_site_*`: ranking テンプレ + query(`fetch_team_leaders` `data_site_query.py:1110` 等を再利用)。
- whitelist(`data-insight-metric-whitelist.md`)準拠の指標のみ。

## やる / やらない

- やる: ranking HUB + 指標別面、pillar への回遊リンク、test。
- やらない: whitelist外指標、pitch-level、publish/mail/X。

## 成功条件

- `/data/ranking/` と主要 `/data/ranking/{metric}/` が 200 で数値表示、各行→pillar 遷移。
- targeted pytest green、production DB verify。
