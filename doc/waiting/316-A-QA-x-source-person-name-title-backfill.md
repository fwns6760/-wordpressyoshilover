# 316-A-QA X source person name title backfill

## 1. 今回の目的

Xポスト本文に選手名・監督名・コーチ名が書かれているのに、記事タイトルや本文で「選手」「投手」「コーチ」「監督」だけになって誰の記事かわからない問題を直す。

方針は固定する。

- Xポスト本文に明記された人物名だけ使う
- source にない名前は足さない
- 画像だけに写っている人物名は使わない
- 記憶や推測で補完しない
- title / body の「選手」「投手」「コーチ」「監督」だけの generic 表現を減らす
- 名前が取れなくても記事生成は止めない

親 ticket:

- `316: remove social fallback instruction leak`

## 2. 今回触る範囲

- `src/rss_fetcher.py`
- 必要なら `src/title_player_name_backfiller.py`
- `tests/test_social_body_template.py`
- 必要なら title / body 生成まわりの既存回帰テスト
- 本 ticket 自身 `doc/waiting/316-A-QA-x-source-person-name-title-backfill.md`

## 3. 今回触らない範囲

- publish
- mail
- scheduler
- env
- secrets
- Cloud Run 設定
- GitHub Actions
- SEO / noindex / canonical / 301
- source 追加
- X 投稿
- Instagram 取り込み
- 画像OCR
- WordPress 本番記事の手動修正
- 指示外の本文テンプレ全体改修
- `doc/README.md`
- `doc/active/assignments.md`

## 4. 影響範囲

- RSS / social_news 経路の title 生成
- Xポスト本文を source とする記事の人物名保持
- fallback 本文内の generic 表現
- 「誰の記事かわからない」タイトルの発生率

本線への影響は title / body の人物名補強に限定する。publish / mail / scheduler / env / Cloud Run 設定には直接影響させない。

## 5. 実行予定テスト

追加する再現テスト:

- Xポスト本文に「浦田俊輔」など人物名がある時、title が「選手」だけにならない
- Xポスト本文に「阿部監督」がある時、title / body に阿部監督を残す
- Xポスト本文に「内海投手コーチ」などコーチ名がある時、generic な「投手コーチ」だけにしない
- Xポスト本文に人物名がない時は、推測で名前を足さない
- source が短い時も記事生成は止めない
- LLM自由作文、主観、source にない選手名・数字・コメントが出ない

実行順:

1. 追加再現テストだけ実行して赤確認
2. コード修正
3. 追加再現テストを再実行して green 確認
4. 関連テスト実行
   - `python3 -m unittest tests.test_social_body_template`
   - 必要なら title 生成 / build_news_block 関連テスト
5. 可能なら既存テスト全件
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 追加再現テストの赤確認ができない
- Xポスト本文にない人物名を足す必要が出る
- 画像OCRや外部人物DBが必要になる
- 記憶や推測で選手名・コーチ名を補完する方向になる
- source にない数字・コメント・評価を足す必要が出る
- publish / mail / scheduler / env / secrets / Cloud Run 設定を触る必要が出る
- `python3 -m unittest discover -s tests` が通らない
- 既存のユーザー未コミット差分を戻す必要が出る

## 7. 禁止事項

- source にない選手名・監督名・コーチ名を足す
- 画像だけから人物名を推測する
- LLM に人物名を補完させる
- X API live call を増やす
- source 追加を混ぜる
- publish / mail / scheduler / env / secrets / Cloud Run 設定に触る
- ついで修正をする
- `git add -A` を使う
- diff 提示前に commit する
- テスト未実行で commit / push / deploy する

## 8. 想定されるデグレ

- source にない人物名を誤って title に入れる
- 「選手」「投手」を消しすぎて title が不自然になる
- 監督・コーチ名を選手名として扱う
- 複数人物が出る Xポストで主語を誤る
- title と本文の主語がずれる
- short source の記事生成が止まる

## 9. 作業ログ欄

