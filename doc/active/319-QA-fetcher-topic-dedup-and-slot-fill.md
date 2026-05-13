# 319-QA fetcher topic dedup and slot fill

- status: REVIEW_NEEDED
- owner: Codex B
- lane: B
- priority: P0.5
- created: 2026-05-11
- user_goal: 次の記事公開から、同じ話題の重複記事で10枠を消費しないようにしたい

## 今回の目的

- 自動起動時に、別URL・別タイトルでも同じ話題の記事が複数公開される問題を狭く抑止する。
- `rss_fetcher.py --limit 10` の10枠を、既存記事再利用や同一話題重複で消費しにくくする。
- 重複で落とした分は、可能なら次の別話題候補を見に行けるようにする。
- 次の記事公開から効くようにする前提で、まず再現テストを固定してから実装修正する。

## 今回触ってよい範囲

- `src/rss_fetcher.py`
- `tests/test_duplicate_prevention_golden.py`
- 必要なら新規 `tests/test_rss_fetcher_topic_dedup_slots.py`
- 本チケット: `doc/active/319-QA-fetcher-topic-dedup-and-slot-fill.md`
- board/dashboard:
  - `doc/README.md`
  - `doc/active/assignments.md`

## 今回触ってはいけない範囲

- publish 条件
- mail 条件
- scheduler
- env
- Cloud Run 設定
- secrets
- GitHub Actions
- SEO
- 指示外の source
- 指示外の本番設定
- X投稿
- `RUN_DRAFT_ONLY`
- `PUBLISH_NOTICE_*` の挙動変更
- unrelated dirty files

## 背景

2026-05-11 JST 時点の観察では、`giants-realtime-trigger` は `/run` に body `{}` でPOSTしており、server側は `rss_fetcher.py --limit 10` を実行する。

現在の `--limit 10` は「公開10本」だけでなく、実装上は作成・再利用に成功した候補数 `success` で止まる。既存記事再利用や、同じ話題の別URL・別タイトル候補が枠を消費すると、別話題の記事が後ろに残る可能性がある。

既存の重複抑止は以下を持つ。

- source URL history
- source title norm history
- same-fire source URL guard
- X status id same-run guard
- duplicate news ledger
- WP create_post の source_url / title reuse

ただし、別媒体が同じ話題を少し違うタイトルで出した場合は、同一話題として完全にはまとまらない余地がある。

## 今回やること

1. 再現テストを追加する。
   - 同一話題の別URL候補が複数あるとき、公開候補は1本だけ通す。
   - 重複skip後に、次の別話題候補が10枠に入れることを確認する。
   - 既存post再利用が新規公開枠を不用意に消費しないことを確認する。
2. 追加した再現テストが赤になることを確認する。
3. `rss_fetcher` の候補選別だけを狭く修正する。
   - publish / mail / scheduler / env / Cloud Run 設定は変更しない。
   - 同一話題判定は強くしすぎず、明確な同一話題に限定する。
4. 追加テストと関連テストを緑にする。
5. diff を提示してから commit 判断を待つ。

## 実装方針

- まず同一run内で効く guard を優先する。
- AI の記憶から話題を再構成しない。topic key は source / entry / 既存metadata から機械的に作る。
- silent skip を禁止する。重複で落とす場合は skip reason と sample title を summary に残す。
- AI自己評価だけでOKにしない。追加テスト、構造化ログ、post-deploy の公開記事確認で判定する。
- topic key は以下のような保守的な材料だけで作る。
  - game id がある場合: `game_id + subtype`
  - 選手名が明確な場合: `player + subtype + 主要イベント語`
  - canonical URL がある場合: canonical URL
  - X status id / source URL は既存guardを維持
- topic key が弱い場合は無理に重複扱いしない。
- 重複でskipした候補は `success` を増やさず、次候補を走査する。
- 既存記事 reuse の扱いは、実装前にテストで期待値を固定する。

## 影響範囲

### 本線に直接影響する範囲

- `rss_fetcher.py` の候補選別。
- 自動起動で同じ話題の複数記事が出る頻度。
- `--limit 10` の枠の使われ方。

### 間接影響のみの範囲

- publish-notice mail は、公開された記事数・post_idに追随するだけ。
- mail送信条件そのものは変えない。
- Scheduler起動条件は変えない。
- Cloud Run設定は変えない。

## 実行予定テスト

- 追加する再現テスト単体
- `python3 -m compileall src tests`
- touched Python AST parse
- 関連テスト:
  - `python3 -m pytest tests/test_duplicate_prevention_golden.py`
  - `python3 -m pytest tests/test_rss_fetcher_reliability_2026_05_08.py`
  - 追加した `tests/test_rss_fetcher_topic_dedup_slots.py`
