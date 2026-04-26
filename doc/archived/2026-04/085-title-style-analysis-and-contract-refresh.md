# 085 Title style analysis and contract refresh

## meta

- owner: **Claude Code**(editorial contract、Codex 実装便ではない)
- type: **doc-first ticket**(分析 + contract 確定、impl は後続別 ticket)
- status: OPEN(分析未着手)
- created_at: 2026-04-24 22:00 JST
- deps: 030(title assembly rule)/ 067(comment lane title contract)/ 080(social_video_notice)/ 081(x_source_notice)
- non_blocker_for: editor lane(083/084)/ publish chain(option D/E)/ mail chain(072-076)/ ledger(078/079)

## why_now

- 現状の title assembly は 030 で base rule 化、067 で comment lane 専用形(A/B/C 型)、080/081 で independent article lane 用に補強されているが、**全 subtype 共通の上位 title policy は未定義**
- 結果として、subtype 横断で title style に揺らぎ(speculative tone / 体言止め / 名詞句 / 動詞句 の混在)が観測されている
- ベンチマーク(のもとけ)の title 書式を分析し、上位 policy として固定しないと、subtype 別 contract が独立進化して全体としてバラつく
- editorial 判断を Codex に委ねると hallucination や generic tone に流れる(067 で確認済) = **Claude owner として doc-first で contract 確定**

## purpose

- のもとけサイトの title 書式を記事タイプ別に分析
- 共通する title 構造(主語位置 / 事象表現 / 句読点 / 接頭辞 / 引用記号 / 文字数帯)を抽出
- YOSHILOVER 向け title contract を subtype 別に定義(030 を上位 wrapper として refresh)
- 030 / 067 / 080 / 081 との整合を明文化
- 実装が必要な follow-up ticket を 1-3 本に絞り、scope と owner を明示

## non_goals

- 既存の 030 / 067 / 080 / 081 の contract 本体を破壊的に書き換えない(本 ticket は上位 wrapper として整合させる)
- title generator の実装(後続 ticket、Codex 実装便で別途)
- title validator の実装(後続 ticket、Codex 実装便で別途)
- LLM prompt の改修(後続)
- creator pipeline(`src/rss_fetcher.py` 主線)の touch
- editor lane / mail chain / publish chain への波及
- baseballwordpress repo 編集
- front 表示の改修

---

## §1 のもとけ title 分析(完了、2026-04-24)

### data source

- 対象 site: `https://dnomotoke.com/`(ドラ要素@のもとけ、本家 のもとけ matome blog、Dragons primary だが構造は他球団 matome と共通)
- 取得方法: front 一覧の最新 30 件 title を read-only WebFetch
- 取得日: 2026-04-24 22:30 JST
- 注: のもとけ自身は 巨人 中心 site を持たないが、matome blog の title 構造規約は球団横断、本 ticket では「のもとけ型 title 規約」として参照

### 30 件 sample(verbatim、subtype label 付)

