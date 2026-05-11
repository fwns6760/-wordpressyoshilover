# 323-QA-source-body-excerpt-clean-truncation

| field | value |
|---|---|
| ticket_id | 323-QA-source-body-excerpt-clean-truncation |
| priority | P1 |
| status | BLOCKED_USER_DIFF_REVIEW |
| owner | Codex B |
| lane | B |
| created | 2026-05-11 |
| doc_path | doc/waiting/323-QA-source-body-excerpt-clean-truncation.md |
| related | 314-QA-rss-source-body-excerpt-followup / 312-QA-source-body-excerpt-expansion / 315-QA-source-featured-media-site-extraction |
| evidence_post_id | 66280 |

## 1. 今回の目的

ブログ本文の `📖 本文抜粋` が、600文字化後も途中で切れたり、本文以外のノイズを含んだりする問題を狭く直す。

対象は「ブログ本文の抜粋表示」だけ。

- source記事本文の主要段落だけを抜く
- title echo / date / navigation / share UI / 通知ON/OFF / 関連記事 / おすすめ記事を抜粋に混ぜない
- 600文字以内を守りつつ、文章の途中で不自然に切らない
- 取れない場合は excerpt block を出さず、記事生成は止めない

## 2. 背景

`312` で source本文 excerpt を広げ、`314` で RSS / tag_scrape 経路にも `raw_html` を渡して 600文字 excerpt を使うようにした。

その後、post `66280` で以下を確認した。

- タイトルと出典URLは Daily の坂本記事
- ブログ本文の `📖 本文抜粋` は長く出るようになった
- ただし、抜粋表示としては途中で切れて見える
- Daily HTML を現行 extractor に直接通すと、本文以外に title echo / 日付 / `拡大` / `続きを見る` / `野球スコア速報` / `編集者のオススメ記事` などが混ざる

今回 ticket は「その2: ブログ本文の抜粋が途中で切れる / ノイズが混ざる」だけを扱う。

別記事本文が混ざる問題、別媒体画像が混ざる問題は関連するが、本 ticket の主目的ではない。

## 3. 今回触ってよい範囲

実装 GO 後に触ってよい範囲:

- `src/source_article_body_extractor.py`
- `src/tools/manual_intake.py`
- 必要な場合のみ `src/rss_fetcher.py` の `raw_html` / enrichment 受け渡し周辺
- `tests/test_source_article_body_extractor.py`
- `tests/test_manual_intake.py`
- 必要な場合のみ RSS enrichment 関連の既存テスト
- 本 ticket Markdown の作業ログ追記

## 4. 今回触ってはいけない範囲

- publish 条件
- mail 通知
- scheduler
- Cloud Run env
- Cloud Run service / job 設定
- Secret Manager
- GitHub Actions
- SEO / noindex / canonical / 301
- X投稿 / X API / 自動投稿
- source 追加
- featured_media / アイキャッチ選定
- frontend / 320-FRONT / AdSense / scroll UI
- WP本番記事本文の手動修正
- Gemini / Grok / LLM call 追加

## 5. 影響範囲

直接影響:

- `📖 本文抜粋` block の本文抽出品質
- 600文字以内の excerpt 切り方
- source本文が薄い時の fallback

影響しない範囲:

- 記事の公開可否
- メール送信量
- scheduler実行頻度
- Cloud Run revision / env
- X投稿文生成
- SEO設定
- WP post status

## 6. API / 状態変更

なし。

REST API、WP meta、option、DB table、Cloud Run env、Scheduler は変更しない。

## 7. 実装方針

1. Daily 66280 型の実HTML fixtureまたは最小HTML fixtureで再現テストを先に追加する。
2. 現行 extractor が本文以外の行を混ぜること、または不自然に途中で切ることを赤で確認する。
3. site-specific selector または本文候補の後処理を狭く追加する。
4. 抜粋は source HTML 由来の literal text だけにする。
5. sentence boundary / paragraph boundary を優先し、本文が取れない場合は `""` を返す。
6. excerpt 不足を LLM や独自作文で補わない。

## 8. Acceptance

