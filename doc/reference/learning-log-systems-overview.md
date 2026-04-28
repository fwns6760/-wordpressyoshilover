# learning log 3 系統 overview(GCS legacy + GCP active 統合参照)

## meta

- 種別: reference / runbook
- 作成: 2026-04-26
- 役割: 学習用 log の 3 系統を統合参照し、各 ledger の rule / schema / GCS path / 役割を集約する
- 対象 reader: Claude / Codex(GCP 上の formatter / aggregation 実装時の参照)
- 関連: 038 / 040 / 048(baseballwordpress 既存)/ 168 / 179(yoshilover GCP)

## 3 系統の整理

| 系統 | source | format / schema | 用途 | 既存 GCS |
|---|---|---|---|---|
| **A. 038 ledger** | Claude が手動更新 | 17 field / JSONL / 1 Draft 1 行 | 記事品質判定 + 昇格 trigger(036 / 037 / 035 判定の根拠)| `gs://yoshilover-history/legacy_logs/038_ledger/` |
| **B. 168 repair_provider_ledger** | 042 cron(Cloud Run Job)が自動書込 | 18 field / JSONL / 1 repair 1 行(provider 比較用)| Gemini vs Codex shadow の strict_pass 比較、本線昇格判定 | `gs://yoshilover-history/legacy_logs/168_repair_provider_ledger/` |
| **C. draft_body_editor lane logs** | 042 runner stdout 自動書込 | aggregate JSON / 1 tick 1 行 | tick 単位の集計(candidates / processed / put_ok / fail 件数 / per_post_outcomes)、運用 health monitor | `gs://yoshilover-history/legacy_logs/draft_body_editor/` |

加えて GCP active(179 land 後):
- B の本線書き先: **Firestore** `repair_ledger` collection(structured query)
- 本文 raw before/after: **GCS** `gs://yoshilover-history/repair_artifacts/<date>/<post_id>_<provider>_<run_id>.json`(ArtifactUploader)

## 各系統の rule 詳細

### A. 038 ledger(`docs/handoff/ledger/<date>.jsonl`)

**正本**: `/home/fwns6/code/baseballwordpress/docs/handoff/ledger/README.md`

#### schema(17 field、固定)

```
date / draft_id / candidate_key / subtype / event_family /
source_family / source_trust / chosen_lane / chosen_model /
prompt_version / template_version / repair_applied /
repair_trigger / repair_actions / source_recheck_used /
search_used / changed_scope / fail_tags / outcome / note
```

#### fail_tags(固定 10 種)

`thin_body` / `title_body_mismatch` / `abstract_lead` / `fact_missing` / `attribution_missing` / `subtype_boundary` / `duplicate` / `low_assertability` / `pickup_miss` / `close_marker`

context flag(`ctx_*` prefix)は別 namespace、`fail_tags` には混ぜない:
- `ctx_subject_absent` / `ctx_event_diverge` / `ctx_multiple_nuclei`(071 nucleus validator emit、078 adapter)
- `ctx_full_rewrite` / `ctx_source_weak` / `ctx_title_body_core_ambiguous`(playbook 内部用)

#### 昇格基準(優先度 036 > 037 > 035)

- **036 系**: same `subtype` + same `fail_tag` + same `prompt_version` が **24h で 3 件以上 または 7d で 5 件以上**
- **037 系**: same `source_family` + same `fail_tag` が **2 subtype 以上**で出る
- **035 判定**: `close_marker` fail が **7d で 2 件以上、または 10% 以上**
- 上記基準未満: `repair_closed` で閉じる、新規 ticket 切らない

#### 運用ルール

- 1 Draft = 1 行
- Codex repair を使った記事は `repair_trigger` / `repair_actions` / `changed_scope` 必須
- 昇格 trigger 発動 → `current_focus.md` / `decision_log.md` 還流
- `search_used=yes` の記事は週次で hallucination 温床化観測

#### 既存 entry(GCS upload 済)

- `2026-04-21.jsonl`(1 KB、1 entry: Draft 63175 accept_draft)

### B. 168 repair_provider_ledger(`logs/repair_provider_ledger/<date>.jsonl`)

**正本**: `/home/fwns6/code/wordpressyoshilover/doc/done/2026-04/168-repair-provider-ledger.md`

#### schema(18 field、v0 固定、179 で Firestore 化)

```json
{
  "schema_version": "repair_ledger_v0",
  "run_id": "uuid4",
  "lane": "repair",
  "provider": "gemini|codex|openai_api",
  "model": "gemini-2.5-flash|gpt-4o-mini|gpt-4o|chatgpt-pro",
  "source_post_id": 123,
  "input_hash": "sha256",
  "output_hash": "sha256",
  "artifact_uri": "gs://...",
  "status": "success|failed|skipped|shadow_only",
  "strict_pass": true,
  "error_code": null,
  "idempotency_key": "post_id + input_hash + provider",
  "created_at": "ISO8601 JST",
  "started_at": "ISO8601 JST",
  "finished_at": "ISO8601 JST",
  "metrics": {
    "input_tokens": 0,
    "output_tokens": 0,
    "latency_ms": 0,
    "body_len_before": 0,
    "body_len_after": 0,
    "body_len_delta_pct": 0.0
  },
  "provider_meta": {
    "raw_response_size": 0,
    "fallback_from": null,
    "fallback_reason": null,
    "quality_flags": []
  }
}
```

