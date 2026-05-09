# 2026-05-09 本文情報量の改善 調査

## 1. 今回の目的

- 現在の記事本文がどこで生成されているかを特定する。
- 「本文情報量の改善」だけを目的に、どの箇所なら安全に触れてよいかを切り分ける。
- publish / mail / scheduler / Cloud Run env / source追加 / X投稿 / SEO / デザイン変更へ波及しない調査方針を固める。

## 2. 今回触る範囲

- 本文生成の入口ファイルの調査
- 記事テンプレート生成箇所の調査
- Gemini / LLM 呼び出し箇所の調査
- 固定テンプレートで本文を組み立てている箇所の調査
- quality guard / body validator の調査
- draft body editor との関係整理
- 本作業記録Markdown

## 3. 今回触らない範囲

- publish 条件
- mail 通知
- scheduler
- Cloud Run env
- source追加
- X投稿
- SEO
- デザイン
- commit / push / deploy

## 4. 影響範囲

- 直接影響候補は本文生成ロジックの調査結果整理のみ。
- この時点ではコード未変更のため、実運用への影響はない。
- 調査結果次第で、本文生成ロジックと validator / editor の境界整理が必要になる可能性がある。

## 5. 実行予定テスト

- なし
- 今回は実装禁止のため、read-only 調査と Markdown 追記のみを行う

## 6. STOP条件

- publish / mail / scheduler / env / source追加 / X投稿 / SEO / デザインに触れないと整理できない場合
- 本文改善のために publish 条件や運用ジョブの変更が前提だと判明した場合
- 調査対象が広がりすぎて「本文情報量の改善」単独で切り出せない場合

## 7. 想定デグレ

- 調査時点ではなし
- 将来の実装で想定されるデグレは、調査後に Regression Memo へ整理する

## 8. 作業ログ欄

- 2026-05-09 JST: 作業記録Markdownを新規作成。現時点の変更はこのファイルのみ。
- 2026-05-09 JST: read-only 調査を実施。現状の初回本文本線は `src/rss_fetcher.py`、`manual_intake.py` は別入口、`draft_body_editor.py` は後段修正レーンであることを確認。
- 2026-05-09 JST: `本文情報量の改善` を安全に進めるため、対象記事タイプを 4 種に絞る narrow 設計、画像1枚方針、media enrich 別タスク方針を追記。
- 2026-05-09 JST: 危険側だった `A〜F を広く見せる前提` を修正し、初回実装は `A+B` または `A+C`、多くても `A+B+D` までとする safe-narrow 設計へ更新。

## 9. Regression Memo欄

- 変更着手前
- 調査後に「本文情報量の改善」を実装する場合の回帰観点を追記する

## 調査結果表

| 項目 | ファイル | 役割 | 触ってよいか | 理由 |
|---|---|---|---|---|
| 本文生成の入口ファイル | `src/rss_fetcher.py` | RSS本線の記事本文を生成し、`apply_rss_pipeline_enrichment` を通したうえで `wp.create_post()` へ渡す。初回本文の主経路。 | はい | 「本文情報量の改善」の主戦場。初回本文はここでほぼ決まっているため。 |
| 記事テンプレート生成箇所 | `src/rss_fetcher.py` | `_build_rule_based_subtype_body()` が rule-based 本文を返し、`generate_article_with_gemini()` 内の category / subtype prompt 群が本文構成と密度を決める。 | はい | 本文の増量ブロック設計を入れるなら、ここに閉じるのが最も自然。 |
| Gemini / LLM を呼んでいる箇所 | `src/rss_fetcher.py` | `_request_gemini_strict_text()` と `generate_article_with_gemini()` が Gemini Flash 2.5 を呼ぶ。現状は抽出ではなく本文そのものを返させている。 | 条件付き | 触るなら「自由作文の本文生成」ではなく「抽出JSON専用」に寄せる方向が安全。 |
| 固定テンプレートで本文を組み立てている箇所 | `src/rss_fetcher.py`, `src/tools/manual_intake.py` | RSS本線では rule-based body / safe fallback が固定構成。manual intake 側には `_build_body_for_news()` の別経路フォールバック本文がある。 | RSS本線ははい / manual intake は基本いいえ | manual intake は手動取り込み系の別経路で、今回の「現状の本文本線」とは分けて扱うべきため。 |
| quality guard / body validator の箇所 | `src/body_validator.py`, `src/article_quality_guards.py` | 見出し順、必須ブロック、source block、fact conflict、禁止語、H3数などを検証する。 | 条件付き | 本文増量後の整合確認には必要だが、主目的は validator 緩和ではなく本文改善。 |
| draft body editor との関係 | `src/tools/run_draft_body_editor_lane.py`, `src/tools/draft_body_editor.py` | 既存 draft を後段で修正する side lane。`current_body` と `source_block` を元に Gemini で差分修正し、Guard A/B/C を掛ける。 | 基本いいえ | 初回本文の生成器ではなく post-process。今回の本文本線調査とは役割が別。 |
| publish / mail に影響する箇所としない箇所 | `src/rss_fetcher.py`, `src/tools/manual_intake.py` | 本文生成自体は `rss_fetcher` / `manual_intake` 側。publish 条件、mail 通知、scheduler、env は別経路。`rss_fetcher.py` の `create_post` 近傍には `status` 分岐がある。 | 本文ロジックだけなら可 / status 周辺は不可 | 本文改善は生成関数内に閉じるべき。`resolved_status` や通知系へ触れると今回のスコープを外れる。 |

### 調査メモ

- 現状の「初回本文の本線」は `src/rss_fetcher.py`。
- `src/tools/manual_intake.py` は手動取り込み用の別入口で、fallback shell + enrichment の別経路。
- `src/tools/draft_body_editor.py` は既存 draft の後段編集であり、初回本文生成器ではない。
- 本文情報量だけを安全に改善するなら、第一候補は `src/rss_fetcher.py` の rule-based / prompt / fallback 周辺で、`wp.create_post()` の status 分岐や publish / mail には近づかない方針が妥当。

### 現行との差分メモ

| 観点 | 現行 | ここまでの設計案との差分 |
|---|---|---|
| 本文の作り方 | `rss_fetcher.py` 本線は Gemini 本文生成が主、rule-based は一部 subtype 限定 | 自由作文を減らし、事実ブロックを deterministic に組む方向 |
| 本文ブロック | 現行は category / subtype ごとの見出しテンプレート中心で、A〜F の共通 fact block は未導入 | `3行ファクトサマリー`、`確認できる事実`、`数字ブロック` などを明示的に追加する想定 |
| 情報量の源泉 | 現行は Gemini prompt 内で Web検索や周辺情報を取りにいく前提が強い | 入力済みの元記事本文、RSS要約、既存メタに限定し、未確認情報を増やさない方針 |
| quality guard | 現行は validator / forbidden phrase / heading 正規化で後段抑制する設計 | 先に fact block を fail-closed で組み、guard 頼みを減らす設計 |
| X embed | 現行は `manual_intake.py` の nomotoke marker 経路では `関連 X 投稿` が入る。RSS本線 AI body は marker がないため enrichment が基本乗らない | X embed を本文情報量とは分離し、使うなら「見た目強化 / 補助証跡」として別設計にする |
| 他人の X ポスト | 現行でも `manual_intake.py` の cached pool から 2〜3 件選ぶ仕組みはある | ただし本文情報量の改善ではなく、採用ルール付きの media enrichment として整理が必要 |
| YouTube / 動画 | 現行は `manual_intake.py` に `nomotoke_card_video_v1` があり、YouTube URL 正規化と video card 抽出がある。RSS本線の一般本文では未統合 | 動画は「楽しさ」は増えるが本文事実量は増えないため、本文改善とは別テーマとして切り出す |
| 画像 | 現行は source 側画像を featured media や hero 表示に使う経路は一部あるが、元サイト画像の直貼りを本文改善の既定路線にはしていない | 画像直貼りは権利・hotlink・参照切れリスクがあるため、今回の本文改善案には含めない |

### テンプレ適用可否メモ

`manual_intake.py` の article type / template_key と、`rss_fetcher.py` の本文設計に照らすと、今回の「事実ブロック追加」は全テンプレ一律ではなく、以下の切り分けが妥当。

| テンプレ / 記事タイプ | 現行キー | 適用可否 | 適用メモ |
|---|---|---|---|
| 試合結果 | `nomotoke_card_short_news_url_v1` | 可能 | A/B/D/F が効きやすい。数字と展開があるため最も伸ばしやすい。 |
| 試合速報 | `nomotoke_card_postgame_v1` | 可能 | A/B/D/F が効く。postgame 系は事実量が比較的多い。 |
| 予告先発 | `nomotoke_card_pregame_pitcher_v1` | 可能 | A/B/D/E/F のうち、予想禁止で pregame 情報だけに限定すれば安全。 |
| 公示 | `nomotoke_card_official_notice_v1` | 可能 | A/B/E が効く。登録日、抹消、対象選手、成績など事実整理向き。 |
| 監督談話 | `nomotoke_card_manager_comment_v1` | 可能 | A/B/C/E が効く。発言要旨と文脈整理に向く。 |
| 選手コメント | `nomotoke_card_player_comment_v1` | 可能 | A/B/C/D/E が効く。発言と数字がある場合に伸ばしやすい。 |
| 成績 | `nomotoke_card_short_news_url_v1` | 可能 | A/B/D/E が効く。数字中心の事実ブロックと相性が良い。 |
| 番組情報 | `nomotoke_card_short_news_url_v1` | 部分適用 | A/B 程度は可能だが、事実量が薄い記事では増量幅は小さい。 |
| コラム | `nomotoke_card_short_news_url_v1` | 部分適用 | 入力が事実中心なら可。意見・感想寄りコラムには今回方針を強く当てにくい。 |
| ニュース | `nomotoke_card_short_news_url_v1` | 可能 | 汎用だが、元記事本文やRSS要約があれば A/B を積みやすい。 |
| 動画 | `nomotoke_card_video_v1` | 部分適用 | 見た目は強いが、本文情報量は動画説明文や抽出済み facts に依存。本文改善の主対象にはしない。 |

