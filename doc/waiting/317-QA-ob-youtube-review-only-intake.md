# 317-QA OB YouTube Review-Only Intake

作成日: 2026-05-10
状態: IMPLEMENTED_NOT_DEPLOYED

## 1. 今回の目的

巨人OB本人または巨人OBが継続的に出演するYouTubeチャンネルを、YOSHILOVERの「巨人ファン向け総合話題サイト」用の素材として扱えるようにする。

のもとけ型を参考に、YouTube動画そのものを記事の核にする。記事本文は動画タイトル、チャンネル名、公開日、埋め込み、明示された巨人関連トピック、必要ならタイムスタンプまでに抑える。

発言内容を自動で深掘り・要約・断定しない。動画内発言の詳細は、人間が確認した場合だけ短く追記する前提にする。

初期方針は `review-only`。自動公開ではなく、人間確認前の下書き候補または手動取り込み候補として出す。

## 2. 今回触る範囲

このMarkdown作成時点で触る範囲:

- `doc/waiting/317-QA-ob-youtube-review-only-intake.md`

GO後に検討する実装候補:

- OB YouTube source候補棚または `config/rss_sources.json` の狭い追加
- OB YouTubeを `media_quote_only` または `review-only` として扱うための設定
- YouTube動画タイトル、公開日、チャンネル名、URLから薄い記事候補を作る処理
- のもとけ型のYouTube記事本文テンプレート
- 巨人文脈フィルタ
- OB本人チャンネルと「他チャンネルにOBが出演する動画」の扱い分け
- 対応する回帰テスト
- このMarkdownへの作業ログ追記

初期候補として検討するチャンネル:

- 既存: 上原浩治の雑談魂、元木大介YT、髙橋尚成のHISAちゃん
- 追加候補: デーブ大久保チャンネル、アスリートアカデミア 岡崎郁公式チャンネル、ミスターパーフェクト槙原、江川卓のたかされ、清ちゃんスポーツ

## 3. 今回触らない範囲

- publish条件
- mail通知
- scheduler
- env
- Cloud Run設定
- secrets
- GitHub Actions
- SEO / noindex / canonical / 301
- X自動投稿
- WordPress本番記事の直接編集
- YouTube Data API導入
- YouTube文字起こし取得
- 動画コメント欄利用
- 動画内容の長文要約
- 画像保存、動画保存、再アップロード
- 指示外のsource追加

## 4. 影響範囲

GO後に実装する場合の想定影響:

- OB YouTube由来の下書き候補数
- 記事タイトルに出るOB名、選手名、監督名
- 記事本文に出るYouTube embed
- `OB・解説者` または関連カテゴリへの候補流入
- 人間レビュー時の確認対象
- 既存YouTube scraperの取得件数
- post_gen_validate / review通知の候補量

自動公開は対象外にするため、公開済み記事やpublish gateへの直接影響は持たせない方針。

## 5. 実行予定テスト

GO後に実装する場合の予定:

- OB YouTube source棚の読み込みテスト
- 既存YouTube sourceが壊れないテスト
- `media_quote_only` と `review-only` の扱いが混線しないテスト
- 巨人文脈がある動画タイトルだけ候補化するテスト
- 巨人文脈が薄い動画を記事候補にしないテスト
- 動画タイトル、チャンネル名、公開日、URLだけで本文を作るテスト
- YouTube embed blockが入るテスト
- タイトルに `選手` などgeneric語だけが出ないテスト
- 発言内容を未確認で断定しないテスト
- 動画コメント欄や文字起こしを使わないテスト
- `python3 -m compileall -q src tests`
- touched Python filesのAST parse
- 関連unittest / pytest
- 可能なら `python3 -m unittest discover -s tests`

## 6. STOP条件

- 自動公開を触る必要が出た
- publish / mail / scheduler / env / Cloud Run / secrets / GitHub Actions の変更が必要になった
- YouTube Data API key、OAuth、secret追加が必要になった
- 動画本文の文字起こし取得が必要になった
- コメント欄利用が必要になった
- 動画内容を見ないと成立しない本文しか作れない
- 巨人文脈が薄いOB雑談まで候補化するしかない
- OB本人性やチャンネル本人性を安全に扱えない
- タイトルがgeneric `選手` / `OB` / `動画` だけになる
- 追加すべき回帰テストを作れない
- 関連テストがgreenにならない
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
- YouTube動画の保存、再アップロード、加工
- YouTubeコメント欄の利用
- YouTube文字起こしの自動取得
- 動画内発言の未確認要約
- 元動画にない数字、発言、評価、感想を足すこと
- 自動公開判定への変更

