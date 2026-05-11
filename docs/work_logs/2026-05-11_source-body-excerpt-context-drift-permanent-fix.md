# 2026-05-11 source body excerpt context drift permanent fix work log

## 1. 目的

post `66369` などで、タイトル / source URL と `📖 本文抜粋` の内容が別記事にずれる問題を、今後の生成で恒久的に防ぐ。

lead / summary / JSON-LD author の混線も観測しているが、今回の直接修正は `📖 本文抜粋` の誤挿入 guard に限定する。

公開済み記事の本文修正は行わない。

## 2. 現時点の観測

- post `66369` は、タイトルと出典URLが報知記事だが、`📖 本文抜粋` と lead / description / JSON-LD author が日刊スポーツ系の別記事に寄っている。
- post `66296` でも、出典URLと異なる大城卓三ヘルメット直撃記事の抜粋混入を確認した。
- 既存 ticket `323-QA-source-body-excerpt-clean-truncation` では post `66331` 型の source excerpt context drift を扱っているが、`66369` 型は summary / lead 側も汚染されるため、既存ガードをすり抜ける可能性がある。
- 現行 `_source_excerpt_matches_context()` は title だけでなく summary も照合語に使うため、summary が汚染されている場合に wrong excerpt を通すリスクがある。

## 3. 今回触らない範囲

- 公開済み WP 記事本文の修正
- WP post status 変更
- publish 条件
- mail 通知
- scheduler
- Cloud Run service / job 設定
- Cloud Run env
- Secret Manager
- GitHub Actions
- SEO / noindex / canonical / 301
- X投稿 / X API / 自動投稿
- source 追加
- featured_media / アイキャッチ選定
- frontend / AdSense / scroll UI
- Gemini / Grok / LLM call 追加
- unrelated docs / logs / build artifacts
- 既存 dirty worktree の差分

## 4. 影響範囲

直接影響する可能性:

- manual intake / RSS enrichment の source body excerpt block 挿入可否
- source URL / title と excerpt の文脈一致判定
- summary が汚染されていても source excerpt block がそれを信頼しないこと
- `📖 本文抜粋` の silent wrong insertion 抑止

影響させない範囲:

- 既存公開記事の表示
- 記事公開可否
- メール送信量
- scheduler 実行頻度
- Cloud Run revision / env
- X投稿文生成
- SEO設定
- アイキャッチ fallback

## 5. 実行予定テスト

実装では、先に再現テストを追加して赤確認する。

- `tests/test_manual_intake.py`
  - `66369` 型: title/source URL は報知記事、summary/raw_html は別記事寄りの場合に `📖 本文抜粋` を挿入しないこと。
  - summary が汚染されても、title/source URL と excerpt が一致しなければ source excerpt block を出さないこと。
  - 正常な title/source URL/raw_html の組み合わせでは source excerpt block が残ること。
  - excerpt skip 時に記事生成自体は止めないこと。
- 必要に応じて `tests/test_source_article_body_extractor.py`
  - extractor は source にない文を補完しないこと。
- targeted:
  - `python3 -m unittest tests.test_manual_intake.SourceBodyExcerptExpansionTests`
  - `python3 -m unittest tests.test_manual_intake`
  - `python3 -m unittest tests.test_source_article_body_extractor`
- touched Python がある場合:
  - `python3 -m py_compile <touched files>`
  - `python3 -m compileall <touched files>`
  - AST parse check
- baseline:
  - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 再現テストの赤確認ができない。
- 恒久修正に source にない文の作文 / LLM 補完が必要になる。
- publish / mail / scheduler / env / Cloud Run / GitHub Actions を触る必要が出る。
- WP 公開済み記事の本文修正が必要になる。
- X投稿や X API に触る必要が出る。
- source 追加が必要になる。
- featured_media / アイキャッチ選定に波及する。
- 既存 dirty worktree を戻す必要が出る。
- diff が title / source excerpt / summary guard 以外へ広がる。
- full test が赤のまま原因説明できない。

## 7. 禁止事項

- 公開済み WP 記事を修正しない。
- WP post status を変更しない。
- `git add -A` しない。
- push しない。
- deploy しない。
- env / Secret / scheduler / Cloud Run 設定を変更しない。
- X API を叩かない。
- Xへ投稿しない。
- frontend / AdSense / CSS を触らない。
- アイキャッチ / featured_media を同じ作業に混ぜない。
- source にない本文・数字・選手名を補完しない。
- AI の記憶から再構成しない。
- silent skip で終わらせない。
- 自己評価 OK で終わらせない。

## 8. 想定されるデグレ