補足:

- 実質的には `text-heavy template` には適用できる。
- `video / embed-heavy template` には全文量改善ではなく、最小限の fact block だけ部分適用が妥当。
- したがって「10種類に適用できるか」の答えは `はい、ただし一律ではなく、強適用 7〜8種 + 部分適用 2〜3種`。

### テンプレ別の着地点

重要:

- repo 上では `article_type` と `template_key` は 1:1 ではない。
- `src/tools/manual_intake.py` で確認できる concrete な `article_type` は `auto` を除くと 11 個あり、同じ `template_key` に複数 article type が乗る。
- したがって、今回の本文改善は「template_key 単位」より「記事タイプごとの許容ブロック単位」で設計した方が安全。

| 記事タイプ | 現行 template_key | 今回の着地点 | 出すブロック | 出さない / 弱くするもの |
|---|---|---|---|---|
| 試合結果 | `nomotoke_card_short_news_url_v1` | 試合結果向け fact-heavy 本文へ寄せる | A, B, D, F | 根拠の薄い感想、抽象総論 |
| 試合速報 | `nomotoke_card_postgame_v1` | postgame 事実整理を強化 | A, B, D, F, 条件付き C | 予想、感情作文 |
| 予告先発 | `nomotoke_card_pregame_pitcher_v1` | 試合前の確認事項整理に限定 | A, B, D, E, F | 勝敗予想、起用断定 |
| 公示 | `nomotoke_card_official_notice_v1` | 登録 / 抹消 / 合流の事実整理を厚くする | A, B, 条件付き D, E | 理由の推測、内情説明 |
| 監督談話 | `nomotoke_card_manager_comment_v1` | 発言要旨中心の整理型へ | A, B, C, E | 監督意図の補完、一般論 |
| 選手コメント | `nomotoke_card_player_comment_v1` | コメント + 数字があれば成績補足 | A, B, C, 条件付き D, E | 心理描写、期待論 |
| 動画 | `nomotoke_card_video_v1` | 動画カード主体、本文は補助に留める | 条件付き A, 条件付き B, 条件付き D | 無理な長文化、動画内容の推測要約 |
| 成績 | `nomotoke_card_short_news_url_v1` | 数字主導の短い fact block 構成 | A, B, D, E | 冗長な感想、背景補完 |
| 番組情報 | `nomotoke_card_short_news_url_v1` | 放送日時・出演者・媒体整理の短文型 | A, B, 条件付き F | 事実の少ない水増し |
| コラム | `nomotoke_card_short_news_url_v1` | 事実が取れる範囲だけ短く整理 | A, B | 主観増量、論評膨張 |
| ニュース | `nomotoke_card_short_news_url_v1` | 汎用ニュース整理型 | A, B, 条件付き C, 条件付き D, 条件付き E | 事実なし背景説明 |

補足:

- `short_news_url_v1` に乗っている型でも、実際の本文構成は一律にしない。
- `試合結果 / 成績 / ニュース / 番組情報 / コラム` は同じ template_key でも、出すブロック条件を分ける必要がある。
- `動画` は見た目の楽しさは増やせるが、本文情報量の改善対象としては最も弱い。

### 人間向けイメージ

以下は「実装名」ではなく、「読者から見て記事がどう見えるか」の整理。

1. 試合結果
   - 最初に「今日は誰がどう勝った / 負けた」が 2〜3 文で出る。
   - その下に、スコア、決め手、主な選手成績が短く並ぶ。
   - 最後に「次の試合でどこを見るか」が 1 段だけ入る。

2. 試合速報
   - 最初にその記事時点の状況を短く整理する。
   - その下に、流れが動いた場面と数字を並べる。
   - 試合中の記事なら「次にどこを見るか」、試合後なら「何が勝敗を分けたか」で締める。

3. 予告先発
   - 最初に対戦カード、球場、開始時刻、予告先発を整理する。
   - その下に、確認できる数字や直近状況を短く置く。
   - 最後は「どこが確認ポイントか」で止める。予想は書かない。

4. 公示
   - 最初に「誰が登録 / 抹消 / 合流したか」をはっきり出す。
   - その下に、対象選手の基本情報や直近数字を置く。
   - 最後に「一軍起用 / 次戦帯同 / 二軍継続」などの確認ポイントを 1 段だけ入れる。

5. 監督談話
   - 最初に「監督が何を言ったか」を短くまとめる。
   - その下に、発言の要旨を 1〜2 個並べる。
   - 最後に、その発言を受けて次にどこを見るかを短く整理する。

6. 選手コメント
   - 最初に「選手が何について話したか」を短くまとめる。
   - その下に、コメント要旨と、あれば成績や数字を足す。
   - 最後に、次の試合や起用でどこを見るかを 1 段だけ入れる。

7. 成績
   - 最初に「誰がどんな数字を出したか」を短く出す。
   - その下に、打率、防御率、本塁打、登板内容など確認できる数字を並べる。
   - 最後に、その数字が次にどうつながるかの確認ポイントだけを書く。

8. 番組情報
   - 最初に放送日、時間、出演者、番組名を整理する。
   - その下に、見どころや扱うテーマを短く置く。
   - 長文化せず、案内記事として短く終える。

9. コラム
   - 事実が取れる場合だけ短い要約と確認事実を置く。
   - 事実が薄いなら無理に膨らませず、短めのままにする。
   - 今回の方針では、主観コラムを長くする用途には使わない。

10. ニュース
   - 最初に「何が起きたか」を 2〜3 文で整理する。
   - その下に、名前、日付、数字、発言があれば箇条書き風に入れる。
   - 最後に、巨人ファンとして次にどこを見るかを 1 段だけ入れる。

11. 動画
   - 見た目の主役は動画カードのまま。
   - 本文は「動画で扱っているテーマ」と「確認できる事実」を短く補う程度に留める。
   - 動画記事を無理に長文記事へ変えない。

### 現時点の不安点

1. 入力事実量のばらつき
   - `元記事本文あり` と `X単独` で出せる情報量が大きく違う。
   - 同じテンプレ方針を無理に当てると、薄い記事だけ不自然になる。

2. `template_key` と記事タイプが 1:1 でない
   - 同じ `nomotoke_card_short_news_url_v1` でも、試合結果、成績、ニュース、番組情報、コラムで欲しい本文が違う。
   - template_key 単位で一括実装するとズレやすい。

3. validator / 見出し契約との衝突
   - 本文ブロックを増やしても、`body_validator.py` の heading / block order 契約に触れると reroll / fail になる。
   - 先に subtype ごとの許容構造を確認してから差し込む必要がある。

4. 重複しやすい
   - `3行サマリー` と `確認できる事実` と `数字ブロック` が同じ話を繰り返しやすい。
   - 情報量は増えても、読後感は悪くなる可能性がある。

5. 現行 enrich と本線本文が分かれている
   - `manual_intake.py` 側には X embed / related / standings などの enrich がある一方、RSS本線 AI body にはそのまま乗らない。
   - 「本文改善」と「見た目改善」を混ぜると設計が崩れやすい。

6. 画像 / 動画 / 他人の X を混ぜる境界
   - 楽しさは増えるが、本文情報量の改善とは別テーマ。
   - ここを同時にやると scope が膨らみやすい。

7. 記事ごとの最適長が違う
   - 公示や番組情報は短い方が読みやすい。
   - 逆に試合結果や成績記事は数字ブロックが多い方がよい。
   - 「全部少し長くする」は中途半端になりやすい。

### 多角的な改善提案

1. まず「記事の濃さ」を 3 段階に分ける
   - `薄い`: X単独 / 一言ニュース
   - `中`: タイトル + RSS要約あり
   - `厚い`: 元記事本文あり / 数字・発言あり
   - これで出すブロック数を変える。

2. 記事タイプごとに「最初に欲しい情報」を固定する
   - 試合結果なら `スコア / 決め手 / 主な数字`
   - 公示なら `誰がどう動いたか`
   - 監督談話なら `何を言ったか`
   - 動画なら `何の動画か`

3. 事実ブロックは最大 3 つまでに絞る
   - `A. サマリー`
   - `B. 確認できる事実`
   - `D. 数字` または `C. コメント`
   - 何でも全部出さない。

4. `確認ポイント` ブロックは厳格に絞る
   - 事実トリガーがあるときだけ出す。

