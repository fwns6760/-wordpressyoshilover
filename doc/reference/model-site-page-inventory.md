# モデルサイト ページ網羅目録(data-site 設計の土台)

作成: 2026-06-01 / 用途: yoshilover データサイト(443 系)の page IA 設計の前提資料。
方針: モデルサイトの「全ページタイプ」を先に網羅し、その後で yoshilover に載せるページを選定・追加する(設計は別 phase)。
証拠規律: 全エントリは実 WebFetch クロール根拠。取得失敗/未取得は明記。推測補完なし。

---

## モデル A: my-favorite-giants.net(巨人総合データベース型)

性格: 1936年からの**網羅・歴史アーカイブ型**。広さと年度別深度が圧倒的。鮮度は弱い(多くが 2025/10 一斉更新、年度集計中心、選手近況も不定期更新・最新1試合のみ)。
スコープ境界: `/giants_game/` `/giants_data/` = 巨人特化、`/npb/` = NPB全体、`/japan/` = 侍ジャパン、`/mlb/` = MLB日本人。

### A1. 試合日程・結果

| ページ名 | URL パターン | データ内容 | 粒度 | 更新 |
|---|---|---|---|---|
| 年度トップ(月別index) | `/giants_game/[YYYY]/top_major.htm` | 月リンク(2-11月)・結果/ロスター/NPBリンク | 年度index | 静的 |
| 月別日程 | `/giants_game/[YYYY]/[MM].htm` | 日付/曜日/対戦相手/球場/開始時刻/結果スコア | 月単位 | 試合後即時 |
| 個別試合詳細 | `/giants_game/[YYYY]/[MM]/[MMDD].htm` | 観客数/気温/試合時間/イニング別得点/両軍打撃/投手成績/メモ | 1試合 | 試合後即時 |
| 年度別結果(1軍公式戦) | `/giants_data/result_year/[YYYY].htm` | 全試合: 日付/相手/回戦/球場/勝敗/イニング別スコア/継投/安打/HR/順位(交流戦・CS・日本S含む) | 1試合(年集約) | シーズン後 |
| オープン戦結果 | `/giants_data/result_year/open/[YYYY].htm` | 日付/相手/球場/勝敗/スコア/継投/安打/HR | 1試合 | 2-3月 |
| シーズン中結果(1軍live) | `/giants_game/[YYYY]/result_major.htm` | 試合一覧(通算勝敗付き、live版) | 1試合(年集約) | 試合後即時 |
| 2軍結果(年度別) | `/giants_data/farm/result_year/[YYYY].htm` | 2軍全試合 | 1試合 | 試合後即時 |
| 交流戦成績一覧(巨人) | `/giants_data/result/inter.htm` | 年度別: 順位/勝敗/打率/HR/盗塁/防御率/優勝/GB/H・V/パ各球団別 | 年度サマリー | 不定期 |
| CS試合結果一覧(NPB) | `/npb/result/climax-series.htm` | 2004-: 年度/リーグ/上位3/各ステージ結果/日本S進出 | 年度 | 静的アーカイブ |
| 日本シリーズ結果一覧(NPB) | `/npb/result/japan-series.htm` | 1950-: セ/パ球団/各戦スコア/MVP/球場 | 年度 | 静的アーカイブ |

### A2. 選手名鑑・個人成績

| ページ名 | URL パターン | データ内容 | 粒度 | 更新 |
|---|---|---|---|---|
| 年度別個人成績トップ(索引) | `/giants_data/result_player/top.htm` | 1936-2026各年・派生へのリンク集 | 索引 | 年度追加時 |
| 年度別個人成績(1軍) | `/giants_data/result_player/[YYYY].htm` | 打者標準23列 + 投手標準24列(下記★) | 年度・選手 | シーズン中随時 |
| 交流戦個人成績 | `/giants_data/result_player/inter/[YYYY].htm` | 打者拡張(守備位置別起用)+投手拡張 | 年度 | 交流戦期 |
| CS個人成績 | `/giants_data/result_player/cms/[YYYY].htm` | 打者(守備位置含)+投手拡張 | 年度 | CS進出年のみ |
| 日本シリーズ個人成績 | `/giants_data/result_player/jps/[YYYY].htm` | 打者+投手 | 年度 | 日本S進出年のみ |
| オープン戦個人成績 | `/giants_data/result_player/open/[YYYY].htm` | 打者拡張+投手拡張 | 年度 | キャンプ〜開幕前 |
| 2軍個人成績 | `/giants_data/result_player/farm/[YYYY].htm` | 打者23列+投手22列 | 年度 | シーズン中随時 |
| 選手名鑑 | `/giants_data/member/[YYYY].htm` | 背番号/名(リンク)/年齢/身長/体重/投打/経歴/ドラフト/在籍年/備考 | 年度・選手一覧 | 年度・移籍時 |
| 選手近況 | `/giants_data/now.htm` | 背番号/名/最新試合出場/公示/備考(1-3軍) | 現役選手一覧 | ほぼ毎日 |
| 歴代在籍選手一覧 | `/giants_data/player/allplayer.htm` | 名/読み/在籍期間(数百名) | 全歴代 | 引退・入団時 |
| **個別選手プロフィール** | `/giants_data/player/playerN/{romaji}.htm` (N=1-8) | プロフィール(生年月日/身長/体重/投打/出身/ドラフト/経歴) + **年度別成績(1軍/2軍/CS/日本S/オールスター、在籍全年推移)** | 選手単位 | 成績更新時 |

