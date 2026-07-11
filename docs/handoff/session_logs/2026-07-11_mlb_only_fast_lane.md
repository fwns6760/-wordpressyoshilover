# 2026-07-11 MLB動画 高速引用RT便 (478) + 3万フォロワー計画

- 背景: user「1万アカ達成、目指すは3万」→ 戦略3層(勝ち型集中 / 連載固定化 / 学習ループ)提示、user「全部やる」。固定ポスト刷新は user 却下(やらない)。
- user 追加指示: 「メジャーの動画が日本人より早くほしい。動画が見れるポスト、だから海外のものが良い」→ 478 として即実装。

## log

- 09:59 JST | commit | 478 | `2045c149` | mlb_watch 鮮度順 sort + --mlb-only 軽量便 + tests (283 passed)
- 10:00 JST | push | 478 | origin feat/yt-shorts-motion-and-player-diversity | Cloud Build fire (tag mlbonly-2045c149)

## 3万フォロワー計画 残タスク (次便以降)

1. フォロワー日次スナップショット + 投稿型別の帰属分析基盤(無認証経路は syndication 系全滅を確認済み → RSSHub 経由 or 別経路の設計から)
2. x-engagement 直近30日の型別棚卸し → DAILY_LIMIT 配分再設計
3. 連載2枠のテンプレ設計(試合日データ先読み / 毎晩データ1枚)
- 10:04 JST | deploy | 478 | build 4165386d (clean worktree) SUCCESS 1m46s | image mlbonly-2045c149 job 反映
- 10:05 JST | scheduler | 478 | x-post-mail-flush-mlb-live */10 8-15 JST ENABLED | args --mlb-only
- 10:10 JST | verify | 478 | 初回自然発火 candidates=2 mail送信+dedup記録 ok=True | LIVE
- 10:12 JST | 棚卸し | 3万計画② | x_engagement 4週レポート集計 | quote_comment型が一貫最強(avg fav 45-188)/data_fact型一貫最弱(4-9)→配分見直しは user 報告へ