## 実装ログ: 公示 第1段

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_notice_body_template.py`
- `docs/work_logs/2026-05-09_body-information-density-investigation.md`

### 2. diff概要

- `player_notice` の `record_fact` 抽出で、日付付きの公示文を「成績情報」と誤認していた優先順を修正。
- `打率 / 本塁打 / 打点 / 登板 / 防御率` などの成績・数字を優先し、`登録 / 抹消 / 合流 / 昇格` などの公示動作を含む文は `basic info` の成績枠から外すようにした。
- `player_notice` の `background_fact` でも、既に使った `notice_fact` / `record_fact` を除外し、2つ目以降の source fact を優先するようにした。
- 結果として、`公示の要旨` と `対象選手の基本情報` の重複が減り、`基本情報=成績`、`背景=合流や補足事実` になりやすくした。

### 3. 実行したテスト

- `python3 -m unittest tests.test_notice_body_template.NoticeBodyTemplateTests.test_notice_build_news_block_uses_numeric_record_in_basic_info`
  - 追加直後: `FAIL`
  - 修正後: `OK`
- `python3 -m unittest tests.test_notice_body_template tests.test_rss_fetcher_rule_based_subtypes tests.test_rss_article_generation_contract_skeleton`
  - `17 tests OK`
- `python3 -m py_compile src/rss_fetcher.py tests/test_notice_body_template.py`
  - `OK`
- `python3 -m compileall src tests`
  - `OK`
- `python3 - <<'PY' ... ast.parse(...)`
  - `ast_ok`
- `python3 -m unittest discover -s tests`
  - sandbox では `test_manual_intake_service.LiveServerSmokeTest` の localhost bind 制約で `3 errors`
- `python3 -m unittest discover -s tests`
  - 権限昇格で再実行
  - `3288 tests OK`

### 4. テスト結果

- `player_notice` の追加 regression は、修正前に赤、修正後に緑を確認。
- `notice` 周辺の関連テスト群は全件通過。
- 全体 `unittest discover` は sandbox 制約の 3件を除き repo 側の fail なし。
- 権限昇格後の全件実行で `3288 tests OK` を確認。

### 5. 残った懸念

- 今回は `公示` のうち `成績行をどこへ置くか` の修正のみ。見出し数や visible structure は既存 contract を維持した。
- `player_notice` の `読売ジャイアンツの選手です` という基本情報文はまだ粗い。`投手 / 外野手 / 内野手` の補完精度は別便で改善余地がある。
- `今後の注目点` セクション自体は残している。`A+B` に visible structure ごと縮めるのは、既存 contract / tests / prompt 群をまとめて扱う別段階が必要。

### 6. 新しく見つかったデグレ

- 新規デグレは未検出。
- 既知の sandbox 制約として、`LiveServerSmokeTest` は localhost bind のため非昇格実行では失敗する。

### 7. 追加した回帰テスト

- `tests/test_notice_body_template.py`
  - `test_notice_build_news_block_prefers_fact_template_before_gemini`
  - `test_notice_build_news_block_uses_numeric_record_in_basic_info`
- 特に後者で、
  - `今季打率.280、2本塁打。` が本文に残ること
  - `東京ドームに合流した。` が背景に回ること
  - `4月28日、浅野翔吾が一軍登録。` の重複が 1回に減ること
  を固定した。

### 8. 次回触ってはいけない範囲

- publish 条件
- mail 通知
- scheduler
- Cloud Run env
- source追加
- X投稿
- SEO
- デザイン
- `manual_intake` 側の media enrich
- `body_validator.py` / `article_quality_guards.py` の contract 緩和
- `player_notice` 以外の subtype への横展開を同一便で行うこと

## 実装ログ: 監督談話 第1段

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_manager_body_template.py`
- `docs/work_logs/2026-05-09_body-information-density-investigation.md`

### 2. diff概要

- `manager` fallback で quote あり case の 2つ目の fact を `発言の要旨` と `文脈と背景` に二重出力していたため、`発言内容` に寄せて 1 回に減らした。
- quote あり case では、`発言の要旨` は lead fact に絞り、`発言内容` に quote 軸 + 2つ目の事実を置くようにした。
- `文脈と背景` は追加 fact がある場合のみそれを使い、quote case で同じ detail を再掲しないようにした。

### 3. 実行したテスト

- `python3 -m unittest tests.test_manager_body_template.ManagerBodyTemplateTests.test_manager_quote_case_does_not_repeat_same_detail_fact_twice`
  - 追加直後: `FAIL`
  - 修正後: `OK`
- `python3 -m unittest tests.test_manager_body_template tests.test_rss_manager_short_subtype_tune tests.test_rss_fetcher_manager_quote_short tests.test_rss_article_generation_contract_skeleton`
  - `25 tests OK`
- `python3 -m py_compile src/rss_fetcher.py tests/test_manager_body_template.py`
  - `OK`
- `python3 -m compileall src tests`
  - `OK`
- `python3 - <<'PY' ... ast.parse(...)`
  - `ast_ok`
- `python3 -m unittest discover -s tests`
  - sandbox では `test_manual_intake_service.LiveServerSmokeTest` の localhost bind 制約で `3 errors`
- `python3 -m unittest discover -s tests`
  - 権限昇格で再実行
  - `3289 tests OK`

### 4. テスト結果

- 追加した manager regression は修正前に赤、修正後に緑を確認。
- manager 周辺の関連テスト群は全件通過。
- 全体 `unittest discover` は sandbox 制約の 3件を除き repo 側の fail なし。
- 権限昇格後の全件実行で `3289 tests OK` を確認。

### 5. 残った懸念

- 今回は `監督談話` のうち quote あり case の重複整理だけ。見出し数や visible structure は既存 contract を維持した。
- quote なし manager 記事はまだ generic 文が多い。`A + C` にさらに寄せるなら、topic-only case を別便で絞る必要がある。
- `文脈と背景` / `次の注目` 見出し自体は残している。visible structure を縮める変更は contract / tests / prompt 群の整理が先。

### 6. 新しく見つかったデグレ

- 新規デグレは未検出。
- 既知の sandbox 制約として、`LiveServerSmokeTest` は localhost bind のため非昇格実行では失敗する。

### 7. 追加した回帰テスト

- `tests/test_manager_body_template.py`
  - `test_manager_quote_case_does_not_repeat_same_detail_fact_twice`
- この test で、
  - `スタメン起用の理由にも触れた。` が 1 回だけ出ること
  - quote 軸 `今回の発言の軸は「状態がいいので使った」という言葉です。` が残ること
  を固定した。

### 8. 次回触ってはいけない範囲

- publish 条件
- mail 通知
- scheduler
- Cloud Run env
- source追加
- X投稿
- SEO
- デザイン
- `manual_intake` 側の media enrich
- `body_validator.py` / `article_quality_guards.py` の contract 緩和
- `manager` 以外の subtype への横展開を同一便で行うこと
   - 毎回入れない。入れすぎると全部同じ記事に見える。

5. 数字は「意味つき」で見せる
   - ただ数字を並べるのではなく、`7回2失点`, `3安打1打点`, `打率.284` のように短い意味つきで並べる。
   - これが一番「情報が増えた感」を出しやすい。

6. コメントは引用でなく要旨中心にする
   - 長い引用は避ける。
   - `発言者 + 要旨` で短く整理した方が読みやすく安全。

7. 画像は 1 枚だけにする
   - `先頭に画像1枚`
   - `その下にファクトサマリー`
   - `その下に事実ブロック`
   - これがコストと見た目のバランスが良い。

8. X / YouTube / 他人の X は別レイヤにする
   - 本文を濃くする施策と混ぜない。
   - 将来やるなら `media enrichment` として別タスク化する。

9. 「読者が次に知りたいこと」を型ごとに固定する
   - 一軍起用
   - 次戦先発
   - 二軍継続か昇格か
   - スタメン入り
   - これを `E/F` に限定して出す。

10. 実装順を narrow に切る
   - まず `試合結果 / 公示 / 監督談話 / 選手コメント` の 4 タイプ
   - 次に `成績 / ニュース / 予告先発`
   - 最後に `番組情報 / コラム / 動画`
   - 一気に全型へ入れない。

### 判断メモ: LLM は必須か

- 今回の目的が「主観や自由作文ではなく、事実ベースの情報量を増やすこと」なら、LLM は必須ではない。
- 第一候補は、`rss_fetcher.py` の rule-based / fixed-template 側を強化し、タイトル、RSS要約、取得済み本文、既存メタ、抽出済み数値から deterministic に本文ブロックを組み立てること。
- LLM を使う場合でも、本文生成には使わず、「抽出 JSON を返すだけ」の補助役に限定するのが安全。
- したがって設計優先順位は `non-LLM deterministic blocks > LLM extraction JSON > LLM free-writing` とする。

### 制約メモ: X 単独入力では情報量に上限がある

- X の本文だけを入力にすると、事実量は短くなりやすい。これは生成器の問題というより、入力ソースの情報量上限の問題。
- 安全に本文情報量を増やすには、X 単独ではなく、既存で取得済みの元記事本文、RSS要約、OG / source metadata、既存 summary を優先入力に使う必要がある。
- したがって「X 単独しかない記事」は短文を許容する fail-closed 設計が必要で、無理に本文を膨らませるべきではない。
- LLM を使う場合も、X 単独の短文から本文を膨らませる用途ではなく、元記事本文があるケースで事実抽出 JSON を返させる用途に限定する。

### 見込みメモ: 本文情報量はどれくらい増えるか

- `X単独`
  - 増量見込みは小さい。安全に増やせるのは `+0〜80字` 程度、または `事実箇条書き 1〜2項目` まで。
  - 誰が / 何を / いつ の基本要素が欠ける場合は、ほぼ増やせない想定。
- `タイトル + RSS要約あり`
  - `A. 3行ファクトサマリー` と `B. 確認できる事実` を足せるため、`+80〜220字` 程度の増量余地がある。
  - 増量率の目安は `1.2x〜1.6x`。
- `元記事本文あり`
  - コメント、数字、日付、選手名、球団名まで拾えるため、`+180〜400字` 程度の増量余地がある。
  - 増量率の目安は `1.4x〜2.0x`。
- `試合結果 / 公示 / コメント記事のように数字や発言が多い入力`
  - `C` と `D` まで使えるので、増量幅は比較的大きい。
- `雑報 / 一言コメント / X速報のように入力事実が少ない記事`
  - 増量幅は小さい。無理に `E` `F` を出さず、短いまま止める方が安全。
- 重要なのは「文字数を何倍にするか」より、「同じ事実の重複なしで何ブロック増やせるか」。

### 境界メモ: 見た目の楽しさを増やす案

- `X embed` や `YouTube embed` は、見た目の楽しさや滞在感の向上には有効。
- ただし、これは「本文情報量の改善」ではなく「視覚的な enrich / embed 強化」の別テーマ。
- `X embed`
  - 公式埋め込みなら権利・実装の筋は比較的良い。
  - ただし、表示不安定、読込速度、ポスト削除時の欠落リスクがある。
  - 自アカウントだけでなく、他者の X ポストでも公式 embed 自体は候補になる。
  - ただし、本文情報量の改善ではなく、話題の補助証跡・見た目強化として扱うべき。
  - また、どの発言者を許可するか、速報・感想・憶測をどう弾くかの選定ルールが要る。
- `YouTube embed`
  - 公式動画や球団・メディアの公開動画がある場合は有効。
  - ただし、全記事で材料があるわけではなく、本文事実量そのものは増えない。
- `元サイト画像の直貼り`
  - 見た目は改善しやすいが、著作権、hotlink、参照切れ、外部依存の面でリスクが高い。
  - 現時点では「安全な既定案」にはしない方がよい。
