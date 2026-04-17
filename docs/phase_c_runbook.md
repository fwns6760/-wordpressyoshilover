# Phase C Runbook

Phase C は「カテゴリ単位で publish を段階的に有効化し、その後で X 自動投稿を段階的に有効化する」ための運用手順です。安全側の既定値は以下です。

- `RUN_DRAFT_ONLY=1`
- `AUTO_TWEET_ENABLED=0`
- `ENABLE_PUBLISH_FOR_POSTGAME=0`
- `ENABLE_PUBLISH_FOR_LINEUP=0`
- `ENABLE_PUBLISH_FOR_MANAGER=0`
- `ENABLE_PUBLISH_FOR_NOTICE=0`
- `ENABLE_PUBLISH_FOR_PREGAME=0`
- `ENABLE_PUBLISH_FOR_RECOVERY=0`
- `ENABLE_PUBLISH_FOR_FARM=0`
- `ENABLE_PUBLISH_FOR_SOCIAL=0`
- `ENABLE_PUBLISH_FOR_PLAYER=0`
- `ENABLE_PUBLISH_FOR_GENERAL=0`
- `ENABLE_X_POST_FOR_POSTGAME=0`
- `ENABLE_X_POST_FOR_LINEUP=0`
- `ENABLE_X_POST_FOR_MANAGER=0`
- `ENABLE_X_POST_FOR_NOTICE=0`
- `ENABLE_X_POST_FOR_PREGAME=0`
- `ENABLE_X_POST_FOR_RECOVERY=0`
- `ENABLE_X_POST_FOR_FARM=0`
- `ENABLE_X_POST_FOR_SOCIAL=0`
- `ENABLE_X_POST_FOR_PLAYER=0`
- `ENABLE_X_POST_FOR_GENERAL=0`

## 1. 公開の段階的有効化手順

### Step 1: 受け入れOKカテゴリの publish フラグを `1` にする

対象 subtype に対応する env だけを有効化する。

- `postgame` -> `ENABLE_PUBLISH_FOR_POSTGAME`
- `lineup` -> `ENABLE_PUBLISH_FOR_LINEUP`
- `manager` -> `ENABLE_PUBLISH_FOR_MANAGER`
- `notice` -> `ENABLE_PUBLISH_FOR_NOTICE`
- `pregame` -> `ENABLE_PUBLISH_FOR_PREGAME`
- `recovery` -> `ENABLE_PUBLISH_FOR_RECOVERY`
- `farm` / `farm_lineup` -> `ENABLE_PUBLISH_FOR_FARM`
- `social` -> `ENABLE_PUBLISH_FOR_SOCIAL`
- `player` -> `ENABLE_PUBLISH_FOR_PLAYER`
- `general` / `game_note` / `roster` -> `ENABLE_PUBLISH_FOR_GENERAL`

### Step 2: `RUN_DRAFT_ONLY=0` に切り替える

この時点でも publish フラグが `0` の subtype は公開されず、draft のまま残る。

### Step 3: smoke test を実行する

```bash
bash scripts/cloud_run_smoke_test.sh
```

### Step 4: 次回 scheduler 実行で公開確認

確認対象:

- `rss_fetcher_run_summary`
- `rss_fetcher_flow_summary.publish_skip_reason_counts`
- `publish_disabled_for_subtype`
- `[公開]`

### Step 5: WordPress とログを確認する

- WP 管理画面の公開一覧に、想定した subtype のみが出ているか
- `publish_skip_reason_counts.publish_disabled_for_subtype` が想定どおりか
- 想定外カテゴリの公開がないか

## 2. X 自動投稿の段階的有効化手順

前提:

- 対象 subtype の `ENABLE_PUBLISH_FOR_XXX=1`
- 対象 subtype の `ENABLE_X_POST_FOR_XXX=1`
- 対象カテゴリが `AUTO_TWEET_CATEGORIES` に含まれている
- `X_POST_AI_MODE=gemini`

X 投稿フラグの対応は publish フラグと同じです。