★打者標準列: 試合/打席/打数/得点/安打/二塁打/三塁打/本塁打/塁打/打点/盗塁/盗塁刺/犠打/犠飛/四球/故意四球/死球/三振/併殺打/打率/出塁率/長打率/OPS
★投手標準列: 登板/勝/敗/S/H/HP/完投/無失点勝利/無四球試合/勝率/打者/投球回/被安打/被本塁打/与四球/故意四球/与死球/奪三振/暴投/ボーク/失点/自責点/防御率/WHIP
注: 個人成績テーブル内の選手名はリンクなし。選手名→プロフィールURLマッピングは名鑑/歴代一覧側から取得が必要。

### A3. ランキング・記録

| ページ名 | URL パターン | 指標 | 粒度 |
|---|---|---|---|
| 歴代通算ランキング | `/giants_data/player/lifetime/{batter|pitcher}_{m}.htm` | 打者8(試合/打数/安打/HR/打点/盗塁/三振/打率)・投手8(登板/勝/敗/S/H/投球回/奪三振/防御率) TOP100/50 | 選手通算 |
| 歴代シーズンランキング | `/giants_data/player/season/{batter|pitcher}_{m}.htm` | 同指標 TOP30 | 選手×シーズン |
| 守備位置別通算ランキング | `/giants_data/player/lifetime_position/{p_gs|p_rel|p_clo|c|1b|2b|3b|ss|of}.htm` | 投手15列/野手 打撃+失策・守備率 | 選手×ポジション |
| タイトルホルダー(打撃) | `/giants_data/title_holder/batter.htm` | 三冠王/首位打者/HR/打点/安打/盗塁/出塁率/勝利打点 | 年度 |
| タイトルホルダー(投手) | `/giants_data/title_holder/pitcher.htm` | 最優秀投手/防御率/勝率/最多勝/奪三振/中継ぎ/S/沢村賞 | 年度 |
| MVP・新人王・その他 | `/giants_data/title_holder/other.htm` | MVP/新人/カムバック/正力賞 | 年度 |
| ベストナイン | `/giants_data/title_holder/best9.htm` | ポジション別7枠(1950-) | 年度 |
| ゴールデングラブ | `/giants_data/title_holder/golden.htm` | ポジション別7枠(1972-) | 年度 |
| 歴代4番打者 | `/giants_data/player/giants4.htm` | 名/期間/試合/打数/安打/HR/打点/打率(96人) | 選手 |
| 永久欠番 | `/giants_data/player/retired_number.htm` | 背番号/名/在籍/通算成績(6名) | 選手 |
| 背番号推移 | `/giants_data/player/backnumber.htm` + `-player{1|2}.htm` | 背番号/名/使用期間 | 背番号/選手 |
| 個人シーズン球団記録 | `/npb/record/player_season/{G|cl}.htm` | 打撃/投手/守備の項目別最高記録 | 球団記録 |
| NPB個人最高記録 | `/npb/holder/{all|season|game|inning|rookie...}.htm` | 打撃/投手/守備フル | NPB記録 |
| 記録達成選手 | `/npb/{milestones/index|triple-crown|perfect-game|hit-for-the-cycle}.htm` | マイルストーン/三冠王/完全試合/サイクル | 選手 |
| 名球会・殿堂 | `/npb/history/{golden_players|baseball_hall_of_fame}.htm` | 200勝/250S/2000安打/殿堂 | 選手 |

### A4. チーム成績