- したがって今回の ticket では、
  - 本文情報量の改善 = `事実ブロック追加`
  - 見た目の楽しさ = `embed / media enrichment`
  と分離して扱うのが妥当。

## Task 2: 本文増量ブロック設計

### 1. 採用するブロック

前提:

- `A〜F` は新しい visible section を増やすためのものではなく、本文の中身を組み立てるための部品として扱う。
- 初回実装では `E / F` は原則使わないか、極小の補助文に留める。
- 初回実装の基本は `A + B`、または `A + C`、多くても `A + B + D` まで。

| ブロック | 採用 | 目的 | 備考 |
|---|---|---|---|
| A. 3行ファクトサマリー | 採用 | 記事の核を最初に明示する | 全記事で最優先候補 |
| B. 確認できる事実 | 採用 | 元入力から取れる事実を箇条書き化する | 安全に情報量を増やしやすい |
| C. コメント・発言ブロック | 条件付き採用 | コメント記事や談話記事の密度を上げる | 発言が入力にある場合のみ |
| D. 数字・データブロック | 条件付き採用 | 試合結果、選手成績、登板内容の数値整理 | 数字がある場合のみ |
| E. 巨人ファン向け確認ポイント | 将来の限定採用 | 読者が次に確認すべき事実ベースの論点整理 | 初回実装では原則 OFF |
| F. 関連する次の見どころ | 将来の限定採用 | 次戦や起用の注目点を事実ベースで整理 | 初回実装では原則 OFF |

### 2. 採用しないブロック

| ブロック | 不採用理由 |
|---|---|
| 背景説明ブロック | 入力にない説明を足しやすく、ハルシネーション源になる |
| 人物の心理・意図解説 | 監督や選手の内心推測に流れやすい |
| 一般論だけの水増し段落 | 情報量ではなく文字量だけ増える |
| ファン感情ブロック | 事実から外れやすく、作文化しやすい |
| 予想・展望ブロック | 次戦予想や起用予想は根拠逸脱しやすい |
| 長い引用ブロック | 原文依存が強く、独自性と著作権リスクの両面で不利 |

### 3. 各ブロックの文字数目安

| ブロック | 文字数目安 | 行数目安 |
|---|---|---|
| A. 3行ファクトサマリー | 100〜180字 | 2〜3文 |
| B. 確認できる事実 | 1項目 20〜45字、全体 80〜220字 | 3〜6項目 |
| C. コメント・発言ブロック | 60〜140字 | 1〜3項目 |
| D. 数字・データブロック | 1項目 15〜35字、全体 45〜140字 | 2〜5項目 |
| E. 巨人ファン向け確認ポイント | 40〜100字 | 1〜3項目 |
| F. 関連する次の見どころ | 40〜100字 | 1〜3項目 |

### 4. 出力条件

| ブロック | 出力条件 |
|---|---|
| A. 3行ファクトサマリー | タイトル、ソース本文、RSS要約、取得済みメタのいずれかから「誰が・何を・いつ/どこで・どうなった」を2要素以上埋められる場合のみ |
| B. 確認できる事実 | 入力から固有名詞、日付、数字、球団名、試合名、発言者名のいずれかを3件以上抽出できる場合 |
| C. コメント・発言ブロック | 入力に発言者名と発言内容または要旨がある場合のみ |
| D. 数字・データブロック | 成績や試合データなどの数値が2件以上ある場合のみ |
| E. 巨人ファン向け確認ポイント | 登録抹消、昇格、先発、打順、二軍成績、復帰、次戦影響などの事実トリガーが入力にある場合のみ |
| F. 関連する次の見どころ | 次戦、次カード、起用継続、ローテ、登録動向などに直結する事実が入力にある場合のみ |

補足ルール:

- 初回実装の基本構成は `A + B` または `A + C`、多くても `A + B + D` までにする。
- `A〜F` をそれぞれ新見出しとして増やさない。既存の subtype heading の中で使う。
- A と B を優先し、E と F は初回実装では基本出さない。
- 同じ事実を A / B / D で重複させない。
- コメント記事では `A + C`、試合結果記事では `A + B + D`、登録・昇格記事では `A + B` を基本形にする。

### 5. デグレリスク

| リスク | 内容 |
|---|---|
| 重複リスク | 同じ数字や固有名詞をサマリーと箇条書きで繰り返して冗長化する |
| 根拠逸脱リスク | E / F が少しでも自由記述に寄ると推測混入が起こる |
| 短文化リスク | 安全側に倒しすぎて、情報量は増えても読み味が断片的になる |
| タイトル追従過剰 | タイトルだけを膨らませて本文にない要素を補ってしまう |
| コメント誇張 | 発言要旨の圧縮時にニュアンスを盛ってしまう |
| 数字混線 | 複数選手・複数試合の数字を取り違える |

### 6. 必要なテスト

| テスト種類 | 確認内容 |
|---|---|
| ブロック出力条件テスト | 条件を満たすときだけ `A/B/C/D` が出ること |
| ブロック非出力テスト | 条件不足なら `C / D` が出ないこと、`E / F` は初回実装で既定 OFF のこと |
| 重複防止テスト | 同じ事実が複数ブロックに重複しないこと |
| 事実抽出テスト | 日付、数字、発言者名、球団名、試合名の抽出が入力一致であること |
| 禁止表現テスト | 推測語、感情作文、背景補完、架空成績が出ないこと |
| subtype別ゴールデンテスト | 試合結果、選手コメント、監督談話、登録・抹消で `A+B` または `A+C` の期待構成になること |
| validator整合テスト | quality guard / body validator に抵触しないこと |
| draft body editor非干渉テスト | 新ブロック設計が draft body editor の guard 想定と競合しないこと |

## Task 3: Gemini Flash 2.5 用の抽出JSON設計

### 1. 役割定義

- Gemini Flash 2.5 は「記事本文を書く係」ではなく、「入力から事実を抽出して JSON を返す係」に限定する。
- 出力は JSON のみ。
- 入力にない情報は出さない。
- 推測しない。
- 補完しない。
- 背景説明を書かない。

### 2. 採用する JSON 設計

```json
{
  "summary_facts": [
    {
      "fact": "",
      "evidence_text": "",
      "confidence": "high|medium|low"
    }
  ],
  "people": [
    {
      "name": "",
      "role": "player|manager|coach|team|other",
      "evidence_text": ""
    }
  ],
  "numbers": [
    {
      "value": "",
      "unit": "",
      "meaning": "",
      "evidence_text": ""
    }
  ],
  "dates": [
    {
      "date_text": "",
      "meaning": "",
      "evidence_text": ""
    }
  ],
  "quotes": [
    {
      "speaker": "",
      "quote_summary": "",
      "evidence_text": ""
    }
  ],
  "topic_angle": {
    "type": "game_result|player_comment|manager_comment|farm_result|roster|injury_return|starting_lineup|pitching|batting|other",
    "evidence_text": ""
  },
  "safe_reader_points": [
    {
      "point": "",
      "based_on_fact": ""
    }
  ],
  "do_not_write": [
    ""
  ]
}
```

### 3. 各フィールドの制約

| フィールド | 制約 | 目的 |
|---|---|---|
| `summary_facts` | 0〜5件。1件 30〜70字。記事本文ではなく「事実文」だけ | A. 3行ファクトサマリーの原材料 |
| `people` | 0〜12件。重複禁止。役割は enum 固定 | 固有名詞の抽出固定 |
| `numbers` | 0〜12件。`value` と `unit` は分離。`meaning` は 5〜20字程度 | D. 数字・データブロックの原材料 |
| `dates` | 0〜8件。日付表現は原文どおり保持 | 時系列の根拠固定 |
| `quotes` | 0〜6件。`quote_summary` は 20〜50字程度。長い引用は禁止 | C. コメント・発言ブロックの原材料 |
| `topic_angle` | 1件必須。`type` は enum 固定 | 本文テンプレートの分岐材料 |
| `safe_reader_points` | 0〜4件。断定禁止。「確認ポイントです」レベルまで | E / F の原材料 |
| `do_not_write` | 1〜8件。入力不足や曖昧要素を明示 | 禁止事項の fail-closed 化 |

### 4. フィールドごとの安全ルール

| フィールド | 安全ルール |
|---|---|
| `fact` | 原文から直接言い換えられる事実だけ。背景補完禁止 |
| `evidence_text` | 必ず入力本文から拾える短い根拠文字列。空禁止 |
| `confidence` | `high`: 根拠が明示 / `medium`: 文脈で読める / `low`: 曖昧で本文採用しない候補 |
| `name` | 入力本文にある名前だけ。推定補完禁止 |
| `role` | `player / manager / coach / team / other` のみ |
| `value` | 数字文字列を原文どおり保持。丸め禁止 |
| `unit` | `打数 / 安打 / 回 / 失点 / 得点 / 号 / 日 / 年` など短い単位だけ |
| `meaning` | 数字の意味を短く固定。例: `先発回数`, `打点`, `登録日` |
| `quote_summary` | 原文の発言要旨だけ。感情や意図の補足禁止 |
| `point` | 「〜が確認ポイントです」まで。予想・断定禁止 |
| `based_on_fact` | `summary_facts.fact` か `numbers.meaning` 相当の根拠に紐づける |
| `do_not_write` | 曖昧な勝敗、未確認の登録理由、推測しかできない監督意図などを列挙 |

### 5. 追加で固定したい運用制約

| 項目 | 設計 |
|---|---|
| 出力形式 | JSON only。前置き・説明文・Markdown 禁止 |
| 空配列 | 情報がなければ空配列を返す。埋め草禁止 |
| 省略禁止 | キーは固定。情報がなければ空で残す |
| 重複禁止 | 同じ人物、同じ数字、同じ発言を複数配列に重複展開しない |
| 低信頼データ | `confidence=low` は本文側で採用しない前提 |
| 記事本文生成禁止 | モデルに本文段落を書かせない |
| 未確認要素 | `do_not_write` に退避して本文に出さない |