- 可能なら full pytest

## STOP条件

- 修正範囲が `rss_fetcher` の候補選別を超える。
- publish / mail / scheduler / env / Cloud Run 設定変更が必要になる。
- 同一話題判定が強すぎて、別記事まで落とす可能性が高い。
- AI の記憶・推測で topic key を作る必要が出る。
- skip 理由をログと summary に残せない。
- AI自己評価以外の確認手段を用意できない。
- 再現テストを赤にできない。
- 追加テストの緑化ができない。
- 既存テスト全件で unrelated failure と混線する。
- 本番設定変更なしでは次回公開に効かないと判明する。

## 禁止事項

- AI の記憶から記事内容・topic key・人物名・数字を再構成しない。
- silent skip しない。
- AI自己評価だけで修正完了にしない。
- Cloud Run env を独断で変えない。
- scheduler を独断で変えない。
- publish 条件を変えない。
- mail 条件を変えない。
- 指示外の source を追加しない。
- X投稿設定を変えない。
- SEO を変えない。
- cleanup / refactor をしない。
- `git add -A` を使わない。

## 想定されるデグレ

- 同じ選手・同じ試合でも別角度の記事を重複扱いしてしまう。
- topic key が弱い素材で、期待した重複抑止が効かない。
- 既存記事reuseの扱いを変えた結果、同じ記事が新規作成される。
- 10枠補充のために候補走査が長くなり、実行時間が伸びる。
- duplicate ledger の既存挙動と二重判定になり、skip理由が読みにくくなる。

## 受け入れ条件

- 追加した再現テストが、修正前に赤、修正後に緑になる。
- 同一run内の明確な同一話題は1本だけ通る。
- 重複skipは `success` を増やさず、別話題候補で補充される。
- 重複skipは構造化ログまたは `rss_fetcher_flow_summary.skip_reasons` に残る。
- topic key は source / entry / metadata 由来で、AI自由作文や記憶再構成を使わない。
- 完了判定はテストとログ確認で行い、AI自己評価だけでOKにしない。
- publish / mail / scheduler / env / Cloud Run 設定に変更がない。
- 本番deploy前レビューで変更範囲とテスト結果を提示できる。
- deploy後に `/run` の summary、ERROR件数、公開記事タイトル・本文を確認できる。

## 作業ログ欄

- 2026-05-11: user が「次の記事公開でモデルから。重複は出ないようにしたい」と希望。まずチケット化。
- 2026-05-11: 再現テスト `test_same_run_player_incident_different_titles_groups_as_topic_duplicate` を追加。
- 2026-05-11: 修正前の再現テスト赤確認。`topic_key` が空文字で、同一事故話題としてまとまらないことを確認。
- 2026-05-11: `rss_fetcher` に source title / summary / 既存 player / subtype 由来の narrow topic key を追加。
- 2026-05-11: 修正後の再現テスト、関連テスト、compile、AST、全件 pytest を実行。

## Regression Memo欄

- 既存同一URL重複guardは維持する。
- `ENABLE_FETCHER_CROSS_SOURCE_TITLE_REUSE=1` は現行設定として観察済みだが、本ticketで env は変えない。
- `PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=10` は mail側上限であり、本ticketでは変更しない。
- `--limit 10` は serverの `/run` default body `{}` から来る。scheduler body は本ticketで変えない。
- 最大事故源として、AI の「記憶から再構成」「silent skip」「自己評価 OK」を明示的に禁止する。
- **2026-05-14 隣接 scope 観測(本 ticket scope 外)**: `test_event_key_ledger.py::test_group_records_picks_player_anchor_over_empty_player` が現在 fail。要因 = 66667「ライデル・マルティネスを 9 回投入 / サヨナラ勝ちに繋げた」が `derive_event_subtype` で walk_off 判定 + `derive_event_player` でマルティネス検出 → 66669 佐々木 walk_off の child でなく独立 walk_off bucket を立てる。本 ticket の rss_fetcher topic_key 抑止とは別 layer(event_key_ledger.py)で起きる「同 サヨナラ event の 2 重カウント」事象。fix は 321-QA(subtype-routing) で derive_event_subtype の relief vs walk_off order を refine するか、event_key_ledger.py で同日同 walk_off の複数 player bucket を hero に merge する logic を入れる方向。本 ticket では env / src を触らない、観測のみ。

## 作業後に追記すること

