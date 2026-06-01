# data-site 状況別スプリット拡張(452 / Phase B)

> 種別: 仕様書(証拠only。schedule/threshold/file/データ源は grep+DB で 1 件ずつ verify、取れないものは「不明」と明記)
> 対象 ticket: `452-DATA-SITE-situational-depth.md`
> 作成: 2026-06-01 / status: DRAFT(user 受け入れ待ち)
> 目的: ベンチ(baseballdata.jp / my-favorite-giants.net)に対し **今季データの細かさ + UI** で勝つ。
>   現データ(今季のみ・追加source無し)で作れる状況別スプリットを /data/ 選手ページに追加。

## 1. 背景(現物確認)

ベンチ2サイトは多年蓄積+守備+順位表+網羅的状況別を持つ(2026-06-01 WebFetch で確認)。
我々の `insight.db` は現状:

- games: `2026-03-27`〜`2026-05-31`(**今季のみ**、`SELECT MIN/MAX(game_date)` で確認)
- `standings_snapshots` = 0 行 / `fielding_logs` = 0 行 / `at_bat_details.batter_canonical` 非NULL = 0(全て現物 COUNT で確認)

→ 多年・守備・順位表・RISP は **現データに無い**(= Phase C 投資、本spec対象外)。
本spec(Phase B)は **追加source無し・¥0** で作れる状況別スプリットに限定する。

## 2. スコープ(Phase B = 今できる)

### 2.1 追加するスプリット(野手)

| スプリット | データ源(verified) | 区分 |
|---|---|---|
| 曜日別 打率 | `games.game_date` → weekday | 月〜日 の7区分(出場ある曜日のみ) |
| 月別 打率 | `games.game_date` → month | 3〜10月(出場ある月のみ) |
| 交流戦 / リーグ戦 別 | `game_id` の NPB コード相手側がパ6球団 `{h,f,m,l,e,b}` なら交流戦 | 2区分 |
| 試合別ログ(直近) | `batting_logs`(game×player の AB/H/RBI/R/SB) | 直近10試合の1行ログ |

- **導出根拠(verified 2026-06-01)**: 岸田行倫の直近試合で `2026-05-31:f-g-03`(相手 f=日ハム=交流戦)/ `2026-05-22:g-t-09`(相手 t=阪神=リーグ戦)を実データで判定確認。曜日も `game_date` から確定。
- いずれも **既存 `batting_logs` + `games` のみ**で算出。新規 source / ETL / 課金なし。

### 2.2 投手

- 既存の「前回登板の中身」(`pitching_logs`、先発)/「防御率」(救援)を維持。
- 投手の曜日/月別は標本が薄い(先発 週1)ため **本Phaseでは野手のみ**。投手スプリットは対象外(理由: サンプル不足、誇張回避)。

### 3. 表示(UI)

- pillar の既存スプリット section 群(`_build_venue_split_html` 等)と同じカード様式で追加:
  - `_build_weekday_split_html` / `_build_month_split_html` / `_build_interleague_split_html` / `_build_game_log_html`
- 各表は「区分 / 試合 / 打数 / 安打 / 打率(+ RBI)」。venue split と統一。
- **sample 規律**: 打数 0 の区分は省く。打数が少ない区分は **打率の信頼性が低い旨を脚注**で表示(誇張回避、[[feedback_title_polisher_cap_policy]] と同様の silent 防止思想)。

## 4. 受け入れ条件

1. `/data/<player>/` に 曜日別 / 月別 / 交流戦リーグ戦別 / 直近試合ログ の4 section が出る(出場データのある選手)。
2. 数字は `batting_logs`/`games` と一致(production copy で1選手以上クロス検証)。
3. 打数0区分は非表示。新規 source / Gemini / 課金 増なし。
4. data-site の既存テスト + 新規テストが pass。
5. live verify: 1選手の曜日別/交流戦別が production data と一致。

## 5. やらないこと(Phase B 不可触)

- 多年データ / 守備成績 / 順位表 / 得点圏(RISP)/ 対左右 = **Phase C(投資判断、本spec対象外)**。
- 投手の曜日/月別スプリット(サンプル不足)。
- 既存 article path / Scheduler / featured_media / X lane。

## 6. Phase C(参考・本spec対象外)

「ベンチにデータ網羅で勝つ」には以下が必要。いずれも **現データゼロ**(§1 確認)で、source拡張 + ETL + コスト(月単位)を伴う **user 投資判断**:

- 多年データ(2011〜)取り込み源の決定とコスト
- 守備データ source(現 `fielding_logs` 0)
- 順位表/勝敗表(現 `standings_snapshots` 0)
- 得点圏/対左右(`at_bat_details.batter_canonical` backfill = ticket 447)

C は別チケット + 別見積りで扱う(本Phase Bでは着手しない)。
