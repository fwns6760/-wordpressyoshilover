# 234 article subtype template contract

## meta

- number: 234
- type: contract / spec
- status: REVIEW_NEEDED
- priority: P0.5
- parent: -
- related: 224 / 225 / 226 / 227 / 227-followup / 229-A / 229-C / 231 / 232 / 113-A / 210e
- created: 2026-04-28

## background

- YOSHILOVER の現在の不安定さは、AI 自由生成が強すぎて、本文 / タイトル / mail / X 候補 / Gemini 呼び出し / freshness の各面で subtype ごとの境界が曖昧なことに起因している。
- 本票は **6 subtype contract を先に固定する非実装 ticket** であり、後続の `234-impl-1` / `234-impl-2`、225 / 231 mail UX、229-C prompt 圧縮、232 no-new-content no-LLM guard、113-A HALLUC candidate router の単一 source of truth にする。
- 本票は **contract doc 1 本のみ**。判定 logic / prompt template / publish gate / Gemini 入力 / live 実行は一切変更しない。
- read-only で確認できた既存 residue として、repo には `lineup` / `postgame` / `farm` / `notice` / `program` / `default` のほか、scope 外の `pregame` / `live_update` / `farm_lineup` / `player_notice` / `fact_notice` / `notice_event` / `manager` が存在する。本票はそのうち **対象 6 subtype** だけを contract 化する。

## 対象 subtype list

| group | name | 用途 | 本票での扱い |
|---|---|---|---|
| current | `lineup` | スタメン発表、予告先発、試合前の打順・先発の事実整理 | 詳細 contract 定義 |
| current | `postgame` | 試合結果、決勝打、継投、試合展開の整理 | 詳細 contract 定義 |
| current | `farm` | 二軍結果、二軍個人成績、一軍への示唆 | 詳細 contract 定義 |
| current | `notice` | 公示、登録抹消、復帰、出場選手登録、注意系告知 | 詳細 contract 定義 |
| current | `program` | 番組、配信、出演、放送・配信予定 | 詳細 contract 定義 |
| current | `default` | subtype が立ち切らない一般記事、fallback 用の安全 shell | 詳細 contract 定義 |
| follow-up only | `manager_comment` | 監督発言。postgame / pregame の subset で source-anchor 必須 | 名前と用途のみ |
| follow-up only | `player_comment` | 選手発言。postgame / SNS source の quote 主体 | 名前と用途のみ |
| follow-up only | `data_note` | スタッツ、順位、セイバー、数字メモ | 名前と用途のみ |
| follow-up only | `video_notice` | YouTube / GIANTS TV の upload notice / 番組動画告知 | 名前と用途のみ |
| follow-up only | `sns_topic` | SNS バズ、トレンド、topic 起点の事実再確認記事 | 名前と用途のみ |
| follow-up only | `rumor_market` | トレード / FA 噂、未確認マーケット情報 | 名前と用途のみ |

後続候補 6 本は **本便で contract 詳細を定義しない**。名前と 1 行用途だけを置き、`234-followup` 以降で個別 contract 化する。

## contract 原則

- 1 subtype 1 shell。別 subtype の語り口を混ぜない。
- title / body / mail / X / Gemini の 5 軸を別々に扱い、どこで保守的に倒すかを明示する。
- fact-first 優先。主語崩れ、一般論、煽り、未確認 placeholder を禁止する。
- subtype ごとに **rule-based で十分な部分は rule-based に寄せる**。Gemini は必要最小限だけに使う。
- freshness / subtype 信頼度が低い場合、X 誤発火回避を優先して review 側へ倒す。

## 6 subtype × 5 軸 contract

### `lineup`

