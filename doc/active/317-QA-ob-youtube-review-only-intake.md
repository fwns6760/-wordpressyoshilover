# 317-QA OB YouTube Review-Only Intake

作成日: 2026-05-10
状態: LIVE_DEPLOYED_OBSERVE
GitHub Issue: #76

## 1. 今回の目的

巨人OB本人または巨人OBが継続的に出演するYouTubeチャンネルを、YOSHILOVERの「巨人ファン向け総合話題サイト」用の素材として扱えるようにする。

のもとけ型を参考に、YouTube動画そのものを記事の核にする。記事本文は動画タイトル、チャンネル名、公開日、埋め込み、明示された巨人関連トピック、必要ならタイムスタンプまでに抑える。

発言内容を自動で深掘り・要約・断定しない。動画内発言の詳細は、人間が確認した場合だけ短く追記する前提にする。

初期方針は `review-only`。自動公開ではなく、人間確認前の下書き候補または手動取り込み候補として出す。

2026-05-20 追記:

- user 判断: 「巨人OBなら差別化図るため記事にしてもいいかも。記録しといて。後でやる」
- 昨日 2026-05-19 JST のログでは、YouTubeとして下書き化されたのは `post_id=69718` の1本のみ。
- OBチャンネル候補は取得されていたが、多くは `youtube_title_filter_skip reason=no_match` または `stale_rss_entry` で落ちていた。
- 後でやる場合は、公式 YouTube の 395 titleless intake とは分ける。OB / 非公式は relevance gate を維持し、巨人文脈が明確な動画だけ review-only / draft-only に流す。
- 初期上限は 1日1〜2本。カテゴリ候補は `OB・解説者`。自動公開、X投稿、env、scheduler、Secret、YouTube Data API は触らない。
- user 追加判断: 「下書きで作ってもらうでよい。公開は私が判断する」。巨人OB YouTubeは RSS 本線で下書き候補化するが、公開は自動化しない。
- 実装方針: `giants_ob` source は title が弱くても候補化し、`OB・解説者` に寄せる。非巨人OB / 一般OBは従来の巨人 relevance title gate を維持する。公式 YouTube は 395 として別扱い。

## 2. 今回触る範囲

今回触る範囲:

