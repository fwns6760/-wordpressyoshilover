# PUB-004-D all-eligible-draft-backlog-publish-ramp

## meta

- owner: Claude Code(orchestration)/ PUB-004-A + B 既存実装を流用、新規 Codex便なし
- type: ops / backlog drain plan / orchestration
- status: READY(PUB-004-B `f451f17` land 後の主線)
- priority: **P0.5**
- parent: PUB-004 / PUB-002-A
- depends: PUB-004-A(`53561b6`)evaluator / PUB-004-B(`f451f17`)runner
- created: 2026-04-26

## 目的

既存 376 drafts(2026-04-25 24:00 時点 inventory)を全件対象にし、PUB-004 判定に従って **Red 以外の Green / Yellow / cleanup 可能記事を段階的に WordPress 公開**する。

「全記事公開」は status 一括 flip ではなく、**PUB-004 gate を通した eligible draft のバックログ一掃**として扱う。

## 前提

- WordPress publish のみ
- noindex 維持
- X / SNS POST なし
- publish-notice mail は既存 095 cron に任せる
- `RUN_DRAFT_ONLY=False` は触らない
- Cloud Run env は触らない
- 既存 PUB-004-A / B / C に沿う

## 不可触

- 全 draft の無条件 publish(必ず PUB-004-A gate 通過)
- Red 記事の publish
- X / SNS 投稿
- X API 接続
- `RUN_DRAFT_ONLY` flip
- Cloud Run env / scheduler / .env / secrets
- front / plugin
- Yoshilover Exclude Old Articles plugin 再有効化
- baseballwordpress repo
- automation.toml 直接改変
- `git add -A`

## 実装(新規 code なし、既存 PUB-004-A + B 流用)

| Step | 操作 | 道具 |
|---|---|---|
| 1 | 全 draft pool 棚卸し | `python3 -m src.tools.run_guarded_publish_evaluator --window-hours 999999 --max-pool 500 --format json --output /tmp/pub004d_full_eval.json --exclude-published-today` |
| 2 | 件数表確認 | jq で `summary` 部分抽出、Green / Yellow / Red / cleanup_candidate 件数を user に報告 |
| 3 | dry-run with PUB-004-B | `python3 -m src.tools.run_guarded_publish --input-from /tmp/pub004d_full_eval.json --max-burst 3 --format json` |
| 4 | proposed list 確認 | refused 件 / would_publish 件、daily cap 残量を確認 |
| 5 | live publish(burst 3) | `python3 -m src.tools.run_guarded_publish --input-from /tmp/pub004d_full_eval.json --max-burst 3 --live --daily-cap-allow` |
| 6 | postcheck | public URL HTTP 200、history.jsonl の sent 行 |
| 7 | 095 cron で mail 自動配信 | 次の :15 tick で 3 通(burst cap 内) |
| 8 | 翌日以降繰り返し | daily cap 10 内で 1 日 1-3 invocation |

## 段階的 ramp 案(daily cap 上げ判断)

| 段階 | daily cap | burst cap | 観察期間 | 上げる条件 |
|---|---|---|---|---|
| 初期(現状)| 10 | 3 | 1 週間 | mail 配信全 OK / Gmail filter spam なし / Red 誤判定なし / 公開記事 quality 確認 |
| 中期 | 20 | 5 | 1 週間 | 同上、cron ramp 安定 |
| 後期 | 30 | 5 | 続き | 同上、運用負荷確認 |
| 最終 | 50 | 5 | continuous | bulk drain 完了に近づいたら自然減 |

cap 上げは本 ticket scope 外、段階毎に user 判断 escalate(別 narrow ticket)。

## 受け入れ条件

1. dry-run で全 draft の判定表(Green / Yellow / Red / cleanup_candidate 件数)が出る
2. Red 理由(R1-R8)が見える(`refused` 配列の `reasons`)
3. Green / Yellow / cleanup_candidate の公開候補リストが出る
4. live 時は burst cap 3 / daily cap 10 を守る
5. 公開後に public URL HTTP 200 確認
6. publish history(`logs/guarded_publish_history.jsonl`)/ yellow_log / cleanup_log が残る
7. 同一記事の二重 publish 防止(history dedup)
8. X / SNS 投稿が発火しない(verified 2026-04-25、WP REST status flip 単独で X 配線 fire しない)

## stop 条件

- mail burst > 5 通予測 → invocation 内で 3 件で打ち切り(PUB-004-B 既装)
- daily cap 10 到達 → 翌日繰り越し(PUB-004-B 既装、JST 0:00 reset)
- Red 誤判定発生(明らか Red を Green と判定 → publish 事故)→ 即停止 + escalate user
- mail 全件 spam 振り分け → 095 cron 一旦 disable + escalate
- Yoshilover X timeline に自動投稿が出現 → 即 PUB-004-B disable + escalate

## 関連 file

- `doc/PUB-004-guarded-auto-publish-runner.md`(parent contract)
- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(judgment contract)
- `src/tools/run_guarded_publish_evaluator.py`(PUB-004-A、commit `53561b6`)
- `src/tools/run_guarded_publish.py`(PUB-004-B、commit `f451f17`)
- `src/guarded_publish_runner.py`(PUB-004-B helper)
- `logs/guarded_publish_history.jsonl`(history dedup source)
- `logs/guarded_publish_yellow_log.jsonl`(Yellow 改善ログ、PUB-002-B/C/D の input)
- `logs/guarded_publish_cleanup_log.jsonl`(cleanup before/after diff)

## 次の cron 化(PUB-004-C)

PUB-004-D 安定運用 1〜2 日 + 失敗 0 件確認後、PUB-004-C で WSL cron 自動化。
朝 / 昼 / 夜 = `0 8,13,20 * * *` 等で 1 日 3 回起動 → daily cap 10 内で 9 件 / 日 自動 publish 想定。
