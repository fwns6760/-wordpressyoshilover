# 314-QA RSS source body excerpt follow-up

## 1. 今回の目的

RSS / tag_scrape 経路でも、元記事本文から取れる literal excerpt を本文に出せるようにする。

方針は固定する。

- LLM で書き直さない
- source から取れた本文だけ使う
- excerpt が取れなくても記事生成は止めない
- 元記事本文が十分ある場合は、600文字以内で本文がより分かるようにする
- タイトル、ナビ、広告、関連記事、SNS share 文を本文抜粋に混ぜない

## 2. 今回触る範囲

- `src/tools/manual_intake.py`
- `src/source_article_body_extractor.py`
- `src/rss_fetcher.py`
- `tests/test_manual_intake.py`
- `tests/test_source_article_body_extractor.py`
- 必要なら RSS enrichment 用の狭い回帰テスト
- 本 ticket 自身 `doc/waiting/314-QA-rss-source-body-excerpt-followup.md`

## 3. 今回触らない範囲

- publish
- mail
- scheduler
- env
- secrets
- Cloud Run 設定
- GitHub Actions
- SEO / schema
- アイキャッチ選定
- Instagram 取り込み
- X 自動投稿
- WordPress 本番記事の手動修正
- 指示外の source 追加
- `doc/README.md`
- `doc/active/assignments.md`

## 4. 影響範囲

- RSS / tag_scrape 経路の記事本文の見え方
- `📖 本文抜粋` block の出現条件
- source 本文抽出の selector
- source HTML の取得 / 受け渡し
- 記事の情報密度

本線への影響は記事本文生成の見え方に限定する。publish / mail / scheduler / env / Cloud Run 設定には直接影響させない。

## 5. 実行予定テスト

追加する再現テスト:

- RSS enrichment 経路で `raw_html` が無いと `📖 本文抜粋` が出ない現状を赤確認する
- RSS / tag_scrape 経路で source HTML がある場合、`📖 本文抜粋` が出る
- 報知の現行 HTML 形 `preview__detail` / `preview__text` から本文だけ取れる
- 日刊スポーツ / デイリー / スポニチ / Full-Count で、タイトル・ナビ・日付・広告を本文抜粋に混ぜない
- BaseballKing で広告 script 風テキストを excerpt にしない
- source 本文が取れない時は元本文のまま止めない
- excerpt は 600文字以内を厳密に守る
- sentence boundary を守る
- title に近い excerpt でも、source 本文が十分ある時は表示できる
- LLM 自由作文、主観、source にない数字・選手名・コメントが出ない

実行順:

1. 追加再現テストだけ実行して赤確認
2. コード修正
3. 追加再現テストを再実行して green 確認
4. 関連テスト実行
   - `python3 -m unittest tests.test_manual_intake`
   - `python3 -m unittest tests.test_source_article_body_extractor`
   - 必要なら RSS enrichment 関連テスト
5. 可能なら既存テスト全件
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 追加再現テストの赤確認ができない
- literal excerpt ではなく再構成本文に寄ってしまう
- excerpt 不足を埋めるために source にない文を足す必要が出る
- 全文転載に近づくしかない
- 600文字以内を守れない
- 報知以外の媒体で本文誤抽出が悪化する
- publish / mail / scheduler / env / secrets / Cloud Run 設定を触る必要が出る
- `python3 -m unittest discover -s tests` が通らない
- 既存のユーザー未コミット差分を戻す必要が出る

## 7. 禁止事項

- LLM で source 本文を書き直す
- source にない説明、感想、考察、数字、選手名、コメントを足す
- excerpt が取れない記事を止める
- full body copy に近い長文転載をする
- publish / mail / scheduler / env / secrets / Cloud Run 設定に触る
- ついで修正をする
- `git add -A` を使う
- diff 提示前に commit する
- テスト未実行で commit / push / deploy する

## 8. 想定されるデグレ

- source HTML 取得が増えて RSS 実行時間が伸びる
- 媒体 selector が広すぎてナビ、広告、関連記事が本文抜粋に混ざる
- selector が狭すぎて excerpt が出ないままになる
- 600文字上限が緩くなり、引用量が増えすぎる
- sentence boundary 処理で本文が短くなりすぎる
- 同じ source HTML を複数回取得して runtime cost が増える
- manual_intake 側の既存 excerpt 挙動を壊す

## 9. 作業ログ欄