### 6. `safe_reader_points` の厳格ルール

- 書いてよい:
  - `一軍登録の有無が確認ポイントです`
  - `次戦での先発起用が確認ポイントです`
  - `二軍成績の継続が確認ポイントです`
  - `スタメン入りの有無が確認ポイントです`
- 書いてはいけない:
  - `次戦で活躍が期待されます`
  - `先発ローテ入りしそうです`
  - `監督の信頼を勝ち取ったとみられます`
  - `今後の中心選手になる可能性があります`

### 7. `do_not_write` に入れるべき典型例

- 勝敗やスコアが入力内で食い違っている
- 発言者名が曖昧
- 日付が相対表現のみで確定できない
- 数字が誰の成績か不明
- 登録 / 抹消の理由が入力にない
- 次戦や起用方針が明記されていない

### 8. 本文組み立て側への受け渡し方針

- `summary_facts` をそのまま 3行ファクトサマリー候補に使う
- `people / numbers / dates / quotes` を固定テンプレートへ流す
- `topic_angle.type` で本文テンプレート分岐を決める
- `safe_reader_points` は E / F ブロックの候補に限定利用する
- `do_not_write` に入った論点は本文へ一切使わない

### 9. デグレリスク

| リスク | 内容 |
|---|---|
| evidence なし抽出 | `fact` や `quote_summary` が根拠文なしで出る |
| summary の作文化 | `fact` が事実抽出でなく要約作文になる |
| angle 誤分類 | `topic_angle.type` を誤ると不適切テンプレートへ流れる |
| low confidence 混入 | 本文側が `low` を拾うとハルシネーションが再侵入する |
| do_not_write 無視 | 禁止論点が本文に流れ込むと設計全体が崩れる |
| quote 膨張 | 発言要旨が原文以上の意味を持ってしまう |

### 10. 必要なテスト

| テスト種類 | 確認内容 |
|---|---|
| JSON schema テスト | 全キー存在、enum 制約、型整合 |
| evidence 必須テスト | `summary_facts / people / numbers / dates / quotes` の各要素に `evidence_text` があること |
| no free-writing テスト | 入力にない固有名詞、数字、背景説明が出ないこと |
| topic_angle 分類テスト | 記事 subtype ごとに許容 `type` へ入ること |
| safe_reader_points 制約テスト | 断定語、予想語、感情語が出ないこと |
| do_not_write fail-closed テスト | 曖昧入力で禁止事項が `do_not_write` に入ること |
| empty-safe テスト | 情報がない配列は空配列で返り、埋め草しないこと |
| duplicate suppression テスト | 同一人物・同一数字・同一発言の重複がないこと |

## Task 4: 安全設計

### 1. 基本方針

- 今回の改善は `本文情報量の改善` に限定する。
- `LLM自由作文` は使わない。
- `入力にある事実だけ` を増やす。
- `X / YouTube / 他人のX / 画像` は本文情報量とは別レイヤで扱う。
- `入力が薄い記事` は短文を許容する。無理に膨らませない。

### 2. まず対象にする記事タイプ

最初の実装対象は 4 タイプに絞る。

1. `試合結果`
2. `公示`
3. `監督談話`
4. `選手コメント`

理由:

- 事実量が比較的安定している
- 数字や発言者名を拾いやすい
- 主観を減らしても読み味が保ちやすい
- validator 契約を壊しにくい

### 3. 後回しにする記事タイプ

- `予告先発`
- `成績`
- `ニュース`
- `番組情報`
- `コラム`
- `動画`

理由:

- 事実量のばらつきが大きい
- 短い方が自然な型が混ざる
- 動画や番組情報は「本文を濃くする」より「見せ方」の比重が高い

### 4. 各記事タイプで出してよいブロック

| 記事タイプ | 最小構成 | 条件付き追加 | 初回上限 |
|---|---|---|---|
| 試合結果 | `A + B` | `D` | 3要素 |
| 公示 | `A + B` | なし | 2要素 |
| 監督談話 | `A + C` | なし | 2要素 |
| 選手コメント | `A + C` | `B` または `D` のどちらか1つ | 3要素 |

補足:

- `A = 3行ファクトサマリー`
- `B = 確認できる事実`
- `C = コメント・発言ブロック`
- `D = 数字・データブロック`
- `E = 巨人ファン向け確認ポイント`
- `F = 関連する次の見どころ`
- 初回実装では `E / F` は対象外とみなす

### 5. 出さないルール

- 同じ事実を `A / B / D` で重複させない
- 初回実装では `E / F` を出さない
- コメントがなければ `C` は出さない
- 数字がなければ `D` は出さない
- `X単独` で事実が少なければ `A` だけ、または `A + B` で止める
- H3 を増やすためにブロックを足さない

### 6. 文字数の安全上限

| 記事タイプ | 目標 |
|---|---|
| 試合結果 | 現状比 `1.3x〜1.8x` |
| 公示 | 現状比 `1.2x〜1.6x` |
| 監督談話 | 現状比 `1.2x〜1.6x` |
| 選手コメント | 現状比 `1.2x〜1.7x` |

補足:

- 文字数目標より `重複なしで事実ブロックを何個出せるか` を優先する
- `X単独` の記事はこのレンジを下回ってよい

### 7. 画像1枚の扱い

- 画像は `先頭に1枚だけ` を前提にする
- 本文改善と画像改善を混ぜない
- 想定する見え方は以下

1. 先頭に画像1枚
2. その下に `A. 3行ファクトサマリー`
3. その下に `B/C/D`
4. 既存の短い締めや CTA

- `本文途中に2枚目` は今回は入れない
- `元サイト画像の直貼り` は今回の安全設計には含めない

### 8. media enrich の扱い

- `X embed`
- `YouTube embed`
- `他人のXポスト`

これらは本文改善とは別タスクに切り分ける。

理由:

- 見た目の楽しさは増える
- ただし本文の事実量そのものは増えない
- ここを同時にやると scope が広がる

### 9. fail-closed 条件

以下のどれかに該当したら、増量せず短文を維持する。

- 入力が `X単独`
- 数字がない
- 発言者が曖昧
- 日付が曖昧
- 対象選手や対象試合が曖昧
- validator 契約に触れそう

### 10. 実装順の安全案

1. `試合結果`
2. `公示`
3. `監督談話`
4. `選手コメント`
5. 効果確認後に `成績 / ニュース / 予告先発`
6. 最後に `番組情報 / コラム / 動画`

### 11. 今回の着地点

- まずは「全部の記事を少し長くする」ではなく、「4タイプだけ安全に濃くする」設計とする
- `本文情報量`
  - 事実ブロックで改善
- `見た目`
  - 画像1枚で改善
- `media enrich`
  - 別タスク

### 12. 差分として大きく変わる本文内容

読者から見て大きく変わるのは、以下の 5 点。

1. 冒頭が「感想寄り」から「事実要約」に変わる
   - 先頭で `誰が / 何を / いつ / どこで / どうなったか` を 2〜3 文で出す。
   - 最初の数行で記事の芯が分かる形にする。

2. 固有名詞と数字が増える
   - 選手名、球団名、日付、試合名、スコア、成績数字を短く整理して入れる。
   - 「情報が増えた感」は主にここで出す。

3. コメント記事は「発言者 + 要旨」が見えやすくなる
   - 長い引用ではなく、誰が何を言ったかを短く整理する。
   - 監督談話、選手コメントは特に差分が出やすい。

4. 記事の終わりが「ふんわりした締め」から「確認ポイント」に変わる
   - 次戦、起用、一軍登録、先発、二軍継続など、次にどこを見るかを事実ベースで示す。
   - 予想や感情で締めない。

5. 薄い記事は無理に長文化しなくなる
   - X単独や情報が少ない記事は、短いまま止める。
   - 「全部少し長い」より、「厚くできる記事だけ厚くする」方向になる。

タイプ別に見ると、見え方は以下のように変わる。

- `試合結果`
  - 現行: 試合の雰囲気や総論が先に出やすい
  - 変更後: スコア、決め手、主な数字が先に出る

- `公示`
  - 現行: 公示の話題が短く流れることがある
  - 変更後: 誰が登録 / 抹消されたか、何が確認ポイントかが先に分かる

- `監督談話`
  - 現行: 談話の周辺説明や一般論が混ざりやすい
  - 変更後: 発言者、発言要旨、次に見る点が整理される

- `選手コメント`
  - 現行: コメント紹介で終わりやすい
  - 変更後: コメント要旨 + 数字 + 次の確認ポイントまで入る

### 13. 実装可否判定

#### 結論

- `大筋は実装に進める`
- ただし `そのまま全面実装` ではなく、既存 contract に合わせた 3 つの締め直しを前提にする

#### 前提として確認した既存設定

- `docs/ops/ARTICLE_BODY_QUALITY_REQUIREMENTS_V1.md`
  - 短く、事実ベース、source-grounded を優先
  - H3 は `0〜2` を基本
  - source が短いなら本文も短くてよい
  - `ファン注目ポイント section を強制しない`
- `docs/ops/RSS_ARTICLE_GENERATION_CONTRACT.md`
  - 短い素材は `short_social` / `source_link_only` として短文成立を優先
  - source 外の事実追加は禁止
  - candidate 出力までが責務で、publish / mail は触らない
- `tests/test_rss_article_generation_contract_skeleton.py`
  - subtype ごとに body contract を前提にしている
- `tests/test_game_body_template.py`
  - game 系は required headings と H3 数の契約がある

#### 違和感がない点

- `LLM自由作文を減らす`
- `事実ブロックで情報量を増やす`
- `入力が薄い記事は短文許容`
- `4タイプだけ narrow に始める`

これらは既存設定と整合している。

#### そのままだと危ない点

1. `A〜F` を全部 visible section として増やす案
   - 既存の `H3 0〜2` 方針と衝突する
   - `ファン注目ポイント section を強制しない` 方針にも触れやすい

2. `確認ポイント(E)` と `次の見どころ(F)` の常設
   - source が短い記事では水増しに見えやすい
   - `short_social` / `source_link_only` 契約とズレる

