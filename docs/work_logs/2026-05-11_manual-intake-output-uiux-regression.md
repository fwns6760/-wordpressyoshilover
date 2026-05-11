# manual-intake 出力UI/UX回帰調査 作業記録

作成日: 2026-05-11

## 1. 今回の目的

manual-intake-service で手動投入した記事の出方を、本番公開記事として自然な形に寄せる。

具体例として post `66257` で確認した以下の問題を起点にする。

- `コラム` を選んだのに、本文先頭に共有UI・コメントCTA・JS文言が出て本文らしくない
- 共有ブロックが重複している
- 関連試合・順位・次戦・関連Xなどが、コラムにも強く入りすぎている
- 本文内には `og:image` 由来の画像があるが、WordPress の `featured_media` は `0` でアイキャッチがない

## 2. 今回触る範囲

現時点で許可されている変更は、このMarkdown新規作成のみ。

実装GO後に触る候補範囲:

- `src/tools/manual_intake.py`
- `src/manual_intake_service.py`
- `tests/test_manual_intake.py`
- `tests/test_manual_intake_service.py`

必要になった場合のみ調査対象にするが、実装対象に含める前に確認する範囲:

- `src/wp_client.py`
- manual-intake-service の Cloud Run revision / logs の read-only 確認
- post `66257` など公開済み記事の public REST read-only 確認

## 3. 今回触らない範囲

- `yoshilover-fetcher` 本線の挙動
- RSS自動生成の publish 条件
- guarded-publish / publish-notice の条件
- Cloud Run env
- Cloud Scheduler
- GitHub Actions
- Secret Manager
- X API / X自動投稿
- SEO / noindex / canonical / 301
- AdSense / 320-FRONT / scroll UI / 広告表示制御
- 既存公開記事本文の直接編集
- WordPress管理画面での手動設定変更

## 4. 影響範囲

実装GO後の想定影響は、manual-intake-service から新規作成される下書き記事に限定する。

既存公開記事 `66257` は、別途明示GOがない限り修正しない。

RSS自動生成記事・メール通知・publish job・scheduler には影響させない。

## 5. 実行予定テスト

実装GO後に、先に再現テストを追加する。

予定:

- `コラム` 選択時に、本文先頭が共有UI・コメントCTA・JS文言から始まらないこと
- `コラム` 選択時に、過剰な共通ブロックが混入しないこと
- share block が重複しないこと
- `og_image` がある場合に、アイキャッチ設定の扱いが期待どおりになること
- 既存の manual-intake service フォーム表示と article_type 選択が壊れないこと

実行予定コマンド:

- `python3 -m py_compile src/tools/manual_intake.py src/manual_intake_service.py`
- `python3 -m pytest tests/test_manual_intake.py`
- `python3 -m pytest tests/test_manual_intake_service.py`
- 可能なら `python3 -m unittest discover -s tests`

## 6. STOP条件

- アイキャッチ設定に WP media upload の新規大規模実装が必要になる場合
- 既存の `wp_client.py` 共通挙動を変えないと成立しない場合
- RSS自動生成や publish job に副作用が出る設計になる場合
- Cloud Run env / Scheduler / Secret Manager / GitHub Actions の変更が必要になる場合
- 既存公開記事の直接修正が必要になる場合
- コラム以外の manual-intake 記事タイプに大きな仕様変更が波及する場合
- テストで既存の manual-intake 安全条件が崩れる場合

## 7. 禁止事項

- コード編集は、このMarkdown提示後にユーザーGOが出るまで禁止
- commit / push / deploy 禁止
- Cloud Run env変更禁止
- scheduler変更禁止
- Secret Manager変更禁止
- GitHub Actions変更禁止
- publish条件変更禁止
- X API使用禁止
- X自動投稿禁止
- SEO / noindex / canonical / 301変更禁止
- AdSense / 320-FRONT / scroll UI / 広告表示制御への変更禁止
- 既存公開記事本文の直接変更禁止
- ついで修正禁止

## 8. 想定されるデグレ

- `コラム` の装飾抑制が強すぎて、必要な出典リンクや読者導線まで消える
- share / CTA の重複除去で、他の記事タイプの意図した共有導線が消える
- アイキャッチ自動設定を入れた場合、出典画像の利用可否・安全性判断が不十分になる
- `article_type` と WPカテゴリの対応が変わり、既存運用の選択感覚とズレる
- `auto` 判定時のテンプレート選択に副作用が出る
- manual-intake service のスマホフォームで表示量が増え、操作しづらくなる

## 9. 作業ログ欄

- 2026-05-11: post `66257` を調査。`categories=[670]`、`featured_media=0`、本文先頭に共有UI/コメントCTA/JS文言、share block 重複を確認。
- 2026-05-11: 本作業記録Markdownを新規作成。コード編集は未着手。
- 2026-05-11: `tests/test_manual_intake.py` に `コラム` manual-intake の再現テストを追加。
- 2026-05-11: 修正前に追加テストを実行し、2件の赤を確認。本文先頭の読者UI混入と `featured_media` 未設定を再現。
- 2026-05-11: `src/tools/manual_intake.py` で `コラム` / `ニュース` の manual-intake 出力を記事本文優先レイアウトに限定し、過剰な共通ブロックを抑制。
- 2026-05-11: `og:image` を既存 WPClient の media 安全処理で `featured_media` に解決する処理を追加。失敗時は下書き作成を継続する。
- 2026-05-11: 追加テスト、関連 pytest、全件 unittest を実行して緑を確認。

