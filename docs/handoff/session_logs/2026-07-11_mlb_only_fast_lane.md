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