#### strict_pass 判定(5 条件 AND)

```
strict_pass =
  json_schema_valid
  AND hard_stop_flag_resolved
  AND fact_check_pass
  AND no_new_forbidden_claim
  AND -0.20 <= body_len_delta_pct <= 0.35
```

#### 本線昇格判定基準(ChatGPT C 結論)

- 100 件以上の sample(provider 並走 1-3 ヶ月)
- Codex strict_pass 率 > Gemini strict_pass 率
- hard_stop 解消率 Codex > Gemini
- 新規 fact risk Codex <= Gemini
- JSON parse fail < 1%
- 100 件で critical regression 0 件

#### 既存 entry(GCS upload 済)

- `2026-04-26.jsonl`(12 KB、本日 042 経由の repair entries)

### C. draft_body_editor lane logs(`logs/draft_body_editor/<date>.jsonl`)

**正本**: `src/tools/run_draft_body_editor_lane.py` の stdout JSON 出力

#### schema(aggregate per tick)

```json
{
  "candidates": <int>,
  "candidates_before_filter": <int>,
  "skip_reason_counts": {"outside_edit_window": N, "subtype_unresolved": N, "unresolved_and_stale": N, ...},
  "put_ok": <int>,
  "reject": <int>,
  "skip": <int>,
  "stop_reason": "completed|...",
  "next_run_hint": "next hourly run",
  "fetch_mode": "draft_list_paginated",
  "per_post_outcomes": [{"post_id": N, "verdict": "edited|skip|guard_fail", ...}],
  "aggregate_counts": {...},
  "edit_window_jst": "10:00-23:59 JST",
  "current_quiet_hours_before_change": "..."
}
```

#### 用途

- tick 単位の運用 health(candidates 数 / put_ok / fail カテゴリ別 count)
- 042 lane の anomaly 検知(0 publish が連続したら alert 等)
- 048 formatter は B 系統の strict_pass を見るが、C は運用 monitor 補助

#### 既存 entry(GCS upload 済)

- `2026-04-20.jsonl` / `2026-04-21.jsonl` / `2026-04-24.jsonl` / `2026-04-26.jsonl`(計 39 KB、4 file)

## 系統間の関係

```
┌────────────┐   ┌────────────────────┐   ┌───────────────────────┐
│  A. 038    │   │ B. 168 repair_     │   │ C. draft_body_editor  │
│  ledger    │   │    provider_ledger │   │    lane logs          │
│ (人間品質) │   │ (provider 比較)    │   │ (運用 health)         │
└─────┬──────┘   └──────────┬─────────┘   └───────────┬───────────┘
      │                     │                          │
      ▼                     ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 048 formatter(集計 + 昇格 trigger detection)                    │
│ - A の fail_tag aggregate(036/037/035 判定)                     │
│ - B の strict_pass 比較(本線昇格判定、長期 ledger)              │
│ - C は warning-only health monitor(anomaly alert)               │
└──────────┬───────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ 040 repair_playbook update / 036 prompt update(人間 + Codex)   │
│ - 昇格 trigger に応じて prompt 改善 fire                          │
│ - 改善された prompt が次回 repair で適用 → ループ完成             │
└──────────────────────────────────────────────────────────────────┘
```

## GCS bucket 構成(179 land 後の定常状態)

```
gs://yoshilover-history/
├── rss_history.json                      # 既存(yoshilover-fetcher 旧)
├── legacy_logs/                          # 移行前 historic(本日 upload)
│   ├── 038_ledger/
│   │   └── 2026-04-21.jsonl
│   ├── 168_repair_provider_ledger/
│   │   └── 2026-04-26.jsonl
│   └── draft_body_editor/
│       ├── 2026-04-20.jsonl
│       ├── 2026-04-21.jsonl
│       ├── 2026-04-24.jsonl
│       └── 2026-04-26.jsonl
├── repair_artifacts/                     # 179 land 後、active write
│   └── <date>/<post_id>_<provider>_<run_id>.json
└── repair_ledger_038/                    # 048 formatter が定期 sync(将来)
    └── <date>.jsonl
```

加えて Firestore(179 land 後):
- collection `repair_ledger`(168 schema v0 entry、structured query)

## 関連 ticket

- 038 / 040 / 048(baseballwordpress、既存運用、`master_backlog.md` 参照)
- 168 ✓ closed
- 179 IN_FLIGHT(repair learning log infrastructure)
- 180(将来): entrypoint script 統合(各 Cloud Run Job から ledger.write() 呼出)
- 181(将来): 048 formatter を GCS / Firestore aware に修正
- 182(任意): GCP Firestore ledger を local 038 ledger に定期 sync

## 不可触

- A. 038 ledger schema(17 field、固定、変更禁止)
- B. 168 repair_provider_ledger schema v0(18 field、固定、変更禁止)
- C. draft_body_editor lane logs format(既存 stdout JSON、変更禁止)
- 既存 GCS bucket `gs://yoshilover-history/rss_history.json` 触らない(yoshilover-fetcher 旧 monolith 用)
- legacy_logs/ 配下は read-only 参考(history、上書き禁止)
- repair_artifacts/ 配下は 179 land 後の active write target
