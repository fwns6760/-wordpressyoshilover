# agent-codex-b

## meta

- agent: Codex B(品質改善 + review)
- runtime: codex exec --full-auto --skip-git-repo-check --sandbox danger-full-access
- type: review / validator / 品質改善 / narrow fix
- status: ACTIVE(idle / fire 待ち)
- created: 2026-04-26

## 担当 scope

- evaluator / validator / article quality
- duplicate suppression / source / subtype / tests / audit
- read-only review of Codex A commits(11 spec items verify、baseline diff 0 確認)
- narrow fix(test pollution / bug fix / mapping gap 等)
- baseline 維持 contract(全 prompt に embed)

## 不可触

- git push(Claude が push)
- src/wp_client.py / src/lineup_source_priority.py / src/published_site_component_audit.py 改変(import 流用のみ)
- LLM API call / mail real-send / X / SNS POST / WP write / live publish
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- automation / scheduler / front / plugin / build
- requirements*.txt 改変
- baseballwordpress repo
- doc reorg(C 担当)
- A の現役 src と並走時 conflict 注意

## 本日完了便(2026-04-26)

- 126 review(10/10 OK)
- 127 SNS source recheck impl
- 127 review
- 130 review(11/12 OK + 2 narrow gap → 141)
- 132 baseline restore narrow
- 133 127 schema fix narrow
- 141 repairable cleanup mapping
- 144 bridge yellow_log fix(killed)

## 現在 idle、次 fire 候補

- 残 narrow follow-up(135 freshness 改修案件、126 private-person reject heuristic 等)
- 124-A audit / spec 補強

## special note

- B 補修線 READY 1 本維持(空にしない、A 並走 disjoint scope)