| ページ名 | URL パターン | 主な列 | 粒度 |
|---|---|---|---|
| リーグ内成績(年度別順位表) | `/giants_data/result_team/[YYYY].htm` (2001-2025) | 4テーブル(対戦/交流戦/投手/打撃)約70列 | リーグ6球団横断・単年 |
| 年度別チーム成績(一覧) | `/giants_data/result/year.htm` | 西暦/和暦/監督/順位/優勝決定日/日本一/勝敗/勝率/打率/HR/盗塁/防御率/失策/MVP(1936-) | 年度別 |
| 年度別チーム勝敗成績 | `/giants_data/result/year_team.htm` | 順位/試合/勝/敗/分/勝率/差 | 年度別 |
| カード別対戦成績 | `/giants_data/result/record_against.htm` | 各球団別 勝敗(セ1950-/交流戦パ2005-) | 年度×相手 |
| 監督別通算成績 | `/giants_data/result/manager.htm` | 監督名/年数/勝敗/勝率/優勝/日本一/最高最低順位/通算(20列) | 監督別 |
| チーム投手成績 | `/giants_data/result/year_pitcher.htm` | 32列(完投/S/HP/防御率/被打率等) | 年度別 |
| チーム打撃成績 | `/giants_data/result/year_batter.htm` | 26列(塁打/盗塁成功率/OPS/出塁率等) | 年度別 |
| チーム守備成績 | `/giants_data/result/year_fielding.htm` | 守備機会/刺殺/補殺/失策/併殺/捕逸/守備率/順位 | 年度別 |
| 守備(盗塁阻止率) | `/giants_data/result/year_fielding_cs.htm` | 阻止率/企画/許盗塁/盗塁刺 + 最多/次点捕手内訳(20列) | 年度×捕手 |
| 代打成績 | `/giants_data/result/year_ph.htm` | 起用数/打数/安打/HR/打点/打率 | 年度別 |
| 交流戦チーム成績 | `/giants_data/result/inter.htm` (+pitcher/batter) | 順位/勝敗/打率/HR/防御率/パ各球団別 | 年度別 |
| CSチーム成績 | `/giants_data/result/climax_series.htm` (+pitcher/batter) | RS順位/各ステージ結果/日本S進出 | 年度×試合 |
| 日本シリーズチーム成績 | `/giants_data/result/series.htm` (+pitcher/batter/commend) | 勝敗/通算/相手/MVP/各戦スコア(2021以降未更新) | 年度×試合 |
| 球場別勝敗表 | `/giants_data/stadium/game_stadium.htm` | 球場/試合/勝敗/勝率/HR/初戦/直近 | 球場別通算 |
| 都道府県別勝敗表 | `/giants_data/stadium/game_stadium_prefectures.htm` | 48地域 勝敗 | 都道府県別 |
| 都市別勝敗表 | `/giants_data/stadium/game_stadium_city.htm` | 都市別 勝敗 + 年度別開催数 | 都市別 |
| 球場別 年度別開催数 | `/giants_data/stadium/game_{1936-1951|1952-1987|1988}.htm` | 球場×年 開催数 | 球場×年 |

### A5. ドラフト・トレード・FA・補強・契約・負傷

| ページ名 | URL パターン | データ内容 | 更新 |
|---|---|---|---|
| ドラフト指名選手一覧 | `/giants_data/draft/year.htm` | 年/区分/順位/名/守備/出身/巨人通算成績/移籍経過(1965-) | オフ集中 |
| 育成ドラフト指名一覧 | `/giants_data/draft/rearing.htm` | 育成指名+成績+支配下登録(2005-) | オフ集中 |
| ドラフト外入団一覧 | `/giants_data/draft/outside.htm` | 非指名入団+成績 | ほぼ静的 |
| 指名競合選手一覧 | `/giants_data/draft/lot.htm` | 抽選競合/結果(○×)/外れ指名(1966-) | オフ集中 |
| 契約変更(育成→支配下) | `/giants_data/draft/change.htm` | 変更日/育成番号/名/支配下番号/入団年/巡目 | 不定期随時 |
| トレード一覧 | `/giants_data/trading/all.htm` | (403で本文未取得) | 不定期 |
| 交換トレード | `/giants_data/trading/change.htm` | 日付/獲得/相手/放出/備考(1935-) | 不定期随時 |
| MLB挑戦(移籍) | `/giants_data/mlb.htm` | 選手/巨人在籍年/MLB在籍年/成績/球団 | オフ集中 |
| FA選手獲得リスト | `/giants_data/player/fa.htm` | FA年/加入/名/前所属/成績/タイトル(1993-、31名) | オフ集中 |
| FA有資格選手(登録日数) | `/giants_data/player/fa-right.htm` | 名/年齢/在籍/権利状態/必要残り日数 | 試合期+オフ |
| 負傷者リスト | `/giants_data/injured.htm` | 名/守備/日付/怪我内容/全治復帰予定/現状/経過 | 試合期・高頻度 |
| シーズンオフ補強情報 | `/giants_data/news/offnews[YYYY]-[YY].htm` | 入退団/首脳陣人事/FA動向/外国人獲得(日付別+カテゴリ別) | オフ集中・随時 |
| 1軍登録選手(公示) | `/giants_data/major/[YYYY].htm` | 登録△/抹消▼(理由含)/現登録一覧/日次履歴 | 試合期・高頻度 |
| 契約更改 | `/giants_data/contract/[YYYY].htm` | 背番号/名/当年俸/翌年俸/更改日/コメント/増減 | オフ集中 |

### A6. 2軍・3軍・女子

