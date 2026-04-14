# Session Log — 2026-04-14

## 今日やったこと

### 1. 本番側で反映済み

- `Cloud Run /run` を同期実行化
  - `src/server.py`
  - `rss_fetcher.py` を background thread で投げて即 `200` を返す挙動をやめた
  - 子プロセス失敗時は `500`、タイムアウト時は `504`
  - `RUN_SUBPROCESS_TIMEOUT=285`
- `Cloud Scheduler -> Cloud Run` を `OIDC + IAM` に統一
  - `X-Secret` ヘッダ運用をやめた
  - 未認証 `POST /run` は `403`
- `Cloud Scheduler` 6ジョブの `attemptDeadline` を `300s` に更新
- `Grok` リクエストの固定 `x-grok-conv-id` を削除
- `Yahoo realtime` パースを少し壊れにくくした
  - `__NEXT_DATA__` の再帰探索
  - 試合日判定を `フェイルクローズ`
- 本番最新リビジョン
  - `yoshilover-fetcher-00073-dv4`
  - image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher:codex-20260414-003010`

### 2. ローカルでは直したが、まだ本番未反映

- `rss_fetcher.py --draft-only` を追加
  - WordPress に下書きだけ作成
  - 公開しない
  - X投稿しない
- `AI本文が空のとき` に要約をそのままもう一度出すバグを修正
  - 空本文時は安全フォールバック本文を使う
- 安全フォールバック本文を改善
  - タイトル丸写しを減らした
  - `今回の話題は、戸郷翔征投手の最新情報です。` のように導入を書く
  - 3段落で読める形に寄せた
- 要約表示も改善
  - RSSの `……` で切れた raw summary をそのまま見せない方向に修正
- `Yahoo` のファン声検索を改善
  - 以前: `巨人 + タイトル先頭20文字`
  - 現在ローカル: `戸郷翔征投手 巨人` / `戸郷翔征投手` / `巨人 発言フレーズ` のような複数クエリで再検索
- ローカル test
  - `python3 -m unittest tests.test_server tests.test_cost_modes tests.test_article_guardrails tests.test_history_persistence tests.test_game_inference tests.test_yahoo_realtime tests.test_draft_only tests.test_build_news_block`
  - `31 tests OK`

### 3. WordPress で確認したもの

- 確認用 draft
  - `post_id=61853`
  - edit URL: `https://yoshilover.com/wp-admin/post.php?post=61853&action=edit`
- この draft はローカルコードから手動で更新済み
  - ただし `Cloud Run` 経由の本番自動生成ではない
- 問題として確認できたこと
  - 旧版は要約重複で壊れていた
  - 修正後は重複は消えた
  - ただし `STRICT_FACT_MODE` のせいで Gemini が長文を返せず、安全版に落ちている
  - そのため `独自性が弱い / ニュース整理に見える / 短い`
  - `ファンの声（Xより）` セクションはこの draft では空

## いまの状況

### 本番の状態

- セキュリティ・運用面はかなり改善済み
  - `/run` 同期化
  - OIDC/IAM
  - Secret Manager
  - Scheduler deadline
- ただし `記事品質改善の最新ローカル修正` はまだ未デプロイ

### 品質面の現状認識

- ユーザー評価:
  - `見るに値しないレベル`
  - `独自性がない`
  - `情報が足りない`
- これは正しい
- 原因:
  - `STRICT_FACT_MODE` が強すぎて Gemini が短文しか返さない
  - `Yahoo` ファン声が 0件だと記事がただの整理文になる
  - フォールバック本文が安全寄りすぎる

## Claudeの10項目への対応表

### 修正済み

1. `server.py: limit 判定バグ`
   - 修正済み
   - `src/server.py:72`
   - `limit=10` が `1` に化ける substring 判定を廃止し、form/json を正しく parse するよう変更
   - なぜ痛いか:
     - 1回で10本流すつもりが1本しか流れず、運用が不安定になる

2. `_last_ai_body` グローバル漏れ
   - 修正済み
   - 現在は `build_news_block()` の返り値を `ai_body_for_x` として記事ごとに保持し、X投稿文生成に渡している
   - `src/rss_fetcher.py:1940-2001`
   - なぜ痛いか:
     - 前の記事の本文が次の記事のX投稿に混ざるので、誤投稿になる