3. `4ブロック上限` でも article type によってはまだ多い
   - 公示や短いコメント記事では `A+B` だけで十分なケースがある

#### 実装に進むための締め直し

1. `A〜F` を「見出し」ではなく「中身の部品」として扱う
   - visible H3 を増やさない
   - 既存 subtype heading の中で使う

2. `E / F` はデフォルト OFF に近い扱いにする
   - 明確な事実トリガーがある時だけ出す
   - まずは `試合結果` だけ `F`、`公示/談話/コメント` は `E` を極小で許可する程度が安全

3. 1本目の実装では `A+B+1要素` までに絞る
   - 試合結果: `A + B + D`
   - 公示: `A + B`
   - 監督談話: `A + C`
   - 選手コメント: `A + C`

#### 最終判断

- `違和感なく実装に進めるか` という問いには、`はい。ただし safe-narrow に締め直した形なら進める` が回答。
- `A〜F を広く見せる大きいテンプレ改造` として進めるのはまだ危ない。
- `既存 heading 契約を維持しながら、冒頭の事実密度だけ上げる` 方向なら着手してよい。

### 14. 実装ログ

#### 2026-05-09 JST / 公示 第1段

- 対象: `公示`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - `登録 / 抹消` の事実と `数字` の事実を分離する
  - `基本情報` で日付付き公示文を重複させない
  - `背景` には別の source fact を回す
- 実装メモ:
  - `src/rss_fetcher.py`
  - `tests/test_notice_body_template.py`
- 追加回帰:
  - `test_notice_build_news_block_uses_numeric_record_in_basic_info`
- 結果:
  - 修正前 red / 修正後 green
  - 関連 `17 tests OK`
  - full suite は sandbox bind 3 error 後、権限昇格で `3288 tests OK`

#### 2026-05-09 JST / 監督談話 第1段

- 対象: `監督談話`
- 変更: `A + C` に寄せる narrow 調整
- ねらい:
  - quote あり case で `detail fact` を `発言内容` と `文脈と背景` に二重で出さない
  - `誰が何を言ったか` を先に分かる形に保つ
- 実装メモ:
  - `src/rss_fetcher.py`
  - `tests/test_manager_body_template.py`
- 追加回帰:
  - `test_manager_quote_case_does_not_repeat_same_detail_fact_twice`
- 結果:
  - 修正前 red / 修正後 green
  - 関連 `25 tests OK`
  - full suite は sandbox bind 3 error 後、権限昇格で `3289 tests OK`

#### 2026-05-09 JST / 選手コメント 第1段

- 対象: `選手コメント`
- 変更: `A + C` に寄せる narrow 調整
- ねらい:
  - 野手の quote 記事に投手向けの文言 (`相手打線 / マウンド / 配球 / 阪神戦の入り方`) が混ざる事故を止める
  - `何を意識しているか` を role-safe な文に置き換える
  - 既存 heading 数や route は変えない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `player_quote` fallback 用の safe line helper を追加
    - `focus / watch / closing` を helper 経由に差し替え
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_player_quote_hitter_fallback_avoids_pitcher_specific_language`
- 結果:
  - 修正前 red (`相手打線` が本文に混入)
  - 修正後 green
  - 関連 `70 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3290 tests OK`

### 15. Regression Memo

- `player_comment` は generic fallback が強く、role 判定を誤ると野手記事でも投手向けの filler が混ざる。
- 今回は `player_quote` の fallback 文面だけを narrow 修正し、route / validator / publish / mail は不変更。
- 次に `試合結果` へ進める場合も、まず `summary fact` と `数字ブロック` の重複を赤で固定してから触る。

#### 2026-05-09 JST / 試合結果 第1段

- 対象: `試合結果`
- 変更: `A + B + D` に寄せる narrow 調整
- ねらい:
  - `【選手成績】` で使った数字 fact を `【試合展開】` で重複させない
  - `スコア / 決め手 / 主な数字` の役割を section ごとに少し分ける
  - 既存 heading 契約は維持する
- 実装メモ:
  - `src/rss_fetcher.py`
    - `postgame` fallback の flow fact 選択を narrow 修正
  - `tests/test_game_body_template.py`
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_postgame_safe_fallback_avoids_repeating_stat_fact_in_flow`
- 結果:
  - 修正前 red (`田中将大投手は7回2失点だった。` が `【選手成績】` と `【試合展開】` に重複)
  - 修正後 green
  - 関連 `56 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3291 tests OK`

### 16. Regression Memo 追記

- `postgame` fallback は summary sentence 数が少ないと、数字 fact を `flow` に再利用しやすい。
- 今回は `flow` 用 fact を `stat_lines` / `highlight_source` と重ならないものに限定し、無ければ score-based の generic flow 文へ落とす形にした。
- `lineup / live_update / pregame` には波及させていない。

#### 2026-05-09 JST / 予告先発 第1段

- 対象: `予告先発`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - thin summary で `【具体的な変更内容】` が generic filler だけになるケースを減らす
  - `雨天中止 / スライド登板 / 先発予定` の title から安全に拾える先発名があるときだけ、事実 line を 1 本補う
  - `postgame / lineup / live_update` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `pregame` 専用の starter detail helper を追加
    - `detail_lines` が空のときだけ title / summary から `予告先発はXです。` を補う
  - `tests/test_game_body_template.py`
- 追加回帰:
  - `test_pregame_safe_fallback_surfaces_starter_when_summary_is_thin`
- 結果:
  - 修正前 red (`予告先発は田中将大です。` が出ず generic filler のまま)
  - 修正後 green
  - 関連 `57 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3292 tests OK`

### 17. Regression Memo 追記

- `pregame` fallback は summary が 1 文しかないケースだと、`球場 / 開始時刻` は拾えても `先発名` が `【具体的な変更内容】` へ落ちず、generic filler に逃げやすい。
- 今回は `detail_lines` が空のときだけ `pregame` 専用 helper を通し、`予告先発 / 先発予定 / スライド登板` の marker がある場合に限って `予告先発はXです。` を補う形にした。
- 既存の長めの `pregame` summary や、`postgame / lineup / live_update` の経路は不変更。

#### 2026-05-09 JST / スタメン 第1段

- 対象: `スタメン / lineup`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - `【先発投手】` に `予告先発` が 2 行出る重複を止める
  - normalized line (`予告先発はXです。`) を残しつつ、同内容の raw line (`予告先発はX投手。`) は落とす
  - `pregame / live_update / postgame` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `lineup` 用の starter dedupe helper を追加
    - safe fallback / rule-based lineup の `starter_lines` にだけ適用
  - `tests/test_game_body_template.py`
- 追加回帰:
  - `test_lineup_safe_fallback_dedupes_starter_line`
- 結果:
  - 修正前 red (`予告先発は` が 2 回出る)
  - 修正後 green
  - 関連 `58 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3293 tests OK`

### 18. Regression Memo 追記

- `lineup` fallback は `_extract_game_pitcher_lines(...)` の normalized line と source sentence の両方をそのまま積むため、`【先発投手】` に同じ意味の `予告先発` が重複しやすい。
- 今回は `lineup` 経路だけに starter dedupe helper を入れ、`予告先発は...` の 1 本目だけを残す形にした。
- helper は `lineup` safe fallback と `rule-based lineup` にだけ適用し、`pregame / postgame / live_update` には波及させていない。

#### 2026-05-09 JST / live_update 第1段

- 対象: `live_update / 試合速報途中経過`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - `live_update` が `pregame` fallback に誤落下して `【変更情報の要旨】` などの見出しになる状態を止める
  - `【いま起きていること】 / 【流れが動いた場面】 / 【次にどこを見るか】` の 3 見出しへ閉じる
  - 途中経過の score / イニング / 流れを短く整理し、予想や試合前文脈は混ぜない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `live_update` 専用の safe fallback helper を追加
    - `_build_game_safe_fallback(...)` の routing に `live_update` 分岐を追加
  - `tests/test_game_body_template.py`
- 追加回帰:
  - `test_live_update_safe_fallback_uses_live_update_headings`
- 結果:
  - 修正前 red (`【変更情報の要旨】` へ落下)
  - 修正後 green
  - 関連 `66 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3294 tests OK`

### 19. Regression Memo 追記

- `live_update` は `_build_game_safe_fallback(...)` で専用分岐がなく、`pregame` fallback に落ちていた。
- 今回は `live_update` 専用 helper を追加し、`facts[0]` を現況、`facts[1:]` を流れ変化、最後を次の注目点へ分ける 3 見出し構成にした。
- 変更は `safe fallback` の routing と本文整理に限定し、`lineup / pregame / postgame / live_anchor` には波及させていない。

#### 2026-05-09 JST / farm_result 第1段

- 対象: `farm_result / 二軍試合結果`
- 変更: `A + B + D` に寄せる narrow 調整
- ねらい:
  - `【二軍結果・活躍の要旨】` に出した team result fact を `【二軍個別選手成績】` へ再掲しない
  - team result は lead に残し、個人成績 section は野手 / 投手の数字 fact を優先する
  - `farm_lineup` や `player_notice` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `farm` fallback の `stat_facts` 抽出を narrow 修正
    - score を含む `勝利 / 敗戦 / 敗れ / 引き分け / コールド` 系の lead fact が team result そのものだった場合だけ、`【二軍個別選手成績】` から除外
  - `tests/test_farm_body_template.py`
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_farm_safe_fallback_keeps_team_result_out_of_stat_section`
- 結果:
  - 修正前 red (`巨人二軍がロッテ二軍に4-1で勝利した。` が lead と `【二軍個別選手成績】` に重複)
  - 修正後 green
  - 関連 `58 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3295 tests OK`

### 20. Regression Memo 追記

- `farm_result` fallback は `facts` の先頭に team result sentence があると、そのまま `stat_facts` にも流れやすく、`【二軍個別選手成績】` が team score の繰り返しになりやすい。
- 今回は `lead_fact` と一致し、かつ score と勝敗 marker を持つ sentence だけを `stat_facts` から外す narrow rule に絞った。
- 数字を含む個人成績 line は残すため、`ティマが2安打3打点` や `山城京平は3回1失点` のような fact は維持される。
- `farm_lineup`、`postgame`、通常 `game_result` にはこの dedupe を広げていない。

#### 2026-05-09 JST / 成績 第1段

- 対象: `成績 / stats`
- 変更: `A + B + D` に寄せる narrow 調整
- ねらい:
  - `screen-level 成績` が `player_status` 風の generic 文へ落ちる状態を止める
  - `打率 / 本塁打 / 打点 / 防御率 / 投球回` など、source にある数字を先に見る本文へ寄せる
  - `二軍戦や調整登板`、`次の登板や一軍合流` のような status story 文言を stats 記事へ混ぜない
  - `player_notice` や `player_recovery` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `stats` 専用の safe fallback helper を追加
    - `build_news_block(...)` から safe fallback へ落ちるとき、routing 済みの `body_subtype` を `article_subtype_override` として渡せるようにした
    - `選手情報 + stats` のときだけ `成績を整理します。` を起点に、数値軸の本文へ寄せる
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_stats_safe_fallback_avoids_status_story_language`
  - `test_build_news_block_stats_fallback_respects_stats_subtype`