| ページ名 | URL パターン | データ内容 | 更新 |
|---|---|---|---|
| 2軍日程hub | `/giants_game/[YYYY]/top_farm.htm` | 月別分岐(F02-F11) | 静的 |
| 2軍試合結果 | `/giants_data/farm/result_year/[YYYY].htm` (+pre_spring/pre_autumn) | 日付/相手/回戦/球場/勝敗/スコア/継投/安打/HR | シーズン中 |
| 2軍個人成績 | `/giants_data/result_player/farm/[YYYY].htm` | 投手22列+打撃23列(OPS/WHIP含) | 速報随時 |
| 2軍年度別チーム成績 | `/giants_data/farm/result-year.htm` (+_team) | 監督/順位/日本一/勝敗/打率/HR/盗塁/防御率(1961-) | 年次 |
| 2軍タイトルホルダー | `/giants_data/farm/titleholder.htm` (+_pitcher/_batter) | 三冠王/首位打者/HR/打点/盗塁/防御率/勝利/救援 | 年次 |
| 3軍日程hub | `/giants_game/[YYYY]/top_farm3.htm` | 月別分岐(T02-T11) | 静的 |
| 3軍試合結果 | `/giants_data/farm3/result_year/[YYYY].htm` (2016-) | 日付/相手/**種別**(大学/社会人/独立等)/球場/勝敗/スコア | 試合ごと |
| 3軍個人成績 | `/giants_data/result_player/farm3/[YYYY].htm` | (リンク2016-2019のみ、近年欠落) | - |
| 女子選手名鑑 | `/giants_data/women/roster/new.htm` | 背番号/氏名/投打/年齢/在籍年(28名) | 年次 |
| 女子試合結果 | `/giants_data/women/game/[YYYY].htm` (2023-) | 日付/曜日/相手/球場/スコア/継投/安打/HR | 試合ごと |
| 女子個人成績 | `/giants_data/women/stats/[YYYY].htm` (2022-) | 投手15列+打撃24列(OPS/守備位置含) | 随時(2026未作成) |

### A7. NPB全体 / 侍ジャパン / MLB日本人 / 観戦ガイド / 球団情報

| ページ名 | URL パターン | データ内容 | 粒度 |
|---|---|---|---|
| NPB年度別順位表 | `/npb/result/standings.htm` | 全球団順位 日本一★/CS△▼(1936-) | 年×球団 |
| NPB年度別勝敗表 | `/npb/stats/regular/top.htm` + `regular_[期間].htm` | 勝/負/分/勝率/順位(年代分割6本) | 年×球団 |
| NPB対戦相手別勝敗表 | `/npb/stats/regular_against.htm` | チーム間対戦 | 球団×球団 |
| NPBチーム打撃/投手/守備 | `/npb/result/regular/{batter|pitcher|fielding}.htm` | 三部門チーム成績 | 年×球団 |
| NPB通算/シーズン個人ランキング | `/npb/player/{lifetime|season}/{batter|pitcher}_[m].htm` | 打者8/投手8 TOP100 | 選手 |
| NPBタイトル一覧 | `/npb/title/{all|mvp|rookie|best9|[year]}.htm` | MVP/新人/打8冠/投7冠/沢村賞 | 年×リーグ×賞 |
| NPB監督通算 | `/npb/result/manager/all.htm` | 監督別勝敗 | 監督 |
| NPB12球団個別 | `/npb/teams/[team].htm` | 球団別 | 球団 |
| 侍ジャパン試合結果 | `/japan/game/[YYYY].htm` (+all) | 日付/種別/相手/球場/スコア/ラウンド(2003-) | 試合 |
| 侍ジャパン代表選手 | `/japan/member/[YYYY].htm` (+all_wbc/olympic/premier12) | 位置/背番号/名/年齢/投打/所属 | 大会×選手 |
| 侍ジャパン通算個人成績 | `/japan/stats/{all|wbc|olympic|premier12}.htm` | 代表通算打撃/投手 | 選手/大会 |
| 侍ジャパン大会別/データ | `/japan/{wbc|olympic|premier12}/[YYYY].htm`, `/japan/data/{country|cleanup}.htm`, `/japan/rank.htm` | 大会結果/国別対戦/4番/世界ランク | 各単位 |
| MLB日本人打者/投手通算 | `/mlb/result_player/{batter|pitcher}.htm` | 23項目通算(60名超) | 選手通算 |
| MLB大谷本塁打 | `/mlb/result_player/homerun_ohtani.htm` | 本塁打記録 | 1本単位 |
| 観戦ガイド・チケット | `/giants_data/guide/ticket_news.htm` | 座席別価格/キャッシュレス/購入先 | 座席×球場 |
| 本拠地観戦ガイド | `/giants_data/guide/watch_guide.htm` | 住所/収容/アクセス/飲食/マナー | 球場 |
| 応援歌 | `/giants_data/guide/supportersong.htm` | 球団歌/コール/チャンステーマ/選手別歌詞(30名超) | 曲単位 |
| 球場天気 | `/giants_data/guide/weather.htm` | 球場天気 | 球場×日 |
| キャンプ情報 | `/giants_data/camp/{schedule|guide|list}.htm` | 日程/休日/練習試合/球場/軍別ロスター | 日単位 |
| 球団プロフィール | `/giants_data/teamprofile.htm` | 沿革/創立/オーナー/球場/通算成績/優勝数 | 球団 |
| 観客動員/視聴率 | `/giants_data/{audience|audience-rating}.htm` | 動員数/TV視聴率 | 年×試合 |
| 東京ドーム関連 | `/giants_data/{tokyodome-bigbord|tokyodome-memory}.htm`, `result/year_tokyodome.htm` | 受賞/メモリアル/球場別成績 | 各単位 |

### A8. IA / UX 所見(実ページ4枚精査・全取得成功)

実取得: トップ / now.htm / 個別試合 `/giants_game/2026/05/0531.htm` / 選手プロフィール `abe-shinnosuke.htm`。

- **URL が意味的・年月体系**: `/giants_game/2026/05/0531.htm`、`/giants_data/player/.../abe-shinnosuke.htm`。SEO フレンドリー。
- **title 統一**: `【カテゴリ】固有名 ～my favorite giants～`。試合=`【日付】カード○回戦試合結果詳細`、選手=`【巨人歴代選手名鑑】選手名`。検索意図(「選手名 成績」「巨人 日付 試合結果」)直撃。
- **パンくず一貫**: 下層全ページに `HOME > GIANTS > カテゴリ > … > 現在` あり。
- **試合ページに前後ナビ**(←前試合/次試合→)。連続閲覧導線あり。
- **now.htm がハブ**: 選手名→プロフィール、日付→試合 の双方向リンク + 更新日「○月○日現在(不定期更新)」明示。
- **情報密度が突出**: 選手1ページ=最大8表×24-30列、試合=4表、now=80行超。
- 弱点(我々の空白):
  - **試合ボックススコアの選手名がリンクなし**(プレーンテキスト)→ 試合↔選手の最重要内部リンクが切断。
  - **更新日表記が不統一**(now/トップは有り、個別試合・選手プロフィールは無し)。
  - **動的UIゼロ**(年度切替・検索フィルタ・ソートなし、全静的)。見たい年度/指標へ素早く到達できない。
  - **読み物価値ほぼ無し**(散文 recap/物語/分析コメント皆無、表の集積のみ)。
- マネタイズ=アフィリエイト集約(楽天/Yahoo/Amazon/JCB)、記事単位 SNS シェアなし、X+Bluesky フォロー導線のみ。
- → **AI メディア(yoshilover)の差別化空白** = (a)試合↔選手の内部リンク網、(b)生データへの文脈/物語付与、(c)更新日・ソート・年度切替の UX、(d)記事単位 SNS シェア。

### A9. 読み物・特殊コンテンツ(成績表以外、ファン訴求)

実取得確認。yoshilover が PA-level / 試合データ pipeline から派生実装しやすい順:

| ページ | URL | 切り口 |
|---|---|---|
| サヨナラ本塁打一覧 | `/giants_data/walkoff_homerun.htm` | 1941-2026 計161本、通算最多王8本、種別/対戦投手/前後スコア。SNS拡散性 非常に高 |
| 東京ドーム ビッグボード賞 | `/giants_data/tokyodome-bigbord.htm` | 看板直撃弾、方向/距離/スポンサー/賞金。唯一無二 |
| 視聴率推移 | `/giants_data/audience-rating.htm` | 1965-2009、ノスタルジー訴求 |
| 観客動員推移 | `/giants_data/audience.htm` | 1950-2025、75年トレンド+コロナ |
| 巨人vsヤンキース | `/giants_data/yankees.htm` | 日米名門対比、企画性 |
| スコアメモリアル | `/giants_game/memorial/top.htm` | 名勝負16試合アーカイブ(10.8決戦等)、1試合1ページ |
| 今更聞けないQ&A | `/giants_data/Q&A.htm` | 命名由来/マスコット 等トリビア、SEO/共有性高 |
| 応援歌 | `/giants_data/guide/supportersong.htm` | 歌詞+ドラム譜、検索需要大、選手別ページ内部リンク資産 |
| サイクルヒット | `/npb/hit-for-the-cycle.htm` | ナチュラル判定/最年長 等「付加切り口」が秀逸 |
| 三冠王/完全試合/ノーヒッター | `/npb/{triple-crown|perfect-game}.htm` | 希少記録の歴史トリビア |
| メモリアルアーチ | `/npb/memory.htm` | 「リーグ通算◯号は誰か」 |
| 球団変遷/本拠地比較 | `/npb/{team-history|stadium}.htm` | 消滅球団年表/球場スペック横比較 |

yoshilover が真似できる切り口: **サヨナラ本塁打DB / 節目HR自動検知記事 / トリビアQ&A / 観客動員・視聴率の長期トレンド読み物 / 球場別特殊集計 / 応援歌アーカイブ / 名勝負アーカイブ**。いずれも事実 literal 中心で AI 生成事故が少なく、data-focus 方針と整合。

---

## モデル B: baseballdata.jp(セイバー・条件別集計型)

性格: 「データで楽しむプロ野球」。**条件別集計(split)とセイバーメトリクス独自指標**に特化。my-favorite-giants の歴史網羅とは逆方向の深さ。年度別 2011-2026 を `/{YYYY}/` プレフィックスで遡及。巨人 = 球団ID=1(他球団 2-12,376)、リーグ `/c/`(セ)`/p/`(パ)、SABR `/sabr/`、コンテンツ `/mdata/`、交流戦 `/mm/`、選手詳細 `/playerB/{id}.html`(打者)`/playerP/{id}.html`(投手)、単試合ダッシュボード `/dashboard/{YYYYMMDD}_{id}{P|B}.html`。

global nav: ホーム / チーム(12球団) / 個人成績(打撃・投手・SABR・左右別) / 交流戦 / コンテンツ / 用語集 / 年度別 / ダッシュボード。

### B1. トップ・チーム・試合

| ページ名 | URL パターン | データ内容 | 粒度 | 年度 |
|---|---|---|---|---|
| サイトホーム(2リーグ合体順位) | `/index.html`, `/[YYYY]/index.html` | セ・パ両リーグ順位1画面: 試/勝/敗/分/率/差/防御率/打率/HR/盗/得/失/犠打/QS率/得点圏/HR-WPO打率/代打率/失策 | リーグ並列 | 2011- |
| チームトップ | `/[teamID]/index.html` | 球団の打撃集計+投手集計(本拠/ビジター/デイナイト/曜日/球場/月/打順の条件別行)※実物の並びは未確認(下記 gap) | チーム | 全年度 |
| 試合結果サマリー | `/[teamID]/GResult.html` | 月日/曜日/相手/球場/開始/スコア/区分/観客数/勝敗/順位/貯金/試合時間/先発/相先発/決勝点選手/決勝打/勝敗投手/安打/HR/盗/三振/被安打/被本/失点/自責/奪三振 ※実物未確認(下記 gap) | 1試合 | 全年度 |
| リーグ順位表 | `/c/index.html`(セ), `/p/index.html`(パ) | 順位表+打撃+投手+対戦相手別勝敗表。先発防御率/救援防御率/QS率/WHIP 等 | リーグ/チーム | 全年度 |

### B2. 個人成績ランキング

| ページ名 | URL パターン | 主な列 | 粒度 | 年度 |
|---|---|---|---|---|
| チーム/リーグ打撃ランキング | `/[teamID]/ctop.html`, `/ctop.html`(セ), `/ptop.html`(パ) | 選手/一軍/**調子/最近5試合**/打率/打点/HR/安打/単打/2B/3B/出塁率/長打率/OPS/得点圏(打数安打率)/**HR-WPO(打数安打率本)**/試合/打席/打数/得点/四球/死球/盗塁(企図成功率)/犠打/犠飛/代打/併殺/失策/三振 | 選手 | 全年度 |
| 指標別打撃ランキング(個別) | `/[teamID]/c{stat}.html`(chr/cOPS/ctkr/cst…30+) | 当該指標ソート | 選手 | 全年度 |
| チーム/リーグ投手ランキング | `/[teamID]/cptop.html`, `/cptop.html`, `/pptop.html` | 防御率/勝/敗/S/奪三振/試合/投球回/**K/9**/投球数/打者/被安打/被本/四球/死球/敬遠/失点/自責/完投/完封/無四球/被打率/**QS率/援護点率**/WHIP/HR-WPO/**最速/最低球速/球速差**/HP(33列) | 選手 | 全年度 |
| 指標別投手ランキング(個別) | `/[teamID]/c{win|save|getk|toq|qsr|whip|uppr|mxq|HP}.html` | 当該指標ソート | 選手 | 全年度 |
| 非規定打者一覧(menu名「左右別成績」※誤ラベル) | `/[teamID]/cdrm.html`, `/pdrm.html` | 打撃ランキング同列・規定打席未達 | 選手 | 全年度 |
| 交流戦個人成績 | `/mm/{c|p}top.html`, `/mm/{c|p}ptop.html` | 交流戦限定 打撃/投手 | 選手 | 2012- |

