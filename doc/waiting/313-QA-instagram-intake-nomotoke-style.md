# 313-QA Instagram Intake Nomotoke Style Expansion

作成日: 2026-05-10
状態: IMPLEMENTED_TESTED_PRE_DEPLOY

## 1. 今回の目的

巨人関連のInstagram投稿を、のもとけ型の記事素材として広く拾えるようにする。

目的は、Instagram投稿をそのまま公開することではなく、巨人公式、報知、現役選手、育成選手、監督・コーチ、OB、球団周辺アカウントを候補棚として整理し、人間レビュー前提で下書き記事に使える素材を増やすこと。

記事本文では、Instagram公式embedを中心に使い、本文側は短い事実説明または短い引用に留める。画像の保存、長文転載、LLMによる感想・考察の追加はしない。

## 2. 今回触る範囲

このMarkdown作成時点で触る範囲:

- `doc/waiting/313-QA-instagram-intake-nomotoke-style.md`

GO後に検討する実装候補:

- Instagramソース候補のallowlistまたは設定ファイル
- Instagram投稿URLを記事素材として扱うための本文生成または手動取り込み経路
- アカウント分類ロジック
- Instagram embedを使った記事本文テンプレート
- 対応する回帰テスト
- このMarkdownへの作業ログ追記

## 3. 今回触らない範囲

- publish
- mail
- scheduler
- env
- Cloud Run設定
- secrets
- GitHub Actions
- SEO
- schema
- アイキャッチ
- X自動投稿
- WordPress本番記事の直接編集
- 指示外のsource
- 指示外の本番設定
- `doc/README.md`
- `doc/active/assignments.md`

## 4. 影響範囲

GO後に実装する場合の想定影響:

- Instagram由来の下書き候補数
- 記事本文に出るInstagram embed block
- タイトルに出る選手名、コーチ名、OB名、アカウント名
- 手動レビュー時の素材確認量
- 巨人関連SNS素材の情報密度

本番公開判定は人間レビュー前提とし、自動公開の判定条件には直接触れない。

## 5. 実行予定テスト

GO後に実装する場合の予定:

- 確定アカウント、候補アカウント、保留アカウント、除外アカウントの分類テスト
- 現役選手、育成選手、監督・コーチ、OB、報知、球団公式の分類テスト
- Instagram投稿URLからembed中心の本文が生成されるテスト
- 投稿キャプションを長文転載しないテスト
- LLM自由作文、主観、考察が入らないテスト
- 画像を保存、再アップロードしないテスト
- embed取得失敗時に記事作成経路全体を止めないテスト
- 別人または巨人関係が薄いアカウントを除外または保留にするテスト
- 関連テスト実行
- 可能なら `python3 -m unittest discover -s tests`

## 6. STOP条件

- Instagram素材拡張のために publish / mail / scheduler / env / Cloud Run / secrets / GitHub Actions を触る必要が出た
- Instagram API token、Meta app review、権限追加、secret追加が必要になった
- 公式embedではなく画像保存や再アップロードが必要になった
- 投稿キャプションの長文転載に近づくしかない
- LLM自由作文で本文を水増しする必要が出た
- アカウントの本人性が確認できず、別人混入リスクを下げられない
- 追加すべき回帰テストを作れない
- 追加テストまたは関連テストがgreenにならない
- `python3 -m unittest discover -s tests` が通らない
- 指示外ファイルを触る必要が出た

## 7. 禁止事項

- GO前のコード編集
- GO前のcommit
- GO前のpush
- GO前のdeploy
- env変更
- scheduler変更
- Cloud Run設定変更
- secrets参照または変更
- GitHub Actions変更
- `git add -A`
- 指示外のついで修正
- Instagram画像の保存、再アップロード、加工
- Instagramキャプションの全文転載
- Instagram投稿本文をLLMで言い換えて事実のように出すこと
- 元投稿にない数字、選手名、発言、感想を足すこと
- 自動公開判定への変更

## 8. 想定されるデグレ

- 別人アカウントを巨人選手として拾う
- 移籍済み、退団済み、旧アカウントを現役扱いする
- 巨人関連が薄いOB投稿まで下書き候補に混ざる
- タイトルが「選手」「コーチ」など曖昧になる
- Instagram embedが表示されず空本文に近くなる
- キャプション引用が長すぎて転載に近づく
- 投稿URLが消えた、非公開化された、embed無効化された時に本文が弱くなる
- SNS素材が増えすぎて人間レビューの負荷が上がる
- 既存RSS記事本文の品質改善と混線する

## 9. 作業ログ欄

- 2026-05-10: PRE_GO_RECORD_ONLYとして本Markdownを作成。許可された変更はこのファイル作成のみ。コード、commit、push、deploy、env、scheduler、Cloud Run、secrets、GitHub Actionsには触っていない。
- 2026-05-10: 開発GO後、既存 `social_video_notice` 経路を確認。再現テストを先に追加し、未実装状態で赤確認。
- 2026-05-10: Instagram source registry、Instagram embed本文、validator、dry-run CLIのregistry入口を実装。
- 2026-05-10: 追加テスト、関連テスト、既存テスト全件を実行。sandbox内のsocket制限で一度3件error、同一コマンドを通常権限で再実行して全件green。

