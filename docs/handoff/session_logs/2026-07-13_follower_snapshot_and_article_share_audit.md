# 2026-07-13 フォロワー計測追加 + article_share縮小調査

15:20 JST | 調査 | article_share縮小 | - | 結論=7/6 user決定(98682962 おりポスURLレス化)の分類副作用。生成停止ではない。復旧不要
15:32 JST | commit | follower-snapshot | eab813d5 | x-engagement にフォロワー日次snapshot (X GraphQL, rsshub-twitter-auth-token 相乗り)
15:36 JST | deploy+verify | follower-snapshot | build 3f059a3b / exec x-engagement-p4kfq | followers/2026-07-13.json 書込確認 (6760=10650, naka=7694)。push済
next | 週次レポート(月曜)に■フォロワー欄が出る。v2候補: classify_style をおりポス+リプ型対応 (x_share_thread_posted ログ突き合わせ)