## 10. Regression Memo欄

- 再現対象: post `66257`
- 選択内容: `コラム`
- 実際のカテゴリ: `670` (`コラム`)
- 実際の featured_media: `0`
- 本文内画像: `nomotoke-hero` として存在
- 問題: WordPress アイキャッチではない
- 問題: 本文先頭が記事本文ではなく UI ブロックから始まる
- 問題: share block が2回入る
- 問題: コラムにも関連試合・順位・次戦・関連Xが入る

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/tools/manual_intake.py`
- `tests/test_manual_intake.py`
- `docs/work_logs/2026-05-11_manual-intake-output-uiux-regression.md`

### 2. diff概要

- `コラム` / `ニュース` manual-intake を記事本文優先レイアウトとして判定する helper を追加。
- 記事本文優先レイアウトでは、本文先頭の read-time meta / コメントCTA / share block を出さず、hero / lead を先に出すように変更。
- 記事本文優先レイアウトでは、関連試合・順位・次戦・関連X・選手stats・著者関連記事などの強い共通ブロックを抑制。
- share block は下部1回に限定。
- `og:image` が安全な HTTPS 画像の場合、既存 media の再利用または upload により `featured_media` を設定。
- `featured_media` 解決失敗時は warning のみで、下書き作成は継続。
- RSS 自動生成の既定挙動は変えず、manual-intake から明示引数が渡された場合だけ記事本文優先レイアウトを有効化。

### 3. 実行したテスト

- 修正前: `python3 -m pytest tests/test_manual_intake.py::ManualIntakeColumnOutputRegressionTests -q`
- 修正後: `python3 -m pytest tests/test_manual_intake.py::ManualIntakeColumnOutputRegressionTests -q`
- `python3 -m py_compile src/tools/manual_intake.py tests/test_manual_intake.py`
- `python3 -m pytest tests/test_manual_intake.py -q`
- `python3 -m pytest tests/test_manual_intake_service.py -q`
- `python3 -m py_compile src/tools/manual_intake.py src/manual_intake_service.py tests/test_manual_intake.py tests/test_manual_intake_service.py`
- `python3 -m unittest discover -s tests`
- `git diff --check -- src/tools/manual_intake.py tests/test_manual_intake.py docs/work_logs/2026-05-11_manual-intake-output-uiux-regression.md`

### 4. テスト結果

- 修正前追加テスト: 2 failed。本文先頭の読者UI混入と `featured_media` 未設定を確認。
- 修正後追加テスト: 2 passed。
- `php` 対象なし。
- `py_compile`: OK。
- `tests/test_manual_intake.py`: `72 passed, 3 warnings, 39 subtests passed`。
- `tests/test_manual_intake_service.py`: sandbox 内では localhost `HTTPServer` 作成が `PermissionError`。権限付きで再実行し `20 passed, 3 warnings`。
- 全件 `python3 -m unittest discover -s tests`: `Ran 3421 tests` / `OK`。
- `git diff --check`: 出力なし。

### 5. 残った懸念

- 既存公開記事 `66257` は直接修正していないため、既存記事の表示はこの local 修正だけでは変わらない。
- アイキャッチは出典 `og:image` を WP media に取り込めた場合のみ設定される。画像URLの安全判定、取得失敗、MIME不一致、WP upload 失敗時は従来どおりアイキャッチなしで下書き作成を継続する。
- `ニュース` も `コラム` と同じ記事本文優先レイアウト対象にした。対象は explicit manual article type に限定し、game / quote / video / notice / pitcher 系には適用しない。

### 6. 新しく見つかったデグレ

- 新しい本番挙動デグレは未検出。
- テスト環境上の制約として、sandbox 内で `tests/test_manual_intake_service.py` の localhost server 起動が `PermissionError` になった。権限付き再実行では全件緑。

### 7. 追加した回帰テスト

- `ManualIntakeColumnOutputRegressionTests.test_column_manual_intake_does_not_put_reader_ui_before_article_body`
  - `コラム` manual-intake の本文で hero / lead が読者UIより前に出ること。
  - top コメントCTA / top share が先頭に出ないこと。
  - share block が1回だけであること。
  - recent games / standings / next game / X embeds が混入しないこと。
- `ManualIntakeColumnOutputRegressionTests.test_column_manual_intake_uses_og_image_as_featured_media`
  - `og:image` を WP media upload し、`featured_media` として `create_post` に渡すこと。

### 8. 次回触ってはいけない範囲

- publish条件
- mail通知
- scheduler
- Cloud Run env
- GitHub Actions
- source追加
- X API / X自動投稿
- SEO / noindex / canonical / 301
- AdSense / 320-FRONT / scroll UI / 広告表示制御
- 既存公開記事本文の直接編集