### B3. セイバーメトリクス(SABR ランキング)

打者: `/sabr/cNOI.html`(セ)`/sabr/pNOI.html`(パ)起点。指標別個別ソート `/sabr/c{GPA|IsoD|IsoP|BABIP|BBK|PAK|ABHR|SecA|TA|PS|RC|RC27|XR|XR27|XRPLUS|XRWIN}.html`。
共通列: 打率/HR/打点/**NOI/GPA/IsoD/IsoP/BABIP/BB-K/PA-K/AB-HR/SecA/TA/PS/RC/RC27/XR/XR27/XR+/XRWIN**。

投手: `/sabr/cHIDARITU.html` 起点。指標別 `/sabr/c{HISHUTU|HICHODA|HIOPS|QS|QSRITU|FIP|LOB|DIPS1|DIPS2|BB9|HR9|RSAA|WHIP}.html`。
共通列: 防御率/勝/敗/**被打率/被OBP/被SLG/被OPS/QS/QS率/FIP/LOB%/DIPS1/DIPS2/BB9/HR9/RSAA/WHIP**。
注: 各指標ページは同一表の再ソート。計算式は glossary のみ(NOI/RC/XR/BABIP/ISO/BB-K のみ散文定義、他は列名のみで式非公開)。

### B4. 独自コンテンツ(`/mdata/`)

| ページ名 | URL | 内容 | 粒度 |
|---|---|---|---|
| 得点圏被打率 | `/mdata/hidaritu.html` | 投手 被打率(規定到達/一軍の2表)+HR-WPO打者数・被安打 | 投手 |
| 直球(ストレート)被打率 | `/mdata/sthidaritu.html` | 投手 直球限定被打率(規定/一軍)+HR-WPO | 投手 |
| 得点差状況別打率 | `/mdata/TKdaritu2.html` | 打者 得点差11バケット(ビハインド5+〜リード5+/同点)別 打率/打数/安打/HR/打点/三振 | 打者 |
| 殊勲打ランキング | `/mdata/shukunda.html` | 殊勲打/決勝打/サヨナラ/逆転/1B-2B-3B-HR/打率/打点/得点圏打率 | 打者 |
| 選球眼指標(SQG) | `/mdata/SQG.html` | ボール総数/見数/判別率/ストライク総数/見逃数/空振数/スイング率/見逃率/空振率 | 打者 |
| 観客動員&試合時間 | `/mdata/doin.html` | 主催試合数/動員総数/平均最大最小動員/平均最長最短試合時間 | チーム |

### B5. 選手個別ページ(打者 `/playerB/{id}` 5枚・投手 `/playerP/{id}` 7枚)

playerID は不規則数値(例 泉口=1750321 / 坂本=700003 / 大城=1700044 / 大勢=2103697 / 戸郷=1800028 / 田中将=700069)。ランキングのリンクから取得。表示 split は出場実績のある区分のみ動的表示。

**打者(5枚):**
| 枚 | URL | 内容 |
|---|---|---|
| 詳細トップ | `/playerB/{id}.html` | 通算打撃フル + split: デー/ナイター・ホーム/ビジター・曜日別・球場別・月別・打順別(先発1-8番/途中出場)・対戦球団別・リーグ区分 |
| SABR&選球眼 | `/playerB/{id}_2.html` | NOI/GPA/IsoD/IsoP/BABIP/BB-K/PA-K/AB-HR/SecA/TA/PS/RC/RC27/XR系 + 選球眼9指標 |
| 状況別 | `/playerB/{id}_3.html` | 得点圏(ビハインド/同点/リード)・**走者状況8マトリクス**(なし〜満塁)・得点差別・**対左右投手**・**球種別安打割合** |
| カウント/イニング/打球方向 | `/playerB/{id}_4.html` | カウント別(0-0〜3-3,ファウル)・イニング別(1-12回)・**打球方向別打率**(左中右/内野安) |
| 対戦成績 | `/playerB/{id}_5.html` | **対個別投手別**(投手名/球団/率/打席/打数/安打/HR/打点/三振…) |

**投手(7枚):**
| 枚 | URL | 内容 |
|---|---|---|
| 詳細トップ | `/playerP/{id}.html` | 投手成績33列 + split: **先発/救援**・デー/ナイター・ホーム/ビジター・曜日・球場・対戦球団・月・交流戦/AS後 |
| SABR | `/playerP/{id}_2.html` | 被打率/被OBP/被SLG/被OPS/QS/QS率/FIP/LOB%/DIPS1/DIPS2/BB9/HR9/RSAA/WHIP |
| 状況別 | `/playerP/{id}_3.html` | 得点圏被打率(通算/リード時)・**走者8×得点状況3マトリクス**・**対左右打者別**・登板試合打者成績 |
| カウント別・球種別 | `/playerP/{id}_4.html` | **球種別**(ストレート/フォーク/スライダー…被打率/空振率/見逃率)・カウント別球種配分&成績 |
| 対戦成績 | `/playerP/{id}_5.html` | 対戦球団別→**対個別打者** |
| 全投球成績 | `/playerP/{id}S1.html` | 1登板1行ログ(日付/場所/相手/投球回/球数/被安打/奪三振/失点/WHIP/最高最低球速) |
| コース別(ゾーン別) | `/playerP/{id}_course.html` | **9ゾーン strike zone別**(打数-被安打/被打率/被本/奪三振)×(通算/対右/対左) |

### B6. ダッシュボード(日次・pitch-level)

日別一覧 `/dashboard.html`(投手)/`/dashboard2.html`(打者)から各試合の登板投手・出場打者ごとに1ページ。日次更新(一覧が 2026-03-31〜前日まで連続網羅、で実確認)。

| ページ名 | URL | 内容(実取得確認済) | 粒度 |
|---|---|---|---|
| 投手 単試合ダッシュボード | `/dashboard/{YYYYMMDD}_{id}P.html` | 基本情報/当日成績(空振率/見逃率/ストライク/ボール/ファウル/得点圏被打率)/**配球チャート×3(対右・対左・結果別、●で1球ずつゾーン配置)**/球種別詳細(球数・平均/MAX/MIN球速・空振率・見逃率・打球種別ゴロフライライナー・被安打)/**ゾーン別成績(9分割×対右対左、投球割合%・被打率・本・K)**/年度別 | 選手×1試合 |
| 打者 単試合ダッシュボード | `/dashboard/{YYYYMMDD}_{id}B.html` | 当日成績30列超/**打席ごとの配球シーケンス表(投球数・球種・球速km/h・結果)**/カウント推移/球種別詳細/**ゾーン別成績(9分割)**/年度別 | 選手×1試合 |
| 用語集 | `/glossary.html` | 全指標の散文定義(式は NOI/RC/XR/BABIP/ISO/BB-K 等一部のみ)。列=用語/略号/分類/定義 | — |

