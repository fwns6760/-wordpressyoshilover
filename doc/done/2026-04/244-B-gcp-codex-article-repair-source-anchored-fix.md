---
ticket: 244-B
title: GCP Codex article repair が source/meta に anchor して本文を直すように narrow 修正
status: CLOSED
owner: Codex A (実装)
priority: P0.5
lane: A
ready_for: codex_a_fire (244-B-followup wire)
created: 2026-04-28
updated: 2026-04-28 (244 module landed at f2cc8a3 → 244-B-followup で stub → 共通 module reuse wire)
parent: 244 (publish blocker、共通 numeric module 提供)
related: 178 (GCP Codex 本線昇格), 243 (emit observability), 234-impl-1, 242-B
---

## 進捗 (2026-04-28)

- e04eee1 で Phase 2-B (prompt anchor 強化 + adapter stub) 着地
- f2cc8a3 で 244 共通 module `src/baseball_numeric_fact_consistency.py` 着地
- 次: **244-B-followup** で stub `_post_check_repaired_body` を `from src.baseball_numeric_fact_consistency import check_consistency` の wire に置き換え
- inline checker を 244-B 内で増やすことは継続して禁止

## 目的

GCP Codex article repair (Cloud Run Job `draft-body-editor`) が本文を直す時に、**スコア・勝敗・被安打・失点・日付・選手名を source/meta と一致するように正しく修正する**。

「review/draft に落として人間に振る」 ticket ではない。
**Repair 処理そのものを source/meta anchor に寄せて、Gemini が数字・選手名を勝手に作らないようにする narrow 修正**。

244 (publish 前 / X 表示前 抑止 detector) と独立。244 = 「止める」、244-B = 「正しく直す」。

## 現状仮説

- repair prompt 生成: `src/tools/draft_body_editor.py:224 build_prompt(subtype, fail_axes, current_body, source_block, headings)`
- Gemini 呼び出し: `src/tools/draft_body_editor.py:284-310 _call_gemini_repair`
- Lane runner: `src/tools/run_draft_body_editor_lane.py:1218 main()` から呼ばれる
- 既存 source_block は渡されているが、**prompt instructions が「source 内の値を改変するな」「source にない数字を作るな」を強く言っていない可能性**
- repair 後の post-check が gemini_to_gemini ループ前に存在しない、または弱い → 矛盾本文がそのまま WP draft PUT される
- `score` regex は既に存在(line 90)だが、prompt anchor / post-check に活用されていない可能性

これらを Codex A が実装着手前に inspect して narrow 修正する。

## やること(Codex A scope)

### 1. repair prompt の anchor 強化(`src/tools/draft_body_editor.py:build_prompt`)

- prompt template に **「source/meta 内の数字・選手名・スコアは絶対に改変しない」「source にない数字・選手名は新たに作らない」** instruction を冒頭で強制
- source_block の score / player names / pitcher stats / dates を **構造化 facts block** として prompt に埋め込み(例: `[FACTS] score: 1-11 (away), player: 山本由伸, ...`)
- これにより Gemini が generated body 作成時に anchor 値から逸脱する余地を減らす

### 2. repair 後の deterministic post-check(**244 共通 module reuse 前提**)

**重要**: numeric / player / pitcher-stats / date 判定 logic は **244 ticket の `src/baseball_numeric_fact_consistency.py`(共通 module、Codex B が実装中)を再利用する**。本 ticket は独自の inline numeric checker を作らない(user 明示禁止、判定 2 種類化はデグレ源)。

#### 244 module が impl 着手時に存在する場合(`src/baseball_numeric_fact_consistency.py` git log 確認):

- `from src.baseball_numeric_fact_consistency import check_consistency` を draft_body_editor.py に追加
- Gemini repair 後の new_body に対して `check_consistency(source_block, new_body, ...)` を呼ぶ
- 不一致検出時の挙動:
  - **WP draft PUT を行わない**(repair 失敗扱い、既存の repair_provider_ledger に `strict_pass=false` で記録)
  - 失敗 reason を ledger に記録(244 module が返す mismatch flag をそのまま記録、新 reason 値の発明禁止)
  - **Gemini 再呼び出しはしない**(user 明示禁止、Gemini 1 回までで止める)
- 既存 WP 記事の本文修正は禁止(失敗時は draft 状態維持)

#### 244 module が未 commit の場合(本 ticket impl 着手時に未完成):

post-check insertion は **本 commit に含めない**。代わりに以下に scope を絞る:
- **section 1 の repair prompt anchor 強化のみ**実装(これ単独で repair の hallucination は減る、依存なし)
- post-check 用 **adapter 準備**(draft_body_editor 内に「ここに 244 module を呼ぶ insertion point」の placeholder + skip implementation コメント)
- 244 commit 後に follow-up commit `244-B-followup-postcheck-wire` で実際の wire を入れる(Claude が後続 ticket で起票)
- inline numeric checker は **絶対に書かない**(判定 logic 重複禁止、デグレ源)

### 2-A. 244 module 存在確認手順(Codex A が impl 着手前に実行):

```
git log --oneline | grep -i "^.*: baseball numeric fact"
ls src/baseball_numeric_fact_consistency.py 2>&1
```

両方 hit すれば「244 module 存在」、片方でも miss なら「未完成」扱い。

### 3. tests (narrow):

#### prompt anchor 関連(244 module 有無に関わらず必須):