- 安全側に倒しすぎて、正しい source excerpt block まで出なくなる。
- title が抽象的な記事で、本文抜粋を過剰 skip する。
- summary を使わないことで、短いタイトルの記事の文脈判定が弱くなる。
- player / team name だけの一致を generic と見なしすぎ、正しい記事を落とす。
- source excerpt block が減り、本文の情報量が下がる。
- guard の条件追加により、manual intake / RSS enrichment の既存 fixture が落ちる。

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-11 JST | work log作成 | user 指示「公開記事は直さないでよい。恒久的に直して」により、既存 WP 記事修正を対象外に固定し、今後の生成を止める恒久対応の作業記録を作成。コード編集・commit・push・deploy・env変更・scheduler変更は未実施。 |
| 2026-05-11 JST | 回帰テスト追加 | post `66369` 型として、title/source URL は報知 YouTube 記事、summary/raw_html は大城卓三ヘルメット直撃記事寄りの場合に `📖 本文抜粋` を挿入しないテストを追加。 |
| 2026-05-11 JST | 赤確認 | 追加テスト単体で失敗し、現行実装が汚染 summary の語句を使って別記事本文抜粋を通すことを確認。 |
| 2026-05-11 JST | 実装 | `_source_excerpt_matches_context()` を title-first 判定に変更。title 由来の非 generic term がある場合は title との一致を必須にし、summary は title から usable term を作れない時だけ fallback として使う。 |
| 2026-05-11 JST | 緑確認 | targeted / manual intake / source extractor / compile / AST / full unittest を実行。sandbox full suite は既存 localhost socket 制限で3 error、権限付き再実行で `Ran 3425 tests ... OK`。 |

## 10. Regression Memo欄

- 事故の本質は「title/source URL と body excerpt の source context drift」。lead / summary / author drift は関連する残懸念として扱う。
- 公開済み記事は修正しない。恒久対応は今後の生成 guard と regression test に限定する。
- `summary` は汚染され得るため、source excerpt の通過条件として強く信頼しない。
- `title` / `source_url` / source HTML 由来本文の関係を fixture で固定する。
- source と一致しない excerpt は block を出さず、記事生成は止めない。
- source にない本文を AI が補完しない。
- silent skip 防止のため、skip 理由を既存ログまたはテストで確認できる形にする。

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/tools/manual_intake.py`
- `tests/test_manual_intake.py`
- `docs/work_logs/2026-05-11_source-body-excerpt-context-drift-permanent-fix.md`

### 2. diff概要

- `tests/test_manual_intake.py`
  - `SourceBodyExcerptExpansionTests` に post `66369` 型の回帰テストを追加。
  - title/source URL は報知 YouTube 記事、summary/raw_html は大城卓三ヘルメット直撃記事寄りの fixture を作り、`📖 本文抜粋` と `大城卓三` が出ないことを固定。
- `src/tools/manual_intake.py`
  - `_source_excerpt_matches_context()` の照合順を title-first に変更。
  - title から非 generic context term を作れる場合は、excerpt が title と一致しない限り block を挿入しない。
  - summary は汚染され得るため、title から usable term が作れない場合だけ fallback として使う。
- 作業ログへ、赤確認、実装、テスト結果を追記。

### 3. 実行したテスト

- `python3 -m unittest tests.test_manual_intake.SourceBodyExcerptExpansionTests.test_rss_pipeline_source_body_excerpt_ignores_polluted_summary_for_66369`
- `python3 -m unittest tests.test_manual_intake.SourceBodyExcerptExpansionTests`
- `python3 -m unittest tests.test_manual_intake`
- `python3 -m unittest tests.test_source_article_body_extractor`
- `python3 -m py_compile src/tools/manual_intake.py tests/test_manual_intake.py`
- `python3 -m compileall src/tools/manual_intake.py tests/test_manual_intake.py`
- AST parse for `src/tools/manual_intake.py` and `tests/test_manual_intake.py`
- `python3 -m unittest discover -s tests`
- `python3 -m unittest discover -s tests` (sandbox localhost bind failure のため権限付き再実行)

### 4. テスト結果

- 赤確認:
  - 追加テスト単体で失敗。
  - failure: `📖 本文抜粋` が挿入され、wrong excerpt に `大城卓三` が出た。
- 修正後:
  - 追加 targeted 1 test: OK
  - `SourceBodyExcerptExpansionTests`: 8 tests OK
  - `tests.test_manual_intake`: 74 tests OK
  - `tests.test_source_article_body_extractor`: 17 tests OK
  - `py_compile`: OK
  - `compileall`: OK
  - AST parse: OK
  - sandbox full suite: `Ran 3425 tests ... FAILED (errors=3)`
    - `tests/test_manual_intake_service.py::LiveServerSmokeTest` の localhost socket bind が `PermissionError: [Errno 1] Operation not permitted`
  - 権限付き full suite: `Ran 3425 tests in 51.980s ... OK`

### 5. 残った懸念

- title が短い / 汎用的すぎる場合は summary fallback が残る。ただし title から usable term が作れる通常記事では title-first で wrong excerpt を止める。
- 安全側に倒すため、title と本文で語彙が大きく違う記事では `📖 本文抜粋` が出ない可能性がある。
- 既存公開記事 `66296` / `66369` は user 指示どおり修正していない。
- deploy / runtime ログ観測は未実施。

### 6. 新しく見つかったデグレ

- 赤確認で、汚染 summary の語句だけで wrong source excerpt が context match になり得ることを確認。
- 修正後テストでは新規デグレなし。

### 7. 追加した回帰テスト

- `tests.test_manual_intake.SourceBodyExcerptExpansionTests.test_rss_pipeline_source_body_excerpt_ignores_polluted_summary_for_66369`

### 8. 次回触ってはいけない範囲

- 公開済み WP 記事本文の修正
- WP post status 変更
- publish / mail / scheduler / env / Cloud Run / Secret / GitHub Actions
- X API / X投稿
- source 追加
- featured_media / アイキャッチ選定
- frontend / AdSense / CSS
- unrelated dirty files
