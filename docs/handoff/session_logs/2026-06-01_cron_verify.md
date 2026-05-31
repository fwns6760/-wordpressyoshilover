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