`tests/test_draft_body_editor.py`:
- `test_repair_prompt_includes_source_anchor_facts_block`(prompt に [FACTS] block が含まれる)
- `test_repair_prompt_instructs_no_fabrication`(prompt に「source にない数字・選手名を作らない」指示がある)

#### post-check wire 関連(**244 module 存在時のみ追加**):

`tests/test_draft_body_editor.py` に追加:
- `test_post_check_calls_baseball_numeric_fact_consistency_module`(244 module の `check_consistency` が呼ばれる、mock で確認)
- `test_post_check_score_mismatch_blocks_wp_put`(244 module が score mismatch を返す → WP put 呼ばれない)
- `test_post_check_pass_allows_wp_put`(244 module が pass を返す → 既存 WP put 経路が動く)
- `test_repair_failure_records_strict_pass_false_with_244_flag`(244 module の mismatch flag が ledger reason に記録される)
- `test_repair_does_not_retry_gemini_on_post_check_fail`(Gemini 再呼び出しなし)

`tests/test_run_draft_body_editor_lane.py` (243 で touch 済) に 1 fixture 追加(244 module 存在時のみ):
- `test_lane_skips_wp_put_when_post_check_fails`(post-check fail → no WP PUT、既存 emit_no_op_skip path 既存 logic 不変)

#### 244 module 未完成時:

prompt anchor 関連 2 fixture のみ実装。post-check fixture は本 commit に含めず、follow-up commit に回す。

## やらないこと

- review/draft に落とす話にしない(本 ticket は repair correctness 修正、publish 抑止 ticket は 244)
- Gemini 追加呼び出し(prompt 強化のみ、post-check は 244 共通 module reuse、再 repair なし)
- **inline 独自 numeric checker の増殖**(score / player / pitcher stats の判定 logic を draft_body_editor 内に複製禁止、244 共通 module のみ使用)
- 244 module 未完成時の inline 仮実装(adapter placeholder のみ、判定 logic は書かない)
- Web 検索 / browser / 外部 API
- roster DB / NPB / Yahoo API 新規参照
- heavy facts extractor / spaCy / NER ライブラリ追加
- 全 template 一括改修(本 ticket は repair logic 修正のみ、234 6 subtype contract 反映は別便)
- H3 required 化
- 既存 WP 記事の本文修正(過去 publish 済記事は触らない、失敗時は draft 状態維持)
- 63844 / 63475 / 63470 の status / draft 変更(別件、user 専決)
- src/guarded_publish_evaluator.py touch(244 publish blocker scope)
- src/baseball_numeric_fact_consistency.py touch(244 で新規 module、244-B は独立)
- src/article_entity_team_mismatch.py touch(242-B)
- src/llm_cost_emitter.py touch(243)
- env / Secret / Scheduler / Cloud Run / RUN_DRAFT_ONLY / WP REST 設定変更
- automation.toml / cron
- ambient dirty 巻き込み
- doc/active/assignments.md / doc/README.md 編集

## デグレ防止 contract

- **digit boundary invariant**: source `1-11` を post-check で `19-1` / `11-1` / `1-9` / `9-1` などに一致と判定しない
- 既存 fixture 全件 pass を維持(既存 fixture 1 件も変更しない、追加のみ)
- post-check を OFF にした場合、既存 repair lane 出力が完全に同じ(diff 0)を担保(コードレビュー観点 yes)
- false positive(良 repair を fail 扱い)1 件でも疑いがあれば実装止めて Claude に report
- repair logic 自体の broad 変更禁止(prompt anchor 強化 + post-check 追加のみ、既存 flow 保持)
- 既存 repair_provider_ledger schema は不変(`strict_pass=false` reason field の値に新値追加のみ、schema 拡張禁止)

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 file (`src/tools/draft_body_editor.py` + tests 1-2 file) のみ stage、git add -A 禁止
2. **挙動**: 新規 fixture 全 pass、既存 fixture fail 0、pytest baseline 維持(post-check 時の strict_pass=false 件数増は ledger に記録される、それ以外の挙動 diff 0)
3. **境界**: Gemini call 数不変(repair 1 回まで)、Cloud Run / Scheduler / Secret / WP / 既存 repair logic flow すべて不変、prompt template の anchor 強化 + post-check 追加のみ

## commit 規約

- git add -A 禁止、明示 path のみ stage
- commit message: `244-B: GCP Codex repair source-anchored prompt + post-check (no Gemini retry)`
- push は Claude が後から実行
- `.git/index.lock` 拒否時は plumbing 3 段 fallback

## 完了後の Claude 判断事項

- pytest baseline 確認 + commit accept
- git push (Claude 実行)
- live 反映 (draft-body-editor image rebuild) は別判断、243 / 244 と bundle 検討
- repair_provider_ledger の `strict_pass=false` 件数を 1-2 tick 観察、誤 fail 多発時は narrow 緩和

## 完了報告 (必須)

- changed files (path + 行数)
- repair prompt anchor 強化の差分概要(冒頭 instruction + [FACTS] block 構造)
- post-check 5 軸の関数名と blocking severity
- 新規 fixture pass 数 + 既存 fixture pass 数
- pytest collect / pass / fail (全体 baseline 比、fail 増加 0)
- post-check OFF 時の既存挙動 = 完全一致 (yes/no)
- Gemini call 数増加 0 の確認 (yes/no、確認方法)
- 既存 WP 記事を touch していないこと (yes/no)
- commit hash
- remaining risk / open question
- 次 Claude 判断事項
