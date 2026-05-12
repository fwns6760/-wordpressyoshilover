# 2026-05-12 cross-run topic dedup persistence work log

## 1. 今回の目的

報知・日刊・サンスポ・スポニチなど、媒体が違っても同じ話題の記事が複数本生成されないようにする。

ただし、複数媒体がそろうまで待つ方式にはしない。最初に来た信頼できる1本は通常どおり記事化し、その `topic_signature` を永続履歴に残す。後から来た同一話題の別媒体記事だけを、新規記事にせず skip する。

既存の 319-QA は、同じ `/run` 内の明確な同一話題を skip できるが、別 `/run` にまたがる同一話題の集約はまだ弱い。今回はその不足を狭く補い、先着代表方式で `topic_signature` を永続履歴に残して、次回以降の `/run` でも同一話題を重複扱いできるようにする。

公開済み記事は修正しない。今後生成される記事の重複抑止だけを対象にする。

## 2. 今回触る範囲

この時点で触る範囲は、この作業記録 Markdown の新規作成のみ。

- `docs/work_logs/2026-05-12_cross-run-topic-dedup-persistence.md`

GO 後に実装する場合の想定範囲:

- `src/rss_fetcher.py`
  - duplicate guard / topic_key / ledger / history persistence 周辺
  - 先着代表の `topic_signature` を別 run でも照合する処理
  - 同日 / 同一選手または監督 / 同一 subtype / 主要語の強一致による保守的な topic signature 作成
- `tests/test_rss_fetcher_duplicate_guard.py`
  - 別 run をまたいだ同一 topic skip の回帰テスト
  - 先着1本を待たずに通し、後続だけ skip する回帰テスト
- 必要な場合のみ新規または既存の duplicate / history 関連テスト
- 本 Markdown への作業後追記

## 3. 今回触らない範囲

- 公開済み WP 記事本文の修正
- 既存公開記事の統合・削除・リダイレクト
- WP post status 変更
- publish 条件
- mail 条件
- scheduler
- Cloud Run service / job 設定
- Cloud Run env
- Secret Manager
- GitHub Actions
- SEO / noindex / canonical / 301
- X投稿 / X API / 自動投稿
- source 追加
- DAZN / 日テレ / 試合中ソース制御
- 複数媒体がそろうまで記事化を待つ仕組み
- 後続媒体を既存記事へ追記する仕組み
- featured_media / アイキャッチ選定
- frontend / AdSense / CSS
- Gemini / Grok / LLM call 追加
- unrelated dirty files / build / logs / data の整理

## 4. 影響範囲

直接影響する可能性:

- `rss_fetcher.py` の同一話題重複判定
- 同一日・同一人物・同一 subtype・主要語が強く重なる記事の生成数
- `--limit 10` の枠消費
- duplicate skip reason / summary log
- duplicate ledger / history の記録内容

影響させない範囲:

- 記事の publish 可否そのもの
- publish-notice / mail 送信条件
- scheduler 実行頻度
- Cloud Run revision / env / scaling 設定
- X投稿文生成
- SEO設定
- アイキャッチ fallback
- 既存公開記事

## 5. 実行予定テスト

GO 後は、先に再現テストを追加して赤確認する。

- 再現テスト
  - 1回目の run で、最初に来た信頼できる媒体記事を skip せず通し、`topic_signature` を ledger / history に記録する。
  - 2回目の run で、別URL・別タイトル・別媒体でも同じ `topic_signature` なら skip される。
  - 複数媒体がそろうまで待たず、先着1本が記事化対象になる。
  - 同じ人物でも別角度・別 subtype・主要語が弱い記事は skip されない。
  - 別選手または別 topic_signature の記事は skip されない。
  - skip 時に `duplicate_news_pre_gemini_skip` または同等の skip reason が記録される。
- targeted tests
  - `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py`
  - 必要なら `python3 -m unittest tests.test_rss_fetcher_history_duplicate_audit`
  - 必要なら `python3 -m pytest tests/test_duplicate_prevention_golden.py`
- touched Python checks
  - `python3 -m py_compile src/rss_fetcher.py tests/test_rss_fetcher_duplicate_guard.py`
  - `python3 -m compileall src/rss_fetcher.py tests/test_rss_fetcher_duplicate_guard.py`
  - AST parse for touched Python files
- baseline
  - `python3 -m unittest discover -s tests`
  - sandbox 制限で localhost socket 系が落ちる場合は、原因を記録したうえで権限付き再実行を行う。

## 6. STOP条件

以下に該当したら停止し、コード編集・commit・deploy に進まない。

- GO 前に Markdown 以外の変更が必要になる。
- 別 run 重複判定に env / scheduler / Cloud Run 設定変更が必要になる。
- 公開済み記事の統合・削除・本文修正が必要になる。
- WP REST で既存公開記事を更新する必要が出る。
- source 追加や DAZN / 日テレ / 試合中ソース制御に波及する。
- 複数媒体がそろうまで記事化を待つ必要が出る。
- AI の記憶や推測で topic_signature を作る必要が出る。
- topic_signature が弱く、別話題まで落とす可能性が高い。
- skip 理由をログまたは summary で確認できない。
- 再現テストを赤にできない。
- 追加テストを緑にできない。
- full test が赤のまま原因説明できない。
- diff が duplicate guard / ledger / history 周辺を超える。
- unrelated dirty worktree を戻す必要が出る。