8. `/test-gemini` 無認証
   - 修正済み
   - `src/server.py:121-139`
   - `ENABLE_TEST_GEMINI=0` なら `404`
   - 有効時も認証必須
   - なぜ痛いか:
     - 外部から任意にCLI実行される入口だった

9. `Cloud Run allUsers + 固定X-Secret`
   - 修正済み
   - Cloud Scheduler からの呼び出しは `OIDC + IAM`
   - `X-Secret` 前提をやめた
   - Secretは Secret Manager 管理
   - `src/server.py:15-18`, `src/server.py:33-69`
   - なぜ痛いか:
     - シークレット漏洩時に誰でも `/run` を叩ける状態だった

10. `Cloud Run 上のロックファイル競合`
   - 一部改善
   - `containerConcurrency=1`, `maxScale=1` に絞った
   - GCS history は世代付きマージ保存に変更
   - `src/rss_fetcher.py:1472-1517`
   - なぜ痛いか:
     - 同時実行で履歴が飛ぶと重複投稿や取りこぼしが出る
   - 残り:
     - 真の分散ロックではないので、完全解決ではない

### 改善済みだが、まだ注意が必要

3. `check_giants_game_today()` のHTMLスクレイピング
   - 一部改善
   - Yahoo側の確認を先に使うようにした
   - 失敗時は `True` ではなく `False` に倒すよう変更
   - `src/rss_fetcher.py:1716-1809`
   - なぜ痛いか:
     - 壊れると Grok 側へ倒れて余計なコスト・誤判定が起きる
   - 残り:
     - NPB HTML 依存そのものはまだ残っている

4. `Yahoo Realtime` の深い JSON パス
   - 一部改善
   - `__NEXT_DATA__` の再帰探索を追加
   - silent fail をやめて warning を出すよう変更
   - `src/rss_fetcher.py:418-452`
   - なぜ痛いか:
     - ファンの声が急にゼロになっても気づきにくい
   - 残り:
     - Yahoo 側の構造変更リスクはまだある

### まだ残っている / 未解決

5. `gemini-2.5-flash` モデル名固定
   - 未解決
   - `src/rss_fetcher.py` の Gemini 呼び出しはモデルID固定
   - なぜ痛いか:
     - Google側のモデル名変更で 404 / 空応答になる可能性がある
   - 明日やるなら:
     - モデルIDを env 化する
     - 404時に fallback model を試す

6. `Grok max_output_tokens=800` が少ない
   - 未解決
   - `src/rss_fetcher.py:1180-1212`
   - ログでは `incomplete_details` を警告しているだけ
   - なぜ痛いか:
     - `SUMMARY + ARTICLE + FANS + STATS + IMPRESSION` を一度に返させるには足りず、途中切れで品質が落ちる
   - 明日やるなら:
     - 1800 付近まで上げる
     - もしくは `記事本文` と `FANS` を分離する

7. `_fact_check_article()` が未使用
   - 未解決
   - `src/rss_fetcher.py:730`
   - なぜ痛いか:
     - せっかく作った事実確認の層が本番経路で一切使われていない
   - ただし:
     - 今は `STRICT_FACT_MODE` とガードレールで代替している
     - どちらを正式系にするか整理が必要

## 追加の懸念事項

### A. 記事品質のほうが、いまは運用上いちばん痛い

- セキュリティやSchedulerはかなり改善した
- しかし記事が `ニュース整理にしか見えない` のが現状の最大課題
- なぜ痛いか:
  - サイトの独自性が出ない
  - ユーザーが「見るに値しない」と判断する
  - 自動化しても読まれない

### B. `STRICT_FACT_MODE` は安全だが、強すぎる

- Gemini が十分な本文を返せないと安全フォールバックに落ちる
- 今回の draft `61853` がその例
- なぜ痛いか:
  - ハルシネーションは減る
  - 代わりに `短い / 薄い / 面白くない`

### C. `ファンの声` が取れないと、このサイトらしさが消える

- `ファンの声` はこのブログの核コンテンツの一つ
- Yahoo 0件だと、ただの要約サイトになる
- なぜ痛いか:
  - `のもとけモデル` の再現に失敗する
  - SNS的な熱量が消える