## 10. Regression Memo欄

- 現時点では実装前のため、回帰テスト追加なし。
- GO後は、Instagram素材の広げすぎによる別人混入、長文転載、空embed、タイトル曖昧化を重点回帰ポイントにする。
- 公開判断は人間レビュー前提。自動公開条件の変更はこのticketの対象外。
- 実装後の重点回帰ポイント:
  - 未知アカウントを勝手にconfirmed扱いしない
  - `hold` / `excluded` をreview candidateにしない
  - Instagram本文はWordPress embed中心で、画像再アップロードにしない
  - captionは短いliteral excerptだけを使い、全文転載しない
  - source日時やembed URLでtitle/body nucleus判定が誤検知しない

## 作業後追記欄

### 1. 実際に変更したファイル

- `config/instagram_sources.json`
- `src/instagram_source_registry.py`
- `src/social_video_notice_builder.py`
- `src/social_video_notice_validator.py`
- `src/tools/run_social_video_notice_dry_run.py`
- `tests/test_instagram_source_registry.py`
- `tests/test_social_video_notice_builder.py`
- `tests/test_social_video_notice_validator.py`
- `doc/waiting/313-QA-instagram-intake-nomotoke-style.md`

### 2. diff概要

- 巨人関連Instagram source棚をJSONで追加。
  - `confirmed` / `candidate` / `hold` / `excluded` を明示。
  - 球団公式、報知、現役選手、育成選手、コーチ、OB、保留・除外fixtureを含める。
- `src/instagram_source_registry.py` を追加。
  - handle / profile URL正規化。
  - source棚ロード。
  - unknownをsilent confirmしないlookup。
  - review candidate判定。
- `social_video_notice`本文をInstagram向けに拡張。
  - のもとけ型のsource headerを追加。
  - WordPress Instagram embed blockを本文に挿入。
  - captionは先頭literal sentenceだけを本文に使う。
- validatorを拡張。
  - Instagram profile URLを記事URLとして拒否。
  - Instagram embed block必須化。
  - `<img>` / `wp-content/uploads` / `wp-image-` を画像再アップロードとして拒否。
  - source header日時やembed URLをtitle/body nucleus判定から外す。
- dry-run CLIを拡張。
  - `--instagram-url` + `--account-handle` + `--caption` からregistry経由でpayload生成。
  - unknown / hold / excluded sourceはpayload errorで止める。

### 3. 実行したテスト

- 赤確認:
  - `python3 -m unittest tests.test_instagram_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator`
  - `python3 -m unittest tests.test_social_video_notice_validator.SocialVideoNoticeValidatorTests.test_cli_can_build_instagram_notice_from_registry_account tests.test_social_video_notice_validator.SocialVideoNoticeValidatorTests.test_cli_rejects_unknown_instagram_account_instead_of_silent_confirming`
- 修正後green:
  - `python3 -m unittest tests.test_instagram_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator`
  - `python3 -m unittest tests.test_social_video_notice_validator.SocialVideoNoticeValidatorTests.test_cli_can_build_instagram_notice_from_registry_account tests.test_social_video_notice_validator.SocialVideoNoticeValidatorTests.test_cli_rejects_unknown_instagram_account_instead_of_silent_confirming`
  - `python3 -m unittest tests.test_social_video_notice_contract tests.test_instagram_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator tests.test_title_body_nucleus_validator`
  - `python3 -m unittest discover -s tests`

### 4. テスト結果

- 追加テスト赤確認: OK。
  - source registry未実装、embed未実装、validator未実装、CLI入口未実装で期待通りfail。
- 追加・関連テスト修正後: `54 tests OK`。
- 既存テスト全件:
  - sandbox内初回: `3369 tests`, `errors=3`
  - 原因: `test_manual_intake_service.LiveServerSmokeTest` の `HTTPServer(("127.0.0.1", 0), ...)` がsandboxのsocket制限で `PermissionError: [Errno 1] Operation not permitted`
  - 通常権限で同一コマンド再実行: `3369 tests OK`

### 5. 残った懸念

- source棚は受け入れ試験用に広めに作成。`candidate` は本人性・巨人文脈の目視確認が必要。
- Instagram API連携や自動収集は未実装。今回の入口はregistry + dry-run CLI + embed本文生成まで。
- Instagram投稿が削除、非公開、embed不可の場合は、記事候補としてはsource URLと短いcaption excerptだけが残る。
- `hold` にした移籍済み・退団済み疑いのアカウントは自動review candidateにはしない。巨人文脈で使う場合は個別判断が必要。

### 6. 新しく見つかったデグレ

