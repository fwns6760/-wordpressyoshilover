# marketing board

## meta

- owner: Claude Code / Codex A / Codex B
- type: marketing ticket board
- status: READY
- created: 2026-04-27
- updated: 2026-04-29
- source_of_truth: marketing ticket order, status, alias, and doc path

## rules

- Marketing tickets use `MKT-001`, `MKT-002`, `MKT-003`... numbering.
- Historical numeric tickets remain as aliases where the work first appeared.
- The source of truth for marketing tickets is this file.
- The repo-wide execution board remains `doc/README.md`, which should link here instead of duplicating the full marketing backlog.
- Current active implementation lanes are Codex A / Codex B only. Do not dispatch marketing cleanup to Codex C or Codex-M.

## folder policy

- `doc/marketing/active/`: current marketing specs and bootstrap marketing tickets
- `doc/marketing/waiting/`: blocked or explicitly deferred marketing tickets after a future status move
- `doc/marketing/done/YYYY-MM/`: closed marketing tickets

## marketing tickets

| ticket | alias | priority | status | summary | doc_path |
|---|---|---|---|---|---|
| **MKT-001 publish-notice marketing mail classification** | 219 | P0.5 | CLOSED | 件名 prefix 6 class + 本文 metadata が live 反映済み。publish-notice image `25f176b` で運用中。 | `doc/marketing/done/2026-04/MKT-001-publish-notice-marketing-mail-classification.md` |
| **MKT-002 gmail label filter color runbook** | - | P1 | DROPPED | Not needed now; PC/mobile notification delivery is already confirmed, and Gmail filtering adds overhead. | `doc/marketing/done/2026-04/MKT-002-gmail-label-filter-color-runbook.md` |
| **MKT-003 daily manual x posting workflow** | - | P1 | DROPPED | Manual X workflow is handled by user + GPTs; no repo-side workflow ticket needed. | `doc/marketing/done/2026-04/MKT-003-daily-manual-x-posting-workflow.md` |
| **MKT-004 x candidate quality scoring** | - | P1 | DROPPED | Candidate scoring/wording is handled by GPTs. | `doc/marketing/done/2026-04/MKT-004-x-candidate-quality-scoring.md` |
| **MKT-005 weekly marketing digest** | - | P1.5 | DROPPED | Weekly digest is not current P0; recreate later only if needed. | `doc/marketing/done/2026-04/MKT-005-weekly-marketing-digest.md` |
| **MKT-006 manual x feedback ledger** | - | P1.5 | DROPPED | Feedback ledger would add process overhead; keep learning in GPTs/user notes for now. | `doc/marketing/done/2026-04/MKT-006-manual-x-feedback-ledger.md` |
| **MKT-007 gmail marketing notification filter and ChatGPT triage ops** | 223 | P0.5 | CLOSED | Gmail通知/ラベル/ChatGPT triage runbook を固定済み。実際のGmail手動設定はuser運用タスクとして扱う。 | `doc/marketing/done/2026-04/MKT-007-gmail-marketing-notification-filter-and-chatgpt-triage-ops.md` |
| **MKT-008 X post candidate text quality hardening** | 225 | P0.5 | DROPPED | X candidate wording is handled by GPTs; repo focuses on article/numeric safety guards. | `doc/marketing/done/2026-04/MKT-008-x-post-candidate-text-quality-hardening.md` |

## related existing tickets(reference only, no move)

- [180 sns topic intake to publish lane separation](/home/fwns6/code/wordpressyoshilover/doc/waiting/180-sns-topic-intake-to-publish-lane-separation.md)
- [128 sns-topic-auto-publish-through-pub004](/home/fwns6/code/wordpressyoshilover/doc/waiting/128-sns-topic-auto-publish-through-pub004.md)
- [147 x autopost phased resume](/home/fwns6/code/wordpressyoshilover/doc/waiting/147-x-autopost-phased-resume.md)
- [149 x autopost phase 2 manual live 1](/home/fwns6/code/wordpressyoshilover/doc/waiting/149-x-autopost-phase2-manual-live-1.md)
- [150 x autopost phase 3 trigger on cap1](/home/fwns6/code/wordpressyoshilover/doc/waiting/150-x-autopost-phase3-trigger-on-cap1.md)
- [151 x autopost phase 4 cap3 ramp](/home/fwns6/code/wordpressyoshilover/doc/waiting/151-x-autopost-phase4-cap3-ramp.md)
- [152 x autopost all categories expansion](/home/fwns6/code/wordpressyoshilover/doc/waiting/152-x-autopost-all-categories-expansion.md)
- [PUB-005 x gate parent](/home/fwns6/code/wordpressyoshilover/doc/waiting/PUB-005-x-post-gate.md)
