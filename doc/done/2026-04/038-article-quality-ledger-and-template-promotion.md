# 038 — 記事品質 ledger と template / prompt promotion loop の正式化

**フェーズ：** 現場の監査運用固定
**担当：** Claude Code
**依存：** 015, 036 accepted

---

## why_now

- 030 / 032 / 033 / 034 の validator と、036 の prompt contract hardening で「書かれた Draft の fail を止める層」は整う。
- ここから先は、発生した fail を **単発 repair で閉じるか**、**036 系 / 037 系 / 035 系 に昇格させるか** を現場で一意に判定する運用が要る。
- 038 は Draft ごとに品質 ledger を残し、再発 fail だけを 036 / 037 / 035 に昇格させる loop を固定する。
- 038 は Claude Code(管理人)の運用 ticket であり、Codex 実装 ticket と混ぜない。

## purpose

- 各 Draft ごとに品質 ledger を残す。
- 単発 fail は `repair_closed` で閉じ、再発 fail だけを 036 / 037 / 035 に昇格させる。
- 別人が ledger を見ても、`repair-only` / `036 系` / `037 系` / `035 系` の振り分けが一致するようにする。

## scope

### ledger 必須項目

- `candidate_key`
- `subtype`
- `event_family`
- `source_family`
- `source_trust`
- `chosen_lane`
- `chosen_model`
- `prompt_version`
- `template_version`
- `repair_applied`
- `repair_trigger`
- `repair_actions`
- `source_recheck_used`
- `search_used`
- `changed_scope`
- `fail_tags`
- `outcome`

### chosen_model

- fixed lane = `Gemini 2.5 Flash`
- agent lane = `Gemini Flash + Codex review`

### fail_tags(固定列挙)

- `thin_body`
- `title_body_mismatch`
- `abstract_lead`
- `fact_missing`
- `attribution_missing`
- `subtype_boundary`
- `duplicate`
- `low_assertability`
- `pickup_miss`
- `close_marker`

### outcome(固定列挙)

- `accept_draft`
- `repair_closed`(単発 fail を Codex repair で閉じた)
- `escalated`(再発 fail で 036 系 / 037 系 / 035 系 へ昇格)

### repair 実績の記録

- `repair_trigger`
  - Codex を呼んだ直接理由を 1 件だけ残す。
  - 例: `title_body_mismatch` / `fact_missing` / `attribution_missing`
- `repair_actions`
  - 実際に行った修正を列挙する。
  - 例: `title_fix` / `lead_replace` / `fact_block_add` / `attribution_add` / `block_reorder`
- `source_recheck_used`
  - source 再確認をしたかを `yes/no` で記録する。
- `search_used`
  - 検索や再取得まで行ったかを `yes/no` で記録する。
- `changed_scope`
  - どこまで触ったかを固定語で記録する。
  - `title_only` / `intro_only` / `attribution_only` / `block_patch` / `full_rewrite`
- `repair_applied`
  - Codex repair が実行されたかを `yes/no` で記録する。
- `repair_closed` の記事では、最低でも `repair_trigger` / `repair_actions` / `changed_scope` を残す。

### 昇格基準

- **036 系 昇格**: same `subtype` + same `fail_tag` + same `prompt_version` が
  - 24h で 3 件以上
  - または 7d で 5 件以上
- **037 系 昇格**: same `source_family` + same `fail_tag` が 2 subtype 以上で出る
- **035 判定**: `close_marker` fail が 7d で 2 件以上、または 10% 以上
- **単発 fail**: 上記基準未満は `repair_closed`

### ledger 置き場

- `docs/handoff/ledger/YYYY-MM-DD.jsonl` に 1 Draft = 1 行で追記する(047 以降の新規 directory、本便で確定)。
- Claude Code が管理人として更新する。Codex 実装側は書かない。
- 集計は週次で Claude が行い、昇格 trigger 発動時に `current_focus` / `decision_log` に記録する。

### 現場運用ルール

- 各 Draft について、上記 12 項目を ledger に 1 行記録する。
- 単発 fail は新規 ticket を切らず Codex repair で閉じる(`repair_closed`)。
- 再発 fail が昇格基準を満たしたときだけ、036 系 / 037 系 / 035 系 のいずれかに昇格させる。
- 昇格先は一意(複数昇格を作らない)。複数候補に該当した場合は優先度 036 > 037 > 035 で振る。
- Codex repair を使った記事は、**何を見て・何を直して・どこまで触ったか** を ledger に残す。
- `040` の playbook に従って title / fact / attribution / block 修正を行った場合、その内容を `repair_actions` と `changed_scope` に対応させる。
- `search_used=yes` の記事は、後で `hallucination` の温床になっていないか週次観測対象にする。

## success_criteria

- 各 Draft が `accept_draft` / `repair_closed` / `escalated` のどれかで必ず閉じる。
- 別人が見ても `repair-only` / `036 系` / `037 系` / `035 系` の振り分けが一致する。
- 代表 10 Draft で ledger 欠落 0。
- 単発 fail で新規 ticket が切られない。
- 再発 fail で昇格先が一意。
- Codex repair を使った記事で、`repair_trigger / repair_actions / changed_scope` の欠落が 0。

## non_goals

- publish path 変更
- 029 gate 変更
- 035 前倒し
- reserve 前倒し(020 / 021 / 023-026)
- Codex 側の新規 src / tests 追加(本便は Claude 運用 ticket)
- `automation.toml` / scheduler / env / secret / mail 変更
- ledger の自動生成(本便は手動運用で固定、自動化は別便)

## acceptance_check

- 代表 10 Draft で ledger 欠落 0。
- 単発 fail で新規 ticket を切らない運用が守られている。
- 再発 fail で昇格先が一意に決まる。
- ledger ファイルが `docs/handoff/ledger/YYYY-MM-DD.jsonl` に存在する。
- 週次集計結果が `current_focus` / `decision_log` に記録されている。

## TODO

【】ledger 必須項目に repair 実績列(`repair_trigger` / `repair_actions` / `source_recheck_used` / `search_used` / `changed_scope`)を追加する
【】`chosen_model` の fixed lane / agent lane 対応を固定する
【】`fail_tags` 10 種を固定する
【】`outcome` 3 種を固定する
【】repair 実績の記録ルールを固定する
【】036 系 / 037 系 / 035 系 の昇格基準を固定する
【】単発 fail は `repair_closed` で閉じる方針を明記する
【】昇格先の一意性(優先度 036 > 037 > 035)を明記する
【】ledger 置き場 `docs/handoff/ledger/YYYY-MM-DD.jsonl` を固定する
【】ledger 更新は Claude 管理人が行う(Codex は書かない)ことを明記する
【】`040` playbook と ledger の接続を明記する
【】週次集計と昇格 trigger の記録先(`current_focus` / `decision_log`)を固定する

## 成功条件

- ledger 項目と 3 outcome、昇格基準が ticket 本文で固定されている。
- Claude Code が管理人として ledger 運用に入れる粒度になっている。
- Codex 実装 ticket(036 / 037 / 028 impl)と混ざらない。
- 037 の accepted 条件(038 accepted)が ticket 単体で読める。