1. 実際に変更したファイル
2. diff概要
3. 実行したテスト
4. テスト結果
5. 残った懸念
6. 新しく見つかったデグレ
7. 追加した回帰テスト
8. 次回触ってはいけない範囲

## 作業後追記

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_duplicate_guard.py`
- `doc/active/319-QA-fetcher-topic-dedup-and-slot-fill.md`
- `doc/README.md`
- `doc/active/assignments.md`

### 2. diff概要

- `rss_fetcher` の duplicate guard context に source-derived `topic_key` を追加。
- 同一選手 / player系 subtype / ヘルメット・頭部 + バット・フォロースイング + 直撃・激突・氷のう等の明確な事故語がそろう場合だけ、`player_incident:head_bat_contact` として同一話題化。
- `duplicate_key` / `group_signature` / `match_basis` に `player + subtype + topic_key` の経路を追加。
- 同一 run 内で同一 group になった secondary 候補は、既存の `duplicate_news_pre_gemini_skip` 経路で Gemini 前 skip される。
- 重複 skip は既存通り `success` を増やす前に発生するため、候補走査は次候補へ進む。
- board / assignments に 319 の状態を追加・更新。

### 3. 実行したテスト

- `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py -k same_run_player_incident_different_titles_groups_as_topic_duplicate`
- `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py -k same_run_player_incident_different_titles_groups_as_topic_duplicate`
- `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py tests/test_duplicate_prevention_golden.py`
- `python3 -m pytest tests/test_rss_fetcher.py tests/test_rss_fetcher_history_duplicate_audit.py`
- `python3 -m pytest tests/test_rss_fetcher_reliability_2026_05_08.py`
- `python3 -m compileall src tests`
- `python3 -c 'import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding="utf-8"), filename=p) for p in ["src/rss_fetcher.py", "tests/test_rss_fetcher_duplicate_guard.py"]]; print("AST OK")'`
- `python3 -m pytest`
- `python3 -m pytest` with escalated permission after sandbox socket failure

### 4. テスト結果

- 再現テスト red: FAIL。`contexts[0]["topic_key"]` が `""` で、期待値 `player_incident:head_bat_contact` に一致しなかった。
- 再現テスト green: `1 passed, 5 deselected, 3 warnings`
- duplicate guard / golden 関連: `10 passed, 3 warnings`
- rss_fetcher / history audit 関連: `33 passed, 3 warnings`
- reliability 関連: `31 passed, 3 warnings`
- compileall: OK
- AST parse: `AST OK`
- full pytest sandbox run: `3568 passed, 3 failed, 3 warnings`
  - failed 3件は `tests/test_manual_intake_service.py::LiveServerSmokeTest` のローカル `HTTPServer(("127.0.0.1", 0), ...)` socket 作成が sandbox で `PermissionError: [Errno 1] Operation not permitted` になったもの。
- full pytest escalated run: `3571 passed, 3 warnings`

### 5. 残った懸念

- 今回の topic key は head / bat contact 事故に狭く限定したため、別パターンの同一話題重複は残る。
- 同じ選手の別角度記事を落としすぎないため、弱い topic key は作らない。結果として拾い漏れはあり得る。
- `WPClient.create_post` 側の既存 post reuse が `success` を消費する経路は今回変更していない。そこを変えるには `src/wp_client.py` まで広げる必要があるため、本 ticket では未対応。
- 本番で期待通りかは、deploy 後の `/run` summary、`duplicate_news_pre_gemini_skip` ログ、公開記事タイトルで確認が必要。

### 6. 新しく見つかったデグレ

- 追加テストと全件 pytest 上では新規デグレなし。
- sandbox 内の full pytest だけ、既知のローカル socket 制限で live HTTPServer テスト 3件が失敗。権限付き再実行では全件 green。

### 7. 追加した回帰テスト

- `tests/test_rss_fetcher_duplicate_guard.py::test_same_run_player_incident_different_titles_groups_as_topic_duplicate`
- 別媒体・別URL・別タイトルでも、同じ選手の明確な head / bat contact 事故は同一 `topic_key` / `group_signature` になり、secondary が `duplicate_news_pre_gemini_skip` で Gemini 前 skip されることを固定。
- 同じ候補群に別話題の3本目を入れ、同一事故 group に入らず `allow` のまま残ることを固定。

### 8. 次回触ってはいけない範囲

- publish 条件
- mail 条件
- scheduler
- env
- Cloud Run 設定
- secrets
- GitHub Actions
- SEO
- 指示外の source
- 指示外の本番設定
- X投稿
- `RUN_DRAFT_ONLY`
- `PUBLISH_NOTICE_*` の挙動変更
- unrelated dirty files