### D. 今の改善コードはローカルにあるが、本番未反映

- `draft-only`
- 改善した安全フォールバック
- 改善した Yahoo fan query
- なぜ痛いか:
  - 明日見直すとき、WordPress の見え方とローカルコードが一致しない

### E. 運用開始時点の懸念メモ（2026-04-14 夜）

- `選手情報` の offday 記事は、現時点では `OK` と判断
  - Gemini の弱い解説調を避け、直球テンプレで出す方針にした
  - ただし安全寄りなので、記事によっては少し短めに見える可能性がある
- `Yahoo` の反応は鮮度と記事適合度をかなり改善した
  - ただしソース側しだいで、まだ雑音が混じる余地はある
- `首脳陣` と `補強・移籍` は、`選手情報` と同じレベルまで本文チューニングしていない
  - 運用を始めると、同じように `弱い / 汎用的` と感じる記事が出る可能性がある
- 元記事の `タイトル` と `要約` が食い違うケースはまだ残る
  - その場合は安全側に倒せるが、読み味や厚みは落ちやすい
- 運用で問題が出る前提で、ここは固定メモとして残す
  - まずは `選手情報はOK`
  - 問題が出たら `カテゴリ別テンプレの追加` と `反応選別の再調整` を優先する

## 明日やること

### 最優先

1. ローカル最新修正を `Cloud Run` にデプロイ
2. `WordPress` に比較用の下書きを2本作る
   - A: `STRICT_FACT_MODE=1` の安全版
   - B: `STRICT_FACT_MODE=0` の比較版
3. 実際にどちらが読めるか WordPress 上で比較する

### 次にやること

4. `Yahoo fan reactions` が実記事で何件拾えるか確認する
5. 0件なら、次のどちらかを決める
   - `Yahoo再検索をさらに強化`
   - `Grokはファン声回収だけ限定ON`
6. 独自性の型を決める
   - ただの要約ではなく
   - `ニュース要点`
   - `ファンの声`
   - `ヨシラバー視点の論点`
   の3層にする

## 明日の再開ポイント

### まず見るファイル

- `src/rss_fetcher.py`
- `src/server.py`
- `tests/test_build_news_block.py`
- `tests/test_yahoo_realtime.py`
- `SESSION-LOG-2026-04-14.md`

### 明日最初に実行する候補

```bash
python3 -m unittest tests.test_server tests.test_cost_modes tests.test_article_guardrails tests.test_history_persistence tests.test_game_inference tests.test_yahoo_realtime tests.test_draft_only tests.test_build_news_block
python3 -m py_compile src/server.py src/rss_fetcher.py src/x_post_generator.py src/wp_client.py
```

### そのあと

```bash
# まだ本番未反映のローカル修正をデプロイ
# その後、品質確認用に1件だけ下書きを作る
python3 src/rss_fetcher.py --limit 1 --draft-only
```

## 明日貼る用の再開プロンプト

```text
SESSION-LOG-2026-04-14.md を読んで再開して。
前回の続きで、まずローカル最新修正が本番未反映なのでそこを整理して。
次に WordPress の品質確認用下書きを2本作りたい。
1本は STRICT_FACT_MODE=1、もう1本は比較用。
独自性が弱いのが問題なので、Yahoo のファン声回収と本文の独自性改善を優先して進めて。
確認対象の draft は post_id=61853。
```

## 2026-04-14 夜の追記

### 1. 試合前スタメンは、いったん使える形まで到達

- 一軍スタメンだけ `Yahoo` 実データから `打率 / 本塁打 / 打点 / 盗塁` を取得する実装を追加
- 過去日のテスト用に `target_day` / `game_id` 指定の helper を追加
- `2026-04-12` の試合ID `2021038704` で実データ `9人` を確認
- テスト公開記事
  - `61920`
  - `https://yoshilover.com/61920`
- 記事UIも変更
  - `【ニュースの整理】`
  - `📊 今日のスタメンデータ`
  - `👀 スタメンの見どころ（3行）`
  - `💬 ファンの声`
- 2軍スタメンは後回し

### 2. 試合後結果のUXを実装

