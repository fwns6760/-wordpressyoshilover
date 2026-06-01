# 457 DATA-SITE Pillar vs左右/RISP 解放(447 re-scope・backfill不要ルート)

- **種別**: 実装 / **priority**: P1 / **effort**: S〜M
- **親**: 443 / 設計: `455...md` §13-2 / **447 を re-scope**(過大見積を是正)/ GH: #121
- **status**: READY

## 背景(深掘りで 447 の見立てを訂正)

447 は「`at_bat_details.batter_canonical` 全件 NULL のため vs左右/RISP が BLOCKED、backfill に3日」とするが、深掘りで**半分誤り**と判明:
- **チーム横断の vs左右/RISP は既に nightly LIVE**(`src/analysis/ranking_article_publisher.py` `aggregate_giants_batter_vs_lr_strict` L3726 / `aggregate_giants_batter_runner_state` L2935 が raw `batter`名 + `at_bat_details.runner_state` + `config/npb_pitcher_throws.json`(405投手左右)で集計、`insight_nightly.py` L291/331/392 から配信)。
- **真にBLOCKは個別選手 Pillar だけ**。原因は `src/analysis/insight_etl.py:470/475` が `batter_canonical`/`pitcher_canonical` を `None` ハードコード(normalize step は存在しない=grep 0件)。`fill_canonical_team_aware()` は logs のみ対象で at_bat_details 未適用。

## ゴール

個別選手 Pillar(`/data/{slug}/`)に **vs左右投手別 / 得点圏RISP** split を追加(打者)。**backfill 不要**ルートで。

## 対象

- `src/data_site_query.py`: vs左右/RISP の Pillar fetch を新設。**read-side fuzzy match** を採用(venue/inning split が既に使う `REPLACE(batter,' ','')=player` 方式、`fetch_venue_split_stats` L1241 等を雛形)。投手左右は `config/npb_pitcher_throws.json` で `current_pitcher`→throws を join。RISP は `at_bat_details.runner_state` を filter。
- `src/data_site_publisher.py` / `src/data_site_template_pillar.py`: 打者分岐(L846-858)に2セクション追加。

## やる / やらない

- やる: Pillar の vs左右/RISP(打者)、read-side match、test。
- やらない: **at_bat_details の batter_canonical backfill(不要)**、ETL upsert 改修、チーム横断ランキング(既LIVE・不可触)、投手側(別途)、publish/mail/X。
- 代替案メモ: 恒久的には `insight_etl.py` の canonical を埋める方が綺麗だが、本 ticket は**最小・可逆の read-side**で解く。canonical 化は別 follow-up。

## 成功条件

- 主力打者(吉川/岡本/丸)pillar に vs左投手/vs右投手・得点圏 が数値入り表示。
- チーム横断ランキング記事の出力に regression 無し(既存 aggregator を壊さない)。
- targeted pytest green、production DB copy preview で1選手 verify。

## 依存

なし(read-side ルートは backfill 不要)。447 は本 ticket 完了で CLOSE/統合。