| 軸 | 契約 |
|---|---|
| 1. 本文テンプレ契約 | 何を書く: 対戦カード、球場、開始時刻、`【試合概要】`、`【スタメン一覧】`、`【先発投手】`、`【注目ポイント】`、source にある打順・選手名・予告先発・成績数字。<br>何を書かない: 試合結果予想、元記事にない打順や選手、source にない数字、抽象的な期待論、一般論。<br>禁止表現: 未発表なのに断定、`勝てそう` などの予測、煽り。<br>source 表示方針: source の打順・選手名・球場名・開始時刻・成績数字をそのまま残す。<br>古い source の扱い: 当日性を失った lineup は stale 扱いで review 側へ倒す。<br>Gemini 入力最小単位: **(Codex 補完案、user review 待ち)** `team / opponent / stadium / start_time / lineup_table / starting_pitcher / source_excerpt / source_url`。<br>rule-based で作れる部分: 見出し、打順列挙、先発欄、source fact block、mail metadata、X 候補 skeleton。 |
| 2. タイトル方針 | 入れてよい要素: `巨人スタメン発表`、`〇〇が〇番`、`先発は〇〇`、対戦相手、球場、試合日。<br>入れてはいけない要素: 勝敗断定、先発や打順の推測、一般論、煽り。<br>fact-first 優先: 誰が何番か、先発は誰か、どの試合かを先に置く。<br>主語崩れ防止: 巨人 / 対戦カード / 選手名の主語をずらさない。<br>未解決 placeholder 禁止: `プロ初〇〇`、`救世主`、`サプライズ起用` など source 未確認語は禁止。 |
| 3. メール表示方針 | 投稿候補を出す: clean かつ当日性ありなら可。<br>要確認: source 古い、先発未確定、打順欠落、subtype 信頼低のとき。<br>見送り: stale / past_date / unresolved fallback 適用時。<br>summary: clean なら通常表示、dirty / 曖昧なら短縮または review 扱い。<br>review 理由 日本語: `時点確認待ち`、`古いスタメンのため要確認`。<br>次アクション: 内容確認後 X 投稿候補から選んで投稿。 |
| 4. X 投稿候補方針 | 出しやすい: `article_intro`、`lineup_focus`、`inside_voice`。<br>`fan_reaction_hook` 条件: 当日 lineup、source current、sensitive なし、summary dirty なし。<br>`inside_voice` 条件: 起用意図を source の事実から 1 文で言い換えられるときだけ。<br>出さない: stale、past_date、subtype 不明、先発 / 打順未確定。<br>URL 付き候補は最大 3 本、280 字以内。 |
| 5. Gemini 利用方針 | 不要でよい部分: 打順一覧、先発欄、タイトル骨格、mail class、X 候補骨格。<br>使うならどの部分: `【注目ポイント】` の prose 整理だけ。<br>入力に含める最低限: **(Codex 補完案、user review 待ち)** `team / opponent / stadium / start_time / lineup_table / starting_pitcher / source_excerpt / source_url`。<br>入力に含めない: source 全文、HTML 全文、過去記事全文、無関係 fan reaction。<br>229-C 接続: lineup は全文投入でなく excerpt + structured facts に圧縮。<br>232 接続: no-new-content no-LLM guard を優先し、skip 多めを既定とする。 |

### `postgame`

