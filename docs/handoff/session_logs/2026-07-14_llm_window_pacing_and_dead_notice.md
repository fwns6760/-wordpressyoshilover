# 2026-07-14 LLM窓残高連動pacing + 枠切れ通知/空発火停止 (user GO)

## 背景

- user「10分毎でもメール来ないなら意味なくない?何か設計間違えてる」
- 設計弱点2つ: ①枠配分が固定値の決め打ちで読みが外れると窓の途中で枯れる (7/11 14:05枯渇) ②枯渇後もschedulerが空発火し続け、userには故障と区別がつかない
- 制約: user「重複ガードで厳しすぎて動画がでなくなるのはやめて」→ ガードレール型 (on-trackなら絞らない)
- user「リプは個人に入らんよ。反応ないから」→ リプ増枠は成長施策から撤回 (memory: feedback_reply_to_individuals_no_effect_2026_07_14)

## 変更 (commit 13e5492c, build 737eab8f, image llmpacing-13e5492c)

- GCS台帳 `x_llm_quota/<窓key>/` (INSIGHT_GCS_BUCKET = baseballsite-yoshilover-insight) に便ごとのLLM呼び出し数を記録。窓key=16:00 JST起点
- ガードレール型pacing (`paced_llm_fire_budget`): 残り枠割合 >= 残り時間割合 なら固定capのまま (夜試合帯=窓の頭はフル予算)。先行時だけ等配分squeeze、floor=2
- 全モデルdead検知 (`llm_all_models_quota_dead`) → DEADマーク + 通知mail 1通「本日のLLM枠終了 (16時に自動復帰)」→ 以降の便はfeed fetch前に即skip
- 配線: 統合便(60分)/mlb-only(10分)/buzz-only(15分)/live-only(5分) の4 lane入口 + 各exit点で `_finish_llm_window_accounting`
- env: `X_POST_LLM_PACING_ENABLED`(既定on) / `X_POST_LLM_WINDOW_QUOTA`(450) / `X_POST_LLM_FIRE_FLOOR`(2)。rollback = PACING_ENABLED=0
- 既存固定cap (`_quota_tail_llm_cap` 午後squeeze) は上限として残置

## 検証

- tests 430 passed (pacing 7件新規)
- prod verify: 10:20 JST便 mail sent / exit 0 / 台帳blob `x_llm_quota/2026-07-13/102021_a7acb208.json` = {calls: 3, job: mlb-only} 書込確認
- 残観測: 今晩試合帯(窓の頭)でフル予算維持されるか / 明日午前〜午後にsqueezeが自然発動するか / DEAD通知は実際の枯渇日まで未検証

## 同日午前の別件 (commit 591a6a25)

- MLB動画引用: 映像内容ハルシ防止prompt + 同一プレーclip重複ガード (詳細: 2026-07-14_mlb_video_halluc_and_dupe_guard.md)

## log

- 10:24 JST | commit 591a6a25 + build + deploy | MLB動画ハルシ+重複ガード
- 10:55 JST | commit 13e5492c | pacing 4 files +443行
- 11:07 JST | build 737eab8f SUCCESS → job update llmpacing-13e5492c
- 11:20 JST | prod verify OK | 10:20便 sent + 台帳記録確認 | push済
- next | フォロワー成長の再配分: 週次実測でワースト枠洗い出し→当たり枠(トレンド反応/MLB動画)へ。リプ増枠はしない