- `src/rss_fetcher.py`
- `src/youtube_ob_source_registry.py`
- `src/tools/run_social_video_notice_dry_run.py`
- `config/youtube_ob_sources.json`
- `config/rss_sources.json`
- `tests/test_rss_fetcher_youtube_integration.py`
- `tests/test_youtube_ob_source_registry.py`
- `doc/active/317-QA-ob-youtube-review-only-intake.md`
- `doc/README.md`
- `doc/active/assignments.md`

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
- 2026-05-20: user が巨人OB YouTubeを差別化記事として後で扱う方針を再確認。GitHub Issue #76 を作成し、本 ticket を PARKED / later backlog として記録。コード、deploy、env、scheduler、Secret、WP、X は未変更。
- 2026-05-20: user が「下書きで作ってもらうでよい。公開は私が判断する」と明示。`giants_ob` source role を追加し、巨人OB YouTube は title が弱くても候補化、RSS 本線では `social_video_notice` body + YouTube embed で draft 作成、publish skip reason `draft_only,youtube_review_source_draft_only` で必ず下書き維持する実装に変更。公式 YouTube は `official_video_source` として既存 395 挙動を維持。非巨人OBは従来 title filter を維持。env / Secret / Scheduler / Cloud Run / WP既存記事 / X は未変更。
- 2026-05-20: user 指示「デプロイ前まで進めて」。status を `READY_FOR_AUTH_EXECUTOR` に正規化し、folder policy に従って `doc/waiting/` へ移動。read-only `gcloud run services describe yoshilover-fetcher --project baseballsite --region asia-northeast1 --format=json` で現行本番を確認: revision `yoshilover-fetcher-00452-glk`、image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:398-media-quote-default-6969375`、traffic 100%、service generation `594`、`RUN_DRAFT_ONLY=True`、`AUTO_TWEET_ENABLED=0`。deploy / build / env / Secret / Scheduler / WP / X / fire は未実行。
- 2026-05-20: user 指示「ならデプロイ」。実装 commit `021c85c` の clean archive から Cloud Build `6a0c0d80-84ad-42fa-9c75-5c547e819b3f` を実行し、image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:317-ob-youtube-021c85c` / digest `sha256:2f1479043bb99ab88f4a1821e7d8df63dfa5d0f705a72036269084ecb5fc3f09` を作成。Cloud Run service `yoshilover-fetcher` へ deploy し、revision `yoshilover-fetcher-00454-ntj`、traffic 100%、`/health` OK、新 revision ERROR log 0 を確認。manual `/run` fire、env / Secret / Scheduler / RUN_DRAFT_ONLY flip / WP既存記事 / X は未変更。
- 2026-05-20: deploy 後の current-state refresh で、fetcher は後続 revision `yoshilover-fetcher-00455-lcf` / image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:400-ext-readable-0a29e7f` / generation `597` / observedGeneration `597` へ進行済みを確認。`git merge-base --is-ancestor 021c85c 0a29e7f` は exit 0 で、317 実装は後続 image に含まれて live 維持。`/health` OK、新 revision `00455-lcf` ERROR log 0。env / Secret / Scheduler / RUN_DRAFT_ONLY flip / WP既存記事 / X / manual `/run` fire は未変更。
- 2026-05-20: user が「引用とかしっかり取れる？変な言葉入らないか。ちゃんと引用だけになるか」と確認。現状確認で、317 本体は title + YouTube embed だが、共通 YouTube caption enrichment が `youtube_review_notice` にも走り、既存実装では「要点」リストが付く可能性を確認。修正として `quote_only` mode を追加し、`youtube_review_notice` では字幕引用 block だけを表示、要点リストを出さない。字幕ノイズ `[音楽]` / `[拍手]` / `チャンネル登録` / `高評価` / `概要欄` / `コメント欄` / URL 系は引用候補から除外。実出力チェックで summary なし、noise なし、blockquote 内の字幕引用のみを確認。env / Secret / Scheduler / WP既存記事 / X / manual `/run` fire は未変更。

## 10. Regression Memo欄

- 最重要回帰ポイントは、YouTube動画を「事実source」として過剰に扱わないこと。
- 初期は `review-only / draft-only` とし、RSS 本線で下書き化しても自動公開には接続しない。
- のもとけ型に寄せ、本文は動画メタ情報、埋め込み、明示トピック、一言に抑える。
- 発言内容は、人間が確認した場合だけ短く追記する。
- `giants_ob` source は user 判断により候補化対象を広げる。ただし公開は user 判断で、本文は動画メタ情報と埋め込みに限定する。
- 非巨人OB / 一般OB は巨人 keyword / 現役巨人選手名 / 元巨人OB名 title filter を維持する。
- 非公式切り抜き、転載、コメント欄、文字起こしは使わない。
- 既存の上原、元木、髙橋尚成のYouTube sourceを壊さない。
- 追加OB候補は一括本線化せず、1本ずつdry-run / review-onlyで確認する。

## 11. 実際に変更したファイル

- `config/youtube_ob_sources.json`
- `config/rss_sources.json`
- `src/rss_fetcher.py`
- `src/youtube_ob_source_registry.py`
- `src/tools/run_social_video_notice_dry_run.py`
- `tests/test_youtube_ob_source_registry.py`
- `tests/test_rss_fetcher_youtube_integration.py`
- `doc/active/317-QA-ob-youtube-review-only-intake.md`
- `doc/README.md`
- `doc/active/assignments.md`

## 12. diff概要

- OB/公式/放送系YouTube source棚を追加。未知チャンネルは安全扱いしない。
- YouTubeチャンネルID、feed URL、channel URL、`youtu.be`、shorts/live/embed URLを正規化するregistryを追加。
- `social_video_notice` のYouTube本文にWordPressのYouTube embed blockを入れるよう変更。
- YouTube本文もInstagram同様、のもとけ型のsource headerを使うよう変更。
- validatorでYouTube動画URL以外のchannel/profile URLを拒否し、YouTube embed block欠落を `EMBED_MISSING` にするよう追加。
- dry-run CLIに `--youtube-url` / `--youtube-channel-id` / `--video-title` を追加。
- 2026-05-20 追加: `giants_ob` role を導入し、巨人OB YouTube source は弱い title でも候補化する。
- 2026-05-20 追加: 巨人OB YouTube source を `OB・解説者` category に override し、RSS 本線では `social_video_notice` body / YouTube embed で draft 作成する。
- 2026-05-20 追加: OB / 非公式 YouTube review source は publish skip reason `draft_only,youtube_review_source_draft_only` を付けて自動公開しない。公式 YouTube は 395 の既存 path を維持する。
- mail、scheduler、Cloud Run、env、secrets、GitHub Actions、X投稿には未接続 / 未変更。

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
- 2026-05-20 追加: `python3 -m unittest tests.test_youtube_ob_source_registry tests.test_rss_fetcher_youtube_integration tests.test_social_video_notice_builder tests.test_social_video_notice_validator`
- 2026-05-20 追加: `python3 -m py_compile src/rss_fetcher.py src/youtube_ob_source_registry.py src/tools/run_social_video_notice_dry_run.py tests/test_rss_fetcher_youtube_integration.py tests/test_youtube_ob_source_registry.py`
- 2026-05-20 追加: `python3 -m compileall -q src tests`
- 2026-05-20 追加: touched Python files AST parse
- 2026-05-20 追加: `python3 -m pytest tests/test_rss_fetcher_youtube_integration.py tests/test_youtube_ob_source_registry.py tests/test_social_video_notice_builder.py tests/test_social_video_notice_validator.py`
- 2026-05-20 追加: `python3 -m pytest`
- 2026-05-20 sandbox 切り分け: `python3 -m pytest tests/test_manual_intake_service.py::LiveServerSmokeTest tests/test_manual_intake_service_x_post.py`

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
- 2026-05-20 追加 unittest: PASS (`Ran 77 tests ... OK`)。
- 2026-05-20 追加 py_compile: PASS。
- 2026-05-20 追加 compileall: PASS。
- 2026-05-20 追加 AST parse: PASS (`AST OK 5`)。
- 2026-05-20 追加 targeted pytest: PASS (`77 passed, 3 warnings`)。
- 2026-05-20 sandbox baseline: `5377 passed, 11 failed, 1 xfailed, 3 xpassed`。失敗11件は `127.0.0.1` socket 作成が sandbox で `PermissionError: [Errno 1] Operation not permitted` になった LiveServerSmokeTest 起点、およびその env bleed による x-post endpoint 403。
- 2026-05-20 sandbox外切り分け: PASS (`14 passed, 3 warnings`)。
- 2026-05-20 full pytest baseline sandbox外: PASS (`5388 passed, 1 xfailed, 3 xpassed, 4 warnings`)。
- 2026-05-20 deploy / log 数値 diff: PASS。fetcher revision `yoshilover-fetcher-00452-glk` -> `yoshilover-fetcher-00454-ntj`、image `398-media-quote-default-6969375` -> `317-ob-youtube-021c85c`、generation / observedGeneration `594/594` -> `596/596`、traffic latest 100% 維持、`RUN_DRAFT_ONLY=True` 維持、`AUTO_TWEET_ENABLED=0` 維持、`/health` OK、新 revision ERROR log 0。
- 2026-05-20 current-state refresh: PASS。fetcher revision `yoshilover-fetcher-00455-lcf`、image `400-ext-readable-0a29e7f`、generation / observedGeneration `597/597`、traffic latest 100% 維持。`0a29e7f` は `021c85c` descendant のため、317 実装は live image に含まれる。`/health` OK、新 revision ERROR log 0。
- 2026-05-20 quote-only caption guard targeted: PASS。`python3 -m py_compile src/rss_fetcher.py tests/test_rss_fetcher_youtube_caption_section.py` OK。`python3 -m pytest tests/test_rss_fetcher_youtube_caption_section.py tests/test_rss_fetcher_youtube_integration.py` は `43 passed, 3 warnings`。手元実出力で `nomotoke-youtube-caption__summary` なし、`チャンネル登録` / `概要欄` / `高評価` / `[音楽]` なし、`<blockquote class="nomotoke-youtube-caption__body">` 内に字幕由来の引用だけを確認。
- 2026-05-20 pre-deploy read-only Cloud Run check: PASS。current service `yoshilover-fetcher` は Ready、latest ready revision `yoshilover-fetcher-00452-glk`、current image `yoshilover-fetcher:398-media-quote-default-6969375`、traffic 100%。

## 15. 残った懸念

- RSS 本線への接続と live deploy は完了。ただし natural fire で実 OB YouTube draft が作られる観察は未実施。
- deploy は clean archive `021c85c` から実施。manual `/run` fire は追加していない。
- OBチャンネルの `channel_handle` は未確認のため空欄が多い。source表示はチャンネル名fallbackになる。
- `giants_ob` source は title が弱くても draft になるため、無関係動画が混じる可能性は残る。公開は user 判断で止める。
- 動画内発言内容は取得していないため、発言詳細を本文に出すには人間確認が必要。
- 字幕がある場合でも `youtube_review_notice` では「要点」化しない。自動字幕の誤認識リスクは残るため、公開前にユーザーが確認する。非本文 CTA / 音楽・拍手ノイズは引用候補から除外する。

## 16. 新しく見つかったデグレ

- 今回差分起因のテスト失敗はなし。
- sandbox内 baseline は localhost socket 制限で `LiveServerSmokeTest` 起点の 11 件が失敗する。sandbox外の失敗 subset は 14 件 pass、full pytest baseline も pass。

## 17. 追加した回帰テスト

- YouTube OB source棚の読み込み、role/status、既知OBチャンネルlookup、未知チャンネル拒否。
- `youtu.be` / shorts URLのcanonical watch URL化。
- YouTube本文にWordPress YouTube embed blockが入り、source headerの後、summaryの前に配置されること。
- YouTube記事でembed blockが欠落した場合は `EMBED_MISSING`。
- YouTube channel/profile URLは `UNSUPPORTED_YOUTUBE_URL`。
- CLIからOB YouTube動画をreview用 `social_video_notice` として生成できること。
- CLIで未知YouTubeチャンネルを安全扱いしないこと。
- `giants_ob` source role は weak title でも pass するが、非巨人OB source は従来の title gate で no_match になること。
- 巨人OB YouTube review source は `OB・解説者` に category override されること。
- 巨人OB YouTube review source は publish path に進まず draft-only reason を持つこと。
- 公式 YouTube source は draft-only override の対象外で、395 の既存挙動を維持すること。
- OB YouTube の `youtube_review_notice` では caption section が quote-only になり、要点 list を出さないこと。
- 字幕の CTA / 音楽・拍手ノイズを quote / summary 候補から除外すること。

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
- 公式 YouTube 395 の titleless intake 挙動。

## 19. Deploy Evidence

状態: `LIVE_DEPLOYED_OBSERVE`

実装 commit:

- `021c85c 317: draft-only OB YouTube intake`

deploy 前 baseline(read-only 確認):

- service: `yoshilover-fetcher`
- project / region: `baseballsite` / `asia-northeast1`
- current revision: `yoshilover-fetcher-00452-glk`
- current image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:398-media-quote-default-6969375`
- traffic: latest revision 100%
- service generation: `594`
- key invariant: `RUN_DRAFT_ONLY=True`, `AUTO_TWEET_ENABLED=0`

