# 2026-06-01 — 443/444/445 daily cron 稼働 verify (read-only)

- 445 SNS realtime: ✓ ran=true at 21:04 JST slot (post_count 55, 1gun+farm 両 page updated, save_counts_ok=true)。kill switch active (social_news_sources_disabled, skipped=15, remaining=66)
- 443/444 data-site: ✓ data-site-publisher-daily(06:00)/ -daygame(17:30)/ -nightgame(23:00)/ -backlink-daily(07:15) 全 ENABLED、5/30・5/31 とも scheduler 試行 INFO (2xx 成功)、ERROR 無し
- fetcher service: severity>=ERROR は全件 HTTP 502 on GET /share-x-image-proxy (Googlebot crawl, 20件/2d)。app error ではなく Cloud Run 段の 502。低volume・content endpoint ではない
- 結論: 443/444/445 daily cron は健全。share-x-image-proxy 502 のみ follow-up 候補

# 2026-06-01 — 447 metric #5 inning split DEPLOY 完了

- 状況: 並行 session が code+commit(`7c792bd`, 08:37 JST)+image build(`inning-split-7c792bd`, 08:40 JST)まで実施済、Job 更新のみ未了だった
- Claude が deploy 完了: data-site-publisher Job image を seo-staff-8b5fe9a → inning-split-7c792bd へ flip → execution `data-site-publisher-6l87n` SUCCESS(succeeded=1/failed=0)
- live verify: /data/yoshikawa-naoki 序盤.194(36/7)/中盤.208(24/5)/終盤.286(28/8)、/data/cabbage も section 描画。production 検証値と一致(H 完全一致、AB は live DB が 1 試合新しく ±1)
- 実装は read-side only(at_bat_details.batter_canonical NULL 非依存)、env flag 無し、追加コスト¥0、rollback=image を seo-staff-8b5fe9a へ戻すだけ
- metric #5 = LIVE_DEPLOYED_VERIFIED。447 残り #1 RISP / #3 vs左右 / #4 count は Phase A backfill 依存で未着手

# 2026-06-01 — SNS マーケ施策 ①②③ (user「全部やって」)

## ① data ページ SNS 共有カード改善 (LIVE_VERIFIED)
- 問題: 全選手ページが同一の汎用 og:image + パンくず+数字羅列の崩れた og:description
- 原因: data ページに featured_media / 有効な description が未設定。SEO SIMPLE PACK は
  featured_media→og:image、 description は WP excerpt を無視し本文先頭テキストから自動生成
- 修正: find_player_featured_media_id (選手写真 attachment id) を featured_media に set
  (commit 004cf4a) + lead 文を本文先頭に置き description が clean 文で始まるように (commit 850077d)
- deploy: image sns-card-004cf4a → sns-desc-850077d、 Job exec SUCCESS
- verify: /data/yoshikawa-naoki og:image=選手写真 / og:description=「吉川尚輝の2026年打撃成績。打率.227…」、 cabbage も同様
- 補足: 通常記事の excerpt も「⏱読了約3分💬コメントする…」と崩れている (記事側 share も弱い、 別 ticket 候補)

## ② share-x-image-proxy 502 (LIVE_VERIFIED)
- 問題: 有効な post_id+token 付き正規リクエストが全件 502 (Googlebot ではなかった)
- 原因: _fetch_media_bytes が attachment を wp.get_post (/posts/{id}) で引き 404 → empty → handle_image_proxy 502
- 修正: WPClient.get_media (/media/{id}) 追加、 get_post→get_media (commit f337723)
- deploy: fetcher image sharex-502-f337723、 rev 00507-d2p、 no-traffic→候補tag smoke→100% traffic
- verify: 旧rev proxy 502 → 新rev proxy 200/image-jpeg/147KB (JPEG magic 確認)、 /health 200

## ③ 差別化データ投稿 (READY_FOR_IMPL、 ticket 448)
- inning/venue split surprise を x-post-mail 候補に。 公開 X 自動投稿はしない (§11、 メール候補まで)
- 設計確定: 検出閾値 (gap>=.120 + AB gate)、 Candidate 仕様、 pick_candidates 統合、 dedup、 env flag、 test 計画
- doc/active/448-XPOST-data-split-surprise-candidate.md

## ③ 差別化データ投稿 (LIVE_DEPLOYED 2026-06-01)
- build_data_split_candidates (x_post_mail_lane) + ENABLE_X_POST_DATA_SPLIT で orchestrator append
- commit c81ccc2 / image data-split-c81ccc2、 x-post-mail-lane Job 更新 + flag ON
- bug fix: SQLite HAVING で SELECT alias 不可 → SUM() 明示 (alias だと 0 件 silent だった)
- verify: exec x-post-mail-lane-x4tqf SUCCESS、 log「data_split: built 2 candidates」「data_split appended: base=0 data_split=2 total=2」「mail send result: status=sent」
- 公開 X 自動投稿は未解放 (§11 user 判断)。 候補=オペレーターメールまで

## 451 video-nostalgia-radar (Xバズ駆動、 LIVE_DEPLOYED_VERIFIED 2026-06-01)
- user「RSSハブ入れて」→ 445 と同じ自前 RSSHub (X→RSS、X API不使用) で巨人系X4accountを読み、
  言及多い=バズ選手を検出 → 公式/OB動画を最優先で x-post-mail 候補化。 チャンネル全部 (excluded除外)
- commit 730bb2a (YouTube radar) → eb2f583 (RSSHub buzz)。 image video-radar-eb2f583、 flag ON、 tests 144 pass
- verify: exec kq85n、 buzz=竹丸和幸18/リチャード5/佐々木3 等、 built 3 (38ch scan)、 appended base=2 video=3 total=5、 mail sent
- 転載しない(URL紹介のみ)/Gemini・X API不使用/追加課金なし(RSSHub既稼働)/公開X自動投稿は§11未解放
- Phase2 改善: buzz NER 誤検出 (名前出るだけの無関係動画) の Giants-relevance gate
