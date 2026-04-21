# Phase C Runbook

2026-04-17 時点の公開運用切替 Runbook。
この文書は `実行手順書` であり、ここに書かれたコマンドは記録用です。実行は別途判断して行うこと。

> **⚠ 2026-04-19 更新**: MVP 枠組みが「Phase C 段階」→「のもとけ再現 Phase 1」に切り替わったため、本 Runbook の内容は **保全用**。現行 release 進捗は `docs/handoff/master_backlog.md` を参照。
>
> - Stage 1（publish 限定開放）→ 既完了（postgame / lineup）
> - Stage 2（X 自動投稿 優先カテゴリ）→ Phase 1 では postgame / lineup のみ解放予定（MB-006 / 007）
> - Stage 3（フル運用）→ Phase 2 送り

## 1. Phase C の段階設計

Phase C は一気にフル公開へ切り替えず、3 段階で進める。

- `Stage 1`
  - 目的: publish 限定開放
  - 変更点: `RUN_DRAFT_ONLY=0`
  - 維持: `AUTO_TWEET_ENABLED=0`
  - 観察期間: 最低 3 日
- `Stage 2`
  - 目的: X 自動投稿を優先カテゴリだけ再開
  - 変更点: `AUTO_TWEET_ENABLED=1`
  - 対象カテゴリ: 優先カテゴリのみ
  - 観察期間: 最低 3 日
- `Stage 3`
  - 目的: フル運用
  - 変更点: 本番 publish + X 自動投稿を通常運用へ移行
  - 観察期間: 最低 3 日

段階を飛ばさない。各 Stage で最低 3 日の観察を行い、異常がなければ次へ進む。

## 2. 移行前の前提条件チェックリスト

実行前に次を満たしていること。

- 最新 GitHub Actions が `success`
- 現行 latest ready revision が `yoshilover-fetcher-00116-ztl`
- 現行 image digest が `sha256:25564c9953d3cca3283c6972fd3ac8774123c675372f74c875dc3658ba507ac3`
- 現行 env が以下と一致
  - `RUN_DRAFT_ONLY=1`
  - `AUTO_TWEET_ENABLED=1`
  - `AUTO_TWEET_CATEGORIES=試合速報,選手情報,首脳陣,ドラフト・育成`
  - `AUTO_TWEET_REQUIRE_IMAGE=1`
  - `PUBLISH_REQUIRE_IMAGE=1`
  - `X_POST_DAILY_LIMIT=10`
  - `ENABLE_LIVE_UPDATE_ARTICLES=0`
- Cloud Scheduler `giants-weekday-daytime` が `ENABLED`
- Scheduler cron が `0 9-16 * * 1-5`
- 直近 run で `rss_fetcher_run_summary` / `rss_fetcher_flow_summary` が取得できている
- `featured_media_missing` や `title_collision_detected` が急増していない
- `media_xpost_embedded` の実績が確認できる
- rollback 対象 revision が明確
  - 現時点の基準 revision: `yoshilover-fetcher-00116-ztl`
  - image tag 相当: `codex-da1a190`

確認コマンド:

```bash
gcloud run services describe yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1

gcloud scheduler jobs describe giants-weekday-daytime \
  --project baseballsite \
  --location asia-northeast1
```

## 3. Stage 1

目的は `publish` だけ再開し、X 自動投稿は止めたまま観察すること。

目標 env:

- `RUN_DRAFT_ONLY=0`
- `AUTO_TWEET_ENABLED=0`
- `AUTO_TWEET_CATEGORIES=試合速報,選手情報,首脳陣,ドラフト・育成`
- `AUTO_TWEET_REQUIRE_IMAGE=1`
- `PUBLISH_REQUIRE_IMAGE=1`
- `X_POST_DAILY_LIMIT=10`
- `ENABLE_LIVE_UPDATE_ARTICLES=0`

手順:

1. 新 revision を `--no-traffic` で作成する
2. `traffic 0%` のまま revision 作成だけ成功したことを確認する
3. 新 revision に `100%` traffic を切り替える
4. 初回 1 run を確認する
5. 最低 3 日観察する

コマンド例:

```bash
gcloud run deploy yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher@sha256:25564c9953d3cca3283c6972fd3ac8774123c675372f74c875dc3658ba507ac3 \
  --update-env-vars RUN_DRAFT_ONLY=0,AUTO_TWEET_ENABLED=0,AUTO_TWEET_CATEGORIES='試合速報,選手情報,首脳陣,ドラフト・育成',AUTO_TWEET_REQUIRE_IMAGE=1,PUBLISH_REQUIRE_IMAGE=1,X_POST_DAILY_LIMIT=10,ENABLE_LIVE_UPDATE_ARTICLES=0 \
  --no-traffic

gcloud run services update-traffic yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --to-latest
```

Stage 1 で見るもの:

- publish 成功件数
- `featured_media_missing`
- `title_collision_detected`
- `rss_fetcher_flow_summary.publish_skip_reason_counts`
- WP 側で誤公開がないか
- 18 時以降の draft / publish の偏り

Stage 1 継続条件:

- 3 日連続で致命的誤公開なし
- `featured_media_missing` が許容範囲
- publish 後の本文型崩れが連発しない

## 4. Stage 2

目的は X 自動投稿を優先カテゴリだけ開放すること。

目標 env:

- `RUN_DRAFT_ONLY=0`
- `AUTO_TWEET_ENABLED=1`
- `AUTO_TWEET_CATEGORIES=試合速報,選手情報,首脳陣`
- `AUTO_TWEET_REQUIRE_IMAGE=1`
- `PUBLISH_REQUIRE_IMAGE=1`
- `X_POST_DAILY_LIMIT=10`
- `ENABLE_LIVE_UPDATE_ARTICLES=0`