- Daily 66280 型の本文から、坂本記事本文の主要段落だけが抜ける。
- 抜粋に以下が混ざらない。
  - title echo
  - 日付だけの行
  - `拡大`
  - `続きを見る`
  - `野球スコア速報`
  - `編集者のオススメ記事`
  - `通知ON`
  - `通知OFF`
  - share / SNS UI 文言
- 600文字以内を守る。
- 文末に安全な句点がある場合、任意の途中切りをしない。
- source本文が安全に取れない場合、記事生成は止めず `📖 本文抜粋` を出さない。
- sourceにない文、数字、選手名、コメントを足さない。

## 9. テスト計画

追加する回帰テスト:

- Daily 66280 型HTMLで、本文以外の UI / 関連記事 / おすすめ記事が excerpt に混ざらない。
- Daily 66280 型HTMLで、本文段落が600文字以内かつ自然な境界で返る。
- source本文が短すぎる / selector不一致の場合、`""` を返して block を出さない。
- 既存の報知 / 日刊 / Full-Count / BaseballKing の excerpt テストを壊さない。

実行予定:

- `python3 -m unittest tests.test_source_article_body_extractor`
- `python3 -m unittest tests.test_manual_intake`
- 必要なら RSS enrichment 関連テスト
- 可能なら `python3 -m unittest discover -s tests`

## 10. STOP条件

- 再現テストの赤確認ができない
- 600文字以内で自然な excerpt を作るには sourceにない文の補完が必要になる
- 全文転載に近づく
- publish / mail / scheduler / env / Cloud Run / GitHub Actions を触る必要が出る
- X投稿や自動投稿に触る必要が出る
- 既存の未コミット差分を戻す必要が出る

## 11. 作業ログ

| timestamp | action | note |
|---|---|---|
| 2026-05-11 JST | ticket作成 | user指示「その2を何かと関連してチケットを切って」により、314関連の狭い follow-up として起票。実装、commit、push、deploy、env変更、scheduler変更は未実施。 |
| 2026-05-11 JST | 赤確認 | Daily detailContent fixture と leading date/通知ON/OFF fixture を追加し、現行 extractor が title/date/UI/recommend/score/notification を混ぜることを確認。 |
| 2026-05-11 JST | 実装 | `daily.co.jp` の `NWrelart:Body` / `mainTxt` selector を追加。date / boilerplate / title echo 除去を狭く強化。LLM / network / publish / mail / scheduler / env / X / SEO は未変更。 |
| 2026-05-11 JST | 緑確認 | targeted 2 tests OK、`tests.test_source_article_body_extractor` 17 tests OK、`tests.test_manual_intake` 70 tests OK、RSS enrichment targeted 1 test OK、`python3 -m unittest discover -s tests` 3419 tests OK。 |
| 2026-05-11 JST | 実HTML確認 | `/tmp/66280_daily.html` の Daily 坂本記事で本文主要2段落のみを抽出し、`拡大` / `続きを見る` / `野球スコア速報` / `編集者のオススメ記事` は混入しないことを確認。 |
| 2026-05-11 JST | 再発確認 | post `66331` で、出典リンクは報知 `20260511-OHT1T51228` だが `📖 本文抜粋` が日刊系の大城卓三バット直撃記事になっていることを WP REST で確認。 |
| 2026-05-11 JST | 原因切り分け | live `yoshilover-fetcher` image は `951d2f5`。同 commit は `d5e40a2` の extractor 清掃を含むが、`24cd9cb` の source excerpt context guard は未反映。 |
| 2026-05-11 JST | 追加回帰テスト | `tests.test_manual_intake.SourceBodyExcerptExpansionTests.test_rss_pipeline_source_body_excerpt_skips_66331_cross_article_body` を追加し、`66331` 型の title/source_url と別記事 raw_html では `📖 本文抜粋` を出さないことを固定。 |
| 2026-05-11 JST | 緑確認 | `python3 -m py_compile tests/test_manual_intake.py` OK、AST parse OK、追加 targeted 1 test OK、`tests.test_manual_intake.SourceBodyExcerptExpansionTests` 7 tests OK、`tests.test_manual_intake` 73 tests OK、`tests.test_source_article_body_extractor` 17 tests OK、`python3 -m unittest discover -s tests` 3422 tests OK。 |
