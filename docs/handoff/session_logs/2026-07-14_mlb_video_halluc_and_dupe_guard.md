# 2026-07-14 MLB動画引用: 映像内容ハルシ防止 + 同一プレーclip重複ガード

## user指摘 2件

1. 「MLBのSNS動画って選手がでてないのに記者のコメントポストをかく。コメントだけでもよいか、内容をまちがえないように」
2. 「動画の重複がある」+ 制約「重複ガードで厳しすぎて動画がでなくなるのはやめて」

## 変更 (commit 591a6a25, build b88ba52a, image samegame-591a6a25)

### ① 動画SNS prompt (x_post_branding_gen.py is_video_sns)

- 「あなたに映像の中身は見えていない。事実は元投稿の本文テキストだけ」を明示
- 場面描写は本文がプレー (HR/好投等) を伝えている時だけ、本文にある要素で具体化
- 記者・媒体・ファンのコメントが主の投稿は、コメント内容への反応だけで成立可 (場面描写を無理に作らない)

### ② 同一プレー重複ガード (x_post_mail_lane.py build_mlb_watch_candidates)

- 引用RTの動画のみ対象。**選手単位の本数制限は追加していない** (別プレーは全部通る = 出なくなる側に倒さない)
- 号数が取れるHR: signature を `mlbevt|sha1(選手|hrN)` に変更 → 媒体違い・URL違い・便またぎでも既存の台帳dedupで1本
- 号数なし動画: 同便内で同一選手の published_at 近接 (45分, `same_play_window_min` param, 0で無効) の2本目だけskip。便をまたぐ時間窓ガードはしない
- カウントダウン文 (「30号に王手」「まで」「あと」「ならず」) は号数と誤認しない (実HR clipの誤ブロック防止)

## 検証

- tests: test_x_post_mail.py + test_x_post_branding_gen.py = 416 passed (新規5件含む)
- 残観測: 次のMLB便 (*/10, 8-15 JST) で候補が正常に出ること / 同一HRの重複が消えること / コメント文が元投稿内容と乖離しないこと

## log

- 09:24 JST | commit 591a6a25 (3 files, 自分の変更のみstage, ambient dirty不混入確認済)
- 09:25 JST | build b88ba52a submit → SUCCESS
- 09:28 JST | gcloud run jobs update x-post-mail-lane → image samegame-591a6a25 反映確認
- 09:29 JST | push origin feat/yt-shorts-motion-and-player-diversity