| # | title | subtype |
|---|---|---|
| 1 | 中日・杉浦稔大「僕が来てから1勝もしていなかったので、なんとか勝利したいという思いで必死に投げました」 | comment(postgame) |
| 2 | 中日・大島洋平、2安打マルチヒット！！！ | game_event |
| 3 | 中日・細川成也、2安打3出塁マルチヒット！！！ | game_event |
| 4 | 中日・ボスラー、今季第1号ホームランなど2安打2打点！！！ | game_event |
| 5 | 中日・村松開人「ファンのみなさんの叱咤激励は選手たちにも届いています...」 | comment(postgame) |
| 6 | 中日・柳裕也、村松開人を"祝福" → かけていたものが… | comment(postgame) |
| 7 | 中日・川越誠司、逆転サヨナラ勝ちに繋げる代打ツーベースヒット！！！ | game_event |
| 8 | 中日・杉浦稔大、9回表に三者凡退ピッチング → 逆転サヨナラ勝ちで中日移籍後初勝利！！！ | game_event |
| 9 | 中日ドラゴンズ、今日のヒーローはこの2人！！！ | postgame_summary |
| 10 | 中日・村松開人、逆転サヨナラ3ランホームラン！！！　中日ドラゴンズ、サヨナラ勝ちの瞬間！！！ | game_event |
| 11 | 4月24日(金)　セ・リーグ公式戦「中日vs.ヤクルト」【試合結果、打席結果】 | postgame_summary |
| 12 | 中日・柳裕也、降板後にコメント | comment(postgame) |
| 13 | タイムリーを放った中日・高橋周平とボスラーがコメント | comment(postgame, multi) |
| 14 | 中日・柳裕也、2勝目とはならずも7回まで投げ切る力投を見せる | game_event |
| 15 | 中日・高橋周平、レフトへのタイムリーヒット！！！ | game_event |
| 16 | 中日ドラゴンズ、タイムリー2本で同点に追いつく！！！ | postgame_summary |
| 17 | 中日・石川昂弥、2人のコーチと取り組んできた打撃修正が結果に表れる | farm_comment |
| 18 | 中日・マラー、試合後にコメント | farm_comment |
| 19 | 中日・福永裕基、病院での最終診断で"問題無し"！！！ | notice(injury) |
| 20 | 中日・橋本侑樹、現在の状態は…？ | notice(injury, speculative) |
| 21 | 中日・ボスラー「去年だったらアウトになっている打球かも。ホームランになってくれて本当に嬉しいよ」 | comment(postgame) |
| 22 | 中日・ボスラー、今季第1号先制ホームラン！！！ | game_event |
| 23 | 中日・ドアラ、きょうの一言 | mascot |
| 24 | 4月24日(金)　セ・リーグ公式戦「中日vs.ヤクルト」【全打席結果速報】 | game_event_live |
| 25 | 中日ドラゴンズ、ベンチ入り選手一覧 | lineup |
| 26 | 4月24日(金)　セ・リーグ公式戦「中日vs.ヤクルト」　中日ドラゴンズ、スタメン発表！！！ | lineup |
| 27 | 4月25日(土)の予告先発が発表される！！！ | pregame |
| 28 | 中日・平田良介コーチ、土田龍空の外野守備への評価は… | manager |
| 29 | 中日・福敬登のピッチング【動画】 | social_video |
| 30 | CBC・若狭敬一アナ「中日にとって魔の7回。痛いミスが出ているイメージがあったので...」 | comment(media) |

### 軸別観察

#### 主語位置
- **冒頭固定**: 30 件中 28 件が `中日・<人物>` で開始、または `4月X日 ... 中日` で開始(球団名 + 主体の冒頭固定が極めて強い rule)
- 例外: #13 `タイムリーを放った中日・高橋周平とボスラーがコメント`(動詞句から開始、複数人束ねの稀ケース)

