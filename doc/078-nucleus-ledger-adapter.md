# 078 Nucleus Ledger Adapter

## Purpose

- ticket 071 の `NucleusAlignmentResult` を既存 ledger fail tag schema に落とす pure adapter を追加する。
- 3 つの `reason_code` は既存 consumer 互換のため、すべて `title_body_mismatch` に集約する。
- 詳細差分は新 fail tag を増やさず、`ctx_*` prefix の context flag で保持する。

## Map Contract

| reason_code | fail_tags | context_flags |
| --- | --- | --- |
| `None` (`aligned=True`) | `[]` | `[]` |
| `SUBJECT_ABSENT` | `["title_body_mismatch"]` | `["ctx_subject_absent"]` |
| `EVENT_DIVERGE` | `["title_body_mismatch"]` | `["ctx_event_diverge"]` |
| `MULTIPLE_NUCLEI` | `["title_body_mismatch"]` | `["ctx_multiple_nuclei"]` |
| unknown string | `[]` | `[]` |

- A1 contract 固定。
- unknown reason の推測 mapping はしない。
- adapter 層では log emit しない。

## Interface

- `src/nucleus_ledger_adapter.py`
  - `validator_result_to_fail_tags(result: NucleusAlignmentResult) -> list[str]`
  - `validator_result_to_context_flags(result: NucleusAlignmentResult) -> list[str]`
  - `KNOWN_REASON_CODES`

入力は `NucleusAlignmentResult` のみ。`None` や他型は `TypeError` で早期 fail する。返り値は空配列か単一要素配列で、順序は deterministic。

## Test Coverage

- aligned / unknown / empty / empty-box (`aligned=False` and `reason_code=None`) を empty で固定
- 3 known reason の fail tag / context flag mapping を個別に固定
- idempotence を確認
- `SUPPORTED_FAIL_TAGS` 内に `title_body_mismatch` だけが出ることを確認
- `ctx_*` prefix を確認
- `None` 引数で `TypeError` を確認
- `validate_title_body_nucleus()` を通した integration 1 本を追加

## Non-Goals

- ledger `*.jsonl` への append
- caller wiring
- automation 経路の変更
- 071 validator 本体の判定変更
- `src/repair_playbook.py` など既存 consumer の変更
- baseballwordpress 側 `docs/handoff/ledger/README.md` の context flag section 更新

## Follow-Up

- ledger README の `ctx_subject_absent` / `ctx_event_diverge` / `ctx_multiple_nuclei` 追記は Claude 側の narrow follow-up とする。