### B7. baseballdata.jp の独自切り口(my-favorite-giants に無い)

1. **HR-WPO**(独自フラッグシップ): 本塁打の勝敗影響が大きい打席機会を整理、全指標に併設カラム
2. **選球眼指標 SQG**: 投球単位の ball判別率/スイング率/見逃率/空振率(pitch-tracking 粒度)
3. **得点差状況別打率**: ビハインド〜リードの得点差別打撃傾向
4. **殊勲打ランキング**: 決勝打/サヨナラ/逆転をクラッチ集計
5. **直球被打率**: 球種限定の被打率
6. **単試合ダッシュボード**: 配球チャート/球種別球速/ゾーン別成績の **Statcast 的 pitch-level を日次無料**
7. **SABR指標別個別ページ**: NOI/GPA/Iso/SecA/TA/RC/XR系/FIP/DIPS/RSAA/LOB%
8. **観客動員+試合時間ランキング**
9. **「調子」「最近5試合」列**: 個人成績一覧に直近トレンド常設(= yoshilover 鮮度方向と同発想)

### B8. ★pitch-level の再現可能性(insight.db 検査・重要)

baseballdata.jp ダッシュボードの中核(1球ごとの球種・球速・ゾーン座標)は **yoshilover の現 insight.db では再現不可**。
- `at_bat_details` の列 = `game_id, inning_no, half, team, pa_index, outs, runner_state, batter, count_balls, count_strikes, result_text, current_pitcher, source_url, ingested_at`。取得元 = NPB `playbyplay.html` = **PA(打席)単位**。
- 球速/球種/コース/velocity/pitch_type の参照は parser に **0件**(grep 確認)。
- → 現スキーマは PA-level 止まり。baseballdata.jp 相当は **pitch-by-pitch トラッキング別ソース + 新テーブル(pitch_details: game_id, pa_key, pitch_no, pitch_type, velocity, zone_x/y, result)** が必要で、現スキーマ拡張だけでは賄えない。
- 設計含意: pitch-level は yoshilover の射程外(別 source 課金/契約が要る領域)。**深追いしない**。我々が取りに行くべきは PA-level で出せる split(打順別/vs球団/イニング別/得点差別/走者状況/対左右/球場別)に留める。

