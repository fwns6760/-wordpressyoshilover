# 2026-07-03 x-post 発言者誤帰属 + record文面ノイズ修正

- 07:07 JST 朝便監査で user 確認 2 件: 候補1 (壊れ文面: 切れURL/ハッシュタグ/名前二重) / 候補2 (キャベッジに坂口智隆氏発言を誤帰属)
- 根因1: long_quote_extractor の proximity 100字緩和 (2026-05-28) で、記事内に名前が出ただけの選手へ他者quoteが付く
- 根因2: _extract_source_record_phrase が X 由来 RSS タイトルのノイズ未除去 + 冠イニシャル表示名と記事表記の不一致で名前二重
- 修正 commit: 93c9f998 (4 files、tests 261+113+15 passed)
- deploy: Cloud Build _TAG=quote-attribution-93c9f998 → x-post-mail-lane Job image 更新 (下記追記)
- 別件 pending: 報道写真添付導線 + 長文丸引用の著作権姿勢は user 判断待ち (推奨: 廃止)
- 07:50 JST | deploy | Cloud Build 6c6b9194 SUCCESS (1m34s) | image x-post-mail-lane:quote-attribution-93c9f998 (sha256:f2027439...) | Job generation 234
- 次便 (09:06 JST 朝便) から新ガード適用。観測: コメント速報の誤帰属 0 / record 文面に URL・#タグ混入 0 を確認する
