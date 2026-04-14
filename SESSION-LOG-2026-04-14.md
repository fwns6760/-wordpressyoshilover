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

### 6. X API クライアントの整合性修正

- `src/x_api_client.py` を現行運用に合わせて修正
- `post` サブコマンド
  - `自動投稿` カテゴリを避けて実カテゴリを選ぶ
  - 記事本文の要約と `content_html` を `x_post_generator.build_post()` に渡す
  - これでスタメン数字や試合後の分岐点を含む現在の X 文面生成ロジックと一致
- `collect` サブコマンド
  - プレーン本文下書きではなく、現行サイトに合わせて X 埋め込みブロック下書きへ変更
  - `AUTO_POST_CATEGORY_ID=673` を付与
  - 根拠のない固定 `cost=$...` / `推定コスト=$...` ログは削除
- テスト
  - `tests/test_x_api_client.py` を追加
  - `python3 -m unittest tests.test_x_api_client tests.test_x_post_generator tests.test_cost_modes`
    - `22 tests OK`

### 7. Cloud Scheduler 再編成

- 汎用の毎時ジョブ `yoshilover-fetcher-job` は `PAUSED`
- 平日 daytime
  - `giants-weekday-daytime`: `0 9-16 * * 1-5`
- 平日 試合前後
  - `giants-weekday-pre`: `0,30 17 * * 1-5`
  - `giants-weekday-post`: `0,30 18-23 * * 1-5`
- 平日 スタメン高速取得
  - `giants-weekday-lineup-a`: `50 16 * * 1-5`
  - `giants-weekday-lineup-b`: `10,20,40,50 17 * * 1-5`
- 土日 既存枠
  - `giants-weekend-pre`: `0,30 11-13 * * 0,6`
  - `giants-weekend-post`: `0,30 16,17 * * 0,6`
  - `giants-weekend-eve`: `0,30 20-22 * * 0,6`
- 土日 スタメン高速取得
  - `giants-weekend-lineup-day-a`: `50 12 * * 0,6`
  - `giants-weekend-lineup-day-b`: `10,20,40,50 13 * * 0,6`
  - `giants-weekend-lineup-late-a`: `50 15 * * 0,6`
  - `giants-weekend-lineup-late-b`: `10,20,40,50 16,17 * * 0,6`

### 8. 巨人データ記事の初回実装

- `src/data_post_generator.py` を追加
  - 初回テーマは `盗塁阻止率`
  - NPB リーダーズ `lf_csp2_c.html` を取得して、巨人目線の比較記事を生成
  - `--dry-run` と `--publish` 対応
- `tests/test_data_post_generator.py` を追加
- 初回下書き
  - `post_id=61938`
  - タイトル: `巨人捕手の盗塁阻止率をデータで見る 岸田　行倫はセ2位スタート`

### 9. 巨人データ記事の運用版を追加

- 2本目として `出塁率` のデータ記事を追加
  - `src/data_post_generator.py on-base`
  - 記事 `61939` を公開
  - タイトル: `巨人打線は打率だけで見ていいのか 出塁率で見ると泉口 友汰が先頭に立つ`
- 仕様
  - `10打席以上` に絞って巨人打線の出塁率一覧を表示
  - 本文上部と末尾に `引用元` を明記
  - 引用元は `NPB 個人打撃成績（読売ジャイアンツ）`
  - URL: `https://npb.jp/bis/2026/stats/idb1_g.html`
- X投稿もデータ記事専用型を追加
  - `阿部監督は打線をどう組むのか。`
  - `出塁率上位5人 + 坂本勇人は10位 + NPB調べ`
  - 上位5人をハッシュタグ化
  - 投稿済み: `https://x.com/i/web/status/2043964115539112393`
- 今後の運用方針
  - `速報記事` と別軸で `巨人データ記事` を継続追加する
  - 次候補は `対左右成績`、`直近10試合`、`先発別援護点`
  - 巨人ファン向けの独自記事として `yoshilover.com` に積み上げる

### 10. 試合日判定の修正と本番反映

- 症状
  - `2026-04-14 17:20` 台の Cloud Run 実行で `本日の巨人戦なし → 選手・コラム記事モードで実行` になっていた
  - 実際には `4/14 阪神 vs 巨人 @甲子園` の試合あり
- 原因
  - `src/rss_fetcher.py` の Yahoo 試合日判定が、`game_id.startswith(today)` のような古い前提に依存していた
  - Yahoo の `game_id=2021038712` は日付先頭ではなく、今日の試合を落としていた
- 修正
  - Yahoo `teams/1/schedule/` の `bb-calendarTable__package--today` から `game_id / opponent / venue` を直接抽出
  - Yahoo 月間日程の `bb-scheduleTable__row--today` からも同様に直接抽出
  - `tests/test_yahoo_realtime.py` に回帰テストを追加
