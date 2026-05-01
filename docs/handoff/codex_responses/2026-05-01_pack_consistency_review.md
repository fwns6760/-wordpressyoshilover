# Pack consistency review

Date: 2026-05-01 JST  
Mode: Codex Lane B round 3 / doc-only / read-only

## Scope

- Reviewed pack docs: `298`, `293`, `282`, `290`, `300`, `288`, `278-280 merged`
- Count basis: **7 files**. The user prompt says "8 existing Pack drafts", but the provided path list contains 7 docs; `278-280` is already one merged 3-phase pack doc.
- Result: **dependency cycle 0 / mutually blocking precondition pair 0**

## 1. Dependency graph

```text
298-Phase3 (already deployed; binding observe window through 2026-05-02 09:00 JST)
├─> 290-QA deploy
│   └─> 278-280-MERGED
├─> 293-COST impl pack
│   └─> 282-COST flag ON
│       └─> 288-INGEST source add
└─> 300-COST source-side reduction

External gates not in the reviewed pack set:
- 290 additionally waits on 299-QA + production_health_observe pass
- 293 additionally waits on 299-QA + production_health_observe pass + Codex fire budget reset
- 288 additionally waits on 289 stable + 291 terminal contract + 295 complete
```

### Dependency interpretation

- `298` is no longer a future pack fire. It is the **already executed safety floor** that other packs wait behind.
- `290` and `293` are **graph-independent** after `298` stability. `290` first is still safer operationally because it is a smaller single-service deploy.
- `300` is also a **parallel branch** after `298` stability. It is not a child of `293` or `282`.
- `282` is the only reviewed pack with a **hard direct dependency** on `293`.
- `288` is the deepest leaf because it depends on both the cost chain (`293 -> 282`) and the quality/visibility chain (`289`, `290`, `291`, `295`).
- `278-280-MERGED` depends on `290 + 24h` and its own merged impl completion, not on `282`, `293`, `300`, or `288`.

## 2. Preconditions cross-check

| pack | extracted Preconditions | reviewed-pack dependency | external dependency | cross-check |
|---|---|---|---|---|
| `298` | already has user GO, green tests, clean export, flag OFF/ON observe green; expiry `2026-05-02 09:00 JST` | none | none | baseline gate only |
| `290` | `298` 24h stable, `299-QA` settled, `production_health_observe` pass, Claude review | `298` | `299-QA`, `production_health_observe` | consistent |
| `293` | `298` stable, `299-QA` + `2026-05-01 17:00 JST` observe pass, Codex budget reset, doc agreement | `298` | `299-QA`, `production_health_observe`, Codex fire budget | consistent |
| `282` | `293` impl+test+deploy complete, `293` 24h stable, `298` stable, 8-item gate all YES | `293`, `298` | none beyond 293's gates | consistent |
| `300` | `298` 24h stable, sink-side 298 flag stays ON, production health normal | `298` | `production_health_observe` | consistent |
| `288` | `289` stable, `290` deploy+24h stable, `295` complete, `291` terminal contract, `282/293` cost chain established | `290`, `282`, `293` | `289`, `291`, `295` | consistent |
| `278-280` | `290` deploy complete, `290` +24h stable, merged impl complete, phase 3 mail-budget quantified | `290` | none | consistent |

### Timing normalization note

- `298` final pack uses **`2026-05-02 09:00 JST`** as the second-wave boundary.
- `290` still phrases its earliest gate as **`2026-05-02 14:15 JST`** after the earlier rollback-observe checkpoint.
- This is **not a contradiction**, but Claude should present the later time as the binding gate when asking for `290` user GO.

### Cycle / contradiction result

- `A waits B` and `B waits A`: **0**
- hard contradiction found in reviewed precondition lines: **0**
- soft normalization needed: **1** (`298 09:00 JST` gate vs `290 14:15 JST` gate wording)

## 3. Blast radius cross-check

### Same-service collision map

| service / runtime surface | packs touching it | collision risk | handling |
|---|---|---|---|
| `publish-notice` | `298`, `293` scanner/persistence side, `278-280` phase 3 | high | never bundle; each changes mail/dedup/cap visibility |
| `yoshilover-fetcher` | `290`, `293` producer side, `282`, `288`, `278-280` phase 1-2 | high | keep one moving part per observe window |
| `guarded-publish` | `300` | medium | isolated service, but it feeds the 298-protected sink |

### Cross-pack conflict observations

