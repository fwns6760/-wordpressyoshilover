# 2026-07-03 x-post 発言者誤帰属 + record文面ノイズ修正

- 07:07 JST 朝便監査で user 確認 2 件: 候補1 (壊れ文面: 切れURL/ハッシュタグ/名前二重) / 候補2 (キャベッジに坂口智隆氏発言を誤帰属)
- 根因1: long_quote_extractor の proximity 100字緩和 (2026-05-28) で、記事内に名前が出ただけの選手へ他者quoteが付く
- 根因2: _extract_source_record_phrase が X 由来 RSS タイトルのノイズ未除去 + 冠イニシャル表示名と記事表記の不一致で名前二重
- 修正 commit: 93c9f998 (4 files、tests 261+113+15 passed)
- deploy: Cloud Build _TAG=quote-attribution-93c9f998 → x-post-mail-lane Job image 更新 (下記追記)
- 別件 pending: 報道写真添付導線 + 長文丸引用の著作権姿勢は user 判断待ち (推奨: 廃止)
- 07:50 JST | deploy | Cloud Build 6c6b9194 SUCCESS (1m34s) | image x-post-mail-lane:quote-attribution-93c9f998 (sha256:f2027439...) | Job generation 234
- 次便 (09:06 JST 朝便) から新ガード適用。観測: コメント速報の誤帰属 0 / record 文面に URL・#タグ混入 0 を確認する

## 追加便: リプ補足型化 + 対象アカ拡張 + MLBリプ (同日 08:0x-)

- user 指示①「リプの型が長い。感想リプではなく補足リプ。相手が喜んでRTしてくれるもの」→ budget_site=reply を 50〜90字補足型に固定 (db_fact 必須、無ければ skip)
- user 指示②「ay222000 / vto6u / sanspo_giants / koba_nikkan / GIANTSLIFE0801 にもリプ」→ media default に Sanspo_Giants+koba_nikkan、fan default に ay222000+vto6u+GIANTSLIFE0801 (+時刻ローテ)
- user 指示③「30R9gmaMUy3guDJ やメジャー系日本公式で大谷/岡本/菅野にもリプ」→ MLBリプ lane 新設 (as_reply=True 流用、require_db_fact=False、env ENABLE_X_POST_MLB_REPLY)
- 追加発見: src/gemini_model_policy.py が commit 漏れ (committed rss_fetcher が import) → 単独 commit で修復。今朝の quote-attribution image は lineup focus のみ soft 劣化 (クラッシュなし、実行前に発見)
- commit: gemini_model_policy 修復 + 5f444655 (4 files)。tests 368 passed
- deploy: image reply-supplement-5f444655 (下記追記)
- 08:1x JST | deploy | Cloud Build 074d6944 SUCCESS (1m52s) | image x-post-mail-lane:reply-supplement-5f444655 | Job generation 235 | env ENABLE_X_POST_MLB_REPLY=1 追加
- 観測: 次便から (a) リプ候補が50〜90字の補足型か (b) 新handle (Sanspo_Giants/koba_nikkan/fan3件/MLB3件) が候補に出るか (c) 誤帰属0か を確認
- 08:2x JST | env | user「リプはより多めにしたい」| Job generation 236 | REPLY_CANDIDATES_MAX 4→6 / FAN_REPLY_MAX 1→2 / MLB_REPLY_MAX →2 / REPLY_LLM_RESERVE 4→8 / MAX_LLM_PER_RUN 8→12 (非リプ枠4は不変)。コスト影響 概算 ¥40/日 → 最大¥60/日程度 (flash-lite、候補がある便のみ消費)
- 08:4x JST | env | user「今より倍に。特に公式と報知」「その他メディア分散」「他レーンも増やしていい」| generation 237-238 | REPLY 6→12 / FAN 2→4 / MLB 2→4 / RESERVE 8→20 / MAX_LLM 12→24→28 (非リプ 4→8) / VIDEO_RADAR 5→8。code側 e0b9fbc1 = 報知/公式 先頭固定 + その他ローテ (build 中)
- 08:5x JST | deploy | Cloud Build 0a855941 SUCCESS (1m34s) | image x-post-mail-lane:reply-priority-e0b9fbc1 | Job generation 239 | 本日の最終形 = 補足リプ型 + 対象拡張 + MLBリプ + 枠倍増 + 報知/公式先頭固定 + その他ローテ + 非リプ枠8
- 09:2x JST | deploy | user 確定「記事の数字ごと載せる」「【選手名】 内容 画像があるとよい」| commit 1bf25bfb | image record-headline-1bf25bfb | Job generation 240 | record post = 【選手名】+記事内容+記事画像添付、mail 表示「記事記載値」
- 10:0x JST | deploy | user GO「見てる人がその時に欲しい情報でない」対応 | commit 94cb2df7 | image now-context-94cb2df7 | Job generation 241 | 今フック優先選定 (スタメン3/昨日結果2/話題1 + metric固有) + 文脈ゼロ候補2件上限 + pregame 午後再掲 + 死にハンドル除去も同梱
- 09:05 便実測: mlb_reply 1件 / media リプ6件 / fan リプ3件 — 全新レーン初便で作動確認
- 残: RSSHub コールドスタート timeout の無料リトライ修正 (次便) / 補足リプ・記録系・今フックの実物品質監査 (今日の便で)
- 11:0x JST | deploy | user 09:06便FB 3点 (ポスト無い/リプ古い/1連勝) | commit d6268850 | image post-topup-d6268850 | Job generation 242 | env NEWS_PRIORITY_CANDIDATES 3→8 | リプ親ポスト鮮度 6h (X_POST_REPLY_MAX_AGE_HOURS)
- 観測: 11:05 便で (a) ポスト側候補が増えたか (b) リプ対象が6h以内か (c) 今フック並びが効いたか
- 12:0x JST | deploy | user「メジャーは朝からやってる」| commit e3c1d42d | image mlb-age-e3c1d42d | Job generation 243 | MLB引用RT鮮度 12h→20h (MLBJapan/SPOTVは夕方後追い、朝はUS公式+昨日夜分で出す)。MLBリプは6hに統一。20hゲートで朝2件出ることを実feedで確認済