| 軸 | 契約 |
|---|---|
| 1. 本文テンプレ契約 | 何を書く: `【試合結果】`、`【ハイライト】`、`【選手成績】`、`【試合展開】`、最終スコア、対戦相手、試合日、勝敗、主要打席 1〜3 点、先発と主要継投、source にある数字、source がある場合のみ選手コメント。<br>何を書かない: source にない数字、比較、結果論の誇張、一般論、未確認コメント。<br>禁止表現: `劇的すぎる`, `歴史的` など根拠のない煽り、score がないのに結果断定。<br>source 表示方針: score、回、打点、投球回、失点、安打数などの固有情報を source の表記で残す。<br>古い source の扱い: final score が古い / 追記不足 / freshness 弱いものは backlog / review 側へ倒す。<br>Gemini 入力最小単位: **(Codex 補完案、user review 待ち)** `final_score / opponent / played_on / key_batting_facts / key_pitching_facts / optional_comment_excerpt / source_url`。<br>rule-based で作れる部分: score 抽出、見出し順、主要数値の残存、mail metadata、X skeleton。 |
| 2. タイトル方針 | 入れてよい要素: スコア、勝敗、対戦相手、決勝打や好投など source で確認できる事実。例: `巨人が3-2で勝利`、`〇〇が決勝打`。<br>入れてはいけない要素: 推測、煽り、一般論、source にない `流れを変えた男` などの解釈先行語。<br>fact-first 優先: 最終スコアと勝敗を先に置く。<br>主語崩れ防止: 巨人 / 対戦相手 / 決定的プレーの主語をずらさない。<br>未解決 placeholder 禁止: `プロ初〇〇`、`史上初`, `完全復活` などの未検証語は禁止。 |
| 3. メール表示方針 | 投稿候補を出す: score と key event が揃い、summary dirty でなく、sensitive でもない場合。<br>要確認: score 不足、key event 不足、選手状態がセンシティブ、freshness 弱い場合。<br>見送り: sensitive / roster yellow / subtype 信頼低。<br>summary: clean なら通常表示、review なら理由を日本語化。<br>review 理由 日本語: `試合結果の核が不足`、`センシティブ要素のため X 見送り`。<br>次アクション: clean なら X 候補から選択、review なら記事だけ確認。 |
| 4. X 投稿候補方針 | 出しやすい: `article_intro`、`postgame_turning_point`、`inside_voice`。<br>`fan_reaction_hook` 条件: final score、決勝打 or 継投の核、sensitive なし、dirty なし。<br>`inside_voice` 条件: 試合後に見たいポイントを事実 1 本に絞れるときだけ。<br>出しにくい: コメント source なし、数字弱い、敗戦記事で核が薄い場合。<br>出さない: sensitive、score 不在、subtype 不明。<br>URL 付き候補は最大 3 本、280 字以内。 |
| 5. Gemini 利用方針 | 不要でよい部分: score 抽出、見出し順、mail class、X skeleton。<br>使うならどの部分: 複数事実を prose に束ねる本文本体、postgame parts の組み立て。<br>入力に含める最低限: **(Codex 補完案、user review 待ち)** `final_score / opponent / played_on / key_batting_facts / key_pitching_facts / key_play_facts / optional_comment_excerpt / source_url`。<br>入力に含めない: source 全文、HTML 全文、試合に無関係な過去データ、未確認コメント。<br>229-C 接続: postgame は subtype 別に excerpt 圧縮し、`全文 -> fact block + suspect block` へ寄せる。<br>232 接続: score / key event / source facts が薄いときは無理に新規生成させず skip or review を優先。 |

### `farm`

| 軸 | 契約 |
|---|---|
| 1. 本文テンプレ契約 | 何を書く: `【二軍結果・活躍の要旨】`、`【ファームのハイライト】`、`【二軍個別選手成績】`、`【一軍への示唆】`、二軍結果、注目選手、source にある安打数・打点・投球回・失点などの数字。<br>何を書かない: 一軍記事のような混同、昇格断定、source にない成績、一般論。<br>禁止表現: `即昇格`, `一軍確定`, `完全覚醒` などの断定。<br>source 表示方針: `二軍` / `ファーム` を明記し、数字は source で確認できるものだけ残す。<br>古い source の扱い: 当日性が弱くても postgame よりは保持余地があるが、numeric weak や stale は review 側へ倒す。<br>Gemini 入力最小単位: **(Codex 補完案、user review 待ち)** `farm_result / opponent / standout_players / numeric_lines / one_gun_implication / source_excerpt / source_url`。<br>rule-based で作れる部分: 見出し、数値抽出、二軍表記の固定、mail metadata、X skeleton。 |
| 2. タイトル方針 | 入れてよい要素: `巨人二軍`、選手名、安打数 / 打点 / 投球内容など source で確認できる数字。例: `巨人二軍 浅野翔吾、2安打マルチヒット`。<br>入れてはいけない要素: 一軍昇格断定、source にない比較、煽り。<br>fact-first 優先: 二軍記事であること、誰が何を残したかを先に置く。<br>主語崩れ防止: 一軍と二軍の主語を混ぜない。<br>未解決 placeholder 禁止: `一軍待望論`, `昇格秒読み` などの未検証語は禁止。 |
| 3. メール表示方針 | 投稿候補を出す: 数字と注目選手が揃い、一軍への示唆を 1 本に絞れる場合。<br>要確認: numeric weak、選手名不足、summary dirty、promotion 断定が混じる場合。<br>見送り: subtype 不明、sensitive、stale すぎる場合。<br>summary: clean なら通常表示、review では short excerpt も可。<br>review 理由 日本語: `二軍成績の核が弱い`、`昇格断定は不可`。<br>次アクション: 内容確認後に X 候補を使うか判断。 |
| 4. X 投稿候補方針 | 出しやすい: `article_intro`、`farm_watch`。<br>`inside_voice` 条件: 一軍への示唆を source 事実 1 本で言えるときだけ。<br>`fan_reaction_hook` 条件: 原則なし。本 subtype は fan hook より numeric / watch point 優先。<br>出しにくい: 数字が薄い、汚れた要約、昇格断定の匂いがある場合。<br>出さない: subtype 不明、sensitive、summary dirty 強。<br>URL 付き候補は最大 3 本、280 字以内。 |
| 5. Gemini 利用方針 | 不要でよい部分: 数字列挙、二軍ラベル固定、mail class、X skeleton。<br>使うならどの部分: 数字と一軍示唆を自然な prose に束ねる部分。<br>入力に含める最低限: **(Codex 補完案、user review 待ち)** `farm_result / standout_players / numeric_lines / one_gun_implication / source_excerpt / source_url`。<br>入力に含めない: source 全文、HTML 全文、確証のない昇格予測。<br>229-C 接続: farm は scorecard 全文ではなく numeric excerpt を主体に圧縮。<br>232 接続: no-new-content guard を優先し、rule-based で十分なときは skip。 |