| 日時 | 内容 | 結果 |
| --- | --- | --- |
| 2026-05-10 JST | user が「Xのポストに書いてある選手名やコーチ名は入れてほしい。本文にはない」と指摘 | 316 子 ticket として起票 |
| 2026-05-10 JST | Codex が title backfill / weak title rescue の恒久対策を実装。`#浦田俊輔 選手` のような X 本文内実名を title に反映し、title では `選手` suffix を出さない方針に統一 | focused tests pass。publish / mail / scheduler / env / Cloud Run / gate 緩和なし |
| 2026-05-10 JST | user が deploy 前レビューで残リスクを確認し「更に安全にしたい」と指示 | 複数人物同数時は先頭人物を採らず neutral `巨人` title に退避。明示 role 付き候補を loose 候補より優先。媒体名風 stopword を追加。full unittest / pytest baseline pass |

## 10. Regression Memo欄

- 本番 post `66043` で title / body に「選手から...」のような generic 表現が残った。
- Xポスト本文に人物名がある場合は source 事実なので使用可。
- ただし Xポスト本文にない名前、画像だけに写る名前、記憶由来の名前は使用不可。
- 受け入れの核は「source text にある人物名を保持し、generic title を減らす」こと。

## 作業後追記

### 1. 実際に変更したファイル

- `src/title_player_name_backfiller.py`
- `src/weak_title_rescue.py`
- `tests/test_title_player_name_backfill.py`
- `tests/test_weak_title_rescue.py`
- `doc/waiting/316-A-QA-x-source-person-name-title-backfill.md`

### 2. diff概要

- X本文/summary/source本文の `#浦田俊輔 選手` のような表記から人物名を拾えるように、title backfill の名前+役割抽出を `#` と空白区切りに対応。
- `若手` / `紹介` / `スポーツ報知巨人班X` などを人名候補として誤採用しないよう、名前候補 stopword を追加。
- title 表示では `選手` suffix を付けず、`浦田俊輔、昇格・復帰 関連情報` のように実名だけを出す方針へ変更。
- weak title rescue でも `泉口友汰選手、...` ではなく `泉口友汰、...` に揃えた。
- 複数人物が同数で出る場合は先頭人物を採らず、generic title を `巨人、...` に退避する。
- 複数人物でも 1 人だけ出現頻度が明確に高い場合だけ、その人物を title に採用する。
- `山瀬慎之助捕手` のような明示 role 付き候補は、`日仕様` のような loose 候補より優先する。
- `ベースボールキングX` など未知媒体名風の source title を人名扱いしない stopword fragment を追加。
- skip/review 条件、narrow unlock、publish/mail/scheduler/env/Cloud Run は変更なし。

### 3. 実行したテスト

- `rg -n "backfill_title_player_name|_NAME_WITH_ROLE_RE|ROLE_DISPLAY_SUFFIXES|weak_title_rescue|per-commit safety gate|選手、昇格" ...`
- `python3 -m unittest tests.test_title_player_name_backfill -v`
- `python3 -m unittest tests.test_title_player_name_backfill tests.test_weak_title_rescue -v`
- `python3 -m unittest tests.test_narrow_unlock_subtype_aware tests.test_title_validator tests.test_rss_fetcher_article_quality_v1 -v`
- `python3 -m unittest tests.test_social_body_template -v`
- `python3 -m unittest discover -s tests`
- `python3 -m compileall -q src/title_player_name_backfiller.py src/weak_title_rescue.py tests/test_title_player_name_backfill.py tests/test_weak_title_rescue.py`
- `python3 -c "import ast, pathlib; ..."` for touched Python files
- `python3 -m pytest -q`
- follow-up: `python3 -m compileall -q src/title_player_name_backfiller.py tests/test_title_player_name_backfill.py`
- follow-up: `python3 -c "import ast, pathlib; ..."` for follow-up touched Python files
- follow-up: `python3 -m unittest tests.test_title_player_name_backfill -v`
- follow-up: `python3 -m unittest tests.test_title_player_name_backfill tests.test_weak_title_rescue -v`
- follow-up: `python3 -m unittest tests.test_narrow_unlock_subtype_aware tests.test_title_validator tests.test_rss_fetcher_article_quality_v1 -v`
- follow-up: `python3 -m unittest tests.test_social_body_template -v`
- follow-up: `python3 -m unittest discover -s tests`
- follow-up: `python3 -m pytest -q`

