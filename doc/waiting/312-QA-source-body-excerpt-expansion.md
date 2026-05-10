# 312-QA source body excerpt expansion

## meta

- number: 312-QA
- type: article body / source excerpt expansion / regression-safe rendering
- status: BLOCKED_USER
- priority: P1
- owner: user GO 待ち
- implementation_owner: Codex after GO
- lane: B
- created: 2026-05-10
- doc_path: `doc/waiting/312-QA-source-body-excerpt-expansion.md`
- note: user 制約により初手はこの Markdown 新規作成のみ。code edit、commit、push、deploy、env / scheduler 変更は GO 後まで保留

## 1. 今回の目的

元記事本文から引ける literal excerpt を、今より広く記事本文に使う。

主眼は次の 3 点。

- 本文が十分長い source から、今より多く本文抜粋を使う
- `short_news_url / postgame` 以外の template にも適用範囲を広げる
- excerpt が取れなくても記事生成を止めず、元本文のまま出せるようにする

今回の方針は、LLM による再構成ではなく、source HTML から抽出した literal substring をそのまま使うこと。

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/tools/manual_intake.py`
- 必要なら `src/source_article_body_extractor.py`
- excerpt block 関連 test
- 本 ticket 自身 `doc/waiting/312-QA-source-body-excerpt-expansion.md`

実装観点は次の 3 本に限定する。

- `本文抜粋` block の適用対象 template を広げる
- excerpt の取得量を今より増やす
- excerpt が取れない時の graceful fallback を維持する

## 3. 今回触らない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/rss_fetcher.py` の publish 条件本体
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- X 自動投稿、SEO、schema、アイキャッチ選定
- WordPress 本番記事の手修正、WP admin 操作
- `doc/README.md` / `doc/active/assignments.md` の同期

## 4. 影響範囲

- `manual_intake` 経路の記事本文見え方
- `📖 本文抜粋` block の出現対象
- source 本文抽出量と記事情報密度

直接影響は本文 presentation だが、適用を広げすぎると

- title と同じ情報ばかりの excerpt が増える
- 引用量が増えすぎて本文の核がぼやける
- source ごとの DOM 差で excerpt が安定しない

可能性がある。

## 5. 実行予定テスト

GO 後の予定テストは次の通り。

1. regression tests
   - `選手情報 / 首脳陣 / 公示 / スタメン / 予告先発 / 短報` で `本文抜粋` block が出る
   - source 本文が取れない時は元本文のまま
   - excerpt の長さ上限と sentence boundary が守られる
   - title に近い excerpt でも、source 本文が十分ある時は安全に表示できる
2. related unit tests
   - `tests/test_manual_intake.py`
   - 必要なら `tests/test_source_article_body_extractor.py`
3. full suite
   - `python3 -m unittest discover -s tests`
4. output spot-check
   - representative article type ごとに `本文抜粋` の見え方を確認

## 6. STOP条件

- excerpt 拡張のために publish / mail / scheduler / env / Cloud Run 変更が必要になった場合
- literal excerpt ではなく LLM 再構成に寄らないと成立しない場合
- excerpt を増やすために全文転載に近づく場合
- 追加テストの赤確認ができない場合
- 全件テスト green を満たせない場合

## 7. 禁止事項

- user の GO 前に code edit しない
- commit / push / deploy / env 変更 / scheduler 変更をしない
- `git add -A` を使わない
- source に無い文を補って excerpt のように見せない
- excerpt 不足を LLM prose で埋めない
- excerpt が取れないことを理由に記事生成を止めない

## 8. 想定されるデグレ

- excerpt block が増えすぎて本文が冗長になる
- source DOM 差で一部 template だけ excerpt が出ない
- title と同内容の excerpt が増え、情報密度改善が弱く見える
- 引用量が増えすぎて本文の固有構造より excerpt が主役になる

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-10 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |

## 10. Regression Memo欄

### current observation

