# Prompt Debug 2026-04-15

2026-04-15 時点の「記事生成 prompt」と「ダメだった具体例」を残すメモ。

## 1. まず重要な事実

今回の draft `62068` は、実際には LLM prompt を通っていない。

- 条件: `category == "選手情報"` かつ `has_game == False`
- 分岐: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:3073)
- 実際の本文生成: `_build_safe_article_fallback(...)`
- 実際の呼び出し: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:3146)

つまり `62068` のズレは、「prompt が悪い」だけではなく、

- `選手情報` のオフデイ記事を LLM から外す分岐
- フォールバック本文テンプレ
- Yahoo リアルタイム由来の fan reactions 選定

の3つで起きている。

## 2. 今の prompt の場所

### Gemini strict prompt

- 定義: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:1020)
- 呼び出し: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2647)

`62068` 相当の入力で組み上がる Gemini strict prompt はこれ。

```text
あなたは読売ジャイアンツ専門ブログの編集者です。
以下の元記事タイトルと要約に含まれる事実だけを使って、読者が最後まで読める日本語の記事本文を書いてください。

【使ってよい事実】
・【巨人】田中将大「打線を線にしない」甲子園の“申し子”が移籍後初の阪神戦で好投誓う
・田中将大が移籍後初の阪神戦に向け「打線を線にしない」と話した
・甲子園での登板へ向けた考え方が出たコメントだった

【厳守ルール】
・具体的な事実として書いてよいのは上の「使ってよい事実」にある内容だけ
・数字、順位、成績、日付、契約、故障情報、比較、引用は、上にあるものだけ使う
・検索して新事実を足さない。推測しない。架空の出典を書かない
・試合がない記事ではスコア・勝敗・試合結果を書かない
・元記事に試合結果が出ていない場合は、「勝利しました」「敗れました」など結果が確定した書き方をしない
・見出しは最大3つまで。本文は550〜750文字程度。ですます調
・最初の1文で田中将大に何が起きたかと、何を変えようとしているのかを明確に書く
・材料が少ない場合でも、上の事実を2文に分けて丁寧に言い換えて厚みを出してよい。ただし事実は増やさない
・新聞要約のように1文へ情報を詰め込みすぎない。1段落1論点で書く
・一番上の見出しは必ず「【ニュースの整理】」にする
・2つ目の見出しは基本として「【ここに注目】」を使い、この話題の焦点を整理する
・3つ目を使う場合は「【次の注目】」とし、新事実を足さずに次にどこを見るべきかを1〜2段落で書く
・【ここに注目】では、田中将大が何を変えているのか、外から受けた助言や投げ方の変化がどこに出ているのかを先に整理する
・【ここに注目】では、結果の羅列よりも、フォーム・投げ方・考え方の変化を1つか2つに絞って掘る
・【次の注目】では、次の実戦でどこを見るかを具体的に書く。『今後に期待』『注目される』のような抽象表現だけで終えない
・『可能性があります』『期待が高まります』『注目されます』『重要な意味を持ちます』のような無難語はできるだけ避け、『どこが気になるか』『どこが分かれ目か』で書く
・『詳細が分かれば』『データが出れば』『明らかになれば』のように、元記事にない追加材料待ちで文を埋めない
・抽象語だけで1文を終わらせない。読者が「どこを見る記事なのか」が分かる書き方にする
・同じ言い回しを繰り返さない。「今回の話題は」だけで始めない
・最後は「みなさんの意見はコメントで教えてください！」で締める
・HTMLタグなし、記事本文のみ出力
```

この prompt 自体に、今回の話題とズレるバイアスが入っている。

- 「何を変えようとしているのか」
- 「外から受けた助言や投げ方の変化」
- 「フォーム・投げ方・考え方の変化」

この3つが、田中将大の quote 記事をフォーム変更系に引っ張る。

### Gemini 非 strict prompt

- 定義: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2594)
- カテゴリ別 prompt: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2688)

非 strict 側は Web 検索前提で、`選手情報` にかなり強いデータ要求を入れている。

- 今季打率 / OPS or 防御率 / WHIP
- 昨季比較
- チーム内ランク
- セイバーメトリクス
- 他球団選手比較

元ネタが薄いコメント記事だと、ここも過剰に重い。

### Grok prompt

- 定義: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2872)
- strict prompt: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2892)
- 試合記事 prompt: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2921)
- 試合なし prompt: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2954)

試合なし prompt の中心はこれ。

