# 453 DATA-SITE リーグ順位バッジ(データページに「打率 セ◯位」)

> parent: 452 / status: READY_FOR_IMPL / owner: Claude Code / 作成: 2026-06-01
> 前提(実測): `advanced_metric_snapshots` 312,657 行に `league_rank / league_total /
> position_rank / position_total` が計算済(例: 平山 AVG last_7d rank=12/127)。 ETL 不要・read-side のみ。

## 1. ゴール

データページの主要 stat(打率・本塁打・打点・防御率・奪三振 等)に、 **「セ・リーグ ◯位 / N人中」**
の順位バッジ(orange `.ys-tag`)を表示する。 大手にない「巨人選手がリーグで今どの位置か」を一目で。

## 2. データ源(確定)

- table: `advanced_metric_snapshots`
- 使う列: `player_canonical, metric_name, metric_value, scope, league_rank, league_total, position_rank, position_total, snapshot_date`
- scope: season 相当を優先(無ければ最新 snapshot_date の該当 scope)。 ※どの scope を採るかは impl 時に実データで確認(season scope の有無を grep/SELECT で verify、 推測しない)。

## 3. 実装スコープ

- `data_site_query.py`: `fetch_player_metric_ranks(player_canonical) -> list[(metric_name, value, league_rank, league_total)]`(read-side、 最新 snapshot、 巨人選手の主要 metric のみ)。
- `data_site_template_pillar.py`: season/pitching stats カードの該当数字の隣に `.ys-tag`(「セ◯位/N人中」)を表示。 順位が無い metric は無印。
- 表示は「リーグで上位(例: 1/3 以内)」のみ強調 or 全件表示かは impl で判断(載せすぎ防止)。

## 4. 触らない

- ETL / insight.db 書き込み / scheduler / env は不可触(read-side 表示のみ)。
- advanced_metric_snapshots の中身は変更しない(読むだけ)。
- 公開 X 投稿・mail lane は不可触。

## 5. 受け入れ

- 選手ページに正しい「セ◯位/N人中」が出る(production 値と一致を 1-2 選手で verify)。
- データ無し選手は無印で崩れない。
- tests: fetch + テンプレ(バッジ有/無)。

## 6. next

- 452 のデザイン刷新と同 commit 群で進めると `.ys-tag` を二度手間なく使える。
