# 2026-07-10 X-post インプ強化セッション (Claude直接開発+deploy)

目標 (user): インプを稼いで認知を上げる。ガードは維持。

## 着地 (すべて x-post-mail-lane、最終 image = digesthourly-8f122f1a)

- 10:15 JST | scheduler | x-post-mail-flush-mlb-morning 30 8-13 → 0 8-11 (毎時00分発火、12/13時は既存便と衝突回避)
- 11:00 JST | manual-intake | ef4dcf8f リプに記事クリック訴求 / 9e6943ed 引用文読みどころ選択(literal gate)+おりポス可読性+リプcuriosity gap → revision 00120
- 11:40 JST | live_game | b1620ed2 候補4/便+voice枠4+巨人選手フルネーム化(roster一意解決)
- 12:00 JST | live_game | 6128fe65 劣勢時フーガ風悔しさvoice
- 12:20 JST | trend | a8b0eca7 Google Trends RSS採用(Yahooリアルタイムscrape破損を実測確認) note+🔥タグ
- 12:40 JST | trend | f333ed06 織り込み(gate:literal/数字/名前/長さ)+反応候補、時間粒度dedup(1日1回制限撤廃)
- 12:27 JST | poll | 8594a57b MVP Poll案 → user「アプリはいいかな」で469ab4a3 revert (未deploy、mail完結維持)
- 12:50 JST | trend | 3c33dd6b 反応ポスト優先実行(毎便確実に1本)、35c8bf5c 長文化+構成5パターンローテ+10位まで+総合TOP10参考行
- 13:00 JST | quote-RT | e7c8af86 動画に加え写真📷・記事📰も引用RT候補 (ENABLE_X_POST_QUOTE_RT_ARTICLES=1)
- 13:10 JST | digest | 8f122f1a 毎時の定点観測ポスト(話題選手TOP5言及数+急上昇ワード+読み解き+締め、437カード自動) (ENABLE_X_POST_MORNING_DIGEST=1)

## env 追加 (x-post-mail-lane job)

- ENABLE_X_POST_SEARCH_TREND=1 / ENABLE_X_POST_QUOTE_RT_ARTICLES=1 / ENABLE_X_POST_MORNING_DIGEST=1
- いずれもコード既定 OFF (unit test hermetic 維持)

## 決定事項 / 学び

- user: プレミアム前提で長文OK・毎回アレンジ変更・トレンド毎時・Xアプリ操作必須の施策はNG (Poll却下)
- 読了率(滞在時間)狙い: force_long にフック行必須を追加 (recap にも効く)
- テスト事故: ローカル .env の GEMINI_API_KEY が unit test で実API を呼ぶ → _IntakeBaseTest で遮断 (今後の新LLM経路は env opt-in 方式にする)
- aux LLM 小枠: live_game=4 / trend_weave=3 / morning_digest=1 (共有20枠とは別勘定)

## 次の観察

- 今日の便で: トレンド一覧/🔥タグ/反応ポスト/定点観測がメールに出るか、織り込みが自然か
- 今夜の試合: 観戦候補4件/フルネーム/悔しさvoice
- 1-2週間: x-engagement で 🔥付き vs 通常、長文 vs 短文のインプ比較 → 効かない要素は切る

## PM 追加分 (最終 image = starterac-585373ec)

- 13:40 JST | trend/digest | 80845d34 3カテゴリ化(巨人/プロ野球/MLB)+ですます調+定点カード廃止
- 14:00 JST | mail | 0d4aa01c ranking図解カード env OFF (X_POST_RANKING_CARD_ENABLED=0、選手写真系は継続)
- 14:10 JST | digest | 86862711 話題選手TOP10化
- 14:40 JST | Claude発案 user GO「AとC」 | 585373ec A=予告先発予習(Yahoo試合ページparse、朝/昼/試合前3回、ですます) + C=スタメン発表9人フルネーム列挙(deterministic、変更で再発火)。B(クイズ)は「インプが自然に上がらない」で却下
- env 追加: ENABLE_X_POST_STARTER_MATCHUP=1 / X_POST_RANKING_CARD_ENABLED=0
- 検証観点追加: 16時台便=A試合前枠、17時台=Cスタメン、毎時=定点TOP10+トレンド3カテゴリ

## PM2 追加分 (最終 image = fanpulse-ea146d33)

- 15:00 JST | llm | 615ad277 3.5-flash温存(連鎖最後尾)+RPM短待ちリトライ (13時便で3.5の20/日を昼に食い潰した実測対策)
- 15:05 JST | excerpt | b4a8c8cd 選択2〜4節600-1000字+400字未満は冒頭1200字へfallback / c59a5ea7 選択対象8000字+冒頭偏り禁止 (user「引用が短い/冒頭しか取ってない」)
- 15:10 JST | mlb | 39319bb9 グリフィン+マイコラスを元巨人枠に追加
- 15:20 JST | scheduler | x-post-mail-flush に 14:05 追加 (14:00 lineup便がスタメン窓外で丸ごとskipし毎時カバーが欠ける穴)
- 15:30 JST | trend | ad7f03ec Yahooスポーツトピックス合流 (Googleに野球ゼロの便でも巨人/プロ野球/メジャー行+反応候補素材を確保)
- 15:50 JST | fan_pulse | ea146d33 ファンの反応まとめ (user GO「記事とポスト。昼/試合後。noindex。アイキャッチはルール通り」)。WP記事自動公開+💬ポスト候補、昼=話題選手/23時=試合反応、oEmbed引用、mail-lane job に WP 認証追加
- env: ENABLE_X_POST_FAN_PULSE=1 / WP_URL / WP_USER / WP_APP_PASSWORD(secret)
- 初回実弾: 23:05便 (今日のDeNA戦の反応まとめ記事+ポスト)
- 17:39 JST | scheduler | x-post-mail-flush-lineup 0 12,14,16 → 0 12,14,16,17 (18:15開始日にgame窓が18:00まで開かず17時台mailゼロになる穴。lineup窓=start-4hなので17:00発火は試合日に通る)
- 17:30便(lineup-1730)は gemini-3.5-flash 503連発→3.1-flash-lite fallback で生成遅延、実行10分超を観測
- 17:52 JST | incident | 17:30 lineup便 attempt1 が task timeout 600s で mail送信前にkill (機能増+3.5-flash 503 fallback+RSSHub timeout×11源×2パスで10分超過)。attempt2 が 17:47:24 に status=sent で送達
- 17:46 JST | fix | x-post-mail-lane task-timeout 600→1200s (gcloud run jobs update)。残課題: RSSHub twitter route全源read timeout / 3.5-flash 503常態化は要観察