### `notice`

| 軸 | 契約 |
|---|---|
| 1. 本文テンプレ契約 | 何を書く: `【公示の要旨】`、`【対象選手の基本情報】`、`【公示の背景】`、`【今後の注目点】`、対象選手名、登録 / 抹消 / 復帰 / 戦力外などの区分、source にある年齢・ポジション・今季成績などの数字。<br>何を書かない: source にない診断名、全治見込み、復帰時期、感想の膨張、一般論。<br>禁止表現: `朗報`, `悲報`, `電撃`, `完全復活`, `戦線復帰確定` などの煽りや断定。<br>source 表示方針: 公示の日付・区分・選手名・役割は source 表記を優先し、背景も source で確認できる事実だけに限る。<br>古い source の扱い: 日付が古い notice は review、X 候補は見送り。<br>Gemini 入力最小単位: **(Codex 補完案、user review 待ち)** `subject / notice_type / player_role / notice_fact / record_fact / background_fact / source_excerpt / source_url`。<br>rule-based で作れる部分: notice subject/type 抽出、見出し固定、数値抽出、mail metadata、X suppress。 |
| 2. タイトル方針 | 入れてよい要素: 選手名、`一軍登録`、`登録抹消`、`復帰`、`出場選手登録`、日付や区分。例: `浅野翔吾が一軍登録`、`【巨人】浅野翔吾が出場選手登録`。<br>入れてはいけない要素: 感情語、煽り、推測の復帰時期、source にない病状。<br>fact-first 優先: 誰に何の公示が出たかを先頭で明確にする。<br>主語崩れ防止: 選手本人と球団判断の主語を混ぜない。<br>未解決 placeholder 禁止: `プロ初〇〇`, `完全復帰`, `次戦即スタメン` などの未検証語は禁止。 |
| 3. メール表示方針 | 投稿候補を出すか: 原則 `要確認` または `見送り`。notice 系は default で `x_post_ready=false`。<br>summary: clean でも本文確認前提。dirty なら短縮 excerpt のみ。<br>review 理由 日本語: `公示・注意系の記事です(本文確認推奨)`、`登録/抹消/復帰系のため X 投稿候補なし`。<br>次アクション: 記事だけ確認。X 投稿は見送り。 |
| 4. X 投稿候補方針 | 出しやすい: 原則なし。<br>出しにくい: event notice や軽い案内でも慎重側を優先。<br>出さない: 怪我、登録抹消、復帰、戦力外、sensitive、subtype 不明。<br>`inside_voice` 条件: なし。<br>`fan_reaction_hook` 条件: なし。<br>やむを得ず出す場合でも `article_intro` 1 本まで、URL 付き候補は最大 1 本、280 字以内。 |
| 5. Gemini 利用方針 | 不要でよい部分: subject/type 抽出、見出し固定、mail class、X suppress。<br>使うならどの部分: 背景 1〜2 文の接続だけ。<br>入力に含める最低限: **(Codex 補完案、user review 待ち)** `subject / notice_type / player_role / notice_fact / record_fact / background_fact / source_excerpt / source_url`。<br>入力に含めない: source 全文、HTML 全文、source にない診断・復帰見込み・感情語。<br>229-C 接続: notice は `source excerpt + extracted facts` に強く圧縮する。<br>232 接続: no-new-content no-LLM guard を優先し、rule-based で閉じる方向を既定にする。 |

