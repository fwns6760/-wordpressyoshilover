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

## 残課題 (次フェーズ)

- syndication endpoint は非公式 = 仕様変更リスク。メトリクス取得失敗はレポート末尾に件数明記 (silent skip 防止済)。
- retweet_count は無料経路で取れない (Hermes x_search ローカル便で補完可能、未着手)。
- レポート蓄積後: 型別/時間帯別の平均♥で X_POST 枠配分を変更する便 (効果学習の本体)。
- 連投スレッド (缶詰45%/フーガ28%) / ポールは計測が回ってから。
