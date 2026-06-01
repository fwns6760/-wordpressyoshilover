# 467 DATA-SITE 選手ページに年度別成績 + 通算(NPB公式 career scrape)

- **種別**: 実装 / **priority**: P2(ライバル超えの最大の残ギャップ=履歴) / **effort**: M
- **親**: 443 / 設計: `455...md` §5/§17 / GH: #131
- **status**: READY(source 確定済)

## 背景(2026-06-02 user 指摘)

選手 pillar は **2026 シーズンのみ表示**(今季通算+直近5+split+SABR)。**年度別履歴 / 通算が無く**、my-favorite-giants(1936-)/ baseballdata(2011-)の年度別履歴に site で負ける。
**「取れない」ではない**:insight.db が当季 box score しか ingest してないだけで、**NPB公式に年度別+通算が full にある**(前回の「取れない撤回」教訓と同じ = [[feedback_no_data_unavailable_without_source_check_2026_06_01]])。

## source 確定(実取得済 2026-06-02)

- **選手 career page**: `https://npb.jp/bis/players/{id}.html` に **年度別成績(例 則本 2013楽天〜2026読売)+ 通算** が table で載る。投手ヘッダ実取得: `年度/所属球団/登板/勝利/敗北/セーブ/H/HP/完投/完封勝/無四球/勝率/打者/投球回/安打/本塁打…`。打者は別ヘッダ(impl時に実取得確認)。
- **name→NPB id マッピング**: `https://npb.jp/bis/teams/rst_g.html`(巨人ロスター)に **104名の `/bis/players/{id}.html` リンク**。例: 田中将大=11215114 / 大勢=81085155 / 戸郷翔征=41045138 / 則本=51055137。`/bis/players/{id}.html"...>名前</a>` で name→id 抽出可。

## ゴール

選手 pillar に「**年度別成績**(各年の所属球団 + 標準成績)+ **通算**」section を追加。移籍履歴(則本=楽天→巨人 等)も出る=ファン価値高い。

## 実装案

- `parse_giants_roster_ids(html)`: rst_g.html → {正規化名: npb_id}(純粋関数)。
- `parse_player_career(html, is_pitcher)`: career page → [(年, 所属, …標準成績), …] + 通算行(打者/投手で列分岐)。純粋関数で fixture test。
- `fetch_player_career(npb_id, is_pitcher)`: scrape。
- publisher/pillar: 選手名→id 解決 → career fetch → 年度別 section render。
- 表記: 日本語、site なので whitelist 非適用(全列OK)。

## やる / やらない

- やる: 年度別+通算の取得・表示、打者/投手 列分岐、roster id マッピング、test。
- やらない: 名鑑プロフィール(生年月日等。別 ticket。career page に一部ある可能性は impl時確認)、whitelist(post)非適用なので気にしない。

## ★設計上の注意(network 負荷)

- pillar は 1 publish で 115 選手 render。各選手 career fetch を毎回やると **100+ NPB リクエスト/run × 3 run/日**= 重い + NPB rate-limit risk。
- career データは**現役年以外ほぼ静的** → **キャッシュ設計必須**(例: career を別 table/JSON に日次1回 ingest して pillar は DB 参照、or insight.db に yearly_stats table 追加して insight-nightly で更新)。pillar publish 時に都度 scrape は避ける。
- name→id マッピングも config 化(roster scrape を日次1回)。

## 成功条件

- 主力選手 pillar に年度別(複数年)+ 通算が数値入り表示、移籍履歴含む。
- 打者/投手で列が正しい。誤った過去成績を出さない(career parse を fixture + 実 NPB で verify)。
- network 負荷が許容内(キャッシュ経由)。
- targeted pytest green。

## 依存

name→id マッピングの精度(同名/表記ゆれ)。キャッシュ層の設計(insight-nightly か別 lane か)。
