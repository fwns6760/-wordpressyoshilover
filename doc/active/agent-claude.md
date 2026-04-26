# agent-claude

## meta

- agent: Claude Code(現場管理)
- model: claude-opus-4-7
- type: orchestration / 監査 / 起票 / 仕様化 / push 担当
- status: ACTIVE
- created: 2026-04-26

## 担当 scope

- 監査・現状復元・台帳整理(README dispatch board の更新)
- ticket / Codex prompt の起票
- Codex 便の accept(5 点追認: git log + status + grep + pytest collect + pytest pass)
- git push(Codex は push しない、本 repo 専属 push 担当)
- doc 整理 / folder policy 維持
- read-only 観測(WP REST GET、git log、grep、pytest)
- 105 ramp orchestration(burst fire + history clear + accept)
- live publish の trigger(autonomous lock 範囲内)

## 不可触

- src 直接編集(原則 Codex 専属、緊急時のみ Claude 手動 narrow fix)
- tests 直接編集(同上)
- LLM API call(Gemini live = 113 PARKED)
- automation.toml / scheduler env / Cloud Run env
- `.env` / secret 表示
- baseballwordpress repo の src
- 本 ticket での X / SNS POST(別 lane PUB-005)

## 現在の主担当

- 105 PUB-004-D ramp orchestration(本日 66 件 publish 完了)
- README dispatch board 維持
- doc folder policy 維持(root = README のみ)
- baseline 1286/0 維持(デグレなし永続 lock)
