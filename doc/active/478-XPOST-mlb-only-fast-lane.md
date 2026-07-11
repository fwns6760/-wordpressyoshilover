# 478-XPOST-mlb-only-fast-lane

- **status**: IN_FLIGHT(impl 着地、prod 反映中)
- **owner**: Claude(直接開発・deploy、2026-05-12 全権体制)
- **created**: 2026-07-11
- **user 指示**: 「スポーツ系だからメジャーの動画が日本人より早くほしい。動画が見れるポスト、だから海外のものが良い」(3万フォロワー計画の一部)

## 目的

海外公式 (MLB / Dodgers / PitchingNinja 等) の動画 clip 投稿を、日本語圏のクリップアカより先に引用RT候補としてメールへ届ける。引用RTなら動画がそのままタイムラインで見られる。

## 実装 (commit `2045c149`)

1. `build_mlb_watch_candidates`(src/x_post_mail_lane.py)
   - 動画グループ内の並びを published_at 降順に変更
   - 従来は handle 定義順(=MLBJapan 等の日本語メディア先頭)がそのまま優先になり、海外公式の最速 clip が後回しだった
2. `run_x_post_mail --mlb-only`(src/tools/run_x_post_mail.py)
   - `--live-only` をミラーした MLB watch 単独の軽量便(統合便の insight.db DL + 全 lane を回さない)
   - fetch 対象は `X_POST_MLB_FAST_HANDLES`(既定 = 米国系 10 handle: MLB, Dodgers, BlueJays, Rockies, Cubs, RedSox, PitchingNinja, MLBStats, MLBONFOX, MLBNetwork)。フル 20 handle を高頻度で回すと RSSHub の Twitter 呼び出しが跳ねるため subset。日本語メディアは統合便が従来カバー
   - dedup 台帳は統合便と共有(並走しても同一 clip の二重 mail なし)、候補ゼロは silent skip(mail 洪水防止)
   - Gemini key 不在時は fetch 前に便ごと skip(voice テンプレ埋め禁止の既存方針)
3. tests: 鮮度順 sort / fast handles env / mlb-only gate(tests/test_x_post_mail.py、283 passed)

## デプロイ

- image: `x-post-mail-lane:mlbonly-2045c149`(cloudbuild_x_post_mail.yaml)
- scheduler: `x-post-mail-flush-mlb-live` `*/10 8-15 * * *` Asia/Tokyo、body overrides `--mlb-only`
- 既存 hourly MLB flush(mlb-morning / mlb-13h)は不変(rollback = scheduler pause のみ)

## acceptance

- [ ] scheduler 自然発火で mlb-only 便の log が出る(candidates>0 の便で mail 到着)
- [ ] 統合便との二重 mail が無い(dedup 共有の実地確認)
- [ ] RSSHub 4xx/5xx が跳ねていない(Twitter 呼び出し負荷)

## 不可触

- 既存統合便の MLB watch ブロック / 他 lane / env 既定値(X_POST_MLB_WATCH_MAX 等は共用)