### 4. テスト結果

- PASS
- 追加指示後の targeted grep PASS。対象 identifier / 既存 test / 運用ロック追記箇所を確認。
- focused / related / social body / full unittest すべて PASS。
- full unittest は sandbox の localhost socket 制限で初回のみ `PermissionError` になったため、同一コマンドを escalation で再実行し `Ran 3380 tests ... OK` を確認。
- compile check PASS。
- AST parse check PASS (`AST OK 4`)。
- pytest baseline は sandbox の localhost socket 制限で初回のみ `3548 passed / 3 failed`。失敗 3 件は `tests/test_manual_intake_service.py::LiveServerSmokeTest` の `PermissionError: [Errno 1] Operation not permitted`。
- 同一 pytest コマンドを escalation で再実行し `3551 passed, 3 warnings, 908 subtests passed` を確認。
- requests dependency warning と related posts の example.com fallback log は既存テスト内の警告/ログ。
- fire / live execution は未実施。log + 数値 diff は `N/A: no fire/live execution`。
- follow-up compile check PASS。
- follow-up AST parse check PASS (`AST OK 2`)。
- follow-up focused title tests PASS (`Ran 12 tests ... OK`)。初回は `日仕様` loose 候補を拾う fail が出たため、明示 role 付き候補優先に修正して green。
- follow-up title + weak rescue tests PASS (`Ran 30 tests ... OK`)。
- follow-up related tests PASS (`Ran 51 tests ... OK`)。
- follow-up social body tests PASS (`Ran 6 tests ... OK`)。
- follow-up full unittest は sandbox の localhost socket 制限で初回のみ `Ran 3382 tests ... FAILED (errors=3)`。失敗 3 件は `tests/test_manual_intake_service.py::LiveServerSmokeTest` の `PermissionError: [Errno 1] Operation not permitted`。
- follow-up full unittest を escalation で再実行し `Ran 3382 tests ... OK` を確認。
- follow-up pytest baseline を escalation で実行し `3553 passed, 3 warnings, 908 subtests passed` を確認。
- follow-up fire / live execution は未実施。log + 数値 diff は `N/A: no fire/live execution`。

### 5. 残った懸念

- 本修正は title の人物名 backfill / suffix 表示に限定。本文中の generic `選手` 全削除は未実施。
- X本文に実名がない場合、source にない名前は足さない。既存 gate / review 判定も緩めない。
- 複数人物が同数の場合は誤名を避けるため `巨人、...` に退避する。実名 title にはならないが、generic `選手` は残さない。

### 6. 新しく見つかったデグレ

- 初回赤確認で `スポーツ報知巨人班X` / `紹介` を人名扱いする候補抽出ミスを確認し、stopword 追加で修正済み。
- follow-up focused test で `日仕様` を人名扱いする loose 候補優先ミスを確認し、role 付き候補優先で修正済み。

### 7. 追加した回帰テスト

- `test_x_post_hashtag_player_name_replaces_generic_player_word_without_suffix`
- `test_fetcher_adapter_uses_x_post_name_and_does_not_leave_player_word`
- `test_unknown_media_like_source_title_does_not_become_player_name`
- `test_multiple_candidates_tie_uses_neutral_subject_without_player_word`
- 既存 backfill / weak title rescue expectation を `〜選手` suffix なしに更新。
- 既存 multiple candidates expectation を「先頭採用」から「出現頻度が明確な候補だけ採用」に更新。

### 8. 次回触ってはいけない範囲

- publish
- mail
- scheduler
- env
- secrets
- Cloud Run 設定
- GitHub Actions
- SEO / noindex / canonical / 301
- source 追加
- X 投稿
- Instagram 取り込み
- 画像OCR
