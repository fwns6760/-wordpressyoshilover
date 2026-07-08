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
