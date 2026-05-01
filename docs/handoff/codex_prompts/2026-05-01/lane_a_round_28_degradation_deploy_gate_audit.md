# Lane A round 28 — デグレ再発リスク + 次 deploy 前チェック audit(read-only)

## 目的

明日以降の自律 deploy 体制で「user 張り付かなくても安全」基盤を作るため、デグレ再発リスク + 次 deploy 前チェック軸 9 件を read-only 調査。各軸で発見事項 + 推奨 guard を doc 化。

read-only 限定。impl / commit 一切なし、stdout 出力のみ(Claude が圧縮して repo 正本 update する)。

## 不可触リスト

- src / tests / scripts / config / .codex 一切編集しない、read-only grep / cat のみ
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- production change 0、deploy 0、commit 0、push 0
- git mutation 一切なし

## 調査軸 9 件

### 1. silent skip 再発ポイント

- POLICY §8 silent skip 0 維持の前提で、現行 code に「publish/review/hold/skip 経由しない skip path」が残ってないか
- 対象 grep:
  - `src/publish_notice_*.py` の skip path
  - `src/guarded_publish_runner.py` の refused / proposed
  - `src/draft_body_editor*` の log-only skip
  - `src/cron_eval.py` の eval skip
- POLICY §8 違反 candidate path 列挙

### 2. mail storm 再発ポイント

- 本日 5/1 朝 99 + 13:35 50 storm 起因の root cause(`PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` + 24h dedup + cap=10)が再発しうる別 path
- 対象:
  - publish-notice ledger の retention(永久 vs 24h vs 168h)
  - guarded-publish の trigger ts 再評価 path
  - 24h dedup window vs first emit cardinality
  - cap=10 per-run vs hour budget の境界
- 再発リスクある path 列挙

### 3. publish / review / hold / skip 経路で候補が見えなくなる箇所

- post 生成 → guarded-publish → publish-notice → user の path で「log only / ledger only / 内部 state」 に落ちる箇所
- 対象:
  - guarded-publish refused (backlog_only 以外、log-only 含む)
  - publish-notice scanner skip
  - draft-body-editor の生成失敗時の log-only path
  - close_marker / strict_validation_fail / weak_title 系の visibility
- 不可視 path 列挙

### 4. pre-existing pytest failure

- 現在の baseline pytest 状態(2018/0)から pre-existing fail が今後 introduce される時の混入検知
- 対象:
  - 過去の transient flaky(299-QA 系)
  - environment-dependent test
  - 本日 5/1 の 7 new test (293 関連) の robustness
- pre-existing fail の trap path 列挙

### 5. dirty worktree / clean build

- Codex 便 fire 前後の worktree clean 確認 protocol
- 対象:
  - 既知 ambient dirty(provenance 不明 modified)
  - .codex / build / data / logs / backups 等の untracked
  - `git add -A` 禁止前提の明示 stage protocol
- pre-fire / pre-commit verify の必要 step 列挙

### 6. HOLD 中 ticket 混入

- HOLD ticket の commit / impl が間違って通常 dev 便に混ざるリスク
- 対象:
  - active / hold / observe / future_user_go の状態 boundary
  - Pack 13 fields UNKNOWN 残のチェック
  - 「HOLD = 作業停止」誤解防止(本日反省 #1)
- 混入検知方法 列挙

### 7. rollback target

- 各 ticket の rollback target(image SHA / env knob / git commit)が記録されているか、3 dimension 全て揃っているか
- 対象:
  - 5 ticket Pack v3 (293/290 split A B/282/300/288)の rollback section
  - last known good commit / image SHA の anchor
  - rollback owner + 経過時間
- rollback target 不足 ticket 列挙

### 8. flag OFF deploy 時の不変確認

- live-inert deploy(flag OFF default、image rebuild のみ)で本当に挙動 100% 不変か検証する protocol
- 対象:
  - 290 Pack A (live-inert)、293 image rebuild、その他 future live-inert
  - flag OFF 時の code path 不到達確認
  - log diff baseline 比較方法
  - mail / Gemini / silent skip baseline 比較方法
- 不変確認の必要 step 列挙

### 9. flag ON 時の検証項目

- flag ON deploy で挙動変化を expected 範囲内に収めるための検証項目
- 対象:
  - mail volume burst 上限(MAIL_BUDGET 30/h・100/d)
  - Gemini call delta(±5%)
  - silent skip 0 維持
  - candidate disappearance 0
  - first emit cardinality vs cap=10 vs 24h dedup
- 検証項目 列挙(定量閾値付き)

## 出力形式(stdout のみ、commit なし)

各軸 9 件で以下の form:

```
### <軸番号> <軸名>

- 発見事項:
  - <bullet 1>
  - <bullet 2>
- 再発リスク level: HIGH / MEDIUM / LOW
- 推奨 guard:
  - <bullet 1>
  - <bullet 2>
- POLICY 該当 section / 反映先 doc:
- Claude 自律 GO で潰せるか: YES / PARTIAL / NO
```

最後に Summary:

```
### Summary

- HIGH risk 軸: <list>
- MEDIUM risk 軸: <list>
- 次 deploy 前必須チェック: <list>
- Pack v3 で対応済 軸: <list>
- POLICY 追加が必要な軸: <list>
- ACCEPTANCE_PACK_TEMPLATE 追加が必要な軸: <list>
- 残 UNKNOWN: <list>
```

## 完了報告

```json
{
  "status": "audit_completed",
  "axes_audited": 9,
  "high_risk_axes": [],
  "medium_risk_axes": [],
  "policy_updates_needed": [],
  "test": "n/a (read-only audit)",
  "open_questions_for_claude": [],
  "next_for_claude": "Read audit output, compress into 8-item report, update repo 正本"
}
```

## 5 step 一次受け契約

- read-only(commit / git / push 一切なし)
- src / tests / scripts / config 一切編集しない
- pytest 不要
- scope 内
- rollback 不要(read-only)