### B9. ★この巡で確認できなかった gap(silent skip しない)

origin が精査中 502/timeout を断続返し、以下は **未確認**(推測補完しない):
- 打者/投手 選手詳細ページの **実物のセクション並び順 / 5枚・7枚タブの遷移導線 / SEO title・見出しパターン**
- **「調子」インジケータの実表現**(色/記号/数値のどれか)
- チームトップ `/[teamID]/index.html` の **条件別集計の実並び**
- 試合結果 `/[teamID]/GResult.html` の実レイアウト
- 選手個別サブページ `_3`/`_4`/`_course` の実データ値(一部 timeout)
- SABR 指標別個別ページ ~29 本の各表内容(href は確認、本体は代表1-2枚のみ展開)
→ 設計確定前に必要なら、origin 回復後に `/playerB/700003.html`(坂本)→ `/playerP/{id}`→ `/1/index.html`→ `/1/GResult.html` の順で 1 枚ずつ再取得して埋める。

---

## 集計

- モデル A(my-favorite-giants): 7領域 / 約 90 ページタイプ。歴史・網羅・年度別が圧倒的、鮮度弱い。
- モデル B(baseballdata.jp): 条件別集計 + セイバー独自指標が圧倒的、深さ特化。
- yoshilover の現状(443/444/447): 当季のみ・選手31名・直近5試合+一部split。**A の網羅 / B の split深度 の両方に対して薄い**。

## 設計 phase で決めること(本目録の次段)

1. A の全ページのうち yoshilover に載せる範囲の選定(table stakes / 鮮度 / 独自 の3層配置)
2. B の split・セイバー指標のうち既存 insight.db で出せるものの map(evidence-only)
3. yoshilover 固有ページ(記事連携 / X導線 / ファンコンテンツ)の追加
4. データ可用性ギャップ(プロフィール source / 年度別履歴 backfill / standings ETL)の phase 化
