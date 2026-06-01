# 459 DATA-SITE /data/team 順位表+フル集計 / /data/schedule 未来試合・予告先発(454包含)

- **種別**: 実装 / **priority**: P2 / **effort**: M
- **親**: 443 / 設計: `455...md` §13-3 / **454(standings-etl)を包含/再編** / GH: #123
- **status**: PARTIAL_LIVE_VERIFIED (2026-06-01) — チーム成績カードは LIVE、 順位表/未来試合は data-block
- **実績(feasible部)**: commit `bb78d24`、image `data-site-publisher:team-record-bb78d24`、execute SUCCESS。/data/team に「巨人 チーム成績」カード(勝敗分/勝率/得点失点/得失点差/連勝連敗/本拠地ビジター別)。verify = page 76294 に 26-24-2 / .520 / 得失点差-17 / 1連敗 / 本拠地13-14・ビジター13-10 反映確認。data-site test 99 passed。
- **data-block(未対応・要 source)**:
  - **セ6球団 順位表**: `standings_snapshots` が prod **空(populate 無)** → 別途 standings ETL/source が必要(元 454 の主眼)。
  - **未来試合 / 予告先発**: `games` は max=当日まで・予告先発カラム無し → 別 source 必要。
  - チーム打撃投手守備のフル集計列(得点圏/盗塁/出塁率 等)は logs から追加集計で拡張可能(follow-up)。

## 背景(深掘り・実取得)

- `/data/team`(`data_site_template_team.py` + `fetch_team_rankings` `data_site_query.py:1049`): **セ・リーグ 球団打率/本塁打/防御率 の3つの1値ランキング(各6行)のみ**。順位表もフル集計列も無い。
- `/data/schedule`(`fetch_giants_schedule` `data_site_query.py:1180`、`games` table): **過去結果カレンダーのみ**。未来試合・予告先発・開始時刻・box scoreリンク無し(`fetch_game_detail`/`game_slug` 生成コードは存在するが未接続)。

## ゴール

1. `/data/team` を**順位表**(順位/勝/敗/分/勝率/ゲーム差)+ **チーム打撃/投手/守備のフル集計列**へ拡張。source は `games` / `standings_snapshots`(既存 table)。可能なら12球団 view。
2. `/data/schedule` に**未来試合 + 予告先発 + 開始時刻**を追加し、各行から **box score 詳細(`/data/game/{slug}`)へリンク**(`game_slug` 既存で接続)。

## 対象

- `src/data_site_query.py`: `fetch_team_rankings`(L1049)拡張 / 順位表 fetch 新設(`standings_snapshots`)/ `fetch_giants_schedule`(L1180)に未来分・予告先発。
- `src/data_site_template_team.py` / `data_site_template_schedule.py`: 表レンダリング。
- 未来試合・予告先発の ingest が games に有るか**先行 verify**(無ければ別 source 確認を本 ticket 内で切り出し)。

## やる / やらない

- やる: 順位表+集計列、未来試合/予告先発、schedule→game詳細リンク、test。
- やらない: 新規 publish/mail/X、放送局データ(後回し)。

## 成功条件

- `/data/team` に順位表+打撃投手守備集計が数値入り表示。
- `/data/schedule` に直近の未来試合+予告先発が出る、各結果行が game 詳細へ遷移。
- targeted pytest green、production DB で verify。

## 依存

`standings_snapshots` の populate 状況、games の未来試合 ingest 有無を先に確認。454 は本 ticket に統合。
