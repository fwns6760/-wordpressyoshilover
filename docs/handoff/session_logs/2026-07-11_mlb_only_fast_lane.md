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
- 17:49 JST | scheduler変更 | lineup mail重複解消 | x-post-mail-flush-lineup を `0 12,14,16,17` → `0 12,14,16` に縮小(17:00発火削除、17:30便=x-post-mail-flush-lineup-1730 に一本化) | 理由: 17時台にlineup mailが2通、17:00便が候補を先食いし17:30便がfallback生成でLLM二重消費(16時枠リセット直後)。次: 明日17時台のmail 1通化を確認
- 18:01 JST | scheduler変更 | LLM収支黒字化(user go) | 23時便削除(x-post-mail-flush 5 7,12,14,15) / live便 5分→15分毎(live-wkday 4-59/15 17-22, live-wknd 4-59/15 13-22) / game flush 15分→30分毎(game-1・game-wknd 0,30 17-21) | 理由: user「放送時間帯はリアルタイム投稿できないので減らしてよい」。MLB朝便は user 指示で */10 のまま不変(一度*/20にして即revert)
- 18:01 JST | note | 収支見込み | 需要~660-690→~450/日 vs 供給~550/日で黒字化。明日16時まで全lane無停止の見込み。7/13(月)のwknd game便cron revert計画は live-wknd 変更(4-59/15)を踏まえて要再確認
