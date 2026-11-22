# 赤星憲広への主エンティティ・トピクラ同期

- status: CLOSED / LIVE_VERIFIED
- owner: Codex
- GitHub: https://github.com/fwns6760/-wordpressyoshilover/issues/133
- authorization: userが本文を書き換え、2026-11-22に「赤星に変えた。」と完了通知。前便で合意した設定同期を実行する。
- target: https://prosports.yoshilover.com/tokuharaeri/ (post 288)

## 範囲

- 芸能人一覧64935から記事288のカード・gh-dataを外し、阪神一覧62065のOBに赤星憲広として掲載。
- 人数、記事末尾の戻りリンク、関連する既存案内を同期。
- 既存snippetの自動生成でArticle.about・パンくず・ItemListを揃え、公開HTMLを検証。
- 必要な一時保護snippetはID・本文hash・権限・有効期限を制限し、実行後停止。

## 不可触

ユーザーが更新した事実本文、タイトル、URL、公開状態、日時、SEOメタ、画像、対象外リンク、恒久snippetコード、GCP/Scheduler/env/Secret/X。

## 完了条件

1. Article.about.nameが赤星憲広、パンくずの所属が阪神一覧。
2. 芸能人カード削除、阪神OBに1件掲載。カード・検索データ・人数一致。
3. 記事と阪神一覧の相互リンク、公開HTTP200を確認。
4. 指定したナビゲーション以外の本文と保護項目が保存前後で一致。
5. 一時snippet停止、実行証跡と台帳を同期。

## 証跡

- 実行中: `/tmp/akahoshi-entity-20261122/`
- baseline: 記事本文とタイトルは赤星憲広中心へ更新済み。主エンティティと所属ピラーは徳原恵梨・芸能人一覧のまま。

## 完了結果

- WP変更は7件・11箇所: 芸能人一覧64935、阪神一覧62065、対象記事288、関連リンクの155/242/1003/11998。
- 芸能人一覧: 13人→12人。阪神一覧: 61人→62人、OB19人→20人。
- 主エンティティ: `徳原恵梨`→`赤星憲広`、alternateName=`あかほしのりひろ`。パンくずの所属: 芸能人一覧→阪神一覧。
- 記事288の変更は末尾の戻りリンク段落1件だけ。ユーザーがリライトした事実本文とタイトルを保持。関連4記事は保存済みリンクタイトル/アンカーだけを同期。
- URLは既存の`/tokuharaeri/`を維持。リダイレクトやcanonicalの変更なし。
- 各保存の直前にstatus=publish・内容hash・保護項目を確認し、同時変更を検知した場合に停止する保護を使用。全7件で保存後hash、タイトル/slug/status/date/modified/meta/カテゴリ/タグ/画像等とSEOメタを照合し一致。
- 一時snippet102は停止済み。常設activeは16/18/19/39/53で前後一致。恒久コード変更なし。既存の保存フックで人物・クラスターキャッシュを更新。

## 検証と証跡

- 573公開レコードを読み取り、旧URLへの参照を調査。対象外の人物への単なる言及は変更なし。
- `prepare.py`: 指定11操作だけで差分を再現、既存カード・画像・JS/CSS保持、Gutenbergブロック整合、カードと検索情報と人数の一致を検証。
- Python compileall / AST parse、PHP lint、Node構文検査: 成功。
- 公開7ページHTTP200、canonical/title/robots/description保持。Article.about・BreadcrumbList・両一覧ItemList・往復リンク・関連4記事の表示を確認。
- 保存済み公開HTMLのトピクラJSをChromiumで実行。PC1280px/スマホ390pxの名前・カナ・別名検索、話題フィルター、単一カード、リンク先、横はみ出しなしを確認。第三者/テーマJSを除外したUI検証であり、実ブラウザでの全機能テストではない。
- 公開記事1件の接続タイムアウトを観測。接続制限外で再取得し、7件すべて成功。WP書き込みの再実行なし。
- 検証結果: `docs/handoff/run_logs/2026-11-22-akahoshi-entity-verification.json`。全before/after、7差分、スクリプト、画像は`/tmp/akahoshi-entity-20261122/`。
- Cloud Run等のfire/log差分: N/A（WP RESTによる記事・一覧の設定同期のみ）。repoアプリテスト: N/A（src/tests変更なし、運用差分と公開検証で確認）。