- 確認
  - ローカルで Yahoo HTML 保存版から `('2021038712', '阪神', '甲子園')` を取得確認
  - `python3 -m unittest tests.test_yahoo_realtime` は `12 tests OK`
  - Cloud Run を `codex-20260414-gamedayfix` で再デプロイ
  - 新 revision: `yoshilover-fetcher-00076-brq`
  - 反映後の本番ログで `本日の巨人戦あり vs 阪神 @甲子園` を確認
- 補足
  - 修正後の手動実行では `取得=28 / 投稿=0`。試合日判定は直ったが、この時点では RSS 側に条件を通る新規記事がまだなかった

### 11. スタメン記事を無料の固定ページ補完へ変更

- 背景
  - `2026-04-14` の阪神戦で、試合日判定は直ったが `17:30〜18:00` の自動実行でもスタメン記事は出なかった
  - 原因は `config/rss_sources.json` のニュースRSSだけでは、スタメン記事が間に合わない/配信されないケースがあるため
- 方針
  - `X検索` は使わない
  - `Yahoo!プロ野球` の固定試合ページから取れるスタメンを、RSS不在時の補完ソースとして使う
- 実装
  - `src/rss_fetcher.py`
    - `_has_primary_lineup_candidate()` を追加
    - `_build_yahoo_lineup_candidate()` を追加
    - RSS由来の `lineup` 候補がゼロで、Yahoo固定ページからスタメン行が取れる時だけ、疑似 `試合速報` 候補を1本追加
  - これにより、通常記事は従来通りRSS、スタメンだけは無料の固定ページ補完で拾う構成になった
- テスト
  - `tests/test_yahoo_realtime.py` に補完候補生成のテストを追加
  - `python3 -m unittest tests.test_yahoo_realtime tests.test_build_news_block` は `36 tests OK`

### 12. X検索なしで固定SNSソースを復活

- 背景
  - `スタメン` や `試合後コメント` は一般ニュースRSSより `公式/番記者SNS` の方が早い
  - ただし `X検索` はコストとノイズの面で使わない方針
- 方針
  - `config/rss_sources.json` に RSSHub の固定アカウント feed を追加
    - `@TokyoGiants`
    - `@hochi_giants`
    - `@nikkansports`
    - `@SponichiYakyu`
    - `@Sanspo_Giants`
  - source type は `social_news`
  - ただし記事化するのは
    - `スタメン`
    - `試合後`
    - `監督/選手コメント`
    - `補強/移籍`
    のような強い投稿だけ
- 実装
  - `src/rss_fetcher.py`
    - `_is_authoritative_social_entry_worthy()` を追加
    - `social_news` は `build_news_block()` を通すが、`news` と違って記事画像取得はしない
    - 弱い宣伝投稿や挨拶投稿は `SKIP:SNS弱い` で落とす
- テスト
  - `tests/test_yahoo_realtime.py` に `social_news` 判定テストを追加
  - `python3 -m unittest tests.test_yahoo_realtime tests.test_build_news_block tests.test_wp_client` は `40 tests OK`

### 13. X運用方針を運用版として固定

- ユーザー方針
  - `Xからの流入` は今後も重要
  - ただし `完全自動アカウント` にはしない
  - 試合中の意見や感想は、ユーザー本人が見ながら手動で投稿する
- 運用方針
  - `サイト`: 速報と整理
  - `X`: 流入と人間味
  - 自動投稿候補は `スタメン / 試合後結果 / 監督・選手コメント / 公示 / 補強・移籍`
  - `データ記事` は原則として手動判断で流す
- 自動X投稿の過去実績
  - `2026-04-12 18:18` 台: `post_id=61564, 61565, 61567, 61570`
  - `2026-04-12 18:42-18:43`: `post_id=61584, 61585, 61586`
  - `2026-04-13 18:45-18:46`: `post_id=61847, 61850`
  - いずれも `logs/rss_fetcher.log` に `X投稿` または `公開+X投稿` で記録あり
- チケット更新
  - `TASKS-4-article-quality.md` に `Ticket 10 — X運用（運用版）` を追加

### 14. 自動X投稿を運用設定で再開

- ユーザー判断
  - `自動X投稿そのものは使う`
  - 対象は `試合速報 / 選手情報 / 首脳陣`
  - `データ記事` は引き続き手動判断
- ローカル設定
  - `.env` を `AUTO_TWEET_ENABLED=1`
  - `AUTO_TWEET_CATEGORIES=試合速報,選手情報,首脳陣`
  - `AUTO_TWEET_REQUIRE_IMAGE=1`
