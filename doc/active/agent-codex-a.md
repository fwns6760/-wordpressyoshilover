# agent-codex-a

## meta

- agent: Codex A(実装本線)
- runtime: codex exec --full-auto --skip-git-repo-check --sandbox danger-full-access
- type: 実装 / バグ修正 / テスト / commit(push なし)
- status: ACTIVE(idle / fire 待ち)
- created: 2026-04-26

## 担当 scope

- ops / mail / cron / publish runner / WP REST / backup / history / queue
- doc commit(明示 path、`git add -A` 禁止)
- 既存 src 改修(`src/guarded_publish_runner.py` / `src/publish_notice_email_sender.py` 等)
- tests 追加 / 既存 tests 維持
- commit(plumbing 3 段 fallback 標準)
- baseline 維持 contract(全 prompt に embed): suite collect / pass / fail 数値報告必須

## 不可触

- git push(Claude が push)
- LLM API call / mail real-send / X / SNS POST / live publish(test は mock のみ)
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- automation / scheduler / front / plugin / build
- requirements*.txt 改変
- baseballwordpress repo
- doc reorg(C 担当)
- AGENTS.md / CLAUDE.md(別 commit で sync)

## 本日完了便(2026-04-26)

- 130 PUB-004 3-class + cleanup chain
- 131 publish-notice burst summary
- 138 spec(impl killed)

## 現在 idle、次 fire 候補

- 124-A live cleanup apply runner
- 残 cleanup_failed の cleanup chain 改善 narrow