### `program`

| 軸 | 契約 |
|---|---|
| 1. 本文テンプレ契約 | 何を書く: 番組名、放送 / 配信日時、媒体名、出演者、source にある見どころ。<br>推奨構成: **(Codex 補完案、user review 待ち)** `【番組概要】` → `【放送・配信日時】` → `【出演・見どころ】` → `【視聴メモ】`。<br>何を書かない: 見ていない内容の感想、source にない出演者、煽り、過剰な fan voice。<br>禁止表現: `必見`, `神回確定`, `絶対に見逃せない` などの煽り。<br>source 表示方針: 日付、時刻、番組名、媒体名、出演者、配信先 URL などの事実を source の表記で残す。<br>古い source の扱い: 放送 / 配信が過去日時に入った program は review または backlog 扱い。<br>Gemini 入力最小単位: **(Codex 補完案、user review 待ち)** `program_title / platform / date / time / cast / short_synopsis / source_url`。<br>rule-based で作れる部分: 日時抽出、媒体抽出、見出し固定、mail metadata、X skeleton。 |
| 2. タイトル方針 | 入れてよい要素: 番組名、媒体、日付、時刻、出演者。例: `GIANTS TV『〇〇』を4月27日20:00配信`、`巨人関連番組の出演情報`。<br>入れてはいけない要素: 視聴後の感想先取り、煽り、未確認出演者。<br>fact-first 優先: 何の番組がいつどこで見られるかを先に置く。<br>主語崩れ防止: 球団告知 / 番組名 / 出演者の主語を混ぜない。<br>未解決 placeholder 禁止: `超豪華`, `神回`, `初公開だらけ` などの未検証語は禁止。 |
| 3. メール表示方針 | 投稿候補を出す: 未来日時が明示され、媒体・時刻・番組名が揃う場合。<br>要確認: 日時欠落、過去日時、summary dirty、出演者が曖昧な場合。<br>見送り: stale / past_date / subtype 不明。<br>summary: clean なら通常表示、review では日時確認を促す。<br>review 理由 日本語: `放送・配信時刻の確認待ち`、`過去日時のため X 見送り`。<br>次アクション: 日時と媒体を確認後、必要なら X 候補を使用。 |
| 4. X 投稿候補方針 | 出しやすい: `article_intro`、`program_memo`。<br>`inside_voice` 条件: future-dated で、見どころが source 1 本で言えるときだけ。<br>`fan_reaction_hook` 条件: 原則なし。program は期待煽りより schedule fact を優先。<br>出さない: past_date、時刻欠落、subtype 不明、notice 混在。<br>URL 付き候補は最大 3 本、280 字以内。 |
| 5. Gemini 利用方針 | 不要でよい部分: 日時 / 媒体 / 出演者抽出、mail class、X skeleton。<br>使うならどの部分: 見どころ 1〜2 文の prose 整理だけ。<br>入力に含める最低限: **(Codex 補完案、user review 待ち)** `program_title / platform / date / time / cast / short_synopsis / source_url`。<br>入力に含めない: source 全文、HTML 全文、配信を見ないと分からない内容、過去番組レビュー。<br>229-C 接続: program は全文要約より structured schedule compression を優先。<br>232 接続: lineup / program / default の skip 強化対象として扱う。 |

### `default`