```text
読売ジャイアンツ応援ブログの記事を書いてください。今日は{today_str}。

タイトル: {title}
要約: {summary_clean}

X検索で「{query_short} 巨人」に関するファンの声を{fan_reaction_limit}件探してください。

【絶対ルール】
・文体は「ですます調」（〜です、〜ます）で統一する
・これは試合記事ではない。スコア・勝敗・試合結果は絶対に書かない・推測もしない
・---SUMMARY---はこのニュースの要点を3〜4文で。選手名・コメント・背景を盛り込む
・---ARTICLE---の最初の見出しは必ず「【ニュースの整理】」にする
・その下の見出しは「【ここに注目】」「【次の注目】」など、論点が伝わる短い見出しにする
・本文は500〜700文字。各段落は3文以内でテンポよく
・数字は上記「タイトル」「要約」に明記されているもののみ使用。書かれていない数字は書かない・推測・架空禁止
・---STATS---はタイトル・要約に含まれる情報のみ。書かれていない数字は省略（空欄可）。試合スコア・勝敗は書かない
・---IMPRESSION---は300文字のブロガー感想（ですます調・最後は「コメント欄で教えてください！」）
・「ファンの声」「Xより」などの見出しは---ARTICLE---内に書かない（---FANS---に書く）
```

こっちは Gemini strict よりはマシだが、

- `X検索で「{query_short} 巨人」`

が広すぎて、今回みたいな quote 記事でも「その日の巨人ファン一般投稿」が混ざりやすい。

## 3. ダメだった具体例

### 例1: draft 62068 の最初の失敗

元記事:

- 投稿ID: `62068`
- source: `スポーツ報知巨人班X`
- source URL: `https://twitter.com/hochi_giants/status/2044162164127052164`
- topic: 田中将大の阪神戦前コメント

最初の悪い出力:

- title: `選手「打線を線にしない」 いま何が変わるのか`
- intro: `選手の現状を整理します。`
- focus paragraph:
  `フォームそのものより、外からの助言を受け入れて投げ方を組み替えているところに今の本気度が出ています。`
- reaction paragraph:
  `反応を見ると、選手の今回の好投そのものより、いまのフォーム変更が次の実戦でも続くかを見たい空気が強いです。`

問題点:

- `田中将大` が title から消えた
- source が「報知新聞からの quote 記事」だと分かりにくい
- 元記事にない `フォーム変更 / 助言 / 投げ方` に話が飛んだ
- 元記事は quote 記事なのに、本文が「調整・改造記事」のテンプレになった

当時混ざっていた fan embeds:

- `https://twitter.com/glaybIsh_29n26y/status/2044190071788843248`
- `https://twitter.com/km89219/status/2044174977084338586`
- `https://twitter.com/forestmoney_net/status/2044173853950390514`
- `https://twitter.com/hold88/status/2044172625887588842`
- `https://twitter.com/Yamashiro_004/status/2044171670173430059`
- `https://twitter.com/g_yktssk9/status/2044169562653118487`
- `https://twitter.com/sixsixmasa/status/2044199062912848226`

問題点:

- quote 記事への反応ではなく、その日の巨人ファン雑談が大量に入った
- 読者目線では「この記事内容と SNS の声が合っていない」になる

### 例2: 62068 の今の残課題

今の live draft:

- title: `田中将大「打線を線にしない」 実戦で何を見せるか`
- source badge: `報知新聞 / スポーツ報知巨人班X`

ここは前より改善した。

ただ、まだ残っている弱さ:

- 本文が薄く、同じ情報を丁寧に言い換えているだけで、整理としては弱い
- `【次の注目】` が quote の言い換えに寄りすぎている
- fan embeds はまだ「その quote に対する反応」ではなく、「今日の田中先発・阪神戦一般」になっている

2026-04-15 09:48 JST 時点で live draft に入っている fan tweets:

```text
@taka_taka3003
おはようございます☀ 甲子園カード初戦勝利💥 則本の好投💥大城卓三の活躍💥 移籍 後初のヒロイン松剛💥 ただワンアウト三塁からの得点圏を2度逃している！才木からあと2点は取れたゲーム🏟️ 今日は 田中将大 先発💥 連勝と行きましょう👍 本日もよろしくお願いします🙇

@Daiki971221
おはようございます☁️。昨日は終盤シーソーゲーム状態でしたが、９回表の剛の決勝点で初戦を制しました⚾🐰✨。甲子園の空模様も心配ですが、今日は田中将大を援護して、開幕戦のリベンジで勝ち越すように頑張ってほしいです⚾🐰✊🏻。
```

これらは「田中将大の quote に対する反応」というより、

- 今日の先発予想
- 今日の試合雑談

に近い。

### 例3: prompt 構造そのもののズレ

今回いちばん大きいのはこれ。

`選手情報` の strict prompt が、comment quote 記事でも強制的に次の型へ寄せる。

- `何を変えようとしているのか`
- `外から受けた助言や投げ方の変化`
- `フォーム・投げ方・考え方の変化`

この型は有効な記事:

- フォーム改造
- コーチ助言
- 復帰調整
- 投球フォーム修正

この型が危ない記事:

