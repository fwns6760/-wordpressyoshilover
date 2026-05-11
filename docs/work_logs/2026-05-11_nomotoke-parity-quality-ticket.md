# 2026-05-11 のもとけ比較からの品質・回遊改善チケット作業記録

## 1. 今回の目的

のもとけ型に近づけるため、ヨシラバーに不足している以下の差分を、まず実装前にチケット化・作業記録化する。

- タイトル・選手名・事実抽出の安定
- 記事本文テンプレートの安定
- アイキャッチ取得率の改善
- 選手別・話題別回遊の強化
- 人気記事・コメント・ファン反応導線の強化
- noindex 方針の整理
  - トップページは index
  - 301 リダイレクトとして運用している記事は index でよい
  - それ以外は noindex 候補

この Markdown 作成時点では、実装・コード編集・commit・push・deploy は行わない。

## 2. 今回触る範囲

この時点で触る範囲は、この作業記録 Markdown の新規作成のみ。

- `docs/work_logs/2026-05-11_nomotoke-parity-quality-ticket.md`

GO 後に実装する場合の候補範囲は、以下を想定する。ただし GO 前には触らない。

- 記事品質ガード
- manual intake / RSS 記事本文テンプレート
- タイトル生成・選手名補完
- アイキャッチ取得・fallback
- 選手タグ・回遊導線
- 人気記事・コメント導線
- robots meta / noindex 出力の狭い制御

## 3. 今回触らない範囲

- 320-FRONT / AdSense / scroll UI / 広告表示制御
- Cloud Run env
- Scheduler
- GitHub Actions
- Secret Manager
- 本番 deploy
- X API / X自動投稿
- publish 条件
- mail 通知量
- canonical / 301 リダイレクト挙動そのもの
- source 追加
- Gemini / Grok / LLM call 増加
- WP 本文の直接変更
- 既存公開記事の status 変更
- 既存 dirty worktree の unrelated 差分

## 4. 影響範囲

GO 後に実装する場合の想定影響範囲は以下。

- トップ・一覧で見える記事タイトル品質
- 記事本文の事実ベース品質
- 手動投入記事の本文構造
- 自動生成記事の title / body / category / tag
- アイキャッチ有無
- 選手別・話題別の内部回遊
- 読者が「何の記事か」を判断する速度
- robots meta の index / noindex 出力

この Markdown 作成のみでは、runtime 影響はない。

## 5. 実行予定テスト

GO 後、実装内容に応じて以下を実行する。

- grep / rg による事前確認
  - title / player / article_type / featured_media / tag / category / popular / comment 関連
  - noindex / robots / redirect / 301 / canonical / SEO SIMPLE PACK 関連
- Python 構文確認
  - `python3 -m py_compile <変更Pythonファイル>`
- AST parse
  - 変更 Python ファイルを `ast.parse`
- 対象 pytest
  - title / manual intake / rss fetcher / media / template の関連テスト
- 既存 baseline
  - `python3 -m unittest discover -s tests`
- 必要時のみ live 後確認
  - Cloud Run revision
  - job execution
  - ERROR log
  - publish / mail の停止有無
  - 記事本文の実データ確認

## 6. STOP条件

以下に該当したら停止し、実装・commit・push・deploy に進まない。

- GO 前にコード編集が必要になった場合
- 作業範囲が 320-FRONT / AdSense / scroll UI に入りそうな場合
- Cloud Run env / Scheduler / GitHub Actions / Secret 変更が必要になった場合
- source 追加が必要になった場合
- Gemini / Grok / LLM call 増加が必要になった場合
- publish 条件 / mail 通知量 / SEO に影響しそうな場合
- canonical / 301 リダイレクト挙動そのものを変更する必要が出た場合
- 301 リダイレクト記事の識別条件が repo から安全に判断できない場合
- タイトル補完が記憶からの再構成になりそうな場合
- 選手名・事実を安全に取れない場合
- テストが赤のまま原因説明できない場合
- diff が予定範囲を超えた場合
- 既存 dirty worktree と衝突し、unrelated 差分を巻き込みそうな場合

## 7. 禁止事項

- 実装前のコード編集
- commit
- push
- deploy
- env 変更
- scheduler 変更
- Cloud Run 設定変更
- GitHub Actions 変更
- Secret 表示・変更
- X API 使用
- X 自動投稿
- publish 条件変更
- mail 通知量変更
- canonical 変更
- 301 リダイレクト挙動変更
- source 追加
- Gemini / Grok / LLM call 追加
- ついで修正
- unrelated dirty files の整形・stage
- `git add -A`

## 8. 想定されるデグレ

GO 後の実装で想定されるデグレ。

- タイトル補完で誤った選手名を入れる
- 「選手」などの placeholder を逆に残す
- 他球団選手を巨人記事に混入させる
- 本文が短くなりすぎる
- 本文が主観的になりすぎる
- 元記事と本文の重心がずれる
- アイキャッチ fallback が本文と無関係になる
- category / tag が過剰に増える
- 選手タグ導線が薄い記事にも付いてノイズになる
- 人気記事・コメント導線が表示崩れを起こす
- 既存 publish / mail / scheduler 監視に副作用が出る
- 301 リダイレクトとして index 維持したい記事まで noindex になる
- トップページまで noindex になる
- canonical / redirect / sitemap に副作用が出る

