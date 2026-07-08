# 2026-07-08 x-post-mail-lane スケジュール間引き + LLM 予算整合

背景: user 指摘「クラウドランがむだになる。スケジュールがおかしい。忙しすぎる」。
実測: 平日 56 fire/日 × LLM budget 48 → Gemini 無料枠(flash-lite 500/日)が昼前に枯渇、
429 が 808 回/24h。枯渇後の fire は LLM 生成不能のまま Cloud Run 実行だけ消費。

## 変更(Scheduler, Asia/Tokyo)

| job | 旧 | 新 | fire/日 |
|---|---|---|---|
| x-post-mail-flush | 5 7-17,23 | 5 7,12,15,23 | 12→4 |
| x-post-mail-flush-mlb-morning | */30 8-12 | 30 9,11 | 10→2 |
| x-post-mail-flush-lineup | 20,40 11-17 | 0 12,14,16 | 14→3 |
| x-post-mail-flush-game-1 | */15 17-21 (平日) | */30 17-21 (平日) | 20→10 |
| x-post-mail-flush-game-wknd | */15 13-21 (土日) | */30 13-21 (土日) | 36→18 |

平日合計 56→19 fire/日 (-66%)、週末 ~72→27。
02:08 UTC 追加 user 指摘「朝が多い」→ 朝帯を再間引き(7:05 / 9:30 / 11:30 の 3 発、旧 6 発)。
12:00/12:05 の二重発火も解消(mlb を 9:30,11:30 へ移動)。

## 変更(Cloud Run job env)

- `X_POST_MAIL_MAX_LLM_PER_RUN` 48→16
- `X_POST_MAIL_REPLY_LLM_RESERVE` 36→12(予約比 75% 維持)

日次 LLM 上限見積: 平日 21×16=336、週末 29×16=464 < flash-lite 無料枠 500/日。

## 残タスク(未実施)

- 429 daily-quota circuit breaker(run 内で日次枯渇検知→残り LLM 呼び出し即スキップ)
- RSSHub timeout(巨人公式X / 報知巨人班X fetch が毎便 TimeoutError)
- dedup 枯渇時の全ソース再スキャン(1 便内二重スキャン)

02:06 UTC | scheduler 5 job update + jobs update env | 直接実行(2026-05-12 全権) | next=翌日 429 件数を観測

## PM: LLM無料枠対策3点 実装+deploy (user GO)

03:14 UTC | commit d57fea10 | day-quota breaker(日次429→16時JSTまでmodel dead、RPM対象外) + 作り直し3→env X_POST_GEN_ATTEMPTS(既定1) | tests 393 passed / 全体45 fail=baseline同一
03:17 UTC | x-post-mail-lane job image quotabreaker-d57fea10 + env X_POST_MAIL_MAX_LLM_PER_RUN 16→10 / REPLY_LLM_RESERVE 12→8 | 直接実行
03:19 UTC | manual-intake-service rev 00116-8wr (同tag) traffic 100% | 直接実行
- 期待効果: 消費 概算半分以下(便あたり上限24→18 + gate落ち再生成廃止) + 枠切れ後の429 storm停止
- 観測: 今夜試合帯→明日朝の lite PerDay 429 初出時刻(昨日=翌8:00 JST)と x_post_llm_daily_quota_dead ログ
- rollback: env X_POST_GEN_ATTEMPTS=3 + 上限env戻し + 旧image tag(revfallback-bf3cc064)
- user 判断保留: それでも枯れる場合の有料キー化。SNSMONEY枠の転用は規約グレー+7/7分離の逆流になるため非推奨で合意

## PM2: 緊急fallback連鎖 2.5世代 追加 (user GO、順序=品質優先はuser指定)

04:52 UTC | commit 8d42bd12 | fallback chain化: 3.5→3.1-lite→2.5-flash→2.5-flash-lite (全段day-quota breaker、モデル別無料枠の合法活用) | tests 394 passed / 全体45 fail=baseline同一
04:53 UTC | x-post-mail-lane job image emergency25-8d42bd12 + manual-intake-service rev 00117-vck | 直接実行
- 2.5-flash / 2.5-flash-lite が prod key で有効なことは models.list で事前確認済み
- 無効化/順序変更: env X_POST_GEMINI_EMERGENCY_MODELS

## PM3: yt-shorts legend形式 QC全落ちバグ修正 (恒久対応)

07:43 UTC | commit a02d7079 | legend narration に BRAND_CLOSING_LINE 欠落 → QC「締めヨシラバー無し」で毎回 qc_failed (7/8 王貞治回で発覚)。LEGEND_CLOSING 直前に挿入 + 再発防止 test | yt-shorts tests 134 passed
07:47 UTC | yt-shorts-gen job image brandclose-a02d7079 (恒久) + 今日分の再生成 execute (8ghqf) | 直接実行
08:06 UTC | commit b60ef4cd | loudnorm一発掛けがナレーション末尾を約3秒切る (repro: 30秒トーン→27.25秒)。aresample=24000追加で全尺化 | yt-shorts-gen image audiofix-b60ef4cd + 再々生成 (j8pwz)

## PM4: 名言レーン画像404 (share_x_cand lifecycle事故) 復旧

08:25 UTC | 原因=bucket lifecycle (share_x_cand/ 7日削除) が吉川/原の名言アーカイブ画像(恒久物)も削除、mail画像ボタン404でポスト失敗 | user報告で発覚
08:25 UTC | 対処① lifecycle prefix を share_x_cand/20 (日付名の使い捨てdirのみ) に限定 ② アーカイブの元URLから再取得し復元 (yoshikawa 43枚 / hara 50枚、失敗0) | 小林・坂本はtext-onlyで無傷
08:31 UTC | user GO (Cloud Run費用増ほぼ無しを確認の上) | リプ強化: env MAX_LLM_PER_RUN 10→14 / REPLY_LLM_RESERVE 8→12 (リプ以外は2のまま) + scheduler x-post-mail-flush-game-1 */30→*/15 17-21 平日 | 観測=今夜の枠消費と明朝の生存
08:39 UTC | user 方針「朝=MLB、夕方から=巨人」 | 実測根拠: 朝5-11時=52本/中央値4いいね(最弱)、当たりは全部17-22時。MLB朝便 30 9,11 → 30 8-13 (毎時6本)。朝MLB実績はn=3で未証明=実験扱い、来週のengagement reportで検証
09:20 UTC | commit be084d4a+74407454 | ①voice考察に論点型指示(リプ獲得) ②_cap_sentence改行保持(prompt改行指示が平文化されていた実測バグ) | x-post-mail-lane image kaigyo-74407454 (2修正まとめbuild)。manual-intake側は次回まとめ
10:05 UTC | commit e84e9743 | 巨人戦ライブ実況候補 v0 (NPB公式スコア前便比イベント検出、缶詰voice最大2本/便、aux枠2、ENABLE_X_POST_LIVE_GAME gate) | image livegame-e84e9743 (論点型+改行保持も同梱)。今夜の残りイニングから観測