## 7. 禁止事項

- Markdown 作成前後にコード編集しない。
- GO 前に commit しない。
- push しない。
- deploy しない。
- env / Secret / scheduler / Cloud Run 設定を変更しない。
- `git add -A` を使わない。
- 公開済み WP 記事を修正しない。
- X API を叩かない。
- Xへ投稿しない。
- source を追加しない。
- 試合中ソース制御の止めた commit を混ぜない。
- 複数媒体がそろうまで記事化を待つ仕組みにしない。
- 後続媒体を公開済み記事へ自動追記しない。
- frontend / AdSense / CSS を触らない。
- アイキャッチ / featured_media を同じ作業に混ぜない。
- source にない本文・数字・選手名を補完しない。
- AI の記憶から再構成しない。
- silent skip で終わらせない。
- 自己評価 OK で終わらせない。

## 8. 想定されるデグレ

- 同じ選手の別角度記事まで重複扱いしてしまう。
- 主要語の一致条件が強すぎて、関連するが別話題の記事を落とす。
- topic_signature が弱く、期待した重複抑止が効かない。
- 永続履歴が残りすぎて、翌日以降の別件まで skip する。
- 重複skipの ledger / history が増え、ログ確認が読みにくくなる。
- `--limit 10` の候補走査が伸び、実行時間が増える。
- 既存 URL / title / X status id 重複 guard と二重判定になり、skip reason が分かりにくくなる。
- Cloud Run の一時 filesystem 前提に寄せると、別 run で効かないままになる。
- 安全側に倒しすぎて、記事本数が減りすぎる。

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-12 JST | work log作成 | user 指示により、別 run をまたぐ topic dedup 永続化の作業記録 Markdown を新規作成。この時点で許可された変更は本 Markdown の作成のみ。コード編集・commit・push・deploy・env変更・scheduler変更は未実施。 |
| 2026-05-12 JST | 方針修正 | user 指摘により、大城 / head_bat_contact 専用ではなく、媒体横断の先着代表方式に目的を修正。複数媒体を待たず、最初の1本は通し、後続の同一話題だけ別 run でも skip する方針に変更。Markdown以外は未変更。 |
| 2026-05-12 JST | deploy後観測で追加修正 | deploy後の `giants-weekday-daytime` 実行ログで、大城ヘルメット直撃系が `category=コラム / subtype=general` に落ち、初回実装の player/subtype 前提では狙った topic dedup に届かないケースを確認。`コラム/general` でも強い事件語が2つ以上ある場合だけ選手名を復元し、incident topic key を付ける追加回帰テストと修正を実施。 |

## 10. Regression Memo欄