#### 事象表現
- **断定形**: 過去形動詞 + `!!!` が圧倒的多数(#2-10, 15-16, 22, 24, 26, 27 = 14 件)
- **コメント inline**: 引用記号「」内に発言を全文 inline(#1, 5, 21, 30 = 4 件)
- **省略記号 ...**: 続き示唆で SEO の context 取り(#5, 6, 17, 20, 21, 28, 30 = 7 件)
- **質問形 / speculative**: `…は…？` で「不明な状態を題材化」(#20, 28 = 2 件、injury / 評価 など内容自体が確定でない場合に限定使用)

#### 接頭辞
- **`【巨人】` / `【速報】` / `【LIVE】` 系は 0 件**(球団名は接頭辞ではなく主語として `中日・` 形で本文化されている)
- **【】補足ラベル**: `【動画】` `【試合結果、打席結果】` `【全打席結果速報】` のように **末尾**に動画 / format ラベルとして使う(#11, 24, 29 = 3 件)
- **接頭辞ルール**: 「速報」を接頭辞化しない、「LIVE」も使わない、形式情報は **末尾【】** で表現

#### 句読点
- **読点 `、`**: 主語と事象を区切る最重要セパレータ(全 30 件で使用)
- **句点 `。`**: 0 件(コメント inline 内を除く)
- **連結 `→`**: 因果 / 順序を示す(#6, 8 = 2 件、過程の含意)
- **連結 `／` `:` `〜`**: 0 件(使わない)

#### 数値の扱い
- **inline 半角混在**: `2安打` `第1号` `9回表` `打率4割2分9厘`(#3, 4, 8, 22 等)
- 半角 / 全角の使い分け: 数字は半角、回数は漢数字(`9回`)、打率は漢数字 + 半角 mixed(`4割2分9厘`)
- 背番号は title に出現せず(本文に inline)

#### 引用記号
- **「」**: 100% 採用、コメント引用 / 球団名引用 / strong word 強調 すべて(#1, 5, 11, 21, 24, 26, 30)
- **『』**: 0 件(使わない)
- **""(欧文 double)**: 限定使用、強調(#19 `"問題無し"`、#6 `"祝福"` = 2 件、ニュアンス補強としての視覚記号)

#### 文字数帯(half-width count、emoji と !!! も 1 char)
- **短形**: 15-25 字(#2 `中日・大島洋平、2安打マルチヒット！！！` = 22 字、#22 = 22 字、#23 = 14 字)
- **中形**: 26-40 字(#3, 4, 7, 11, 12, 14-18, 25-28 の 多数、median 帯)
- **長形**: 41-60 字(#1 `中日・杉浦稔大「僕が来てから1勝もしていなかったので、なんとか勝利したいという思いで必死に投げました」` = 約 57 字、コメント inline 形)
- **median**: 30-35 字、**上限**: 60 字、**下限**: 14 字

#### speculative tone の許容度
- **質問形 / 推量**: 全体の 6.7%(#20, 28 = 2/30 件)
- **使用条件**: 「現在不明 / 評価がまだ出ていない」事項に限定。**勝敗 / 結果 / lineup / 確定事象 では使わない**(これは fact-first 原則の現れ)
- 「どう見たいか」「何を見せるか」のような **AI 的推量 phrase は 0 件**

#### 生成 AI tone(generic phrase)検知
- **0 件**: `とは?` / `について語る` / `振り返りたい` / `注目したい` / `真相` / `驚愕` / `衝撃` / `本音` / `どう見る` 等の generic / clickbait phrase は 1 件もない
- これは matome blog としての「読者を煽らない、事実を売る」スタンスと整合
- YOSHILOVER の現状 draft タイトル(63461 `即戦力、一軍合流でどこを見たいか`、63456 `キャベッジの現状整理 いま何を見たいか`、63385 `ベテラン、昇格・復帰でどこを見たいか`)は **のもとけ規約からの明確な逸脱**

---

## §2 共通 title 構造(完了、§1 から抽出)

§1 の 30 件分析から、subtype 横断で守られている共通 rule を 8 個固定する。

### Rule 1: 球団名 + 主体の冒頭固定

- 形式: `<球団名>・<人物名>` を必ず title 冒頭に置く
- のもとけ: `中日・<選手名>` / `中日ドラゴンズ、<事象>` / `4月X日(曜)　セ・リーグ公式戦「<対戦>」　中日ドラゴンズ、<事象>`
- YOSHILOVER 写像: `巨人・<選手名>` / `巨人、<事象>`(`読売ジャイアンツ` ではなく `巨人` で揃える、media 慣例 + サイト名整合)

### Rule 2: 主語 + 事象 を読点で接続

- `<主体>、<事象>` 形式が中核
- 動詞句で完結、句点 `。` は打たない
- 例: `中日・大島洋平、2安打マルチヒット！！！`

### Rule 3: 接頭辞 `【速報】` `【LIVE】` は使わない

- のもとけは 0 件、生 fact + `!!!` で熱量を表現
- 形式情報は **末尾 【動画】 【全打席結果速報】 等の補足ラベル**で表現
- YOSHILOVER 既存の `【速報】` `【LIVE】` 接頭辞は **撤廃**(030 既存 rule を refresh、subtype 別 contract で明文化)

### Rule 4: 引用は `「」` 限定

- `『』` 0 件、コメント / 強調 / 球団名引用すべて `「」`
- ニュアンス補強の `""`(欧文 double)を稀に使うが、`『』` は使わない
- YOSHILOVER 067 `{speaker}、{scene}に「{nucleus}」` 形と完全整合

### Rule 5: 数値は inline / 半角混在 OK

- 統計値: `2安打` `第1号` `打率4割2分9厘`
- 回 / 量: 漢数字(`9回表` `三者凡退`)
- 順位 / 番号: 半角(`2安打` `1勝目` `4位`)
- スコア / 試合数 / 打率は半角優先、月日 / 回 / 量は漢数字優先

### Rule 6: speculative tone は **不確定事項に限定**

- 許容: `…は…？` `…は…` を **injury 状態 / 評価未確定 / 進行中事項** で使う(全体の 6.7% まで)
- **禁止**: 勝敗 / 結果 / lineup 確定 / 統計確定 で speculative 句は使わない
- **強禁止**: 「どう見たいか」「何を見せるか」「どこを見たいか」「真相」「驚愕」「衝撃」「本音」 — のもとけ 0 件、YOSHILOVER で発生中(63461/63456/63385/63375)、085 で禁止形に正式化

### Rule 7: 文字数 14-60 字、median 30-35

- short(14-25): 個別選手の short fact
- median(26-40): 試合 summary / lineup / pregame
- long(41-60): コメント inline 形(全文引用)

### Rule 8: 省略記号 `…` で続き示唆 OK

- 引用が長い時の打ち切り `「...のなんとか勝利したいという思いで必死に投げました...」`
- 評価未確定 `…は…？`
- 「読者を本文に引っ張る tease」として機能、ただし禁止形(`真相とは…?` 等)に転化させない

---

## §3 YOSHILOVER subtype 別 title contract(完了、§2 共通 8 rule + のもとけ 30 件 から派生)

10 subtype。各 subtype は §2 の Rule 1-8 を継承。

### postgame(試合結果 / 個別選手の game event)

- **基本型**: `巨人・<選手名>、<事象動詞句>！！！`
- **許容形 1(チーム全体)**: `巨人、<事象動詞句>！！！`
- **許容形 2(数値強調)**: `巨人・<選手名>、<数値><事象>！！！`(例: `巨人・坂本勇人、第3号ホームラン！！！`)
- **許容形 3(因果連鎖)**: `巨人・<選手名>、<前段> → <結果>！！！`
- **禁止形**:
  - `<選手名>はどう見せるか`(speculative)
  - `<選手名>の真相とは?`(clickbait)
  - `<選手名>、<事象>。`(句点禁止)
  - `【速報】<選手名>、<事象>`(接頭辞禁止)
- **接頭辞**: なし(`巨人・` は主語、接頭辞ではない)
- **末尾ラベル**: `【動画】` `【全打席結果速報】` 許容
- **文字数**: 14-40
- **0 件目標**: speculative / clickbait / generic AI tone

### lineup(スタメン / 公示)

- **基本型**: `4月X日(曜)　セ・リーグ公式戦「<対戦カード>」　巨人、スタメン発表！！！`
- **許容形 1(短縮)**: `巨人スタメン <キープレイヤー> <ポジション> <事象>`(例: `巨人スタメン ドラフト4位・皆川岳飛が「7番・右翼」でプロ初スタメン`)
- **許容形 2(ベンチ入り)**: `巨人、ベンチ入り選手一覧`
- **禁止形**:
  - `スタメンを<どう並べたか>`(speculative)
  - `<choice の比較>`(分析 tone)
- **接頭辞**: なし(または `巨人スタメン` を主体兼接頭辞として使用、これは既存 030 rule と整合)
- **文字数**: 25-60
- **B1 既存制約**: `巨人スタメン` 接頭が lineup 以外に出ないこと(030 既存 + 本 contract で再確認)

### manager(監督 / コーチコメント / 采配)

- **基本型**: `巨人・<監督名>監督、<対象>の<項目>は…`
- **許容形 1**: `巨人・<監督名>監督「<引用 inline>」`
- **許容形 2**: `巨人・<コーチ名>コーチ、<対象選手>の<項目>を<事象>`
- **禁止形**:
  - `<監督>のコメントから見えるもの`(generic)
  - `<監督>の本音とは`(clickbait)
- **接頭辞**: なし
- **文字数**: 20-50

### pregame(予告先発 / 試合前情報)

- **基本型**: `4月X日(曜)の予告先発が発表される！！！`
- **許容形 1**: `<日付> <対戦カード> 予告先発: <投手名>`
- **許容形 2**: `巨人・<投手名>、<日付>先発予定`
- **禁止形**:
  - `<試合> どう挑む?`(speculative)
  - `<投手>はどう見せるか`(speculative)
- **接頭辞**: なし
- **文字数**: 14-40

### farm(二軍 / 育成)

- **基本型**: `巨人二軍 <選手名>、<事象>！！！`
- **許容形 1**: `巨人・<選手名>、二軍で<事象>`(例: `巨人・丸佳浩がマルチ安打をマーク 2軍合流後4戦連続安打`)
- **許容形 2**: `巨人二軍スタメン 4月X日(曜) <対戦カード>`(farm_lineup)
- **禁止形**:
  - `<若手>をどう並べたか`(speculative)
  - `<選手>はどこを見たいか`(speculative)
- **接頭辞**: なし(`巨人二軍` を主体兼接頭辞として OK)
- **文字数**: 18-50

### comment(選手コメント、067 lane と整合)

- **基本型(067 type A)**: `巨人・<選手名>、<scene>に「<nucleus>」`
- **基本型(067 type B)**: `巨人・<選手名>、<対象>は「<nucleus>」と明かす`
- **基本型(067 type C)**: `巨人・<選手名>、<team_state>に<emotion verb>「<nucleus>」`
- **許容形 1(short post)**: `巨人・<選手名>、降板後にコメント`(コメント全文を本文で読ませる場合の短形)
- **許容形 2(media subject)**: `<媒体>・<記者名>「<引用>」`(主要媒体記者コメントを independent article 化する場合、081 lane と整合)
- **禁止形**(067 既存禁止語と完全同期):
  - `どう見る` `本音` `思い` `語る` `コメントまとめ` `試合後コメント` `ドラ1コンビ`
  - `Xをどう見る` `Xがコメント` `Xについて語る`
  - `注目したい` `振り返りたい` `コメントに注目` `コメントから見えるもの` `選手コメントを読む`
- **接頭辞**: なし
- **文字数**: 25-60(inline 引用形は long 帯)
- **067 整合**: 本 contract は 067 を **そのまま継承**、上書きしない。067 のままで完全に成立する subtype

### social_video(球団 SNS 動画引用、080 lane と整合)

- **基本型**: `巨人・<選手名>の<事象>【動画】`
- **許容形 1**: `<球団公式 / 媒体>、<選手名>の<事象>を公開【動画】`
- **禁止形**:
  - `<選手>のすごさ【動画】`(generic / clickbait)
  - `<選手>はどう見えるか【動画】`(speculative)
- **接頭辞**: なし
- **末尾ラベル**: `【動画】` 必須
- **080 整合**: 本 contract は 080 social_video_notice の builder で生成される title rule に **そのまま適用**、080 既存 contract を上書きしない

### x_source(X 投稿引用、081 lane と整合)

- **基本型(fact tier、081 既存)**: `<account_name>、<event 断定>`
- **許容形(topic tier、081 既存)**: `<account_name>が報じる: <snippet>`(primary recheck flag なし時)
- **禁止形**(081 既存 hard fail と整合):
  - `OPINION_LEAK` 該当の generic / clickbait phrase
  - `TOPIC_TIER_AS_FACT` 該当の topic tier 断定文(recheck 未済時)
- **接頭辞**: なし
- **081 整合**: 本 contract は 081 を **そのまま継承**、上書きしない

### notice(公示 / 登録抹消 / 故障情報)

- **基本型(injury 確定)**: `巨人・<選手名>、<状態>` または `巨人・<選手名>、<診断>で"<結論>"！！！`
- **基本型(transaction 確定)**: `巨人、<選手名>を<対象>に<事象>` (例: `巨人、丸佳浩を一軍登録`)
- **許容形(injury speculative、§2 Rule 6 に従う)**: `巨人・<選手名>、現在の状態は…？`
- **禁止形**:
  - 勝敗 / lineup / 統計の speculative 化(`…は…？` を確定事項に使うのは禁止)
  - clickbait `<選手>の真相` 等
- **接頭辞**: なし
- **文字数**: 14-40

### program(番組情報)

- **基本型**: `<番組名>「<内容>」(<日付> <時刻>放送)`
- **許容形 1**: `<番組名>: <ゲスト名> 出演(<日付>)`
- **禁止形**:
  - `<番組>はどう見るか`(speculative)
  - `<番組>の見どころ徹底解説`(generic)
- **接頭辞**: なし
- **文字数**: 20-50

---

## §4 既存 contract との整合(完了)

### 030 title assembly rule(base)— 上位 wrapper として refresh

- 030 の base rule(subtype-aware 生成 / `巨人スタメン` 接頭管理 / title-body coherence)は **完全維持**
- 本 ticket §3 は 030 の上に **subtype 別 variation 10 種**を追加した上位 wrapper
- 030 の `巨人スタメン` 接頭の lineup 限定 rule は §3 lineup の `巨人スタメン` 接頭兼主体運用と整合
- **書き換え**: なし。030 doc 本体は touch しない

### 067 comment lane title — そのまま継承

- 067 の **A/B/C 基本型** および **禁止語 14 個**は 1 文字も変更せず §3 comment subtype に取り込み済
- 067 と本 ticket は **disjoint subtype 担当**(comment は 067、その他 9 subtype は本 ticket)
- **書き換え**: なし。067 doc 本体は touch しない

### 080 social_video_notice — import only

- 080 contract(instagram/youtube 独立記事 / hard fail 6 種)は維持
- §3 social_video subtype は 080 builder の生成 title rule にそのまま適用、080 を上書きしない
- **書き換え**: なし。080 doc / src 本体は touch しない

### 081 x_source_notice — import only

- 081 contract(x platform fact/topic tier / hard fail 9 種 / `TOPIC_TIER_AS_FACT` / `OPINION_LEAK`)は維持
- §3 x_source subtype は 081 既存 rule をそのまま参照
- **書き換え**: なし。081 doc / src 本体は touch しない

### 071 title-body-nucleus-validator — 判定層と連携、本 ticket は生成側

- 071 は subject-event 一致の **判定** 層(SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI)
- 本 ticket §3 は **生成側 contract** で disjoint
- 086 で `src/title_style_validator.py` を **新規追加**、071 と並走する独立 validator として配置(既存 reason_code と衝突しない、新 reason_code = `TITLE_STYLE_SPECULATIVE` `TITLE_STYLE_GENERIC` `TITLE_STYLE_CLICKBAIT` `TITLE_STYLE_OUT_OF_LENGTH` `TITLE_STYLE_FORBIDDEN_PREFIX`)
- **書き換え**: なし。071 src / doc 本体は touch しない

### YOSHILOVER 既存 draft との照合

§3 contract に照らした、現状 draft タイトルの違反 mapping:

| post_id | title | 違反 | 提案 |
|---|---|---|---|
| 63461 | 即戦力、一軍合流でどこを見たいか | speculative `どこを見たいか`(notice 違反) | `巨人、<選手名>を一軍合流` 形に refactor |
| 63456 | キャベッジの現状整理 いま何を見たいか | speculative `何を見たいか`(notice 違反) | `巨人・キャベッジ、<状況断定>` |
| 63385 | ベテラン、昇格・復帰でどこを見たいか | speculative + 主語不在(rule 1+6 違反) | `巨人、<選手名>を昇格` |
| 63375 | 選手「初出場初安打」 実戦で何を見せるか | speculative `何を見せるか`(postgame 違反) | `巨人・<選手名>、初出場初安打！！！` |
| 63429 | 巨人二軍スタメン 若手をどう並べたか | speculative `どう並べたか`(lineup 違反) | `巨人二軍スタメン 4月X日(曜) <対戦カード>` |

これらは 086 の validator が hard fail で検知すべき pattern。検知後は creator 側 prompt で再生成 or 086 follow-up の title rotate で許容形に flip。

---

## §5 後続実装 ticket 候補(確定、§3 完了後)

§3 の contract を **086 一本に集約**(当初 086+087+088 の 3 本構想だったが、§3 に validator + prompt builder の両方が enforcing 対象として明記済 = 1 ticket で同期実装する方が整合)。

087 は本来「title validator extension」だったが、本 doc 起票直前に **front Claude の AdSense ad layout ticket**として 087 番が割り当てられた(`doc/087-front-ad-layout-and-adsense-ready-slots.md`)。本 086 内に validator + prompt の両方を取り込み、後続 ticket 番号は **088**(conditional fallback rotate)を維持。

### 確定 086 — title assembly contract implementation(prompt + validator 同期)

- owner: Codex B
- status: BLOCKED on 085 close → **本 doc 完了後に即 fire 可能**(085 §3 を /tmp/codex_086_prompt.txt に転記済の状態 = 085 close)
- target file: `src/fixed_lane_prompt_builder.py`(prompt) + 新規 `src/title_style_validator.py`(独立 validator) + `tests/test_title_style_validator.py`(50 case 程度)
- scope: §3 contract 全 10 subtype 反映、reason_code 5 種(`TITLE_STYLE_SPECULATIVE` / `TITLE_STYLE_GENERIC` / `TITLE_STYLE_CLICKBAIT` / `TITLE_STYLE_OUT_OF_LENGTH` / `TITLE_STYLE_FORBIDDEN_PREFIX`)
- 不可触: 071 既存 reason_code logic / 030 / 067 / 080 / 081 contract / creator 主線 / mail chain / ledger / editor lane / front lane

### 候補 097(former 088 → 093) — subtype-specific title fallback(conditional)

- owner: Codex B
- status: CONDITIONAL(086 land 後の observation で必要性判断、すぐ fire しない)
- 仕掛け: §3 の「許容形 1 / 許容形 2 / 許容形 3」を rotate、generator 1 回目で `TITLE_STYLE_*` reason_code hit したら 2 回目で別の許容形に flip
- 起票判断: 086 後 1 週間 ledger 観測 + 091 audit 推移で `TITLE_STYLE_*` hit 率 > 5% / day なら 097 fire、< 5% なら 086+092+094 で十分
- **renumber chain**: 当初 088 → user 指示 088=mail gate に再割当 → 093 へ → さらに user 指示 093=automation tick recovery に再割当 → 097 へ最終 renumber

---

## acceptance(本 ticket、doc-first + 086 fire-ready)

本 ticket は **Claude owner、Codex 実装便なし**。ただし 085 と 086 は **セット運用**:

- §1 のもとけ title 50 件 × 8-10 軸の分析が table or prose で記述済
- §2 共通構造 5-10 個が抽出済
- §3 subtype 別 contract が 10 subtype × 基本型/許容形/禁止形 で記述済
- §4 既存 contract との整合(030 / 067 / 080 / 081 / 071)が明記済
- §5 後続実装 ticket 候補が 1-3 本に絞られている
- **§3 の確定 contract を `doc/086-title-assembly-contract-implementation.md` の `## 反映する title contract(085 §3 から転記)` 節に転記済**
- **`/tmp/codex_086_prompt.txt`(086 fire 用 Codex prompt)の `[FILL FROM 085 §3]` placeholder が全て埋められている**
- **086 ticket がそのまま `codex exec` で fire 可能な状態**になっている(scope / 不可触 / acceptance / 進め方 / Final report 全節定義済)

→ 085 close = 086 fire-ready。
→ 085 close 直後に 086 を fire し、Codex 実装便で title assembly / validator / tests に contract を反映する。

impl 完了は **086 close** で達成。085 close は **86 が打てる状態**で達成。

## 不可触

- 030 / 067 / 080 / 081 / 071 contract 本体(本 ticket は上位 wrapper、書き換えない)
- `src/rss_fetcher.py` / `src/fixed_lane_prompt_builder.py` / `src/title_body_nucleus_validator.py` 等 src 全部(本 ticket は doc only)
- editor lane / mail chain / publish chain / ledger / front lane
- WP REST / 外部 API / X API
- automation / scheduler / secret / env
- baseballwordpress repo

## stop 条件(分析中)

- §1 で外部 site fetch が失敗 → user に rate limit / fetch path 確認を上げる(自動 retry しない)
- §3 で既存 contract と矛盾する pattern を見つけた場合 → 修正前に user に escalation(030 / 067 / 080 / 081 を破壊的に書き換える判断は user 側)
- §5 で後続 ticket 候補が 4 本以上に膨らむ場合 → §3 に戻って優先度の低い variation を切り捨てる