- デフォルトとドキュメント
  - `src/rss_fetcher.py` の `DEFAULT_AUTO_TWEET_CATEGORIES` も `試合速報,選手情報,首脳陣` に変更
  - `.env.example` と `README.md` も同内容へ更新
- テスト
  - `python3 -m unittest tests.test_cost_modes tests.test_yahoo_realtime tests.test_build_news_block` は `49 tests OK`
  - `python3 -m py_compile src/rss_fetcher.py src/wp_client.py src/x_api_client.py src/x_post_generator.py` は成功
- 本番反映
  - Cloud Run revision: `yoshilover-fetcher-00080-78w`
  - 確認値
    - `AUTO_TWEET_ENABLED=1`
    - `AUTO_TWEET_CATEGORIES=試合速報,選手情報,首脳陣`
    - `AUTO_TWEET_REQUIRE_IMAGE=1`
    - `X_POST_DAILY_LIMIT=5`

### 15. Yahoo固定ページで試合終了を見て試合後記事を補完

- 背景
  - `スタメン` は Yahoo 固定試合ページで補完できるようにしたが、`試合後結果` も一般ニュースRSSより遅れる可能性がある
  - ユーザー要望は `Yahooで試合終了を確認して、それでポストと記事へつなげたい`
- 実装
  - `src/rss_fetcher.py`
    - `_parse_yahoo_game_status()` を追加
      - `bb-gameCard__state` から `試合終了` を判定
      - スコアボードから `巨人/相手のスコア・安打・失策` を抽出
    - `fetch_giants_game_status_from_yahoo()` / `fetch_today_giants_game_status_from_yahoo()` を追加
    - `_has_primary_postgame_candidate()` を追加
    - `_build_yahoo_postgame_candidate()` を追加
      - RSS側に強い試合後記事が無い時だけ、Yahoo固定ページから疑似 `postgame` 候補を1本作る
  - 既存の `スタメン補完` も内部履歴キーを `#lineup` に変更
  - `試合後補完` の内部履歴キーは `#postgame`
  - これで同じ Yahoo 試合ページから `スタメン記事` と `試合後記事` を別々に重複管理できる
- テスト
  - `tests/test_yahoo_realtime.py`
    - 試合終了判定テスト
    - 疑似 `postgame` 候補生成テスト
  - `python3 -m unittest tests.test_yahoo_realtime tests.test_build_news_block tests.test_cost_modes` は `52 tests OK`
  - `python3 -m py_compile src/rss_fetcher.py` は成功
- 本番反映
  - Cloud Run revision: `yoshilover-fetcher-00081-qfd`
  - image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher:codex-20260414-postgamefallback`

### 16. X運用に2軍情報と動画を追加する方針を固定

- ユーザー意図
  - 試合中は一軍の流れだけでなく、`2軍情報` や `動画` もXへ混ぜたい
  - 仕事で試合を見られない日があるため、投稿の柱を増やしたい
- 運用方針
  - `試合中の手動X投稿` の補完ネタとして以下を明示的に追加
    - `2軍の注目結果`
    - `昇格候補の動き`
    - `公式動画 / 話題動画`
  - いきなり `ドラフト・育成` を自動X投稿カテゴリへ広げるのではなく、まずは運用で反応を見る
  - `2軍情報 / 動画記事` をどこまで記事化・自動化するかは次段で詰める
- チケット更新
  - `TASKS-4-article-quality.md` の `Ticket 10 — X運用（運用版）` に反映済み

### 17. 途中経過と2軍情報の自動X運用を拡張

- ユーザー判断
  - 試合を見られない日があるので、`途中経過` も `記事 + X` を自動で流したい
  - `2軍情報` も通常運用に含めてよい
  - ただし `ボット感の強い連投` にはしない
- 実装
  - `src/rss_fetcher.py`
    - `DEFAULT_AUTO_TWEET_CATEGORIES` を `試合速報 / 選手情報 / 首脳陣 / ドラフト・育成` に拡張
    - `social_news` も自動X投稿対象に変更
    - `RSSHub固定SNSソース` の画像を `entry.summary` 内の `<img>` から先に拾い、取れなければ元ページから取得
    - Yahoo固定試合ページのスコア差分を見て、`同点 / 勝ち越し / 逆転 / 複数得点` だけ `途中経過記事` 候補を生成
    - `#live-スコア` の履歴キーで重複防止
  - `src/x_post_generator.py`
    - `途中経過` 専用文面を追加
    - `ドラフト・育成` 専用文面を追加
    - 2軍や昇格候補の記事も `ボット感の薄い問いかけ型` に寄せた
- テスト
  - `python3 -m unittest tests.test_cost_modes tests.test_x_post_generator tests.test_yahoo_realtime` は `47 tests OK`
  - `python3 -m py_compile src/rss_fetcher.py src/x_post_generator.py` は成功