- `postgame` -> `ENABLE_X_POST_FOR_POSTGAME`
- `lineup` -> `ENABLE_X_POST_FOR_LINEUP`
- `manager` -> `ENABLE_X_POST_FOR_MANAGER`
- `notice` -> `ENABLE_X_POST_FOR_NOTICE`
- `pregame` -> `ENABLE_X_POST_FOR_PREGAME`
- `recovery` -> `ENABLE_X_POST_FOR_RECOVERY`
- `farm` / `farm_lineup` -> `ENABLE_X_POST_FOR_FARM`
- `social` -> `ENABLE_X_POST_FOR_SOCIAL`
- `player` -> `ENABLE_X_POST_FOR_PLAYER`
- `general` / `game_note` / `roster` -> `ENABLE_X_POST_FOR_GENERAL`

手順:

1. まず `ENABLE_PUBLISH_FOR_XXX=1` の状態で数日観察し、公開品質を確認する
2. 問題がなければ対象 subtype の `ENABLE_X_POST_FOR_XXX=1` に切り替える
3. 1時間は `AUTO_TWEET_ENABLED=0` のまま draft 生成ログを観察し、`x_post_ai_generated` と preview 品質を確認する
4. 問題がなければ `AUTO_TWEET_ENABLED=1` に切り替える
5. さらに1時間観察する
6. 以下を確認する

- `[公開+X投稿]`
- `[X投稿スキップ]`
- `x_post_subtype_skipped`
- `x_post_ai_generated`
- `x_post_ai_failed`
- `rss_fetcher_flow_summary.x_skip_reason_counts`

## 3. 緊急止血手順

### ケースA: 意図せぬカテゴリ公開

1. 対象 subtype の `ENABLE_PUBLISH_FOR_XXX=0`
2. deploy
3. smoke test
4. `publish_disabled_for_subtype` が出ることを確認

### ケースB: 全面止血

1. `RUN_DRAFT_ONLY=1`
2. deploy
3. smoke test
4. WP 公開一覧に新規公開が増えないことを確認

### ケースC: X 自動投稿止血

1. `AUTO_TWEET_ENABLED=0`
2. deploy
3. smoke test
4. `[X投稿スキップ] reason=auto_tweet_disabled` を確認

### ケースD: 特定 subtype の X 投稿だけ止める

1. 対象 subtype の `ENABLE_X_POST_FOR_XXX=0`
2. deploy
3. smoke test
4. `x_post_subtype_skipped` と `x_skip_reason_counts.x_post_disabled_for_subtype` を確認

## 4. 公開記事の draft 戻し手順

WordPress REST API で `status=draft` に戻す。

- 認証: 既存の `WP_USER` と `WP_APP_PASSWORD`
- 対象: 誤って `publish` になった post ID

確認:

- `GET /wp-json/wp/v2/posts/<post_id>` で `status=draft`
- WP 管理画面の公開一覧から消える
- 公開 URL が 404 になる

## 5. 日次 / 週次チェックリスト

日次:

- 各カテゴリの draft 件数
- 公開件数
- `publish_skip_reason_counts`
- `x_skip_reason_counts`
- `x_post_subtype_skipped`
- `x_post_ai_failed`

週次:

- Gemini 利用量
- Cloud Run 実行量
- X API 利用量
- 誤分類 / 誤公開の有無

## 6. 受け入れフロー

### 受け入れ基準

- 本文型が期待どおり
- アイキャッチが付与されている
- タイトルが不自然でない
- `publish_disabled_for_subtype` を外した後も誤公開がない
- X 文面が必要なら `x_post_ai_generated` の品質が許容範囲

### OK 判定

- 直近の観察期間で誤公開なし
- 同 subtype の draft 品質が安定
- stop / rollback 手順が確認済み

### NG 判定

- 誤分類
- タイトル衝突
- アイキャッチ欠落
- 本文崩れ
- X 文面の品質不良

### 差し戻し

1. 対象 subtype の `ENABLE_PUBLISH_FOR_XXX=0`
2. 問題記事を draft に戻す
3. ログと post ID を添えて修正依頼
4. 修正後に再度 subtype 単位で受け入れ確認
