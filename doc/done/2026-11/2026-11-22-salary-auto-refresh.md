# 契約更改期の年俸自動取得・2027年表示

Status: CLOSED / LIVE_DEPLOYED_VERIFIED / Codex
Issue: https://github.com/fwns6760/-wordpressyoshilover/issues/132

User authorization: 2026-11-22「自動取得がほしい。」「特にこの時期は」「常にYを押さなくても続けて」。年俸更新・SEOタイトルの先行依頼を自動取得まで完了した。確認済みの範囲では追加の意思確認を挟まず進める。

## 実装と公開動作

- 既存 `rotation-updater-daily` → `rotation-updater`、毎朝7:30 Asia/Tokyo。Scheduler設定を維持したまま年俸取得を先頭へ追加。年俸失敗時も他データ更新を継続し、ジョブの失敗状態は隠さない。`--salary-only` は年俸だけの検証用。
- MFGの契約更改表とスポーツナビの週別契約更改情報を取得。年度・選手名・巨人所属・金額・報道日を照合し、2サイト一致だけ採用。未発表、未来日、年度違い、表構造変化、異なる金額は自動採用しない。LLM/API有料情報源なし。
- 契約更改期（10〜12月）は翌年度、1〜9月は当年度を対象。1月に再度年を進めない。過年度履歴は削除せず、訂正は以前の値と出典も保存。
- 既存bucketの `data_site/salary/ledger-v1.json` に出典URL・金額・報道日・確認日・保留理由を保存。世代条件と6分leaseで重複実行を防ぎ、永続化成功後にWP更新。取得失敗は掲載済み金額を維持する。
- 既存年俸101選手ページ＋一覧を更新。2027年俸27人を確認済み、未確認74人を別表に表示。年俸確認済みのタイトル/H1/本文は2027年、未確認は「2027年は未確認」。2026年の金額を2027年に流用しない。
- 公開タイトル例: `巨人の年俸・契約更改【2027年】ランキングと選手別推移`、`田中将大の年俸【2027年】推移・契約金・通算年俸`。
- 保留2件: 則本昂大（2サイトの金額不一致）、李健熙（2サイト目の確認材料不足）。次回取得でも再照合。過年度値を保持。
- 同一の履歴を持ち既存slug辞書で同一選手と確認できる別名だけを統合（ウィットリー）。未公開の小笠原慎之介ページは新設せず、未公開URLを一覧へ出さない。新規ページ作成は本laneの範囲外。
- 年俸コスパは最新の巨人成績データの年度と同年の年俸を結合。2026年成績を2027年俸で割らず、暦年だけで表示年を進めない。新ロジックは本番imageへ配備済み、今回のsalary-only smokeはコスパページ自体を変更しない。

## 範囲と保持項目

新規source/自動更新モジュール、年俸/コスパtemplate、daily entrypointの独立wrapper、関連tests/fixtures/docsのみ。現行本番digestへの5ファイルoverlayで11/9のcompact DB・ドラフト更新を保持した。既存ページのtitle/content/excerptだけを更新し、id/parent/slug/status/公開日時/URLと2026年成績ページは保持。Scheduler/env/Secret/IAM/resources/X/mail/公開ゲート/他記事変更なし。mainの無関係dirty変更はbuild・commitに含めない。

## 検証と本番証跡

- 関連122 tests passed。fixtureの空白整理後、追加23 tests passed。compileall、AST、git diff --check成功。
- source障害、年・週・表構造違い、金額不一致、履歴保持、訂正、GCS世代競合、lease、同時WP編集、readback不一致、未公開ページ、別名、年俸と成績の年度一致を検証。
- 初回 `rotation-updater-4gvch`: 101ページ更新後、別名重複と未公開ページを検知して一覧を保留。自動retryでは101ページの再更新0。この2ケースを修正して完了した。
- 最終Build `9a5b7051-c304-4d65-8cf9-7aac40f3ad8e` SUCCESS。
- 最終image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/rotation-updater@sha256:4c1dc0227a03adc7770c62e55c87c377f283b84c8c65b05dec4f5d88e5bb3599`。
- 修正版 `rotation-updater-vp2gx` 成功（約17秒）。27人の履歴を保持、101ページ変更なし、一覧更新、失敗0。
- 再実行 `rotation-updater-9thwc` 成功（約13秒）。101ページ＋一覧すべて変更なし、WP書込み0、履歴差分0、保留2件維持。
- API135ページ再取得: 変更102、metadata変更0、2026成績3ページ変更0。公開6ページでtitle/H1/canonical、2027年・確認済み27行・未確認・照合中・2026履歴表示を確認。
- 初期imageとの比較で実行設定はimageのみ変更。既存Scheduler ENABLED、`30 7 * * *`、Asia/Tokyoを再確認。手動実行の成功であり、次回自然発火は未観測。

証跡: 親workspace `implementations/salary-auto-20261122/`。source patch、overlay manifest、テスト結果、WP前後snapshot、ledger、execution logs、deployment/public/source-sync verification。詳細はsecretを含み得るJob JSON全体をchatへ転記せず、必要項目のみ参照する。

Rollback: 機能停止が必要な場合は旧rotation image `sha256:ca8731dd84e6987475c775c88a9adda5f776f6709c4a35e93dc27b6e93071e9a` へ戻す。履歴objectを削除しない。記事内容の復元はsnapshotと現内容を比較して対象102ページだけに限定する。
