# 会話ログ要約: 2026-04-17 事故+Phase C準備

詳細ログ: [docs/daily_logs/2026-04-17.md](../../daily_logs/2026-04-17.md)

## 朝（観察フェーズ初日）

- revision `00115-sqd` から観察開始
- 確認した懸念: title collision / featured_media欠落 / B.5非発動理由不明 / X文面subtype差なし

## 事故発生

- **何が起きたか**: 新規Claudeチャットから `RUN_DRAFT_ONLY=0` が設定された
- **結果**: 4記事がpublishされた（意図しない公開）
- **止血**: 4記事をdraftに戻す、`RUN_DRAFT_ONLY=1` に戻す
- **再発防止**: 「env変更は既存Claudeチャット経由」ルールを確立

この事故がenv変更ルール（[06_failure_patterns.md](../06_failure_patterns.md) 参照）の起源。

## title衝突+featured_media修正（revision 00117〜00119）

- title rewriteの多様化でcollision率を低減
- featured_media fallback強化: `article_image_refetched` / `featured_image_fallback_applied`
- featured_media再利用: `featured_media_reused_from_existing_post`

## Phase B.5観察ログ強化（revision 00120）

- `media_xpost_evaluated` / `media_xpost_skipped` / `media_xpost_embedded` を追加
- B.5が発動しなかった理由をCloud Loggingで追えるようになった

## X投稿subtype分岐（revision 00121〜00122）

- X文面にsubtype専用の分岐を追加
- postgame用の試合後テンプレート
- lineup用のスタメン告知テンプレート
- 280字境界テスト強化

## Gemini AI有効化（revision 00123）

- `X_POST_AI_MODE=gemini` で本番観察モードへ
- `x_post_ai_generated` / `x_post_ai_failed` ログ追加

## live_update制御（revision 00124）

- `ENABLE_X_POST_FOR_LIVE_UPDATE=0` 追加
- live_updateのX自動投稿を完全禁止

## カテゴリ別publish/X投稿フラグ（revision 00125）

- 20個のフラグを実装（ENABLE_PUBLISH_FOR_XXX × 10 + ENABLE_X_POST_FOR_XXX × 10）
- Phase C段階的公開の制御機構が完成

## カテゴリ別X投稿フラグの観察強化（revision 00126）

- `publish_disabled_for_subtype` / `x_post_subtype_skipped` ログ追加

## 🔴2件の品質監査修正（revision 00127）

- 🔴 live_updateが publish側でgeneralに漏れる問題を緊急修正
- 🔴 draft-only中のfeatured_media観測が低下していた問題を修正

## 受け入れチェックリスト整備

- `docs/acceptance_test_checklist.md` 新規作成
- よしひろさん（判断）/ Claude（監査）/ Codex（実装）の役割分担を明文化

## X休眠明け復活活動（夕方）

- @yoshilover6760アカウントの投稿を再開
- 泉口・大城・ダルベック・勝利ポストなどを投稿
- エンゲージメント良好（巨人ファンからの反応あり）
- 詳細ポスト例: [14_x_posting_examples.md](../14_x_posting_examples.md)

## のもとけ戦略深掘り（夜）

- dnomotoke.com: 1,642ページであることを発見（想定より少ない）
- 選別的インデックス仮説を立案
- 「ヨシラバーもページ数より品質密度」の方針確定
- 詳細: [13_strategy_deep_dive.md](../13_strategy_deep_dive.md)

## 深夜: acceptance fact check CLI実装

- `python3 -m src.acceptance_fact_check` を実装
- `--category` / `--post-id` / `--limit` オプション
- Cloud Run エンドポイント `/fact_check_notify?since=yesterday` も同時実装
- 翌朝のメール通知への布石

## 4/17終了時の状態

- revision: `yoshilover-fetcher-00127-98x` or 以降
- Phase C制御機構: 完成
- 受け入れチェックリスト: 整備済み
- acceptance_fact_check: 実装済み（メール送信は翌朝の課題）