- 既存 319-QA は同一 run 内の topic dedup。今回は別 run をまたぐ永続化が目的。
- 複数媒体がそろうのを待たない。先着代表方式で最初の1本は通す。
- 後から来た同一話題の別媒体記事だけを skip する。
- 大城卓三ヘルメット直撃型は代表 fixture の1つであり、専用仕様にはしない。
- topic_signature は title / summary / source metadata 由来の deterministic な語だけで作る。
- AI の記憶や推測で、人物名・事故内容・数字を補完しない。
- 弱い一致では skip しない。明確な同一話題だけを落とす。
- 既存 URL / title / X status id / duplicate ledger guard は維持する。
- Cloud Run のローカルファイルだけに依存すると別 run 保証が弱い。既存の永続 history / ledger の扱いを確認してから実装する。
- skip した場合は、silent skip にせず skip reason / sample title / structured log のいずれかで観測可能にする。
- 公開済み記事は直さない。今後の生成で同じ話題が増えないようにする。

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_duplicate_guard.py`
- `docs/work_logs/2026-05-12_cross-run-topic-dedup-persistence.md`

### 2. diff概要

- `rss_fetcher.py`
  - 既存の同一 run 内 duplicate guard に加え、履歴に残した `topic_terms` を次回以降の run でも照合する cross-run topic dedup を追加。
  - `topic_dedup:<date>:<player>:<subtype>` 形式の履歴 bucket を使い、同日・同一人物・同一 subtype・主要語の重なりが強い後続記事だけを `duplicate_news_pre_gemini_skip` で止める。
  - 最初の信頼できる1本は skip せず、記事作成後に topic marker を履歴へ記録する先着代表方式にした。
  - `ARTICLE_AI_MODE=none` でも効くよう、`build_news_block()` 前の main loop で pre-Gemini duplicate guard を評価する経路を追加。
  - 画像未取得などで投稿されなかった候補でも、URL / title の通常履歴は増やさず、topic marker だけ残せるようにした。
- `tests/test_rss_fetcher_duplicate_guard.py`
  - 別 run をまたいだ媒体横断の同一話題 skip の回帰テストを追加。
  - 未投稿候補でも topic marker が残り、通常 URL 履歴は汚さない回帰テストを追加。
- 作業記録 Markdown
  - 実施内容、テスト結果、残懸念、回帰メモを追記。

### 3. 実行したテスト

- 赤確認:
  - `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py -k cross_run_topic_history`
    - 期待どおり失敗: `_evaluate_pre_gemini_duplicate_guard()` が `duplicate_history` 未対応。
- 追加テスト / 対象テスト:
  - `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py -k cross_run_topic_history`
  - `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py`
  - `python3 -m pytest tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_history_duplicate_audit.py`
  - `python3 -m unittest tests.test_draft_only`
- touched Python checks:
  - `python3 -m py_compile src/rss_fetcher.py tests/test_rss_fetcher_duplicate_guard.py`
  - `python3 -m compileall src/rss_fetcher.py tests/test_rss_fetcher_duplicate_guard.py`
  - AST parse for `src/rss_fetcher.py` and `tests/test_rss_fetcher_duplicate_guard.py`
- 関連緑:
  - `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_history_duplicate_audit.py tests/test_rss_fetcher.py tests/test_rss_fetcher_reliability_2026_05_08.py`
- 全件:
  - `python3 -m pytest`
  - `python3 -m unittest discover -s tests`
- diff hygiene:
  - `git diff --check -- src/rss_fetcher.py tests/test_rss_fetcher_duplicate_guard.py docs/work_logs/2026-05-12_cross-run-topic-dedup-persistence.md`

### 4. テスト結果

- 赤確認:
  - `tests/test_rss_fetcher_duplicate_guard.py -k cross_run_topic_history` は実装前に失敗し、再現できた。
- 追加テスト / 対象テスト:
  - `tests/test_rss_fetcher_duplicate_guard.py -k cross_run_topic_history`: 1 passed
  - `tests/test_rss_fetcher_duplicate_guard.py`: 8 passed
  - `tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_history_duplicate_audit.py`: 9 passed
  - `python3 -m unittest tests.test_draft_only`: OK, 4 tests
- touched Python checks:
  - `py_compile`: OK
  - `compileall`: OK
  - AST parse: `AST OK`
- 関連緑:
  - 77 passed
- 全件:
  - `python3 -m pytest`: sandbox 内は `tests/test_manual_intake_service.py::LiveServerSmokeTest` 3件が localhost socket 制限で `PermissionError`。権限付き再実行で 3616 passed。
  - `python3 -m unittest discover -s tests`: sandbox 内は同じ localhost socket 制限で 3 errors。権限付き再実行で 3437 tests OK。
- diff hygiene:
  - `git diff --check` は対象3ファイルで出力なし。

### 5. 残った懸念

- 現在のローカル HEAD には、前回 user が止めた `410a101 fix: apply game live source policy` が含まれている。今回の cross-run topic dedup をこのまま deploy すると、止めた試合中ソース制御も本番に混ざる。deploy 前 STOP 条件として扱う。
- 今回の dedup は「同日・同一人物・同一 subtype・主要語の強一致」に限定している。媒体ごとの見出し差が大きすぎる場合、期待した同一話題を拾いきれない可能性は残る。
- 後続媒体を既存記事へ追記する機能は入れていない。今回は「後続を新規記事にしない」まで。
- Cloud Run 本番反映は未実施。

### 6. 新しく見つかったデグレ

- 新規デグレはテスト上なし。
- sandbox だけで localhost socket を使う live server 系テストが落ちることを再確認した。権限付き再実行では pytest / unittest とも全件緑。

### 7. 追加した回帰テスト

- `test_cross_run_topic_history_skips_later_media_without_waiting_for_all_sources`
  - 最初の媒体記事は通す。
  - 投稿後に topic marker を履歴へ保存する。
  - 別 run の別媒体・別URL・類似同一話題は skip する。
  - 同じ人物でも別話題は通す。
- `test_persist_processed_entry_history_records_topic_marker_without_url_for_unpublished_post`
  - 投稿されなかった候補でも topic marker は残す。
  - 通常の URL / title 履歴は未投稿候補で増やさない。
- `test_cross_run_topic_history_handles_player_incident_misclassified_as_general`
  - 実ログで確認した `category=コラム / subtype=general` の大城ヘルメット直撃系でも player/topic_key を復元する。
  - 先着1本を履歴化し、後続の同一話題を skip する。

### 8. 次回触ってはいけない範囲

- 公開済み WP 記事
- WP post status
- publish / mail 条件
- env / Secret / scheduler / Cloud Run 設定
- X API / X投稿
- source 追加
- DAZN / 日テレ / 試合中ソース制御
- `410a101 fix: apply game live source policy` の deploy 混入
- アイキャッチ / featured_media
- frontend / CSS / AdSense
- unrelated dirty files / build / logs / data
