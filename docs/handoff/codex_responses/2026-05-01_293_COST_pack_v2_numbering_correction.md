# 293-COST pack v2 numbering correction

Date: 2026-05-01 JST  
Mode: Codex Lane B round 10 / doc-only / cross-reference only

## 0. Purpose

`docs/ops/POLICY.md` was simplified to 12 sections in the user-reset baseline.  
`docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md` §8-§11 still contains old section-number references such as `POLICY §18` and `POLICY §22`.

This note is the normalization layer for tomorrow morning's user-facing compression.  
It does **not** change design substance, pack completeness, or go/hold judgment.

Sources:

- current canonical policy: `docs/ops/POLICY.md`
- current pack template: `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
- stale-citation review already recorded: `docs/handoff/codex_responses/2026-05-01_293_COST_pack_final_review.md`
- historical artifact to read through this mapping: `docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md`

## 1. New POLICY 12-section mapping

| old POLICY reference | old meaning in 293-COST docs | current canonical reference | normalization rule |
|---|---|---|---|
| `POLICY §6` | silent skip must not reappear; skipped candidates must become visible | `docs/ops/POLICY.md §8` | Replace `POLICY §6` with `POLICY §8 Silent Skip Policy`. |
| `POLICY §18` | "Acceptance Pack 18 項目" and `UNKNOWN` safety gate | `docs/ops/POLICY.md §9` + `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` Required Fields `1-13` | Replace `POLICY §18` wording with `POLICY §9 Acceptance Pack Requirement` and `ACCEPTANCE_PACK_TEMPLATE 13 required fields`. If the pack is a `298-Phase3` re-ON pack, also include `298-Phase3 Additional Required Fields`; do not keep the old `18 項目` label as canonical policy wording. |
| `POLICY §22` | `MAIL_BUDGET` / mail-volume guard / unknown mail impact is HOLD | `docs/ops/POLICY.md §7` | Replace `POLICY §22 MAIL_BUDGET` with `POLICY §7 Mail Storm Rules`. |

## 2. Numbering verify for old `POLICY §7`

`design v2` uses `POLICY §7` as the source for `293 -> 282` order lock, but current `POLICY.md §7` is **Mail Storm Rules**, not dependency ordering.

Therefore:

- `POLICY §7 順序固定` should **not** be remapped to current `POLICY.md §7`.
- The current canonical source for `293 -> 282` order lock is:
  - `docs/ops/OPS_BOARD.yaml` dependency state
  - `docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md` §9 order block
  - `docs/handoff/codex_responses/2026-05-01_pack_consistency_review.md`
- In tomorrow morning's Decision Batch, Claude should say `293 -> 282 order lock` or `OPS_BOARD dependency lock`, not `POLICY §7`.

## 3. 293-COST design v2 §8-§11 correction targets

| location in `2026-05-01_293_COST_design_v2.md` | stale wording | tomorrow-morning replacement |
|---|---|---|
| `715-753` | `Acceptance Pack 18 項目 final draft` | Read as `Acceptance Pack final draft` under `POLICY §9` + `ACCEPTANCE_PACK_TEMPLATE 13 required fields`. If Claude is compressing a `298-Phase3` re-ON pack, append the template's `298-Phase3 Additional Required Fields`. |
| `724`, `758`, `763`, `816` | `POLICY §7 順序固定` | Replace with `293 -> 282 order lock` or `OPS_BOARD dependency lock`. Do not cite current `POLICY §7` here. |
| `740`, `799` | `silent skip 増加(POLICY §6)` / `silent skip 復活(POLICY §6 P0)` | Replace with `POLICY §8 Silent Skip Policy`. |
| `783` | `POLICY §18 UNKNOWN GO 禁止` | Replace with `POLICY §9 Acceptance Pack Requirement` + `ACCEPTANCE_PACK_TEMPLATE` HOLD rule for `UNKNOWN` in safety-critical fields. |
| `788` | `POLICY §22 MAIL_BUDGET 違反継続` | Replace with `POLICY §7 Mail Storm Rules`. |

Additional read-through note:

- `743`, `765`, `779`, `788` all talk about `MAIL_BUDGET`.
- When Claude needs one canonical policy citation for those lines, use `docs/ops/POLICY.md §7`.

## 4. Application policy

- `2026-05-01_293_COST_design_v2.md` remains a **historical artifact**. Do not edit it just to repair numbering.
- `2026-05-01_293_COST_pack_final_review.md` also remains unchanged. It already flagged the stale numbering correctly.
- Tomorrow morning, Claude should apply this mapping when compressing `design v2` into a user-facing Decision Batch or Acceptance Pack summary.
- This file stays as the stable cross-reference so later readers do not have to re-derive the old-to-new numbering map after the policy reset.

## 5. Net effect

- Substance unchanged
- pack completeness unchanged
- go/hold judgment unchanged
- numbering confusion removed for user-facing summaries
