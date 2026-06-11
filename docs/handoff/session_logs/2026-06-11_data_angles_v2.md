# 2026-06-11 データ角度 v2 (勝利相関/対戦別/歴代チェイス + 話題選手連動)

user「ファンが驚く機械学習的なデータはとれるの？」「その試合で話題になった選手がインプとれそう」→「全部やるgo」

- 13:00 JST | impl | `src/x_post_data_angles.py` 新設 (4角度、LLM不使用・新規課金なし) | - | テストへ
- 13:20 JST | bugfix | 周東佑京(SB)混入 → 選手識別を team_name='巨人' に修正 (team_role は陣営ラベル)。fixture 回帰テストで lock | - | -
- 13:30 JST | commit | 角度v2 + win_split カード + runner 配線 (partial stage、469 WIP と分離) | `d5994902` | build へ
- 13:33 JST | build | Cloud Build `45cf959f` SUCCESS 1m26s | image `x-post-mail-lane:data-angles-d5994902` | deploy へ
- 13:34 JST | deploy | Job generation `175` + env `ENABLE_X_POST_DATA_ANGLES=1` / `X_POST_DATA_ANGLES_MAX=3` / `ENABLE_X_POST_TOPICAL_BOOST=1` | - | 次便 verify

## 設計メモ

- **勝利相関**: batting_logs×games join の条件付き勝率 (打点あり/マルチ安打)。閾値 条件側8試合+全体20試合+gap.150。ローカル実測例: キャベッジ 打点あり9勝2敗(.818)/なし14勝17敗(.452)
- **対戦別split**: 対戦打率がシーズン比+.080以上の「対○○キラー」。対戦15打数+シーズン60打数
- **歴代通算チェイス**: alltime_ranking (OB878+現役 npb_career GCS cache) で「あと○本(≦8)で△△に並ぶ」。mail lane は INSIGHT_GCS_BUCKET 既設で cache 取得可。cache 無し環境は graceful 空
- **話題ブースト**: video_radar.fetch_buzzing_players (自前RSSHub) 再利用。focus_player 言及2件以上の候補を stable sort で先頭へ、why_now に「🔥今夜の話題: ○件言及」。compose 直前 (policy gate は順序保持 cap) に挿入
- カード: 新template `win_split` (左orange=条件あり/右dark=なし)。対戦別と歴代は player_spotlight 流用。PNG は builder 内で生成し Candidate.image_bytes 直接添付 (438 bypass path)
- voice-only allowlist に角度3 metric 追加 (2026-06-04 voice-only は「DBランキング生データ枠」排除の意図、角度v2 は 2-pattern ①たんぱく事実型として user 明示 GO)
- サバメ指数なし (勝敗/打率/本数のみ) — [[feedback_data_insight_user_preferences_2026_05_15]] 整合

## 残課題 / 観察

- 次便 (21:50 ETL 後の 22:05 便が本命) で角度候補 + 🔥話題ブーストの実物 verify
- 歴代「年度別シーズン形比較」(今の○○は2007年の△△と同型) は OB 年度別データの新規 scrape が必要 → needs-ticket (今日は通算チェイスまで)
- RSSHub fetch が topical boost で +5/fire 増 (自前 Cloud Run、課金影響なし) — 負荷気になれば video_radar と fetch 共有化
- rollback: env 3 flag を 0 に戻すだけで既存挙動完全復元 (image 据え置き可)

## 追記: DAZN 試合中動画が出ない件 (user 指摘 → 構造要因特定 → fix)

- 14:00 JST | diagnose | DAZN feed 生存確認 (当日投稿+video marker) / 6/10 ログ実測: 試合中便 x_buzz built 0 連発、21時以降のみ built 1-2 | - | 原因=試合中鮮度窓 0.5h × クリップ編集遅延 20-40分
- 14:10 JST | fix | 動画 lane gather に floor 2h (`max(2.0, phase窓)`)、news/fan_voice の 0.5h 不変 | `ea24cbcc` | build
- 14:12 JST | deploy | Cloud Build `b675436c` SUCCESS、image `video-ingame-floor-ea24cbcc`、Job gen `177` | - | 今夜の試合中便で DAZN 引用RT候補の復活を verify

## 追記2: mainportalhuge 文体模倣 + 今夜の主役優先 (user 指摘の連続反映)

- 15:25 JST | feat | streak 記録文脈1行 (「📝N試合連続安打中」N>=3、mainportalhuge型) を勝利相関/対戦キラー post_text に追加 | `e250b22f` | カード画像は維持 (文体だけ模倣、user「カードがあったほうがよい」)
- 15:30 JST | feat | preferred_players: 話題選手 (言及2+) を gap より優先して角度生成 (今夜の主役の驚きを先に)。話題 counts は 1便1回取得で angles/boost 共用 | `6c8a9f24` | -
- 15:32 JST | deploy | image `tonight-pref-6c8a9f24`、Job gen `178` (streak + preferred 同梱) | - | 今夜 22:05 便で verify
