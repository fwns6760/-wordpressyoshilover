# 424: X-post mail mode unification (on-queue + scheduled 統合)

## meta

- owner: Claude Code
- type: implementation
- status: READY → IN_FLIGHT
- created: 2026-05-22
- updated: 2026-05-22
- priority: P1
- ticket_lineage: 417 (DONE 2026-05-22) の後段、 mode split を是正
- parent_intent: 1 fire = 1 mail = 全 lane 統合
- gh_issue: 起票予定

## 1. 背景

2026-05-22 16:00 JST fire(`x-post-mail-lane-jhqr9`、 9 分実行)で送られた
メールが **「Xポスト案 2 件 ☀️午後｜報知/サンスポ 直結 (queue 417)」** のみで、
data ranking / Gemma branding / team roundup 等の他 lane 候補が含まれて
いなかった。

原因は `x-post-mail-flush` schedule が `_main_on_queue` path を呼ぶ構造に
なっており、 統合 path の `_main_scheduled` は旧 5 schedule (am-1 / lunch /
afternoon / evening / postgame) 側に紐付いていたが、 これら旧 schedule は
2026-05-17 に全 PAUSE された(417 ticket 完了の副作用)。

結果として ENABLED 側 = on-queue 専用 path (queue 417 のみ)、 統合 path =
PAUSED schedule にのみ紐付いた dead code、 という捻れが残った。

## 2. 目的

1. 1 fire = 1 mail = 全 lane mix の統合 path に戻す
2. `--mode` 引数を廃止して code path を簡素化
3. queue 417 由来 candidate に対する unverified_numbers gate を別 lane と
   して分離可能にする(報知/サンスポ literal 数字を活かす余地)
4. 旧 PAUSED schedule(am-1 / lunch / afternoon / evening / postgame)を
   `gcloud scheduler jobs delete` で削除

## 3. 不可触リスト(hard constraint)

| 項目 | 扱い |
|---|---|
| insight.db schema | 不変 |
| WP REST API への書込み (publish) | 不変 |
| guarded-publish / publish-notice job | 不変 |
| Gemma branding safety_check regex (414 axis A-E) | 不変 |
| Tavily REST 呼び出し flow | 不変 |
| 2026-05-22 swap した `gemini-3.1-flash-lite` model 設定 | 不変 |
| WP post (publish 済) | 不変 (forward-only) |
| `data-insight-*-trigger` schedule 群 | 不可触 (X-post mail と別系統) |

## 4. 影響範囲

### 4.1 src 変更

- `src/tools/run_x_post_mail.py`
  - `main()` の mode 分岐廃止
  - `_main_on_queue` のロジックを `_main_scheduled` 内に queue drain ステップとして統合
  - `_parse_args` の `--mode` argument 削除(or DeprecationWarning)
  - mail 構成: data ranking + Gemma branding + team roundup + queue 417 candidates を 1 mail に merge
  - queue 由来候補に対する gate を `_gemma_branding_safety_check` の弱 variant にする(unverified_numbers を warning にとどめ drop しない、 他の axis A-E は維持)

### 4.2 scheduler 変更

- `x-post-mail-flush` / `x-post-mail-flush-game-1` / `x-post-mail-flush-game-2`
  - body の `--mode=on-queue` arg を削除
- 旧 PAUSED schedule(am-1 / lunch / afternoon / evening / postgame)を delete

### 4.3 tests

- `tests/test_run_x_post_mail.py` 系 mode 分岐 test を統合 path test に置換
- queue 由来 gate の弱 variant を unit test 追加

### 4.4 doc

- 本 ticket = `doc/active/424-X-POST-MAIL-MODE-UNIFICATION.md`(本 file)
- `doc/active/assignments.md` に entry 追加
- `doc/README.md` に bucket row 追加
- 417 ticket は close 候補のまま(本 ticket landed 後に 417 を done へ移動)

## 5. 成功条件

1. `python3 -m pytest tests/test_x_post_branding_gen.py tests/test_x_post_gen_mcp.py tests/test_run_x_post_mail.py -q` が 86+ pass
2. deploy 後 1 fire の log で以下 4 lane の candidate_built event が観測できる:
   - `article_info_branding_candidate_built` (data ranking + branding)
   - `team_roundup_candidate_built` (試合日のみ)
   - `gemma_branding_candidate_built` (player-based fan voice)
   - queue 417 drain candidate(報知/サンスポ direct)
3. mail subject が「Xポスト案 N 件 ☀️｜統合(data + branding + queue 417 + roundup)」相当に変わる
4. queue 由来 candidate の unverified_numbers drop 率が下がる(8/10 → <3/10 目安)
5. 旧 PAUSED schedule 5 本が GCP scheduler から消える

## 6. deploy 手順

1. commit 1 = src + tests 統合 path
2. commit 2 = doc 更新(本 ticket + assignments + README)
3. cloud build → image `x-post-mail-lane:mode-unify-<hash>`
4. Cloud Run Job update
5. scheduler body 更新(`--mode=on-queue` arg 削除)
6. 旧 PAUSED schedule 5 本 delete
7. 次自然 fire で log verify

## 7. rollback 経路

- src commit revert + cloudbuild redeploy で前 image(`gemini-flash-lite-4e8e038`)に戻る
- scheduler body も `gcloud scheduler jobs update --update-args` で `--mode=on-queue` を再付与可能

## 8. open question

なし(user の「統合」明示指示で確定)
