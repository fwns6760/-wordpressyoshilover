# 2026-06-12 効果学習 v0 (X エンゲージ収集 + 週次レポート)

- 08:05 JST | commit | x-engagement v0 | 4b9b628b | 新規5ファイルのみ (dirty tree 不混入を stat 追認)
- 08:08 JST | build | cloudbuild_x_engagement.yaml | image x-engagement:engagement-4b9b628 | clean worktree から submit (deploy hygiene)
- 08:09 JST | deploy | Cloud Run job x-engagement 作成 | SA=default compute, mail env は x-post-mail-lane から複製 | next=smoke
- 08:10 JST | verify | collect smoke | x-engagement-2v56h Completed | GCS x_engagement/posts/ に 12 blob
- 08:11 JST | verify | report dry-run | x-engagement-w92wh Completed | 実データ 5 投稿 ♥22、型別/時間帯別/TOP5 出力 OK
- 08:12 JST | scheduler | x-engagement-auto-noon (12:30 JST daily, auto=collect+月曜report) / x-engagement-collect-night (23:45 JST daily, collect) 作成
- 08:13 JST | verify | scheduler 手動 fire → x-engagement-j6s54 Completed | scheduler→job 経路 OK
- 08:14 JST | push | feat/377-phase1c-mail-body-excerpt | fc7cafcd..4b9b628b

## 設計メモ (詳細は src/x_post_engagement.py docstring)

- X API Free = read 全 401 のため impression は取得不可。like+リプを代理指標。
- ID/本文/時刻 = 自前 RSSHub /twitter/user/yoshilover6760 (feed 直近 ~12 件 → daily 2 回収集で upsert)
- like/リプ = X syndication endpoint (認証不要・無料、token は id から算出。golden test あり)
- LLM ゼロ・X API write ゼロ。コスト増 = Cloud Scheduler 2 job (~$0.20/月) + 微小 Cloud Run 実行のみ。
- 初回週次レポートメール = 2026-06-15 (月) 12:30 JST 発火予定。
- 初期サンプル (5 投稿): 引用コメント型 平均♥6.0 > voice型 3.5 > データ型 3.0 (サンプル極小、判断はレポート蓄積後)

## 2026-06-12 AM 追記 — 効果学習の初適用: DB ランキング候補停止 + 【】統一確認

- 分析: 6/11 実投稿 12 件 × 実 like。 【】驚き角度 (松本剛チェイス♥5 / キャベッジキラー♥4) vs 直近7日打率 voice (岸田♥0=最下位 / 大城♥1)。 user 方針「驚きのない数字は出す意味がない。記録は残す」「【】マークがわかりやすい」確定
- 09:0x JST | reconcile | 469 deploy済み未commit作業を repo へ反映 | f89a756c | prod image share-fallback-fc7cafcd は dirty tree 込み build だったため (実環境=正)。 テスト4件を実態追従 (TokyoGiants 常時補完 2件 + 時刻依存 flaky 1件 + 実GCS queue drain flaky 1件)
- 08:55 JST | commit | DB ランキング kill switch | 4b39c43e | pick_candidates に X_POST_MAIL_DB_RANKING_ENABLED gate (code default 1)
- 08:43 JST | build+deploy | image x-post-mail-lane:db-ranking-gate-4b39c43 + env X_POST_MAIL_DB_RANKING_ENABLED=0 | clean worktree build
- 08:46 JST | verify | dry-run x-post-mail-lane-vkzzx exit 0 | gate 発動 log 2回 (本線+relaxed)、 残候補 = data_angles チェイス1 + video_radar 1 + リプ2、 mail compose 正常
- 【】統一は実装不要と確認: data_angles / コメント速報 (build_player_comment_candidate) は既に【名前】形式。 非【】の数字投稿は止めた DB ランキング voice 経路のみだった
- 残 dirty (他レーン、未 commit のまま): mkdocs.yml / mkdocs_docs/spec/data-site-no1-design.md / scripts/build_063_wp_admin_bundle.py / src/custom.css / src/yoshilover-063-frontend.php — 063/データサイト lane の作業、 該当 lane で reconcile すべき
- rollback: env X_POST_MAIL_DB_RANKING_ENABLED=1 (即時) または image share-fallback-fc7cafcd へ戻し

## 残課題 (次フェーズ)

- syndication endpoint は非公式 = 仕様変更リスク。メトリクス取得失敗はレポート末尾に件数明記 (silent skip 防止済)。
- retweet_count は無料経路で取れない (Hermes x_search ローカル便で補完可能、未着手)。
- レポート蓄積後: 型別/時間帯別の平均♥で X_POST 枠配分を変更する便 (効果学習の本体)。
- 連投スレッド (缶詰45%/フーガ28%) / ポールは計測が回ってから。