- 結果:
  - 修正前 red (`article_subtype_override` 未対応、かつ status story 文言が混入)
  - 修正後 green
  - 関連 `53 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3297 tests OK`

### 21. Regression Memo 追記

- `screen-level 成績` は routing 上 `body_subtype=stats` を持っていても、safe fallback 側に専用分岐がないため、generic な `選手情報` fallback へ流れていた。
- その結果、成績記事でも `二軍戦や調整登板`、`次の登板や一軍合流` のような status story 文言が出やすかった。
- 今回は `stats` 専用 helper を追加し、fallback に落ちるときだけ routing 済み `body_subtype` を明示的に尊重するようにした。
- 変更は `stats` 経路に限定し、`player_notice`、`player_recovery`、通常 `player_comment` には波及させていない。

#### 2026-05-09 JST / ニュース 第1段

- 対象: `ニュース / generic off-field news`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - `ファンクラブ / グッズ / イベント / 発表` の generic news に `次の試合や起用` という不適切な watch line が入る状態を止める
  - 発表・案内記事では、追加案内や具体化を追う neutral な文へ寄せる
  - `試合結果 / lineup / player_status / manager` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `off-field news` を marker ベースで拾う helper を追加
    - `safe fallback` の generic branch で、その記事だけ `watch_line / closing` を neutral 文へ差し替える
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_generic_news_safe_fallback_avoids_game_or_usage_watch_line`
  - `test_build_news_block_generic_news_fallback_uses_neutral_watch_line`
- 結果:
  - 修正前 red (`次の試合や起用` が generic news に混入)
  - 修正後 green
  - 関連 `55 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3299 tests OK`

### 22. Regression Memo 追記

- `screen-level ニュース` は manual-intake 上 `コラム / other` を共有するが、本文 fallback は `generic news` として共通化されていた。
- その結果、`ファンクラブイベント` や `グッズ発売` のような off-field news でも `この動きが次の試合や起用にどうつながるか` という sports-action 寄りの文が入りやすかった。
- 今回は `発表 / 開催 / イベント / グッズ / チケット / ファンクラブ / 販売 / 発売 / 案内` marker を持つ記事だけに neutral watch line を当てた。
- 変更は `off-field generic news` に限定し、`試合速報`、`選手情報`、`首脳陣`、`補強・移籍` の既存 watch line には波及させていない。

#### 2026-05-09 JST / 番組情報 第1段

- 対象: `番組情報 / program`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - `5月12日18時` のような和文時刻が `18` だけ欠ける状態を止める
  - 放送日時を generic にぼかさず、source にある `月日 + 時刻` をそのまま出す
  - `ニュース / コラム / 動画` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `PROGRAM_TIME_TOKEN_RE` を追加
    - `program` の schedule 抽出だけ `18時` / `18時30分` を拾えるように変更
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_program_rule_based_keeps_japanese_hour_schedule`
- 結果:
  - 修正前 red (`放送・配信日時は5月12日です。`)
  - 修正後 green
  - 関連 `56 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3300 tests OK`

### 23. Regression Memo 追記

- `program` の日時抽出は `HH:MM` 前提の token regex に寄っており、和文の `18時` / `18時30分` を schedule line に残せていなかった。
- 今回は `program` 専用の時刻 token に限定して widen し、他 route の time parse には広げていない。
- 変更は `program` の schedule label 抽出 1 箇所だけで、`試合速報` や `pregame` の score / state 認識には波及していない。

#### 2026-05-09 JST / コラム 第1段

- 対象: `コラム / other`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - generic な `コラム` に `次の試合や起用` という強すぎる watch line が入る状態を止める
  - 元記事が整理した論点や数字を、そのまま追う neutral 文へ寄せる
  - `ニュース / 番組情報 / 動画` や既存の `notice / recovery` rescue route には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `category == "コラム" and article_subtype in {"", "other"}` の generic branch に neutral `focus_line / watch_line` を追加
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_generic_column_safe_fallback_uses_neutral_column_watch_line`
- 結果:
  - 修正前 red (`この動きが次の試合や起用にどうつながるか` が混入)
  - 修正後 green
  - 関連 `57 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3301 tests OK`

### 24. Regression Memo 追記

- `コラム / other` は `generic news` と同じ default watch line を共有していたため、分析・整理型のコラムにも `次の試合や起用` が入りやすかった。
- 今回は `コラム` の generic branch にだけ neutral line を足し、`off-field news` 用の marker 分岐より後ろに置いた。
- そのため `notice_like_column` や `recovery_like_column` の rescue route、`off-field generic news`、`program` には波及していない。

#### 2026-05-09 JST / 動画 第1段

- 対象: `動画 / video promo -> program route`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - `【動画】...` の rule-based 本文で `YouTube` を媒体名として出せるようにする
  - `出演者: 阿部監督 / で阿部監督` のような壊れた host line を止める
  - `program / news / column` の他 route には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `RULE_BASED_PROGRAM_CHANNEL_MARKERS` に `YouTube` を追加
    - `program host` 抽出で先頭の助詞ノイズを除去する narrow 正規化を追加
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_video_rule_based_uses_youtube_channel_and_clean_hosts`
- 結果:
  - 修正前 red (`媒体はYouTubeです。` が欠け、`出演者: 阿部監督 / で阿部監督` が出る)
  - 修正後 green
  - 関連 `58 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3302 tests OK`

### 25. Regression Memo 追記

- `【動画】` タイトルの一部は `program` route に流れるが、channel marker に `YouTube` がなく、媒体名が空のままになっていた。
- あわせて host regex が前置助詞ごと拾うため、`で阿部監督` のような壊れた出演者名が `出演者` 行に残り得た。
- 今回は `program route` の marker と host 正規化だけを狭く直し、`summary` 本文そのものの fact line や `program` の構造は変えていない。

#### 2026-05-09 JST / farm_lineup 第1段

- 対象: `farm_lineup / 二軍スタメン`
- 変更: `A + B` に寄せる narrow 調整
- ねらい:
  - `【二軍試合概要】` と `【二軍スタメン一覧】` の両方に同じ `スタメンを発表した` 告知文が出る重複を止める
  - 実際の打順・先発情報は `【二軍スタメン一覧】` に残す
  - `farm_result` や通常 `lineup` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `_build_farm_lineup_safe_fallback(...)` の `lineup_facts` 抽出で `スタメンを発表` 告知文だけを除外
  - `tests/test_farm_body_template.py`
- 追加回帰:
  - `test_farm_lineup_safe_fallback_does_not_repeat_lineup_announcement`
- 結果:
  - 修正前 red (`巨人二軍がDeNA戦のスタメンを発表した。` が 2 回出る)
  - 修正後 green
  - 関連 `16 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3303 tests OK`

### 26. Regression Memo 追記

- `farm_lineup` の fallback は summary の先頭 2 fact を `【二軍試合概要】` に置いたうえで、同じ `facts` を `【二軍スタメン一覧】` の素材にも再利用していた。
- そのため、`巨人二軍がDeNA戦のスタメンを発表した。` のような告知文が overview と lineup の両方に重複していた。
- 今回は `farm_lineup` branch の `lineup_facts` 抽出だけを狭く直し、`スタメンを発表` 告知文だけを `【二軍スタメン一覧】` から除外した。
- `1番浅野翔吾、4番ティマ、先発は西舘勇陽投手。` のような実際の並び fact は残るため、情報量は落とさず重複だけを減らしている。

#### 2026-05-09 JST / 画像 fallback 第1段

- 対象: `featured image fallback / player・manager story`
- 変更: `阿部監督で統一` ではなく `主語一致時だけ人物画像` に寄せる narrow 調整
- ねらい:
  - `選手情報 / player` や `首脳陣 / manager` で人物名が取れるのに、先に generic fallback URL を入れてしまう状態を止める
  - その後段で `player_eyecatch_resolver` に主語一致の WP media を選ばせる
  - `試合速報 / pregame` などの generic story fallback には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `_ensure_story_featured_images(...)` で `("選手情報", "player")` と `("首脳陣", "manager")` のみ、`detect_person(title)` が取れる場合は generic fallback URL を入れずに後段 resolver へ委譲
  - `tests/test_featured_media_helpers.py`
- 追加回帰:
  - `test_story_fallback_skips_generic_image_for_detectable_player_story`
- 結果:
  - 修正前 red (`選手情報 / player` でも generic fallback URL が入る)
  - 修正後 green
  - 関連 `26 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3304 tests OK`

### 27. Regression Memo 追記

- 従来の `_ensure_story_featured_images(...)` は、対象 subtype なら `player / manager` でも一律で generic fallback URL を返していた。
- そのため、タイトルから人物名が読める記事でも、後段 `wp_client -> player_eyecatch_resolver` の主語一致 eyecatch より先に generic fallback が確定し、記事主語と画像主語がズレやすかった。
- 今回は `player / manager` のみを狭く扱い、`detect_person(title)` が成功したときだけ URL fallback を抑止した。
- `pregame / lineup` など人物主語でない story fallback は従来どおり generic URL を使うため、featured_media coverage の既存挙動は広くは変えていない。