## 9. 作業ログ欄

- 2026-05-11: ユーザー指示により、実装前の作業記録 Markdown を新規作成。
- 2026-05-11: この時点で許可された変更は本 Markdown の作成のみ。
- 2026-05-11: コード編集・commit・push・deploy・env変更・scheduler変更は未実施。
- 2026-05-11: 作業開始時点の main worktree には既存 dirty / untracked が多数あるため、今後も明示 path 以外は触らない。
- 2026-05-11: noindex 方針を追加。トップページは index、301 リダイレクトとして運用している記事は index、それ以外を noindex 候補とする。

## 10. Regression Memo欄

- AI の記憶から再構成しない。
- silent skip しない。
- 自己評価 OK で終わらない。
- 触る前に grep。
- 書いた後に compile + ast + pytest baseline。
- live fire 後は log + 数値 diff を確認。
- タイトル・選手名・本文の事実性は、実例 post_id / URL / category と紐付けて確認する。
- 「のもとけとの差分」は見た目だけでなく、記事密度・回遊・コメント導線・鮮度・タイトル品質を分けて扱う。
- 岡本和真・菅野智之のような元巨人選手は、現在所属を記憶で固定しない。最新の公式 roster / transaction を確認し、現巨人と元巨人を分ける。
- noindex は robots meta の制御に限定し、canonical / 301 リダイレクト挙動そのものは別 GO なしに触らない。
- 301 リダイレクトとして運用している記事は index 例外にする。ただし識別条件を repo / WP 側で確認できない場合は STOP。

## 作業後追記欄

### 1. 実際に変更したファイル

- `tests/test_manual_intake.py`
- `doc/waiting/323-QA-source-body-excerpt-clean-truncation.md`
- `docs/work_logs/2026-05-11_nomotoke-parity-quality-ticket.md`

### 2. diff概要

- post `66331` の実例に合わせ、出典リンクは報知 `20260511-OHT1T51228` だが raw_html が別記事本文になった場合に、`📖 本文抜粋` を挿入しない回帰テストを追加。
- 323 チケットに、WP REST で確認した再発事実、live image `951d2f5` と未反映 commit `24cd9cb` の切り分け、追加テスト、テスト結果を追記。
- 本 Markdown に作業後記録を追記。

### 3. 実行したテスト

- `python3 -m py_compile tests/test_manual_intake.py`
- AST parse for `tests/test_manual_intake.py`
- `python3 -m unittest tests.test_manual_intake.SourceBodyExcerptExpansionTests.test_rss_pipeline_source_body_excerpt_skips_66331_cross_article_body`
- `python3 -m unittest tests.test_manual_intake.SourceBodyExcerptExpansionTests`
- `python3 -m unittest tests.test_manual_intake`
- `python3 -m unittest tests.test_source_article_body_extractor`
- `python3 -m unittest discover -s tests`

### 4. テスト結果

- `python3 -m py_compile tests/test_manual_intake.py`: OK
- AST parse: OK
- 追加 targeted 1 test: OK
- `tests.test_manual_intake.SourceBodyExcerptExpansionTests`: 7 tests OK
- `tests.test_manual_intake`: 73 tests OK
- `tests.test_source_article_body_extractor`: 17 tests OK
- `python3 -m unittest discover -s tests`: 3422 tests OK
- 最初の全件 baseline は sandbox の local HTTPServer socket 作成制限で 3 errors になったが、権限付き再実行では全件 OK。

### 5. 残った懸念

- 本番 `yoshilover-fetcher` image は `951d2f5` で、`24cd9cb` の source excerpt context guard が未反映。
- 現 local branch の HEAD をそのまま deploy すると、323 以外の後続 commit も含む可能性があるため、deploy 候補は別途 diff 範囲確認が必要。
- post `66331` 自体の既存公開本文は、この作業では直接修正していない。

### 6. 新しく見つかったデグレ

- `66331` で、出典リンクと記事タイトルは報知の交流戦前記事なのに、`📖 本文抜粋` が別記事の大城卓三バット直撃本文になっていた。
- local extractor は報知実HTMLから正しい本文を抽出できるため、production image 差分または raw_html/source_url の context drift が主因候補。

### 7. 追加した回帰テスト

- `tests.test_manual_intake.SourceBodyExcerptExpansionTests.test_rss_pipeline_source_body_excerpt_skips_66331_cross_article_body`

### 8. 次回触ってはいけない範囲

- 320-FRONT / AdSense / scroll UI / 広告表示制御
- Cloud Run env / Scheduler / GitHub Actions / Secret
- source 追加
- X API / X 自動投稿
- publish 条件 / mail 通知量
- canonical / 301 リダイレクト挙動
- WP 本文の直接変更
- unrelated dirty files
