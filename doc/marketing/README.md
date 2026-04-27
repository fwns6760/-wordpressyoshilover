# marketing board

## meta

- owner: Claude Code / Codex-M
- type: marketing ticket board
- status: READY
- created: 2026-04-27
- updated: 2026-04-27
- source_of_truth: marketing ticket order, status, alias, and doc path

## rules

- Marketing tickets use `MKT-001`, `MKT-002`, `MKT-003`... numbering.
- Historical numeric tickets remain as aliases where the work first appeared.
- The source of truth for marketing tickets is this file.
- The repo-wide execution board remains `doc/README.md`, which should link here instead of duplicating the full marketing backlog.

## folder policy

- `doc/marketing/active/`: current marketing specs and bootstrap marketing tickets
- `doc/marketing/waiting/`: blocked or explicitly deferred marketing tickets after a future status move
- `doc/marketing/done/YYYY-MM/`: closed marketing tickets

## marketing tickets

| ticket | alias | priority | status | summary | doc_path |
|---|---|---|---|---|---|
| **MKT-001 publish-notice marketing mail classification** | 219 | P0.5 | IN_FLIGHT | 公開通知メールを Gmail 一覧で即行動できる件名・metadata へ分類し、手動 X 投稿までつなげる。 | `doc/marketing/active/MKT-001-publish-notice-marketing-mail-classification.md` |
| **MKT-002 gmail label filter color runbook** | - | P1 | PARKED | MKT-001 の件名 prefix と metadata を前提に、Gmail label / filter / color の運用手順を固定する。 | `doc/marketing/active/MKT-002-gmail-label-filter-color-runbook.md` |
| **MKT-003 daily manual x posting workflow** | - | P1 | PARKED | メール受信から X 手動投稿、確認、記録までの毎日運用フローを固める。 | `doc/marketing/active/MKT-003-daily-manual-x-posting-workflow.md` |
| **MKT-004 x candidate quality scoring** | - | P1 | PARKED | 手動 X 候補の強弱を人間が短時間で判定できる採点基準を作る。 | `doc/marketing/active/MKT-004-x-candidate-quality-scoring.md` |
| **MKT-005 weekly marketing digest** | - | P1.5 | PARKED | 週次で公開数・X候補・確認事項をまとめる digest 仕様を定義する。 | `doc/marketing/active/MKT-005-weekly-marketing-digest.md` |
| **MKT-006 manual x feedback ledger** | - | P1.5 | PARKED | 手動 X 投稿の結果と学びを残す ledger を定義し、後続の改善に使える形へ整える。 | `doc/marketing/active/MKT-006-manual-x-feedback-ledger.md` |

## related existing tickets(reference only, no move)

- [180 sns topic intake to publish lane separation](/home/fwns6/code/wordpressyoshilover/doc/active/180-sns-topic-intake-to-publish-lane-separation.md)
- [128 sns-topic-auto-publish-through-pub004](/home/fwns6/code/wordpressyoshilover/doc/waiting/128-sns-topic-auto-publish-through-pub004.md)
- [147 x autopost phased resume](/home/fwns6/code/wordpressyoshilover/doc/active/147-x-autopost-phased-resume.md)
- [149 x autopost phase 2 manual live 1](/home/fwns6/code/wordpressyoshilover/doc/active/149-x-autopost-phase2-manual-live-1.md)
- [150 x autopost phase 3 trigger on cap1](/home/fwns6/code/wordpressyoshilover/doc/active/150-x-autopost-phase3-trigger-on-cap1.md)
- [151 x autopost phase 4 cap3 ramp](/home/fwns6/code/wordpressyoshilover/doc/waiting/151-x-autopost-phase4-cap3-ramp.md)
- [152 x autopost all categories expansion](/home/fwns6/code/wordpressyoshilover/doc/waiting/152-x-autopost-all-categories-expansion.md)
- [PUB-005 x gate parent](/home/fwns6/code/wordpressyoshilover/doc/waiting/PUB-005-x-post-gate.md)