| 軸 | 契約 |
|---|---|
| 1. 本文テンプレ契約 | 何を書く: title / summary / source excerpt から確実に言える核だけ。<br>推奨構成: **(Codex 補完案、user review 待ち)** `【記事の要点】` → `【確認できた事実】` → `【次に見る点】`。<br>何を書かない: lineup / postgame / notice / program の専用 shell を無理に流用した prose、推測、一般論、過剰な fan voice。<br>禁止表現: subtype 未確定なのに特定 rail を断定する表現。<br>source 表示方針: 事実核が薄い場合は短く止め、source の表記を崩さない。<br>古い source の扱い: freshness 弱い / topic が古い場合は review or backlog。<br>Gemini 入力最小単位: **(Codex 補完案、user review 待ち)** `title / cleaned_summary / fact_bullets / source_url`。<br>rule-based で作れる部分: summary cleanup、見出し固定、mail metadata、X suppress。 |
| 2. タイトル方針 | 入れてよい要素: 主語、事実核、日付や対象が source で確認できるもの。例: `巨人イベント情報を更新`。<br>入れてはいけない要素: subtype 決め打ち、煽り、未確認の数字、一般論。<br>fact-first 優先: 何が更新されたかだけを短く置く。<br>主語崩れ防止: だれ / なに / どの話題かの主語を曖昧にしない。<br>未解決 placeholder 禁止: `プロ初〇〇`、`悲願`, `衝撃`、`X騒然` などの未検証語は禁止。 |
| 3. メール表示方針 | 投稿候補を出すか: 原則出さない。`default` は clean でも `x_post_ready=false` を既定にする。<br>要確認: summary dirty、subtype 信頼低、freshness 弱い場合。<br>見送り: unresolved / sensitive / stale。<br>summary: clean なら通常表示、dirty は short excerpt のみ。<br>review 理由 日本語: `要約が汚れているため要確認`、`subtype 未確定のため X 見送り`。<br>次アクション: publish 系なら放置可、review 系なら本文だけ確認。 |
| 4. X 投稿候補方針 | 出しやすい: 原則なし。<br>出しにくい: すべて。`default` は subtype 契約未確定のため保守優先。<br>出さない: unresolved、dirty summary、source weak、notice 混在。<br>`inside_voice` 条件: なし。<br>`fan_reaction_hook` 条件: なし。<br>やむを得ず出す場合でも `article_intro` 1 本まで、URL 付き候補は最大 1 本、280 字以内。 |
| 5. Gemini 利用方針 | 不要でよい部分: summary cleanup、title skeleton、mail class、X suppress。<br>使うならどの部分: どうしても prose shell が必要な場合の最小接続だけ。<br>入力に含める最低限: **(Codex 補完案、user review 待ち)** `title / cleaned_summary / fact_bullets / source_url`。<br>入力に含めない: source 全文、HTML 全文、過去記事丸ごと、推測材料。<br>229-C 接続: default は最も圧縮しやすい subtype として扱う。<br>232 接続: no-new-content no-LLM guard の最優先 skip 対象。 |

## subtype 推定外し時の安全側 fallback

226 の `subtype_unresolved` graceful 降格思想を、234 contract 側でも **契約として明記**する。subtype 推定ミスで X 投稿候補が誤発火するのが最大 risk である。

### 契約

| 軸 | 推定ミス時の必須挙動 |
|---|---|
| 扱い | `default` または `notice` 扱い |
| メール表示(軸 3) | **`x_post_ready=false`** |
| X 投稿候補(軸 4) | **`fan_reaction_hook` なし、`inside_voice` なし**。X 候補は **基本出さない**。出すなら `article_intro` 1 本まで |
| メール class(軸 3) | **review 寄り**。`【要確認】` または `【要確認・X見送り】` prefix |
| Gemini 利用(軸 5) | 推測補完禁止。`source excerpt` のみ |

### 具体 trigger

- subtype 推定が `subtype_unresolved` のとき → 上記契約を強制する。
- 推定が `lineup` だが古い source / `past_date` 検出 → 227-followup `backlog_only` 経由で `default` review 扱い + 上記契約を適用する。
- 推定が `postgame` だが score / key event 不在 → `notice` review 扱い + 上記契約を適用する。
- subtype が複数候補で確信度低い場合 → `default` 扱い + 上記契約を適用する。

### 理由

- subtype 推定ミスで X 投稿候補が誤発火することが最大の運用 risk である。
- 慎重側に倒すコストは「投稿候補機会損失」だけだが、誤発火 cost は「誤情報 / 不適切投稿の公開 risk」で非対称に大きい。
- これは contract レベルの安全装置であり、実装は別便 `234-impl-1` で `publish_notice_email_sender` に反映する。反映時は `x_post_ready=false` / `fan_reaction_hook=false` / `inside_voice=false` / `mail_class="review"` を subtype 推定信頼度 low の場合に強制する。

## 既存 ticket 接続 table

