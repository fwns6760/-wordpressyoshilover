# yoshilover.com全登録ページのSEO・本文品質改善

- Status: CLOSED / LIVE_DEPLOYED_VERIFIED / Codex (2026-11-23)
- Issue: https://github.com/fwns6760/-wordpressyoshilover/issues/134
- User: 2026-11-22「直せる？」「indexしてるページ全部だよ」、2026-11-23「昨日yoshilover.comでやってた作業の続きできる？」。

## 範囲

既知1,139 URLの公開・登録状態を確認した先行監査を継続する。共通frontendでデータ表に基づく要点とSNSページの見出し階層を修正。年俸に前年比・掲載期間の最高額・照合方法・前年のNPB公式成績を追加。投球回の実数/野球表記の混同を修正し、投手のシーズン合計はNPB公式を優先。交流戦終了表示とドラフト掲載年度を実データに追従させる。

既存frontend/publisher/rotationの3ジョブを、確認済み本番digestへの対象ファイル限定overlayで更新する。既存対象ページの本文/説明を更新し、公開・API・PC/スマホ・再実行・Search Consoleサイトマップを検証する。

不可触: 外部別サイト、意図的noindex解除、URL/slug/parent/status/公開日、根拠のない成績・年俸履歴修正、無関係dirty差分、Scheduler/env/Secret/IAM/resources/X/mail。既存の取得元URL非掲載方針を維持する。

## 再開時点の証跡

- 作業場所: `baseballwordpress/implementations/site-seo-repair-20261122/`。
- 151 tests passed、PHP lint、compileall、diff-check成功。3イメージのCloud Build `536c443a-6a2e-439b-9b24-b56c05efca1e` SUCCESS。
- 公開1,134固定ページのbefore snapshotあり。本番反映前に当日snapshotを別名で再取得する。
- 2026-11-23、本番3ジョブのspecは昨夜のbaselineと完全一致。対象9ファイルのSHA256はoverlay manifestと一致。まだ本便のデプロイ・WP更新は未実行。
- 朝の既存rotation自然発火 `rotation-updater-nxsjh` 成功。本便の新imageとは別の先行年俸自動取得の実績。

## 完了条件

全既知URLと登録済みページを台帳化し、要点は表から検算できる事実に限定する。登録済み106件中67件に要点適用可能という先行previewを公開HTMLで追認。元の表・リンク保持、年俸比較と公式成績、投球回、交流戦状態、ドラフト年度を検証する。保護metadataを保存前後で比較し、image以外のジョブ設定不変を確認する。検索側の採否・順位改善は修正完了と分けて報告する。

## 完了結果

- 既知1,139 URLを再取得し、HTTPエラー0。要点表示842ページ、年俸専用要点102ページ、重複0。登録済み106 URLのうち66ページに共通要点を表示。先行previewの67件には適用外のトップページが含まれていたため、公開条件を適用した実数は66件。データ不足のページに推測の文章は追加していない。
- 年俸101選手＋一覧に前年比・掲載期間の最高額・照合方法を追加し、該当選手には2026年NPB公式の巨人在籍分成績を掲載。2027年の確認済み27人・保留2件を維持。既存年俸131ページの全表が保存前後で一致し、金額履歴を変更していない。
- 投手33ページを限定更新し、公式に一軍成績のある31人の登板/勝敗/投球回/奪三振/四球/被安打/被本塁打/自責を照合。田中将大68回1/3、赤星優志53回を確認。残る2人は公式一軍記録なしで既存fallbackを維持。33ページの更新後公開HTTP/H1も再確認。
- 交流戦は12球団18試合を条件に「全日程終了」、順位から「暫定」を除去。ドラフトは1965〜2026年という実データの範囲へ変更。2ページは本文とexcerptのみ更新し、保存直前の競合チェックとreadback一致を確認。
- WP公開固定ページ1,134件の新設/削除0、保存内容が変わったのは134件。全件でid/parent/slug/status/公開日/URL/画像/metaとtitleを保持。公開canonical/robots/titleの実変更0（先行監査の接続失敗3件は今回取得成功）。SNS2ページのH1重複を解消。
- Chromiumで6種×PC1280px/スマホ390pxの12ケースを検証。全件HTTP200、H1各1、ページ/要点の横はみ出し0、JSON-LD構文エラー0、空リンク0。広告/計測リクエストは除外した実サイト表示確認。スマホ画像2件を目視確認。

## 自動更新・配備・検証

- Cloud Build `536c443a-6a2e-439b-9b24-b56c05efca1e`の3imageを適用。image以外のジョブ設定差分0。
- frontend `wp-frontend-deploy-tfq88`成功。digest `sha256:27c83f5422ce50c519261f9e6f3459b8a6c0969ccf746116e25ad6786727ac6f`。
- salary `rotation-updater-p8wjr`成功、101選手＋一覧更新。再実行`rotation-updater-4x6tt`成功、更新0/101不変/一覧不変/失敗0。digest `sha256:d51a7879f71fdf01a924b55224ce537965b7aea9950b4f59920f5bd48d7b08eb`。
- publisher `data-site-publisher-dvccw`（2投手）、`data-site-publisher-gdxpx`（31投手）成功。digest `sha256:647cd969a4946583b05aed6a85f0d620bff0fb8390d3754e3ca79e7593e45342`。既存canary引数による対象限定、Jobの永続args変更なし。
- 新imageの自然発火は未観測。既存日次生成元は修正済み。先行年俸自動取得の今朝7:30自然発火は成功していた。
- 先行151 tests passの成果物hashを再検証。正本への同期後、関連146 tests pass（コマンドは証跡に記載）。両checkoutのPython10ファイルcompileall/AST、PHP lint、diff-check成功。
- 正本へ3-wayで13ファイルを同期。既存の人物記事リンクの未コミット変更と既存indexを保持し、無関係dirty変更を本番へ含めていない。

## 検索側の現在地

- 全件の先行Search Console検査: 登録106、クロール済み未登録788、検出未登録87、未認識23、noindex133、redirect2。これは修正前baselineで、修正による改善率ではない。
- 既存サイトマップ`https://yoshilover.com/sitemap.xml`をSearch Consoleへ再送信（HTTP204）、再取得で送信日時更新・処理待ちを確認。
- 対象6 URLを再検査。田中将大/赤星の成績・ドラフト・交流戦は登録済み。田中将大/坂本勇人の年俸は8月の最終クロールのまま未登録。公開修正は完了しているが、Google再クロール/採用/順位効果は未確認。
- Google Indexing APIによる通常記事への登録要求、noindex解除、外部サイト編集は実行していない。

証跡: `docs/handoff/run_logs/2026-11-23-site-seo-repair/`。raw snapshot/HTML/UI画像は親workspaceの`implementations/site-seo-repair-20261122/`。rollbackは各`*-before.json`のimageと既存WP snapshotを用い、現在内容との競合確認後に対象差分だけを復元する。
