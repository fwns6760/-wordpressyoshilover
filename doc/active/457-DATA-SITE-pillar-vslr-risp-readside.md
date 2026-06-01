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

## 設計判断(2026-06-01 深掘りで判明・着手前に解決)

`at_bat_details` には **打数(official AB)列が無い**。result_text から AB を導く分類器も未実装(現存は `ranking_article_publisher._is_hit_result` と `insight_etl.parse_rbi_from_result_text` のみ)。稼働中の vs左右/RISP **lane は PA / 安打 / 打点 集計で「打率」を出していない**。
→ pillar で 打率 を出すには **official AB 分類器(四球/死球/犠打/犠飛/打撃妨害 等を AB から除外)を新規実装する必要**があり、誤分類は公開記事の事実誤り(致命的 NG)に直結する。文脈圧下で雑に書かない。

**選択肢**:
- (A) official AB 分類器を新規実装 + fixture で厳密に固める → pillar の他 split と同じ「打率」で統一(推奨だが慎重なテスト必須)
- (B) lane と同じ PA / 安打 / 打点 + 安打率(安打/PA)を表示し、official 打率 は出さない(AB 誤分類リスク回避・但し他 split の打率と表記が不揃い)

次着手時に (A) を基本線とし、AB 分類器を `insight_etl` に追加(NPB result_text の語彙を fixture 化)。これが 457 の最初のサブタスク。

### 着手済みの基礎(2026-06-01・prod insight.db 735 PA で検証済)

- **official AB 分類器の語彙確定**: non-AB = `フォアボール / 四球 / 敬遠 / デッドボール / 死球 / 犠牲バント / 犠打 / 犠牲フライ / 犠飛 / 打撃妨害`(result_text から `（…）` 注釈除去後に部分一致)。それ以外(三振/ゴロ/フライ/ライナー/ヒット/ツーベース/スリーベース/ホームラン/併殺打)は AB。prod 735 PA で AB=673/nonAB=62/誤分類0 を実証。`is_official_at_bat(result_text)` として `insight_etl` に追加予定。
- **hit 判定の正規表現バグを修正済(commit `c3f14c9`、image `insight-nightly:hit-fix-c3f14c9` deploy 済)**: 旧 `_HIT_RESULT_RE` がカタカナ安打(ヒット/ツーベース/スリーベース)を取りこぼし、 vs左右/RISP 記事の安打数が過少だった。`ヒット|ツーベース|スリーベース` 追加で修正。457 pillar はこの修正後の hit 判定を再利用する。
- **throws**: 投手左右は `config/npb_pitcher_throws.json`(405 投手)。`current_pitcher` 名で join。
- **残**: `is_official_at_bat` 実装+fixture → pillar `fetch_vs_lr_split_stats` / `fetch_risp_split_stats`(read-side `REPLACE(batter,' ','')=player`)→ field/builder/publisher → test → data-site-publisher deploy → verify。

## 依存

なし(read-side ルートは backfill 不要)。447 は本 ticket 完了で CLOSE/統合。**着手前に上記 AB 分類器の設計を確定**(456 と違い単純横展開でない)。