| 既存 ticket | 接続軸 | subtype 影響 |
|---|---|---|
| 229-A LLM call audit + cost report | 5. Gemini 利用方針 | subtype ごとの skip / call / cost を分けて観測し、lineup / program / default の「Gemini 不要」を数値で追えるようにする |
| 229-C prompt input compression | 5. Gemini 利用方針 | postgame / farm の Gemini 入力を subtype 別に圧縮し、lineup / notice / program / default は原則 full text を渡さない |
| 232 no-new-content no-LLM guard | 5. Gemini 利用方針 | subtype 別に「Gemini 不要」判定を強化し、特に lineup / program / default で skip を増やす |
| 225 X candidate quality hardening | 3. メール表示方針 / 4. X 投稿候補方針 | subtype 別に `x_post_ready`、候補表示、候補非表示、notice 系 suppress を制御する前提 contract になる |
| 231 review label / mail UX | 3. メール表示方針 | `【要確認】` / `【要確認・X見送り】` の prefix と review 理由日本語を subtype 別に固定する |
| 224 article entity-role consistency | 1. 本文テンプレ契約 / 2. タイトル方針 | subtype ごとに主語崩れ修正の介入範囲を制御し、notice は控えめ、postgame / farm は事実整理優先にする |
| 226 subtype_unresolved graceful | 推定外し時 fallback | 234 contract で `notice` / `default` 慎重側降格を contract 化する |
| 227 burst freshness | 3. メール表示方針 / 4. X 投稿候補方針 | freshness 弱化時に backlog / review / X off へ落とす基準を subtype ごとに受ける |
| 227-followup burst & freshness follow-up | 3. メール表示方針 / 4. X 投稿候補方針 | `backlog_only` や `past_date` を受けて lineup / program / default を `x_post_ready=false` に降格する |
| 113-A HALLUC candidate router | 4. X 投稿候補方針 / 5. Gemini 利用方針 | notice / data weak / default を high priority HALLUC 候補に寄せ、lineup / postgame は medium 優先に寄せる |
| 210e YouTube / 公式動画 source coverage audit | 1. 本文テンプレ契約 / future subtype split | `program` を将来 `video_notice` に分離可能とし、本票では `program` に内包する前提を置く |

## 後続 subtype 候補(本便では定義のみ、実装なし)

| name | 用途 |
|---|---|
| `manager_comment` | 監督発言。postgame / pregame の subset として、source-anchor 必須で扱う |
| `player_comment` | 選手発言。試合後コメントや SNS quote の慎重な整理に使う |
| `data_note` | スタッツ、順位、セイバー、数字メモ専用の numeric verify 強化 shell |
| `video_notice` | YouTube / GIANTS TV / 公式動画の upload notice や配信告知専用 shell |
| `sns_topic` | SNS バズ / topic を source recheck 前提で記事化する shell |
| `rumor_market` | トレード / FA 噂を `source weak / unconfirmed` 強制付きで扱う shell |

本便では上記 6 subtype を **table contract 化しない**。scope 外とし、`234-followup` 以降で個別定義する。

## 次に実装すべき最小チケット候補

### path 1: subtype template → `publish_notice_email_sender` 反映 (**推奨**)

- scope: `src/publish_notice_email_sender.py` + tests、新規 helper `_subtype_contract_lookup()` 等
- 効果: メール UX 即効改善。225 / 231 拡張が直接効く
- risk: 低。Gemini を触らない。publish gate 不変。225-A 安全 gate 維持
- 想定 ticket 番号: `234-impl-1`

### path 2: subtype template → `rss_fetcher` prompt compression 反映

- scope: `src/rss_fetcher.py` prompt template 修正
- 効果: 229-C と直結し、subtype 別に Gemini 入力を圧縮できる
- risk: 中。prompt 変更で品質回帰 risk があり、fixture test 必須
- 想定 ticket 番号: `234-impl-2` または `229-C` と統合
- 着手前提: 229-A ledger で主因 lane が確定してから。推測作業を避ける

### Claude 推奨

- **path 1 を先**。即効 UX、Gemini risk なし、225 / 231 拡張で済む。
- path 2 は 229-A 結果待ちの後で着手する。

## non-goals

- 実装変更
- subtype 追加実装
- Gemini API call
- prompt 変更
- WP write
- publish 判定変更
- X API 投稿
- GCP live 変更
- secret / env / IAM 変更
- 大規模リファクタ
- 226 graceful 降格 logic 変更
- 224 / 225 / 227 / 227-followup / 229-B の既存 logic 変更
- README / assignments 更新
