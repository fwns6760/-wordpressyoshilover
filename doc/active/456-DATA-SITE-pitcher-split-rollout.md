# 456 DATA-SITE 投手 split 横展開

- **種別**: 実装 / **priority**: P1(最大の見た目改善・最安) / **effort**: S
- **親**: 443 / 設計: `doc/active/455-DATA-SITE-redesign-sitemap-wireframe-uiux.md` §13-1 / GH: #120
- **status**: READY

## 背景(深掘り 1次source)

投手 pillar は通算+直近登板の2表のみで split が全く無い。打者 pillar は split 6種+打順別を表示。原因は ETL でなく**単なる未実装**:
- `src/data_site_template_pillar.py:823` `render_pillar_html()` が `_is_pitcher()`(L509)で分岐、投手=2セクション(L841-845)/打者=10セクション(L846-858)。
- `src/data_site_query.py` に投手 split 関数が無い(`fetch_pitching_stats_season` L1510 / `fetch_recent_pitching_games` L1578 のみ)。

## ゴール

投手 pillar に split 5種を追加:**vs球団 / 本拠ビジター / 曜日別 / 月別 / 交流戦別**。指標は投手用(登板/IP/被安打/奪三振/与四球/自責/防御率/WHIP)。

## 対象

- `src/data_site_query.py`: 投手 split fetch 関数を新設(打者の `fetch_opponent_split_stats` L827 / `fetch_venue_split_stats` L1241 / `fetch_weekday_split_stats` L949 / `fetch_month_split_stats` L962 / `fetch_interleague_split_stats` L975 を雛形に、入力を `pitching_logs` JOIN `games` へ差し替え)。`pitching_logs` は既に games JOIN 済(`fetch_recent_pitching_games` L1596)。
- `src/data_site_publisher.py`: 投手分岐(L318/334付近)で新 fetch を呼び、PillarPlayerInfo に投手 split フィールド追加。
- `src/data_site_template_pillar.py`: 投手分岐(L841-845)に `_build_pitching_*_split_html` セクションを追加。投手 excerpt(L924)の誇大記述を実装と一致させる。

## やる / やらない

- やる: 上記5 split の query/dataclass/template/test。指標は投手用に適切化。
- やらない: **打順別(投手非該当)**、**イニング相当(別ticket 460系・データ要確認)**、vs左右/RISP(457)、新 ETL、打者側の変更、publish/mail/X lane。

## 成功条件

- 主力投手(戸郷/大勢/山﨑伊織)pillar に5 split が数値入りで表示。
- 登板の無い区分は行を出さない(打者 split と同挙動)。
- targeted pytest green、py_compile/AST OK、production DB copy preview で1投手分 verify。

## 依存

なし(横展開のみ)。新 ETL 不要。