- 試合前コメント
- 心構え quote
- 配球意図 quote
- 相手打線への入り方 quote

田中将大の今回の記事は、明らかに後者。

## 4. いま考えるべき修正案

### 案A: `選手情報` を1本にしない

`選手情報` を少なくとも 3 つに分ける。

- `player_mechanics`
- `player_quote`
- `player_transactional`

この分岐を prompt と fallback の両方で持つ。

### 案B: `62068` 系は LLM を通さず「事実ブロック型」に固定する

quote source が薄いときは、むしろ大人しくする。

- 何を言ったか
- どの相手 / どの場面か
- 次にどこを見るか

これだけで十分。

### 案C: fan reactions を「引用語句一致」まで強める

今回なら、最低でも次のどれかが必要。

- `田中将大`
- `打線を線にしない`
- `阪神戦`

さらに理想は、

- `打線を線にしない`

を含まない投稿は fan embed にしない。

## 5. 補足

このメモ時点での current draft は live WordPress から確認した。

- fetched at: `2026-04-15`
- endpoint: `GET /wp-json/wp/v2/posts/62068?context=edit`

必要なら次は、

- prompt をこのファイル上で書き換え案に落とす
- `player_quote` 専用テンプレを先に作る
- fan reaction の採用条件をこの file を元に stricter にする

の順でやるのがよい。

## 6. 全部の「前の失敗」一覧

これは `62068` だけではなく、ログと品質チケットから見えている全体像。

### 6-1. 選手情報

- `61853`
  - セッションログ上の確認 draft
  - 旧版は `要約重複で壊れていた`
  - 修正後も `STRICT_FACT_MODE` の影響で安全版へ落ち、`独自性が弱い / ニュース整理に見える / 短い`
  - `ファンの声（Xより）` も空だった
  - 出典: [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md)

- `62068`
  - `選手「打線を線にしない」 いま何が変わるのか`
  - 本文が `フォーム変更 / 助言 / 投げ方` に誤着地
  - SNS埋め込みが quote 記事への反応ではなく、その日の試合雑談に寄った
  - 出典: このメモの `3. ダメだった具体例`

- 共通失敗
  - `選手情報` の offday 記事は、弱い Gemini を避けるためテンプレに倒した結果、記事によっては薄くなる
  - これは方針として一度 `OK` 判定されていたが、quote 記事では逆に悪さした
  - 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:19) [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:216)

### 6-2. 首脳陣

- 失敗として明示されているもの
  - まだ `実記事で1本確認` が終わっていない
  - ログでも `コメント要約に戻っていないか確認` が未完
  - つまり、テンプレはあるが、本番の実記事品質は未検証
  - 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:35)

- 過去に起きやすい失敗として把握済み
  - 発言の言い回し要約に戻る
  - ベンチの意図ではなく quote の焼き直しになる
  - コメント導線が弱い
  - 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:35)

### 6-3. 試合前スタメン

- 過去の失敗
  - RSS だけでは `17:30〜18:00` の自動実行でもスタメン記事が間に合わなかった
  - そのため Yahoo 固定ページの疑似 lineup 候補補完を追加した
  - 出典: [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:603)

- 記事品質上の過去失敗
  - `誰が入ったか` だけの羅列に寄りやすかった
  - そのため `どこが動いたか` を中心に直した
  - 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:48)

### 6-4. 試合後結果

- 過去の失敗
  - `勝った / 負けた` の要約に寄り、`どこで流れが傾いたか` が弱かった
  - 似た `試合総括テンプレ` の量産が問題視された
  - フォールバックタイトルも一時 `巨人戦 試合の流れを分けたポイント` のような汎用形が強すぎた
  - 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:62) [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:787)

- 事故として出たもの
  - 汎用タイトルが既存公開記事 `61933` の再利用に当たり、古い記事の再投稿につながった
  - 出典: [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:759)

### 6-5. 途中経過 `live_update`

- 実際に起きた失敗
  - `61984` のような、試合中の一時スコア見出しが遅い時間帯に記事化された
  - `古い途中経過記事`
  - 現在は既定で停止
  - 出典: [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:807)

### 6-6. `social_news`

- 実際に起きた失敗
  - URL / ハッシュタグ / 媒体名 / `Type` の混入
  - 動画プロモ記事化
  - source が弱い投稿まで記事化
  - source badge が読み手に伝わりにくい
  - 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:225) [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:249)

- 実際に起きた関連事故
  - アイキャッチなし公開
  - 本文画像と featured image の重複
  - 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:194)

### 6-7. ファンの声

- 実際に起きた失敗
  - Yahoo realtime が 0 件で、記事が単なる整理文になる
  - 逆に取れた時も `記事内容と合っていない反応` が混ざる
  - `62068` が典型例
  - 出典: [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:196)

## 7. 全部の「今の残課題」一覧

### 7-1. 選手情報

