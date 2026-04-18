# Codexプロンプトライブラリ

## 指示書の書き方原則

よしひろさんが確立した実践知:

1. **長めに詰める**: 細切れより1つの指示書に複数タスクをまとめる
2. **選択肢ボタン禁止**: Codexに「AとBどちら？」と聞かせない。実装する方向に誘導
3. **Codexに自律判断を残す**: 細部の実装方法はCodexに任せる
4. **git push まで含める**: 「実装→test→git push」を1セットとして指示
5. **smokeテスト手順も書く**: deployまで含めるなら確認コマンドも書く

---

## 成功例: カテゴリ別publish/X投稿フラグ実装（revision 00125-dmq）

以下は実際に使った指示書の骨格:

```
## タスク: カテゴリ別publish/X投稿フラグの実装

### 背景
現在は RUN_DRAFT_ONLY で一括制御しているが、カテゴリ（subtype）ごとに
個別にpublish/X投稿を制御したい。Phase C段階的公開のため。

### 実装すること
1. 環境変数を追加（.env.example）
   - ENABLE_PUBLISH_FOR_POSTGAME=0（デフォルト0）
   - ENABLE_PUBLISH_FOR_LINEUP=0
   … 全10カテゴリ分

2. 同様に ENABLE_X_POST_FOR_XXX も全10カテゴリ分

3. src/rss_fetcher.py の publish判定に組み込む
   - RUN_DRAFT_ONLY=0 かつ ENABLE_PUBLISH_FOR_XXX=1 のときだけpublish
   - フラグ=0でスキップした場合は publish_disabled_for_subtype イベントをログ

4. X投稿判定にも同様に組み込む
   - AUTO_TWEET_ENABLED=1 かつ ENABLE_X_POST_FOR_XXX=1 のときだけX投稿

5. テストを追加する
   - フラグ=0でスキップされること
   - フラグ=1で通過すること

6. pytest 全テストグリーンを確認
7. git commit && git push

### 確認コマンド
bash scripts/cloud_run_smoke_test.sh

### 注意
- live_update は ENABLE_PUBLISH_FOR_LIVE_UPDATE=0 で常時禁止
- .env.example は更新するが .env は変更しない（本番envは別途指示）
```

---

## 成功例: acceptance_fact_check CLI実装（2026-04-17深夜）

```
## タスク: acceptance_fact_check CLIの実装

### 背景
受け入れ試験時に、各draftの事実チェックをコマンドラインから実行したい。
WP管理画面を開かなくても、ローカルから確認できる状態にする。

### 実装すること
1. src/acceptance_fact_check.py を新規作成
   - python3 -m src.acceptance_fact_check --category postgame --limit 10
   - python3 -m src.acceptance_fact_check --post-id 62538
   のどちらでも動くCLI

2. 出力フォーマット
   - 🔴 重大欠陥あり（タイトル/本文/事実不一致）
   - 🟡 注意（軽微な問題）
   - ✅ 問題なし
   - WP直リンク付き

3. /fact_check_notify エンドポイント（GET）
   - Cloud Runで動くAPIとしても実装
   - since=yesterday でその日のdraft全量をチェック
   - メール本文を生成して FACT_CHECK_EMAIL_TO に送信

4. メール件名: 【ヨシラバー】MM/DD 事実チェック結果（🔴X / 🟡Y / ✅Z）

5. pytest テスト追加
6. git commit && git push
```

---

## 成功例: Gmail app password修正（revision 00130、2026-04-18朝）

```
## タスク: fact check メール送信のGmail認証修正

### 問題
fact_check_email_failed ログが出ている。
原因: GMAIL_APP_PASSWORD_SECRET_NAME の参照がproject IDと合っていない可能性。

### 確認すること
1. gcloud secrets list --project baseballsite で yoshilover-gmail-app-password が存在するか確認
2. src/acceptance_fact_check.py の secret取得コードを確認
3. project IDのハードコードがあれば、環境変数 GMAIL_APP_PASSWORD_SECRET_NAME から読むように修正

### 実装
- GMAIL_APP_PASSWORD_SECRET_NAME 環境変数でsecret名を柔軟に指定できるように
- デフォルト: yoshilover-gmail-app-password
- secret取得時のproject IDも環境変数 GCP_PROJECT から取得
- demo mode: app passwordが未設定のときはログにfact check結果を出力して終了

### テスト追加
- secret未設定時にdemoモードで動くこと
- メール送信成功時に fact_check_email_sent ログが出ること

### git commit && git push
```

---

## 失敗例から改善した点

### 当初: 小刻み指示（体力消耗）
```
# Task 2: title衝突修正だけ投げる
タイトルの衝突を修正してください。具体的にはrewriteを多様化...
```
→ よしひろさん: 「全部投げていい、楽なんだよね」

### 改善後: 3タスク一括指示書
```
## タスク: 品質改善3点（title衝突/featured_media/B.5観察）

Task1: title衝突修正
Task2: featured_media補強
Task3: B.5観察ログ強化

全て実装→pytest→git push
```

### 学んだ原則
- 関連する修正は1つの指示書にまとめる
- 「何をするか」より「なぜするか」を先に書く
- 確認コマンドを最後に書く（Codexが自己確認できる）