## 8. 想定されるデグレ

- OBの巨人無関係な雑談まで候補化する
- OB本人ではない切り抜き、非公式、転載チャンネルを拾う
- 動画タイトルだけでは分からない内容を本文で断定する
- `巨人OBが語る` のような曖昧タイトルが増える
- タイトルに選手名がないのに本文で選手名を補完する
- `選手` などgeneric語がタイトルに出る
- 既存YouTube sourceの `media_quote_only` 挙動を壊す
- review候補が増えすぎて人間確認負荷が上がる
- YouTube scraperのHTML依存で取得失敗が増える
- OB発言を事実ニュースのように扱ってしまう
- 強い主観、批判、称賛を自動本文に混ぜる
- 同じ話題が新聞記事、X、YouTubeで重複する

## 9. 作業ログ欄

- 2026-05-10: PRE_GO_RECORD_ONLYとして本Markdownを作成。許可された変更はこのファイル作成のみ。コード、commit、push、deploy、env、scheduler、Cloud Run、secrets、GitHub Actionsには触っていない。
- 2026-05-10: ユーザーから開発GOを受領。
- 2026-05-10: 触る前grepを実施。対象は `social_video_notice` / `YouTube` / `youtube` / `source_account` / `media_kind` / `review-only` / `tag_scrape` など。既存ではInstagramのみWordPress embed blockを必須化、YouTubeはリンク中心であることを確認。
- 2026-05-10: 先に回帰テストを追加し、現状で赤になることを確認。失敗内容は `src.youtube_ob_source_registry` 未実装、YouTube本文に `wp-block-embed-youtube` がない、YouTube embed必須validatorがない、CLIが `--youtube-url` を受け付けない、の4系統。
- 2026-05-10: OB YouTube review-only source棚、YouTube source registry、YouTube WordPress embed本文生成、YouTube embed必須validator、dry-run CLIの `--youtube-url` 入力を実装。
- 2026-05-10: 本番fire、deploy、WP書き込み、scheduler変更、Cloud Run変更、env変更、secrets参照/変更、GitHub Actions変更、X投稿は未実施。

## 10. Regression Memo欄

- 最重要回帰ポイントは、YouTube動画を「事実source」として過剰に扱わないこと。
- 初期は `review-only` とし、自動公開には接続しない。
- のもとけ型に寄せ、本文は動画メタ情報、埋め込み、明示トピック、一言に抑える。
- 発言内容は、人間が確認した場合だけ短く追記する。
- OB本人チャンネルでも、巨人文脈がない動画は候補化しない。
- 非公式切り抜き、転載、コメント欄、文字起こしは使わない。
- 既存の上原、元木、髙橋尚成のYouTube sourceを壊さない。
- 追加OB候補は一括本線化せず、1本ずつdry-run / review-onlyで確認する。

## 11. 実際に変更したファイル

- `config/youtube_ob_sources.json`
- `src/youtube_ob_source_registry.py`
- `src/social_video_notice_builder.py`
- `src/social_video_notice_validator.py`
- `src/tools/run_social_video_notice_dry_run.py`
- `tests/test_youtube_ob_source_registry.py`
- `tests/test_social_video_notice_builder.py`
- `tests/test_social_video_notice_validator.py`
- `doc/waiting/317-QA-ob-youtube-review-only-intake.md`

## 12. diff概要

- OB/公式/放送系YouTube source棚を追加。未知チャンネルは安全扱いしない。
- YouTubeチャンネルID、feed URL、channel URL、`youtu.be`、shorts/live/embed URLを正規化するregistryを追加。
- `social_video_notice` のYouTube本文にWordPressのYouTube embed blockを入れるよう変更。
- YouTube本文もInstagram同様、のもとけ型のsource headerを使うよう変更。
- validatorでYouTube動画URL以外のchannel/profile URLを拒否し、YouTube embed block欠落を `EMBED_MISSING` にするよう追加。
- dry-run CLIに `--youtube-url` / `--youtube-channel-id` / `--video-title` を追加。
- 自動RSS本線、publish gate、mail、scheduler、Cloud Run、env、secrets、GitHub Actions、X投稿には未接続。