- 今回の変更による新規デグレはテスト上未検出。
- 実装中に、source headerの日付 `2026-04-24` が既存title/body nucleus validatorで試合結果スコアのように誤認されることを検出。`social_video_notice` validator側でsource headerとembed blockをnucleus判定から除外して対応。

### 7. 追加した回帰テスト

- source棚が広い役割を持つこと。
  - official / media / player / development_player / coach / ob
- status棚を明示すること。
  - confirmed / candidate / hold / excluded
- profile URL / `@` prefix のhandle正規化。
- 公式、報知、現役選手、育成選手、コーチ、OBのlookup。
- `hold` / `excluded` がreview candidateにならないこと。
- unknown sourceをsilent confirmしないこと。
- Instagram本文にのもとけ型source headerが出ること。
- Instagram本文にWordPress embed blockが出ること。
- caption全文ではなく先頭literal sentenceだけ使うこと。
- embedなしInstagram記事を `EMBED_MISSING` で拒否。
- profile URLを `UNSUPPORTED_INSTAGRAM_URL` で拒否。
- 画像再アップロードを `IMAGE_REUPLOAD_FORBIDDEN` で拒否。
- registry accountからCLIで記事候補を作れること。
- unknown accountをCLIでpayload errorにすること。

### 8. 次回触ってはいけない範囲

- publish
- mail
- scheduler
- env
- Cloud Run設定
- secrets
- GitHub Actions
- SEO
- schema
- アイキャッチ
- X自動投稿
- WordPress本番記事の直接編集
- 指示外のsource
- 指示外の本番設定

### 9. 今回触っていない範囲の明示

- publish: 触っていない
- mail: 触っていない
- scheduler: 触っていない
- env: 触っていない
- Cloud Run設定: 触っていない
- secrets: 触っていない
- GitHub Actions: 触っていない
- SEO / schema / アイキャッチ: 触っていない
- X自動投稿: 触っていない
- WordPress本番記事: 触っていない

### 10. deploy前出力確認で見つけた追加修正

- deploy前のdry-run出力確認で、registry由来のInstagram source headerが `表示名(@表示名)` になり、handleが本文に出ない不整合を検出。
- 追加回帰テスト:
  - `test_cli_keeps_registry_display_name_and_handle_distinct`
  - 期待値: `スポーツ報知 巨人取材班(@sportshochi_giants)さん | Instagram`
- 赤確認:
  - `python3 -m unittest tests.test_social_video_notice_validator.SocialVideoNoticeValidatorTests.test_cli_keeps_registry_display_name_and_handle_distinct`
  - 期待通りfail。
- 修正:
  - `src/social_video_notice_contract.py`
    - `source_account_handle` を任意フィールドとして追加。
  - `src/tools/run_social_video_notice_dry_run.py`
    - registryの `display_name` と `handle` を別々にpayloadへ渡す。
  - `src/social_video_notice_builder.py`
    - headerと出典リンクではhandleを `@handle` として表示。
    - title / nucleus subjectはdisplay nameを維持。

### 11. 追加修正後のテスト結果

- 追加回帰テスト単体:
  - `python3 -m unittest tests.test_social_video_notice_validator.SocialVideoNoticeValidatorTests.test_cli_keeps_registry_display_name_and_handle_distinct`
  - `OK`
- 今回追加テスト:
  - `python3 -m unittest tests.test_instagram_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator`
  - `44 tests OK`
- 関連テスト:
  - `python3 -m unittest tests.test_social_video_notice_contract tests.test_instagram_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator tests.test_title_body_nucleus_validator`
  - `55 tests OK`
- 既存テスト全件:
  - `python3 -m unittest discover -s tests`
  - `3370 tests OK`

### 12. 本番deploy記録

- commits:
  - `92efa1b 313: add instagram social video intake registry`
  - `084e682 313: keep instagram handle distinct in intake`
- first image build:
  - Cloud Build `207266a4-d756-45ab-8b21-ab6117289c49`
  - image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/manual-intake-service:92efa1b`
  - result `SUCCESS`
- image build:
  - Cloud Build `a2e5df69-872f-4a08-a768-d300975e393a`
  - image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/manual-intake-service:084e682`
  - result `SUCCESS`
- deploy:
  - service `manual-intake-service`
  - revision `manual-intake-service-00051-gj6`
  - traffic `100%`
  - health `/health` HTTP 200
- post-deploy safe checks:
  - Cloud Run service describe: image `manual-intake-service:084e682`
  - `/health`: HTTP 200 `{"ok": true}`
  - `manual-intake-service` Cloud Run ERROR logs: no rows in latest 20 minutes.
  - `publish-notice` / `guarded-publish` Cloud Run Job ERROR logs: no rows in latest 20 minutes.
- 本番deployで触ったもの:
  - Cloud Run service `manual-intake-service` のimage / revisionのみ。
- 本番deployで触っていないもの:
  - publish / mail / scheduler / env / secrets / GitHub Actions / SEO / schema / アイキャッチ / X自動投稿 / WordPress本番記事。
  - Cloud Run env・secret・scheduler設定は変更していない。