手順:

1. Stage 1 が 3 日安定していることを確認
2. 新 revision を `--no-traffic` で作成
3. `AUTO_TWEET_ENABLED=1` と優先カテゴリだけ設定
4. traffic を新 revision に切り替え
5. 最低 3 日観察

コマンド例:

```bash
gcloud run deploy yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher@sha256:25564c9953d3cca3283c6972fd3ac8774123c675372f74c875dc3658ba507ac3 \
  --update-env-vars RUN_DRAFT_ONLY=0,AUTO_TWEET_ENABLED=1,AUTO_TWEET_CATEGORIES='試合速報,選手情報,首脳陣',AUTO_TWEET_REQUIRE_IMAGE=1,PUBLISH_REQUIRE_IMAGE=1,X_POST_DAILY_LIMIT=10,ENABLE_LIVE_UPDATE_ARTICLES=0 \
  --no-traffic

gcloud run services update-traffic yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --to-latest
```

Stage 2 で見るもの:

- `X投稿失敗`
- `X投稿スキップ`
- `x_skip_reason_counts`
- daily limit 到達時刻
- 画像必須条件での skip 増加
- publish 成功に対する X 投稿成功率

Stage 2 継続条件:

- 3 日連続で X 投稿失敗が致命的でない
- daily limit の早期枯渇がない
- 誤カテゴリ投稿がない

## 5. Stage 3

目的はフル運用へ移行すること。

目標 env:

- `RUN_DRAFT_ONLY=0`
- `AUTO_TWEET_ENABLED=1`
- `AUTO_TWEET_CATEGORIES=試合速報,選手情報,首脳陣,ドラフト・育成`
- `AUTO_TWEET_REQUIRE_IMAGE=1`
- `PUBLISH_REQUIRE_IMAGE=1`
- `X_POST_DAILY_LIMIT=10`
- `ENABLE_LIVE_UPDATE_ARTICLES=0`

手順:

1. Stage 2 が 3 日安定していることを確認
2. 新 revision を `--no-traffic` で作成
3. traffic を新 revision に切り替え
4. 最低 3 日観察

コマンド例:

```bash
gcloud run deploy yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher@sha256:25564c9953d3cca3283c6972fd3ac8774123c675372f74c875dc3658ba507ac3 \
  --update-env-vars RUN_DRAFT_ONLY=0,AUTO_TWEET_ENABLED=1,AUTO_TWEET_CATEGORIES='試合速報,選手情報,首脳陣,ドラフト・育成',AUTO_TWEET_REQUIRE_IMAGE=1,PUBLISH_REQUIRE_IMAGE=1,X_POST_DAILY_LIMIT=10,ENABLE_LIVE_UPDATE_ARTICLES=0 \
  --no-traffic

gcloud run services update-traffic yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --to-latest
```

Stage 3 で見るもの:

- draft / publish / X 投稿の通し成功率
- カテゴリ偏り
- 18 時以降の稼働量
- `media_xpost_embedded` の発動率
- `featured_media_missing`

## 6. ロールバック手順

原則は `traffic` を前 revision に戻す。image の再 deploy より先に、traffic rollback を使う。

現時点の基準 revision:

- `yoshilover-fetcher-00116-ztl`
- image: `codex-da1a190`

手順:

1. rollback 先 revision を確認
2. `update-traffic` で rollback 先へ `100%` 切替
3. `/health` と直近 run を確認

コマンド例:

```bash
gcloud run services update-traffic yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --to-revisions yoshilover-fetcher-00116-ztl=100
```

確認:

```bash
gcloud run services describe yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1
```

rollback の判断基準:

- 誤公開
- X 投稿暴発
- `featured_media_missing` 急増
- `rss_fetcher_run_summary.error_count > 0`
- quality warning の急増

## 7. 日次 / 週次 / 月次モニタリング項目

日次:

- `rss_fetcher_run_summary`
- `rss_fetcher_flow_summary`
- draft / publish / X 投稿件数
- 時刻別 draft 件数
- `featured_media_missing`
- `title_collision_detected`
- `media_xpost_embedded`
- `記事本文が汎用表現に寄りすぎたため、安全版へ差し替え`
- `SUMMARY/STATS/IMPRESSIONブロックを破棄`

週次:

- カテゴリ別 draft / publish 件数
- `Phase B` 本文型の適用率
- `media_xpost_embedded` のカテゴリ別発動率
- X 投稿成功率
- 18 時以降の draft 量

月次:

- `X_POST_DAILY_LIMIT` の適正見直し
- AUTO_TWEET 対象カテゴリの見直し
- rollback 実績の有無
- revision ごとの品質比較

## 8. 未解決事項

- Scheduler cron 拡張
  - 現状 `giants-weekday-daytime` は `0 9-16 * * 1-5`
  - 18 時以降の自然枯渇を是正するには cron 拡張判断が必要
- live_update 本格再開判断
  - 現在の実効 gate は `ENABLE_LIVE_UPDATE_ARTICLES=0`
  - Yahoo synthetic の midgame 再開は別判断
- Gemini 精度改善
  - カテゴリ別モデル切替
  - quote 記事と mechanics 記事の更なる分離
  - fan reaction の関連性改善

## 付記

2026-04-17 時点の current revision は `yoshilover-fetcher-00116-ztl`。  
Phase C 切替時は常に `--no-traffic` で新 revision を作り、その後 `traffic` を移す順を守ること。