- `source_article_body_extractor.py` は本文 excerpt を取れるが、現在の使い方は一部 template に限定されている
- `manual_intake.py` では主に `short_news_url / postgame` だけが `📖 本文抜粋` block を使っている
- 本文が長い source でも、現状は `max_chars=240` 相当の短い excerpt しか出していない
- 記事のつまらなさは「source 本文を使えていないこと」も大きい

### guard hypothesis

- common guard A: excerpt は literal substring のまま使う
- common guard B: excerpt が取れない時は元本文をそのまま出す
- common guard C: excerpt 量は増やすが、記事生成や運用本線の blocker にしない

## 11. 作業後追記欄

GO 後の実装完了時に、同じファイルへ次を追記する。

- 実際に変更したファイル
- diff概要
- 実行したテスト
- テスト結果
- 残った懸念
- 新しく見つかったデグレ
- 追加した回帰テスト
- 次回触ってはいけない範囲

### 2026-05-10 Codex edit pass

#### 実際に変更したファイル

- `src/tools/manual_intake.py`
- `tests/test_manual_intake.py`
- `tests/test_source_article_body_extractor.py`
- `doc/waiting/312-QA-source-body-excerpt-expansion.md`

`src/source_article_body_extractor.py` は既存 extractor のまま変更なし。

#### diff概要

- `manual_intake` の source本文 excerpt 上限を `SOURCE_BODY_EXCERPT_MAX_CHARS = 360` として明示。
- `short_news_url / postgame` 限定だった `📖 本文抜粋` 挿入を `_maybe_insert_source_body_excerpt()` に集約し、nomotoke renderer 成功時の全 template に適用。
- renderer が required-facts gate で落ちて fallback shell になった場合も、`apply_rss_pipeline_enrichment()` 内で同じ source本文 excerpt を挿入。
- excerpt 抽出失敗 / source本文なし / extractor import失敗 / parse例外では、元本文をそのまま返す graceful fallback を維持。
- `_try_render_via_nomotoke()` 内の `normalized_source_published_at` 未定義参照を、引数の `source_published_at_iso` に修正。
- LLM本文生成、sourceにない文の追加、publish/mail/scheduler/env/Cloud Run/secrets/GitHub Actions 変更はなし。

#### 追加した回帰テスト

- `manual_intake` の全 `ARTICLE_TYPE_OVERRIDES` で、source本文がある場合に `📖 本文抜粋` が出ること。
- renderer が fallback shell に落ちても、source本文があれば `📖 本文抜粋` が出ること。
- source本文が取れない場合、記事生成は止まらず、元の fallback 本文のまま `📖 本文抜粋` は出ないこと。
- extractor の長さ上限と sentence boundary が守られること。
- title に近い先頭行があっても、source本文が十分ある場合は本文 detail を返すこと。

#### 実行したテスト

- `python3 -m unittest tests.test_manual_intake.SourceBodyExcerptExpansionTests`
  - 追加直後の赤確認: fail / error を確認
  - 実装修正後: OK
- `python3 -m unittest tests.test_source_article_body_extractor`
  - OK
- `python3 -m unittest tests.test_manual_intake`
  - OK
- `python3 -m unittest discover -s tests`
  - sandbox内: local HTTPServer socket 作成が `PermissionError` で 3 error
  - 権限付き再実行: `Ran 3349 tests ... OK`

#### 残った懸念

- excerpt は literal 抽出のため、source HTML / JSON-LD / article body wrapper が薄いサイトでは出ない。出ない場合も記事生成は止めない。
- 360 chars へ広げたため情報量は増えるが、全文転載に近づかないよう、今後も上限を無制限化しない。
- source本文の先頭が title と完全一致する場合は既存 extractor の title echo 除去を維持する。

#### 次回触ってはいけない範囲

- publish / mail / scheduler / env / Cloud Run / secrets / GitHub Actions
- `src/rss_fetcher.py` の publish 条件本体
- guarded publish / evaluator / publish notice 系
- SEO / schema / アイキャッチ
- sourceにない文を足す LLM 補完
