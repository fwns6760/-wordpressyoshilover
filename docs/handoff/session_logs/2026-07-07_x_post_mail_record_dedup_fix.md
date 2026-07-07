# 2026-07-07 x-post-mail 記録/節目候補の毎便重複 根治

## user 報告

- 「重複ポストが多いのは何故？」（候補例: 記事記載値｜記録/節目案｜ダルベック / 橋上秀樹）

## 実測（原因確定の根拠）

- GCS ledger `gs://baseballsite-yoshilover-insight/x_post_mail/dedup/2026-07-07.jsonl`:
  - `news_opinion|f30ee224…`（橋上秀樹）が 08:30 / 09:00 / 09:05 / 09:30 / 10:00 / 10:05 JST の **6 回送信**
  - `news_opinion|df7d36c2…`（ダルベック）が 3 回送信
- Cloud Logging: player_comment / news_opinion fallback レーンは `*_dedup_skip` が出て正常動作。record 優先レーンだけ skip ログが皆無
- スケジューラ多重発火（flush 毎時:05 + mlb-morning 30分毎 + game-1 15分毎 + lineup 20/40分）で、鮮度窓内の同一記事が毎便再候補化

## 原因

- `_fetch_record_article_priority_candidates`（記録/節目優先レーン）だけ `dedup_set`（168h GCS ledger）が**未配線**
  - すぐ上の player_comment 優先レーンは `dedup_set=dedup_set` を渡している（run_x_post_mail.py:3527）のに、record レーンは引数すら無かった
  - `recent_player_counts` も「record記事は履歴より鮮度優先」で意図的無視 → 全 dedup 層をすり抜け
- レーン内の `seen_urls` / `existing_player_keys` は run 内ローカルのみで便跨ぎに効かない

## 修正（commit 35ca9f93, feat/yt-shorts-motion-and-player-diversity）

- `x_post_mail_lane.news_opinion_signature(url, player)` を共通ヘルパー化（build_news_opinion_candidate と同一式）
- record レーンに `dedup_set` を配線し、**画像取得 / Gemini plain 書き換えの前に** ledger 照合 skip（`record_article_dedup_skip` ログ追加）
- 回帰テスト追加（dedup 済 signature は image fetch 前に skip）。tests/test_x_post_mail.py 全 273 passed

## deploy

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:dedup-35ca9f93`
- `gcloud run jobs update x-post-mail-lane --image=…dedup-35ca9f93`（旧: mlb3-2280d016、rollback は旧 tag へ戻すだけ）

## 検証

- deploy 後の次便ログで `record_article_dedup_skip` の出現と、ledger に同一 signature の再記録が止まることを確認する

---

# 追加便: リプ候補が出ない + 相手の意見への寄り添い (user 2026-07-07)

## user 報告

- 「リプランがあまり出ないんだけど。どうなの？」
- 「あとリプは相手の意見にもっとよりそって」

## 診断（19h ログ実測）

- RSSHub (min-instances=0) handle fetch timeout **62 件/19h** → MLB/ファンリプの親ポスト取得が便ごと全滅する回あり
- built リプ (fan 5 + mlb 5) に対し `dedup_player_recent` drop 6 件 — 12h の reply 群 cooldown が主犯（MLB リプはほぼ大谷固定なので 12h だと 1 日 1〜2 本に絞られる）
- 報知/公式リプ `raw=0〜2 reason=no_eligible_post_or_dedup`（RSSHub timeout と連動）

## 修正（commit 610f3fe9）

1. empathy prompt: 最初の一文=相手の意見への同意 first を明文化（自分の視点始まり禁止・相手と違う意見禁止）。empathy は選手名 lead 強制を除外、MLB リプ (as_reply) の `_ensure_player_name_leads_post_text` も解除
2. reply 群 recent cooldown を分離: `X_POST_MAIL_REPLY_RECENT_COOLDOWN_HOURS`（default 3h、他群は従来 12h）
3. `video_radar.prefetch_feeds`: 失敗 URL を 1 wave だけ再試行（cold start 対策）

- tests: test_x_post_mail / test_video_radar / test_x_post_branding_gen 394 passed
- image: `x-post-mail-lane:reply-610f3fe9`

## 検証（次便以降）

- `Recent-shown player cooldown (12h, reply=3h)` ログ行の出現
- `mlb_watch fetch skip ... TimeoutError` の減少
- fan/mlb リプ候補数の回復、リプ文が同意 first になっているか（user 確認）
