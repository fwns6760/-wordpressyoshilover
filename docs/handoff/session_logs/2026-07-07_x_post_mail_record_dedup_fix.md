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

## 11:00/11:05 JST 便での検証結果（prod 確認済み）

- `record_article_dedup_skip` が橋上秀樹 f30ee224 / ダルベック df7d36c2 を正しく block → 重複根治確認
- `reply=3h` cooldown 稼働確認
- TimeoutError 全滅は解消（残: 30R9gmaMUy3guDJ の一過性 503 → 直後 200、retry wave で回収可能）

---

# 追加便2: MLB おりポス増産 + 全体監査 (user 2026-07-07 PM)

## user 依頼

- 「MLBのおりポスが少ないのは？とくに動画でみせたい」→ velvityrose / MasayaKotani / mochiko_dayo17 追加指示
- 「ほかにもおかしいところないか見直して」

## MLB おりポス修正（commit 835c8336, image mlb-835c8336 deploy 済）

1. MLB watch handle +3（上記。実 feed 検証済・動画マーカー多数・非野球投稿は選手名ゲートで落ちる）
2. `mlb_watch_post` を (選手×媒体) media-aware recent 判定へ（12h player cooldown で大谷引用RT が 1 本/12h に絞られていた）

## 監査発見 + 修正（commit 69156d10, image ledger-69156d10 deploy 済）

1. **dedup 台帳の GCS 書き込み競合（重複再発の残存経路）**: read+concat+re-upload が便の同時発火で衝突し record 消失（実測 load 509→505 後退）。便ごと一意 blob (`{date}_{HHMMSS}_{hash8}.jsonl`) 書き込み + 日付 prefix 一覧読みへ変更（旧 day-file も読める、migration 不要）
2. RSSHub timeout 20s→30s: `x_post_engagement`（x-engagement image 再ビルド）/ `sns_realtime_topic`（**fetcher service 経由のため次回 fetcher deploy に同乗、コードは commit 済み**）
3. stale test 根治: `test_sns_realtime_topic` の岡本和真（MLB 移籍で mention 対象外）→ 戸郷翔征差し替え（commit e10d1dac、baseline fail 解消）

## 監査で確認して問題なかったもの

- fan_reply / 報知リプ / quote_caption 各 lane の dedup gate 配線（全部あり）
- fan_reply の metric 群分類（reply 群 ✓）
- `_record_dedup_signatures` の記録漏れ（送信時に全 lane 分記録 ✓）
- fan_voice_pool writer に同じ read+concat 競合があるが低リスク（scrape cache、消えても再取得）→ 未対応のまま

## 残タスク

- ~~x-engagement image ビルド完了後の job update~~ → 完了 (timeout-69156d10)
- 明日 8-12 時 JST の MLB 便で引用RT🎬 の増加確認

---

# 追加便3: MLB動画量産解禁 + ファンリプ +6 (user 2026-07-07 PM)

- user「大谷岡本など動画SNSはだしちゃっていいよ。沢山」→ build_mlb_watch_candidates の上限 param 化
  (commit 29f1d021): 大谷 3/便・選手ごと 2/便 (媒体違いのみ)・日本人スター群 3/便・全体
  X_POST_MLB_WATCH_MAX=8 (env 4→8)。lane default は従来値、rollback は env のみ。
- user 指定ファンリプ +6 handle (commit 8bcaee34 + test 0f06fc86): VIVAfukky2002 / 522happy522 /
  gsoku_giants / G94292907 / karamus_giants / jm7cybh50364 (実 feed 検証済、16→22 handle)
- **prod 最終 image: `x-post-mail-lane:fanmlb-0f06fc86`** (本日の全修正入り) + X_POST_MLB_WATCH_MAX=8
- 翌日確認: 朝 MLB 便の引用RT🎬 本数 / ファンリプ充足 / 重複ゼロ継続 / 台帳 record 消失ゼロ

---

# 追加便4: MLB取りこぼし対策 + 大谷構成 + コスト削減 (user 2026-07-07 PM2)

- feed 50件化 (commit 69e16806): 公式アカ投稿ラッシュで岡本HRクリップがスクロール落ちしていた
- 元巨人のみ鮮度12h (commit dc5161dc, env X_POST_MLB_WATCH_EX_GIANTS_MAX_AGE_HOURS=12): 米デーゲーム=日本深夜分を朝一便で拾う。user「巨人アカがメインだから岡本菅野は外せない」
- 大谷=動画1本+情報系 (commit 8754e386, env OHTANI_MAX 3→2): user「大谷HR動画は一個でいい。他の動画ではなく情報系を拾って」。(選手×媒体×種別) key で同種連投のみブロック
- コスト削減: 平日13-17の15分便廃止 (game-1→平日17-21、土日用 game-wknd 13-21 新設、実測68便/日中送信12便=82%空振り対策)、Artifact Registry cleanup policy (yoshilover 48GB + cloud-run-source-deploy、直近15世代keep/30日超削除)、≈月1,000円削減見込み
- **prod 最終 image: `ohtani1v-8754e386`**
- インプ実測 (7/6週次): quote_comment 59.1fav >> voice 24.6 > article_share 8.7 > data_fact 3.7。時間帯は 17-22時 47.4fav vs 朝 8.7fav (朝52本は配分逆)。名言集シリーズが週間1位761fav

---

# 追加便5: 名言集の引用日バグ根治 (user 2026-07-07 PM3)

- user「名言集、ポストの引用日間違えてる」: 原/吉川 archive のダミー created_at
  (2021-01-01T00:00:XX、並び順用連番、原44/吉川14件 GCS実測) が X 出典
  「（2021/01/01 媒体）」として表示されていた
- fix (commit c93fb4e5): ダミー検出時は媒体名のみ表示 (媒体×日付の事実誤認を排除)。
  小林/坂本=本人tweet由来で影響なし。image `meigen-mail-lane:dateless-c93fb4e5` deploy済
- 次回配信 15:00 JST から修正形式

---

# 追加便6: 手動intake おりポス長文化+引用主体 (user 2026-07-07 PM4)

- user「引用が出るように文字数ふやして」「オリポスながめ。プレミアプランだし」「雑誌の引用がメイン」「引用をオリポスに長めに入れる」
- manual_intake_x_share v3 (commits e5f14b24 + 56f4ef99):
  main weighted 280→900 (X_SHARE_MAIN_WEIGHTED_LIMIT)、本文200〜400字、
  発言『』2〜3個を一文丸ごとliteral引用が主役、地の文=つなぎ最小限、
  記者の地の文コピー禁止 (著作権)、全員フルネーム+巨人/ジャイアンツ (検索KW)
- **scope訂正**: 「オリポス増やして/長めに」をmail便と誤解して入れた ea0031fb
  (候補14件化・全レーン450字化) は revert 済み (188374bd)。mail便は昼の承認状態のまま
- prod: manual-intake-service `quote-56f4ef99` (health 200)
- 名言集ゴールデン帯: scheduler `0 12,17,18,19,20` + `golden-356c7b79` 反映済み (追加便4.5扱い)
- パーク中: 速報レーン提案 (5分poll+速報語→即メール、月200円弱) — user返答待ち