deploy 実績:

- Cloud Build: `6a0c0d80-84ad-42fa-9c75-5c547e819b3f` / SUCCESS / duration `2M10S`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:317-ob-youtube-021c85c`
- digest: `sha256:2f1479043bb99ab88f4a1821e7d8df63dfa5d0f705a72036269084ecb5fc3f09`
- deployed revision: `yoshilover-fetcher-00454-ntj`
- traffic: latest revision 100%
- service generation / observedGeneration: `596` / `596`
- `/health`: `OK`
- new revision ERROR log: `0`
- invariants: `RUN_DRAFT_ONLY=True`、`AUTO_TWEET_ENABLED=0`

current live refresh:

- current revision: `yoshilover-fetcher-00455-lcf`
- current image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:400-ext-readable-0a29e7f`
- current generation / observedGeneration: `597` / `597`
- ancestry: `0a29e7f` includes `021c85c` (`git merge-base --is-ancestor 021c85c 0a29e7f` exit 0)
- current `/health`: `OK`
- current new revision ERROR log: `0`
- 317 implementation remains live via the descendant image.

実行した deploy command:

```bash
gcloud builds submit /tmp/yoshilover-317-build.W6ekyK \
  --project baseballsite \
  --region asia-northeast1 \
  --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:317-ob-youtube-021c85c

gcloud run deploy yoshilover-fetcher \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:317-ob-youtube-021c85c \
  --project baseballsite \
  --region asia-northeast1 \
  --quiet
```

deploy 時に触っていない範囲:

- `--set-env-vars` / `--update-env-vars` / Secret / Scheduler / RUN_DRAFT_ONLY flip。
- WP 既存記事編集、X投稿、YouTube Data API 追加、manual `/run` fire。

rollback 候補:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:398-media-quote-default-6969375
```

post-deploy verify:

- `GET /health` が 200 / `OK`。
- direct deploy revision `00454-ntj` は new image `317-ob-youtube-021c85c` を向き、traffic 100%。
- current latest ready revision `00455-lcf` は `021c85c` を含む descendant image `400-ext-readable-0a29e7f` を向き、traffic 100%。
- Cloud Logging で direct deploy revision / current revision とも ERROR 0。
- X API POST / publish 自動化 / Secret / Scheduler / env 変更 0。

残 acceptance:

- 次 natural fire 後に `youtube_review_category_override` が出ても ERROR なし。
- OB YouTube draft が作られる場合、status は draft、category は `OB・解説者`、content に `wp-block-embed-youtube` が入る。
