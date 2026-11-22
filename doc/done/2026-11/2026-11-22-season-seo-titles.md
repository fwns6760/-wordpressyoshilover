# 年俸・選手成績ページのSEOタイトル整理

Status: CLOSED / LIVE_DEPLOYED_VERIFIED

User: 2026-11-22「年俸はどうやって自動でかわってく？又タイトルも２０２７にしていったほうがよくない」「SEOに強いタイトルにシテ」。

## 対応

- 既存174ページ: 年俸104、選手成績68、年俸一覧1、選手一覧1。選手名・年俸/成績・対象年を前方に配置し、長い定型末尾を省略。本文にない契約金/通算成績はタイトルで約束しない。
- 年俸タイトルは保存済みの最新年度から生成。「最新」の一律表示を除去。確認済み2027年分を追加すれば年俸タイトル/H1は2027年に切替。2026年成績の年は独立して保持。
- WPはtitleと年俸ページ内H1だけ変更。本文の他部分、金額、成績、id/slug/URL/parent/status/公開日時は保持。変更前snapshotと直前hash比較により競合を防止。
- 本番の正確なdigestから対象テンプレートだけoverlay。data-site-publisherとrotation-updaterはimageのみ変更。Scheduler/env/Secret/IAM/X/mail不変。

## 検証

- 関連既存テスト96 passed。compileall、AST、git diff --check成功。
- 2027年年俸fixtureでtitle/H1切替、成績年2026保持、契約金データなし時の文言除去を確認。
- WP 174/174更新・再取得成功、競合/失敗0。旧本文からH1以外の差分0、固定metadata保持。
- 公開8ページでtitle/H1/og:title一致とcanonicalを確認。
- Cloud Build `53aaf721-0484-4590-907f-378c9f51277f` SUCCESS。
- publisher digest `sha256:e479f16a1ecd1b4ecdd2a53250e2a292451c26cde6d293e3df4ffed40d4a2757`。
- rotation digest `sha256:ca8731dd84e6987475c775c88a9adda5f776f6709c4a35e93dc27b6e93071e9a`。
- Job手動実行はN/A。既存ページを限定PATCHし、自然発火で使う生成元のみ更新。新imageの自然発火は未観測。

## 残る別課題

年俸データの自動取得・照合・保存・公開連携は未実装。今回金額は更新していないため公開年俸は2026年のまま。契約更改情報を取り込んだ後、確認済み2027年分と未確認選手を分けて表示する必要がある。年俸コスパの2026年固定と表示年now.yearの不整合も未変更。これらをタイトル修正の完了と混同しない。

証跡: 親workspace `implementations/season-seo-titles-20261122/` のplan、before snapshot、write-verification、public-verification、local-verification、deployment-verification。rollbackは旧imageへ戻し、対象174ページの旧title/H1だけをsnapshotから復元する。