#### 2026-05-09 JST / 選手情報 当日成績テーブル 第1段

- 対象: `選手情報 / player`
- 変更: 主語が取れる記事だけ、既存入力にある数字を `表形式` で追記する narrow 調整
- ねらい:
  - `title / summary` に含まれる `打率 / 本塁打 / 打点 / 盗塁` を、本文の後段で見やすい `当日成績` テーブルに整理する
  - 主語不明の記事や数字がない記事では何も出さない
  - 外部成績 source や LLM 補完は使わない
  - `player_comment / stats / game` など他 route には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `_extract_player_daily_stat_rows(...)` を追加し、`title + summary` から `打率 / 本塁打 / 打点 / 盗塁` を抽出
    - `body_category == "選手情報" and body_subtype == "player"` かつ `_extract_subject_label(...)` で主語が取れた場合だけ rows を組む
    - `_player_daily_stat_block(...)` を追加し、`📊 {主語}の当日成績` テーブルを follow-up section に挿入
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_player_story_renders_subject_named_daily_stat_table`
- 結果:
  - 修正前 red (`📊 浅野翔吾の当日成績` テーブルが出ない)
  - 修正後 green
  - 関連 `59 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3305 tests OK`

### 28. Regression Memo 追記

- `選手情報 / player` の safe fallback は、主語と数字が source にあっても、数値 fact を見やすく並べる共通 slot を持っていなかった。
- そのため、`今季打率.280、2本塁打、14打点、5盗塁` のような事実が summary に含まれていても、本文では通常の説明文に埋もれやすかった。
- 今回は `player` route だけに限定し、`_extract_subject_label(...)` で主語が取れ、かつ `title / summary` に数字がある場合だけ table を出すようにした。
- 数字は `打率 / 本塁打 / 打点 / 盗塁` の 4 種に限定し、見つからない項目は行ごと出さない。
- 外部 source 追加や最新成績補完はしていないため、コスト増や推測混入はない。

#### 2026-05-09 JST / 選手情報 前文 + 当日成績表 + 確認事実 第2段

- 対象: `選手情報 / player`
- 変更: `前文の文脈 1 行` と `確認できる事実` を追加する narrow 調整
- ねらい:
  - `主語つき要約 1〜2文` の前文で、巨人ファンが先に知りたい `日付 / 相手 / 球場` を 1 行で伝える
  - `当日成績テーブル` の下に、source から確認できる `一軍・二軍の状態 / 打順・守備位置 / コメント対象 / 節目 fact` を 2〜4 行だけ足す
  - `player_comment / stats / notice / game` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `_build_player_front_context_line(...)` を追加し、`日付 / 相手 / 球場` が見えるときだけ前文へ 1 行追加
    - `_extract_player_comment_target_label(...)` と `_extract_player_confirmed_fact_lines(...)` を追加し、`一軍 / スタメン / コメント対象 / 今季初` などを source から抽出
    - `_player_confirmed_fact_block(...)` を追加し、`✅ 確認できる事実` block を follow-up section に挿入
    - safe fallback の `選手情報 / player` だけ、前文へ context line を差し込む
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_player_story_adds_front_context_and_confirmed_fact_lines`
- 結果:
  - 修正前 red（`5月9日のヤクルト戦、東京ドームでの話題です。` と `✅ 確認できる事実` が出ない）
  - 修正後 green
  - 関連 `60 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3306 tests OK`

### 29. Regression Memo 追記

- `選手情報 / player` では、lead に主語は出ても、`いつ / どこ / 誰と` の文脈や、`打順 / 守備位置 / 一軍での状態 / コメント対象 / 今季初` のようなファン向け事実をまとめて見せる slot がなかった。
- そのため、source に `5月9日のヤクルト戦（東京ドーム）では3番右翼でスタメン出場。打撃については「自分の形を出したい」と話した。今季初の3番起用となる。` のような情報があっても、本文前半では埋もれやすかった。
- 今回は `player` route だけに限定し、`日付 / 相手 / 球場` は前文 1 行、`一軍・二軍の状態 / 打順・守備位置 / コメント対象 / 節目 fact` は `✅ 確認できる事実` block に分けた。
- 事実は `title / summary` の明示情報だけを使い、見つからない項目は出さない。
- `player_notice` や `player_comment` の専用 route には触れていないため、既存の notice / quote contract は維持している。

#### 2026-05-09 JST / 選手情報 既存 quote fallback の主観文言 cleanup

- 対象: `選手情報 / player`
- 変更: 既存 `player_quote` fallback の `focus / watch / closing` だけを fact-based に締める narrow 調整
- ねらい:
  - `見たい記事です`
  - `次に見たいのは`
  - `見たいところです`
  - `見どころです`
  - `追っていきたいです`
  のような主観寄り文を、source にある quote と対象プレーの整理へ置き換える
  - 直前に追加した `前文 / 当日成績表 / 確認できる事実` には触らない
  - `player_comment / stats / notice / game` には波及させない
- 実装メモ:
  - `src/rss_fetcher.py`
    - `_build_player_quote_safe_lines(...)` の 3 文だけ差し替え
    - quote を `確認できる言葉` として整理し、`次の実戦へ向けた意識` と `実際のプレー / 投球との一致` を確認点として記述
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_player_story_adds_front_context_and_confirmed_fact_lines` に主観語の `not in` と fact-based 文言の `in` を追加
- 結果:
  - 修正前 red（`見たい記事です。` が残る）
  - 修正後 green
  - 関連 `60 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox bind 3 error 後、権限昇格で `3306 tests OK`

### 30. Regression Memo 追記

- `選手情報 / player` の quote fallback は、事実 block を追加した後も `【ここに注目】` と `【次の注目】` の既存 3 文が主観寄りのまま残っていた。
- そのため、本文前半に fact-based block があっても、後段で `見たい / 見どころ / 追っていきたい` が出て、deploy 前の「本文全体を fact-only に寄せたい」という基準とぶつかっていた。
- 今回は `_build_player_quote_safe_lines(...)` だけを狭く直し、quote 自体、次の実戦へ向けた意識、実際のプレーとの一致確認、の 3 点に整理した。
- `quote_phrases` や `subject` の抽出経路は変えていないため、どの言葉を拾うかの contract は維持している。
- `player_mechanics_story` や `player_status_story` の別分岐には触れていないので、影響は `player_quote_story` に限定される。

#### 2026-05-09 JST / post-deploy NG repair 3本

- 対象:
  - `player_notice`
  - `player_recovery`
  - `social_news` の lineup-like digest
- 背景:
  - deploy 後の live post `65664 / 65667 / 65669` で route 誤判定が見えた
  - `代打、昇格` のような断片 title が `player_notice` に流れ、`代打 選手` や `2-4。` のような壊れた本文が出た
  - `審判員` 話題が `player_recovery` に流れ、非選手トピックなのに `選手は読売ジャイアンツの選手です。` が出た
  - lineup shorthand の social title が generic `social_news` digest に流れ、不自然な本文になった
- 変更:
  - `player_notice` に主語品質 gate を追加
    - `代打 / 代走 / 先発 / スタメン / 昇格 / 復帰 / 合流 / 審判員` などの stopword 主語では `player_notice` に流さない
    - 外国人選手名も通せるよう、`title_has_person_name_candidate(...)` に加えて `FOREIGN_STATUS_SUBJECT_RE` を許可
  - `player_recovery` に非選手除外 gate を追加
    - `審判員 / 主審 / 球審 / 塁審 / アンパイア` が本文にある場合は recovery route に流さない
  - lineup shorthand 用の social 専用 signal を追加
    - `1-9` の打順数字が 5 個以上あり、対戦相手 / 球場 / 開始時刻などの試合文脈がある social title は `lineup_short` へ寄せる
    - 共通 `_has_lineup_core(...)` は従来どおりに戻し、`farm_lineup` など他 route の既存 contract を守る
- 実装メモ:
  - `src/rss_fetcher.py`
    - `NON_PLAYER_STATUS_ROLE_MARKERS`
    - `STATUS_SUBJECT_STOPWORDS`
    - `FOREIGN_STATUS_SUBJECT_RE`
    - `_is_notice_like_status_story(...)`
    - `_is_recovery_like_status_story(...)`
    - `_has_social_lineup_shorthand_signal(...)`
    - `_select_template_v2(...)`
  - `tests/test_build_news_block.py`
- 追加回帰:
  - `test_weak_notice_fragment_does_not_route_to_player_notice`
  - `test_umpire_injury_topic_does_not_route_to_player_recovery`
  - `test_lineup_like_social_title_routes_out_of_generic_social_digest`
- 結果:
  - 追加回帰 3 本は修正前 red、修正後 green
  - 一時 regress した `notice_body_template` fixture と `farm_lineup` golden も再調整後 green
  - 関連 `122 tests OK`
  - `py_compile` / `compileall` / `ast.parse` OK
  - full suite は sandbox で既知 bind 3 error のみ、その後権限昇格で `3309 tests OK`

### 31. Regression Memo 追記

- `player_notice` 判定は、`昇格 / 合流 / 復帰` marker の有無に寄りすぎると、`代打、昇格` のような断片 title でも route してしまう。
- `player_recovery` 判定は、`回復 / 負傷 / 復帰` marker だけを見ると、`審判員` や非選手関係者の話題を選手記事に誤分類しうる。
- lineup shorthand は social title でよく使われるが、これを共通 lineup signal に入れると `farm_lineup` など既存 fixture を広く巻き込む。
- 今回はこの 3 点を route-level gate として分離し、共通判定は極力動かさず、`social x_post` だけに shorthand 判定を閉じ込めた。
- その結果、live で見えた NG 3 件に対応しつつ、既存 `notice` / `farm_lineup` / `golden` の contract は維持できた。