- `290` and `282` should not share one deploy window because both change `yoshilover-fetcher` outcome counts and would blur rescue-vs-preflight causality.
- `293` and `278-280 phase 3` should not share one deploy window because both touch `publish-notice` subject/dedup/review visibility.
- `288` must not be bundled with any fetcher-side quality or cost pack because it changes candidate inflow itself.
- `300` can be developed independently after `298` stability, but if it regresses, **rollback `300` first and keep `298` sink-side guard ON**.

### Rollback order consistency

1. If `282` and `293` are both live, rollback order must be `282 fetcher flag OFF -> 293 notification path OFF`, matching the `293` handoff rule for avoiding silent preflight skips.
2. If `300` and `298` are both live, rollback `300` first. `298` is the downstream protective layer and should remain ON unless the incident is proven to be inside `298`.
3. If `278-280 phase 3` is live on top of `293/298`, rollback the newest `publish-notice` mail-routing change first, then reconsider `293/298`.
4. Fetcher-side stack should rollback newest-first: `288 -> 282 -> 293 producer deploy(if any) -> 290`.

## 4. Proposed user GO order

### Hard dependency order

1. `298` observation gate remains first. Earliest morning checkpoint can be `2026-05-02 06:00 JST`, but the pack's own binding boundary is `2026-05-02 09:00 JST`.
2. `290` may be shown only after `298` is still green and the later `2026-05-02 14:15 JST` gate is respected.
3. `293` can follow once `298` stability and `production_health_observe` are confirmed.
4. `282` must stay after `293 deploy + 24h stable`.
5. `288` must stay last because it depends on `290`, `291`, `295`, and the `282/293` cost chain.

### Conservative serialized order for Claude to present

1. `298-Phase3` second-wave observe / hold-carry check on **2026-05-02**
2. `290-QA` deploy pack after **2026-05-02 14:15 JST**
3. `293-COST` impl pack after `298` stability confirmation
4. `282-COST` flag ON after `293` complete + 24h stable
5. `300-COST` impl after `298` stability
6. `288-INGEST` after all five external conditions are YES
7. `278-280-MERGED` after `290 + 24h` and merged impl completion

### Why this order is defensible

- It matches the user's proposed sequence closely.
- It keeps `290` before the broader two-surface `293` work.
- It keeps `300` after `298` stability even though it is graph-parallel, preserving incident isolation.
- It leaves `288` last, where every reviewed pack already points.
- It keeps `278-280` late for operational simplicity, even though hard dependency alone would allow it earlier than `288`.

## 5. UNKNOWN flag review

Count method: **final Acceptance Pack 18-field block only**, not earlier draft paragraphs or side notes.

| pack | UNKNOWN count | remaining UNKNOWN fields | recommended path |
|---|---:|---|---|
| `298` | 0 | none in deploy-ready final pack | none |
| `293` | 0 | none in the impl pack block | none |
| `282` | 2 | `Candidate disappearance risk`, `Cache impact` | resolve by `293` visible path + 24h measurement before `282` GO |
| `290` | 0 | none | none |
| `300` | 0 | none | none |
| `288` | 1 | `Cache impact` | resolve only after source-add observe window |
| `278-280` | 0 | none | none |

### UNKNOWN total

- **Acceptance-pack-only UNKNOWN total: 3**
- Breakdown: `282=2`, `288=1`

### Note on narrative UNKNOWN outside the 18-field blocks

- `298` still contains an older HOLD draft section with `289 24h stable close = unknown`, but the later deploy-ready pack clears it.
- `293` has handoff notes saying `Gemini call delta UNKNOWN` and `Mail volume impact UNKNOWN` for the future `282` decision, but those are **not residual UNKNOWN fields in the 293 pack itself**.

## 6. User contact strategy

### Recommended

- **1 day / 1 pack presentation**
- Reason: most remaining packs share either `yoshilover-fetcher` or `publish-notice`, so batching makes rollback attribution and 24h observation harder.

### Acceptable batch exception

- Small batch only when packs are on different services and not in a dependency chain.
- Safest candidate pair after `298` stability: `290` plus `300` review material on one screen, while still asking for only one execution GO at a time.

### Not recommended

- batching `293` with `282`
- batching `288` with any other pack
- batching `278-280 phase 3` with `298` or `293`

## Final assessment

- **dependency_conflicts detected**: `0`
- `300` is a parallel branch after `298`, not a child of `293/282`
- `278-280` is operationally late by choice, not by hard graph necessity
- `288` is correctly the final leaf
- The main remaining cross-pack risk is not a cycle; it is **same-service deploy overlap**