## 13. 実行したテスト

- red確認: `python3 -m unittest tests.test_youtube_ob_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator`
- `python3 -m compileall src tests`
- touched Python files AST parse
- `python3 -m unittest tests.test_youtube_ob_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator`
- `python3 -m pytest`
- `python3 -m unittest discover -s tests`
- sandbox失敗切り分け: `python3 -m pytest tests/test_manual_intake_service.py::LiveServerSmokeTest` を通常権限で再実行
- `git diff --check`
- dry-run確認: `python3 -m src.tools.run_social_video_notice_dry_run --youtube-url https://youtu.be/abc12345DEF --youtube-channel-id UCKa1VlSq1WwdSQWv4JFdgxg --video-title 巨人OBが試合のポイントを語った --media-kind video --published-at 2026-05-10T09:00:00+09:00`

## 14. テスト結果

- red確認: 想定通り失敗。未実装の期待動作が赤になった。
- `python3 -m compileall src tests`: PASS
- AST parse: PASS (`AST OK 7`)
- 関連unittest: PASS (`Ran 51 tests ... OK`)
- `python3 -m pytest`: 3564 passed / 3 failed。失敗3件は `tests/test_manual_intake_service.py::LiveServerSmokeTest` のlocalhost socket作成がsandboxで `PermissionError: [Errno 1] Operation not permitted` になったもの。
- `python3 -m unittest discover -s tests`: 3393 passed相当 / 3 errors。失敗3件は同じ `LiveServerSmokeTest` のsandbox socket制限。
- `python3 -m pytest tests/test_manual_intake_service.py::LiveServerSmokeTest` 通常権限再実行: PASS (`3 passed`)
- `git diff --check`: PASS
- dry-run確認: PASS。出力本文に `wp-block-embed-youtube` と `<!-- wp:embed {"url":"https://www.youtube.com/watch?v=abc12345DEF","type":"video","providerNameSlug":"youtube","responsive":true} -->` が入ることを確認。

## 15. 残った懸念

- 今回はsource棚とreview-only dry-run経路まで。RSS本線や自動下書き生成には接続していない。
- OBチャンネルの `channel_handle` は未確認のため空欄が多い。source表示はチャンネル名fallbackになる。
- 動画タイトルだけでは巨人文脈が薄い動画を完全には判定できない。自動候補化へ進む場合は巨人文脈フィルタが別途必要。
- 動画内発言内容は取得していないため、発言詳細を本文に出すには人間確認が必要。

## 16. 新しく見つかったデグレ

- 今回差分起因のテスト失敗はなし。
- 既存baselineはsandbox内localhost socket制限で `LiveServerSmokeTest` 3件が失敗する。通常権限で該当3件はpass。

## 17. 追加した回帰テスト

- YouTube OB source棚の読み込み、role/status、既知OBチャンネルlookup、未知チャンネル拒否。
- `youtu.be` / shorts URLのcanonical watch URL化。
- YouTube本文にWordPress YouTube embed blockが入り、source headerの後、summaryの前に配置されること。
- YouTube記事でembed blockが欠落した場合は `EMBED_MISSING`。
- YouTube channel/profile URLは `UNSUPPORTED_YOUTUBE_URL`。
- CLIからOB YouTube動画をreview用 `social_video_notice` として生成できること。
- CLIで未知YouTubeチャンネルを安全扱いしないこと。

## 18. 次回触ってはいけない範囲

- publish条件
- mail通知
- scheduler
- Cloud Run env / service / job
- secrets
- GitHub Actions
- X投稿
- WordPress本番記事
- SEO / noindex / canonical / 301
- YouTube Data API / OAuth / API key
- YouTube文字起こし自動取得
- 動画・画像の保存、再アップロード、加工
- RSS本線への自動接続。ただし、ユーザーが次回明示GOした場合のみ別チケットで小さく実装する。