- `62068` は前より良いが、まだ薄い
- quote 記事と fan embeds の一致度がまだ弱い
- 実運用で 3 本確認は未完
- 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:30)

### 7-2. 首脳陣

- 実記事で 1 本確認が未完
- `この発言をどう見るか` がコメント導線として本当に機能するか未検証
- 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:39)

### 7-3. 試合前スタメン

- 当日の実記事確認が未完
- 実戦のコメント導線確認がまだ
- 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:56)

### 7-4. 試合後結果

- 実記事で 1 本確認が未完
- `今日のMVP` / `勝負の分岐点` の CTA が本当に語りやすい形か未検証
- 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:67)

### 7-5. 移籍・補強

- 実記事確認が未完
- `大型補強 / 激震` のような煽りに戻らないか監視が必要
- 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:79)

### 7-6. 公示 / 故障・復帰 / 2軍・育成

- 本文型そのものが未完成
- 実記事確認も未着手
- 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:89)

### 7-7. `social_news`

- 直近下書きの source 別棚卸しが未完
- source 別採用条件が未確定
- 夜間ノイズ対策が未完
- `試合総括テンプレ量産` の抑制ルールが未完
- 出典: [TASKS-4-article-quality.md](/home/fwns6/code/wordpressyoshilover/TASKS-4-article-quality.md:225)

### 7-8. fan reactions

- `62068` でもまだ「quote への反応」ではなく「今日の試合雑談」が残る
- 厳格一致ルールをどこまで上げるか未確定
- Yahoo realtime 自体の構造変更リスクは残る
- 出典: [SESSION-LOG-2026-04-14.md](/home/fwns6/code/wordpressyoshilover/SESSION-LOG-2026-04-14.md:153)

## 8. 全部の「prompt / 設計の構造的なズレ」一覧

### 8-1. カテゴリ粒度が粗い

- `選手情報` の中に
  - フォーム改造
  - quote コメント
  - 昇格 / 復帰
  - 2軍調整
  が全部入っている

結果:

- mechanics 記事向けの prompt / fallback が
- quote 記事にもそのまま流れる

### 8-2. prompt を直しても、offday `選手情報` では使われない

- `build_news_block()` で `選手情報 + has_game=False` は既定で `article_ai_mode = "none"`
- つまり prompt 改善だけでは効かない
- 実際には fallback テンプレ改善が必要
- 出典: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:3073)

### 8-3. Gemini strict prompt が mechanics バイアスを持っている

- `何を変えようとしているのか`
- `助言や投げ方の変化`
- `フォーム・投げ方・考え方の変化`

は、フォーム改造記事には合うが quote 記事には強すぎる。

- 出典: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:1033) [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:1065)

### 8-4. Gemini 非 strict prompt が薄い source に対して重すぎる

`選手情報` prompt が要求するもの:

- 今季打率 / OPS or 防御率 / WHIP
- 昨季比較
- チーム内ランク
- セイバー
- 他球団比較

これは薄い comment source には重すぎる。

- 結果として hallucination を誘発するか
- strict mode に逃げて薄くなる

### 8-5. Grok の試合なし prompt の X 検索クエリが広すぎる

- `X検索で「{query_short} 巨人」`

だと、quote 反応ではなく

- その日の試合雑談
- 一般応援投稿
- 試合前の挨拶

まで混ざる。

- 出典: [src/rss_fetcher.py](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:2954)

### 8-6. 「薄い source に 550〜750文字」は構造的にきつい

source fact が 2〜3行しかないのに、

- 見出し 3 つ
- 550〜750文字
- 厚みを出す

を要求すると、どうしても

- 言い換え
- 汎用論
- 誇張

に寄りやすい。

### 8-7. fan reactions が本文設計の一部になりすぎている

- `ファンの声` が 0 件だと記事の熱量が落ちる
- 逆にズレた反応が入ると本文全体の信頼感が壊れる

つまり今は、

- `記事本文`
- `コメント導線`
- `fan embeds`

が強く結びつきすぎている。

### 8-8. source label は UI 問題でもある

prompt の問題ではないが、読者には

- どの記事社情報なのか
- X由来なのか
- 新聞社本体なのか番記者Xなのか

が見えにくいと、記事の理解コストが上がる。

今回の `62068` はこれがはっきり出た。

## 9. ここまで見た上での大きい論点

### 論点A

`prompt を直す` だけでは足りない。

- category 分岐
- LLM routing
- fallback template
- reaction matching
- source labeling

をセットで変える必要がある。

### 論点B

とくに `選手情報` は 1 本ではなく、

- `player_mechanics`
- `player_quote`
- `player_status`

くらいには割る必要がある。

### 論点C

`social_news` は source 別というより、

- 投稿種別
- リンク有無
- quote 強度
- 試合依存度

で絞るほうが筋が良い。
