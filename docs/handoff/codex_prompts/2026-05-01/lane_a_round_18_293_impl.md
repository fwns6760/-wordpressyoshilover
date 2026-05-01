# Lane A round 18 prompt: 293-COST impl + test + commit + push(READY_FOR_DEPLOY 目指す)

You are Codex (Lane A round 18, impl + test + commit + push). 293-COST READY_FOR_DEPLOY 化(本番 deploy なし、push しても publish-notice job image 未 rebuild = 反映されない設計).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
293-COST preflight skip visible 化(消化順 順 1、新 OPS_BOARD ACTIVE entry、user 指示「READY_FOR_DEPLOY 目指す」)

参照(設計 doc 着地済):
- design v2: docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md(30c8204 + Claude 補強 7f2f3e9)
- final review: docs/handoff/codex_responses/2026-05-01_293_COST_pack_final_review.md(856dd59、13/13)
- numbering correction: docs/handoff/codex_responses/2026-05-01_293_COST_pack_v2_numbering_correction.md(6ddff7c)
- READY pack: docs/handoff/codex_responses/2026-05-01_293_COST_ready_pack.md(22f0a3e)
- impl 順序 4 commit(設計 v2 §3 / READY pack §4)

[goal]
4 commit 順次 + test + push、deploy なし(user 「pushしても本番反映されない場合のみcommit/push可」整合)。

[scope - touched files]
- commit 1: src/cloud_run_persistence.py(ledger schema + persistence scaffold)+ tests/test_cloud_run_persistence.py 追記
- commit 2: src/publish_notice_scanner.py(scanner parallel path)+ tests/test_publish_notice_scanner.py 追記 + tests/test_preflight_skip_notification.py 新規
- commit 3: src/rss_fetcher.py + src/gemini_preflight_gate.py(skip event 出力 + skip_layer 追加、persisted JSONL row に record_type / skip_layer 保存)
- commit 4: tests 7 cases 全部完成 + test_post_gen_validate_notification.py 既存 維持 verify

[必須条件 全部 AND]
- new env 3 default OFF: ENABLE_PREFLIGHT_SKIP_NOTIFICATION / PREFLIGHT_SKIP_LEDGER_PATH / PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS
- pytest baseline +0 regression(既存 test 全 green、新 test 7 cases 全 pass)
- post_gen_validate path 維持(289 不変)
- Team Shiny `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` 不変
- cap=10 / 24h dedup 不変
- Gemini call 増加 0(scanner / persistence / ledger touch のみ、Gemini 呼び出さない)

[必須 test 7 cases]
1. fetcher が flag ON 時 preflight ledger row 書く
2. scanner が flag ON 時 mail request emit(subject prefix `【要review｜preflight_skip】`)
3. flag OFF 時 silent skip 0(ledger 不作成、scanner emitted=[])
4. 24h dedupe window(同 dedupe_key で skip)
5. 8 reason label mapping(table-driven subtest 1 case)
6. post_gen_validate path 維持(289 emit 不変)
7. persistence entrypoint download/upload(新 state file)

[hard constraints]
- DO NOT touch: src/guarded_publish_runner.py / config/ / Dockerfile / cloudbuild yaml / requirements.txt
- DO NOT image rebuild / cloud build / deploy / env apply / Scheduler 操作
- DO push origin master(本日 push OK、deploy 反映なし、user GO 後の image rebuild で初めて反映)
- minimum-diff、scope 内のみ
- DO NOT install packages
- DO NOT change git config
- 不可触: 290 / 282 / 298 / 300 / 288 関連 file 触らない

[完了 contract - 全部 AND]
1. impl 4 commit 順次着地(各 commit 単独で pytest 通過)
2. tests 7 cases 全 pass
3. pytest baseline failures 増加 0(既存 3 pre-existing failures は scope 外、+0 確認)
4. git add 明示 path のみ、`git add -A` 禁止
5. 各 commit 前 `git diff --cached --name-status` で stage verify
6. push origin master 実行
7. 完了 evidence:commit hashes + pytest before/after counts + new test count + env knobs

[completion report - 7 fields]
- changed_files: [...] (impl 4 commit 分の touched files)
- commit_hashes: [commit 1, commit 2, commit 3, commit 4]
- pytest_baseline: <pass>/<fail>
- pytest_after: <pass>/<fail>(failures 増加 0 必須)
- new_test_count: 7
- env_knobs_added: ENABLE_PREFLIGHT_SKIP_NOTIFICATION / PREFLIGHT_SKIP_LEDGER_PATH / PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS
- push_status: pushed | pending(Claude to push)
- next_action_for_claude: "293 impl + test + commit + push 完了、READY_FOR_DEPLOY 状態確定、本日 deploy なし、明日朝以降 user GO で image rebuild + deploy"

[dialogue rule]
- 既存 test の 3 pre-existing failures は scope 外、新規 fail 増加 0 を維持
- pytest 実行は 2 回まで(baseline + after)、それ以上は scope 拡大
- sandbox `.git/index.lock` 拒否時 plumbing 3 段(write-tree / commit-tree / update-ref)で fallback
- push 失敗 (DNS / auth) なら Claude に "push pending" 報告、Claude が代行 push
- silent skip 検出時 stop + 報告