- `試合後結果` 記事は `【ニュースの整理】` の直後に、結果を先に掴めるブロックを追加
  - `📊 今日の試合結果`
  - `👀 勝負の分岐点`
- `勝負の分岐点` は 3行で出す
- CTAも試合後専用に変更
  - `この試合、どう見る？`
  - `勝負の分岐点は？`
  - `今日のMVPは？`
- 実記事も1本公開確認
  - `61924`
  - `https://yoshilover.com/61924`
- 公開後にタイトルも更新
  - `巨人ヤクルト戦 打線沈黙で何が止まったか`
- X投稿型も実装
  - `結果 -> 分岐点 -> 一問 -> URL -> #巨人 #ジャイアンツ #キーパーソン`

### 3. 今日の最終確認

- `python3 -m unittest tests.test_build_news_block`
  - `22 tests OK`
- `python3 -m py_compile src/rss_fetcher.py`
  - OK

### 4. 次の着手

1. `試合後結果` を実記事で1本確認
2. `首脳陣` の実記事確認
3. `移籍・補強` の実記事確認

## 2026-04-14 深夜の追記

### 1. Gemini課金まわりの調査結果

- ユーザーが見ていた Gemini 課金は「暴走」ではないが、旧本番の呼び出し設計が重かった
- `2026-04-12` 〜 `2026-04-13` の Cloud Run ログでは、旧 revision が以下の多段フローを実行していた
  - `Gemini CLI で記事生成中（Web検索付き）`
  - 失敗時に `Gemini 2.0 Flash + Google Search`
  - さらに `Flash Latest` へフォールバック
  - その後に `ハルシネーションチェック開始（Gemini CLI Web検索）`
- つまり「少ない記事本数でも 1 記事あたりの Gemini 呼び出し回数が膨らむ」設計だった
- Sunday の自動実行だけが主犯ではなく、旧 revision の多段呼び出しが課金源として妥当

### 2. 実施した修正

- `src/rss_fetcher.py`
  - low cost 時の Gemini 試行回数を helper 化
  - `GEMINI_STRICT_MAX_ATTEMPTS=1`
  - `GEMINI_GROUNDED_MAX_ATTEMPTS=1`
  - デフォルトで strict / grounded とも 1 回試行に変更
- `src/x_post_generator.py`
  - `gemini-flash-latest` を `gemini-2.5-flash` に固定
  - `thinkingBudget=0`
  - Gemini CLI は `X_POST_GEMINI_ALLOW_CLI=1` の時だけ使うよう変更
- `src/manual_post.py`
  - `gemini-flash-latest` を `gemini-2.5-flash` に固定
  - `thinkingBudget=0`
- `src/weekly_summary.py`
  - `gemini-flash-latest` を `gemini-2.5-flash` に固定
  - `thinkingBudget=0`
- `.env.example`
  - `GEMINI_STRICT_MAX_ATTEMPTS=1`
  - `GEMINI_GROUNDED_MAX_ATTEMPTS=1`
  - `X_POST_GEMINI_ALLOW_CLI=0`
- `README.md`
  - Cloud Run deploy 例にも上記 env を反映

### 3. 検証

- `python3 -m unittest tests.test_cost_modes tests.test_x_post_generator tests.test_title_rewrite tests.test_build_news_block`
  - `52 tests OK`
- `python3 -m py_compile src/rss_fetcher.py src/x_post_generator.py src/manual_post.py src/weekly_summary.py`
  - OK

### 4. 本番反映

- Cloud Build
  - image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher:codex-20260414-costfix`
- Cloud Run
  - revision: `yoshilover-fetcher-00075-kzf`
  - `GEMINI_STRICT_MAX_ATTEMPTS=1`
  - `GEMINI_GROUNDED_MAX_ATTEMPTS=1`
  - `X_POST_GEMINI_ALLOW_CLI=0`
  - `FAN_REACTION_LIMIT=7`
- これで本番の Gemini 記事生成は、low cost 設定時に「1 記事 1 回試行」が基本になる

### 5. 補足

- コード・ログ上では `Gemini 3 Flash` は確認できなかった
- 一方で `gemini-flash-latest` は複数スクリプトに残っていたため、課金表示名のズレを避けるためにも今回すべて明示モデル名へ固定した