| 日時 | 内容 | 結果 |
| --- | --- | --- |
| 2026-05-10 JST | user 受け入れ確認で「600文字にしたが元と変わらない」と報告 | 調査 ticket 化 |
| 2026-05-10 JST | read-only 調査 | RSS 自動生成側で `raw_html` が渡っていないことを確認 |
| 2026-05-10 JST | read-only 実HTML確認 | 報知は `preview__detail` / `preview__text` に本文があり、現行 selector では excerpt 0 |
| 2026-05-10 JST | read-only 実HTML確認 | 日刊 / デイリー / スポニチ / Full-Count は取れるが、ナビやタイトル混入リスクあり |
| 2026-05-10 JST | read-only 実HTML確認 | BaseballKing は広告 script 風テキスト誤抽出リスクあり |

## 10. Regression Memo欄

- `SOURCE_BODY_EXCERPT_MAX_CHARS = 600` は設定済み。
- `apply_rss_pipeline_enrichment()` には `raw_html` 引数があるが、`rss_fetcher.py` の呼び出しでは渡していない。
- そのため RSS / tag_scrape 自動記事では、600文字化しても `📖 本文抜粋` が出ない。
- 報知の現行記事本文は `preview__detail` / `preview__text` にあり、既存 `article__body` selector では取れない。
- excerpt が取れない場合は記事を止めない方針を維持する。

## 作業後追記

### 1. 実際に変更したファイル

- `src/source_article_body_extractor.py`
- `src/rss_fetcher.py`
- `tests/test_source_article_body_extractor.py`
- `tests/test_rss_fetcher_reliability_2026_05_08.py`
- `doc/waiting/314-QA-rss-source-body-excerpt-followup.md`

### 2. diff概要

- 報知の現行本文 container `preview__detail` を source 本文抽出 selector に追加。
- Full-Count の本文 container `c-wp-post` を本文抽出 selector に追加。
- `script` / `style` / `noscript` / `aside` / `figure` を excerpt 化前に除去。
- `googletag` / `document.write` / `function()` など広告 script 由来の行を除外。
- 先頭のナビ行、日付行、タイトル echo を excerpt から落とす処理を追加。
- RSS draft 作成経路で source HTML を `raw_html` として enrichment へ渡す。
- source HTML が取れない場合は従来どおり本文生成を止めない。

### 3. 実行したテスト

- 赤確認:
  - `python3 -m unittest tests.test_source_article_body_extractor.SiteSelectorPathTests tests.test_source_article_body_extractor.TruncationTests.test_max_chars_caps_at_sentence_boundary`
  - `python3 -m unittest tests.test_rss_fetcher_reliability_2026_05_08.CreateDraftForceStatusTests.test_enrichment_raw_html_reaches_rss_pipeline`
- green 確認:
  - `python3 -m unittest tests.test_source_article_body_extractor.SiteSelectorPathTests tests.test_source_article_body_extractor.TruncationTests.test_max_chars_caps_at_sentence_boundary`
  - `python3 -m unittest tests.test_rss_fetcher_reliability_2026_05_08.CreateDraftForceStatusTests.test_enrichment_raw_html_reaches_rss_pipeline`
  - `python3 -m unittest tests.test_source_article_body_extractor`
  - `python3 -m unittest tests.test_manual_intake`
  - `python3 -m unittest tests.test_rss_fetcher_reliability_2026_05_08`
  - `python3 -m unittest discover -s tests`

### 4. テスト結果

- 追加再現テストは修正前に赤を確認。
- 修正後、追加再現テストは green。
- 関連テスト green。
- `python3 -m unittest discover -s tests` は通常 sandbox では local HTTPServer の socket 作成が `PermissionError: [Errno 1] Operation not permitted` で 3 error。
- 同じ全件テストをローカル socket 許可付きで再実行し、`Ran 3377 tests in 63.479s OK`。

### 5. 残った懸念

- 実HTMLの構造変更がある媒体では selector 追加が必要になる可能性は残る。
- source HTML 取得が増えるため、RSS / tag_scrape 実行時間はやや伸びる可能性がある。
- excerpt は 600文字以内であり、元記事全文に近づけない方針は維持。

### 6. 新しく見つかったデグレ

- 今回差分による新規デグレはテスト上確認なし。
- 既存全件テストは sandbox の socket 制限では失敗したが、許可付き再実行では通過。

### 7. 追加した回帰テスト

- 報知 `preview__detail` から本文だけ取れること。
- BaseballKing の広告 script 風テキストを excerpt に混ぜないこと。
- Full-Count の本文 selector で日付・広告を混ぜないこと。
- 600文字上限を sentence boundary 処理後も超えないこと。
- RSS draft 作成経路から enrichment へ `raw_html` が渡り、`📖 本文抜粋` が出せること。

### 8. 次回触ってはいけない範囲

- publish
- mail
- scheduler
- env
- secrets
- Cloud Run 設定
- GitHub Actions
- SEO / schema
- アイキャッチ選定
- Instagram 取り込み
- X 自動投稿
