# 155 gcp-cron-migration(WSL cron → Cloud Run Jobs 移行)

## meta

- number: 155
- owner: Claude Code(設計 / 起票 / orchestration)/ Codex(実装、push しない、Claude が push)
- type: ops / infra / cron migration
- status: **IN_FLIGHT**(Phase 1a `88391d0` / 1b `c5adfa3` done、Phase 2 = ChatGPT phasing 168-175 chain で展開中)
- priority: P0.5(速報掲示板 24/7 化、PC sleep 依存解消)
- lane: A
- created: 2026-04-26
- parent: -
- related: 042 / PUB-004-C / 095 / gemini_audit / quality-monitor / quality-gmail

## 背景

- 2026-04-26 15:00-15:08 JST、Windows host sleep で WSL2 VM pause、cron 5min 飛び発生(syslog clock change detected)
- 速報掲示板の自動公開 pipeline は **PC 起動状態に依存**(host sleep / WSL idle / Codex Desktop 落ち で停止)
- GCP Cloud Run Jobs + Cloud Scheduler に移行すれば PC 依存ゼロ・24/7 安定化
- コスト試算: 全 6 lane 合算で **$1-3/月**(Cloud Run vCPU 微課金 + Cloud Scheduler 3 jobs 課金、ほぼ無料枠内)
- 既存 giants-* schedulers は同 GCP project 内で稼働中、infra 流用可

## ゴール

WSL crontab で動いている cron 4 lane + Codex Desktop automation 2 lane 計 **6 lane** を Cloud Run Jobs + Cloud Scheduler に段階移行し、最終的に WSL crontab 空・Codex Desktop automation 不要化する。

## Phase 構成(逐次 fire)

| Phase | 内容 | 別 ticket |
|---|---|---|
| **1a** | 042 cron(`run_draft_body_editor_lane`)を Dockerfile + Cloud Build 化(deploy なし、image 作成 + push 確認のみ) | 本 ticket(155-1a) |
| 1b | 042 image を Cloud Run Job として deploy、手動 trigger で smoke 確認 | 156 |
| 1c | 042 に Cloud Scheduler trigger 追加(`2,12,22,32,42,52 * * * *`)、WSL cron は並走維持 | 157 |
| 1d | 042 の env / secret(WP_API_PASSWORD / GEMINI_API_KEY / OPENAI_API_KEY)を Secret Manager 化(API key 経路、auth.json 経路は採用せず)| 158 / 172 |
| 1e | 042 GCP 安定 1 日確認後、WSL crontab 042 行 disable | 159 |
| 2 | PUB-004-C(評価 + publish 2 段)を同パターンで 1a-1e 流用 | 160 |
| 3 | 095 publish-notice 同上 | 161 |
| 4 | gemini_audit 同上 | 162 |
| 5 | quality-monitor / quality-gmail(Codex Desktop 由来 2 lane)を Cloud Run Jobs 化 | 163 |
| 6 | WSL crontab + Codex Desktop automation 全 disable、Cloud Logging dashboard 化、alert 設定 | 164 |

各 Phase は **直前 Phase の smoke 通過後** に fire。並列 fire しない。

## 2026-04-26 PM 改訂(ChatGPT Plan mode A-G 結論受領)

仕様変更 / 追加:

- **本線 provider = Gemini Flash 維持**、Codex CLI(ChatGPT Pro auth.json)は **shadow lane 限定**
- 本線 fallback = OpenAI **API key 経路**(auth.json 経路は ToS 観点で本線非採用)
- Phase 1d で Secret Manager に保存するのは API key のみ(auth.json writeback 設計 = 別 ticket 172、shadow lane 用)
- ChatGPT phasing 8 ticket → 我々 repo で **168-175 として起票** chain 展開:
  - 168 repair-provider-ledger v0(`70009aa` push 済 ✓)
  - 169 cloud-run-repair-job-skeleton(IN_FLIGHT)
  - 170 repair-fallback-controller
  - 171 codex-cli-shadow-runner
  - 172 cloud-run-secret-auth-writeback(shadow lane 限定、本線は API key)
  - 173 x-post-cloud-queue-ledger v0(IN_FLIGHT、168 と並列着手)
  - 174 x-api-cloud-run-live-smoke
  - 175 x-controlled-autopost-cloud-rollout
- **cron 時刻不変 lock**(全 ticket で既存 cron schedule 触らない)
- ChatGPT 助言: 本線昇格は ledger ベースの 100 件以上 A/B 比較 + strict_pass 比較で判定

## Phase 1a 仕様(本 ticket scope)

### 目的

`src/tools/run_draft_body_editor_lane.py` を Cloud Run Jobs で実行可能な container image にし、Artifact Registry に push する(deploy / scheduler 設定は 1b/1c で別 ticket)。

### 成果物

- `Dockerfile.draft_body_editor`(repo root)
- `.dockerignore`(必要なら)
- `cloudbuild_draft_body_editor.yaml`(Cloud Build 用、Artifact Registry 連携)
- `doc/active/155-1a-deployment-notes.md`(image 名 / region / project / Artifact Registry path / build 確認手順)
- 既存 src / tests / .env / crontab 一切変更なし

### Dockerfile 要点

- base: `python:3.12-slim`(WSL の `/usr/bin/python3` が 3.12 確認済)
- workdir: `/app`
- copy: `src/`, `vendor/`, `requirements*.txt`(必要ぶんのみ、`tests/` / `doc/` / `logs/` / `build/` / `backups/` は exclude)
- pip install: `requirements.txt`(無ければ vendor 直 import で動くか確認)
- ENV: `PYTHONPATH=/app`、その他 env は Cloud Run Jobs 側で注入(本 ticket では設定しない)
- ENTRYPOINT: `["python3", "-m", "src.tools.run_draft_body_editor_lane"]`
- CMD default: `["--max-posts", "3"]`(Cloud Run Jobs 側で override 可)
- USER: 非 root user 作成(security best practice)

### Cloud Build 要点

- substitution: `_REGION` / `_PROJECT_ID` / `_IMAGE_NAME` / `_TAG`
- step 1: `docker build`
- step 2: `docker push` to Artifact Registry(`asia-northeast1-docker.pkg.dev/<project>/<repo>/draft-body-editor:<tag>`)
- timeout: 600s
- machine_type: `e2-standard-2`(default で十分)

### 動作確認(Phase 1a 完了条件)

1. `docker build -f Dockerfile.draft_body_editor -t draft-body-editor:local .` が成功
2. `docker run --rm draft-body-editor:local --max-posts 0` が `usage` または `--max-posts must be >= 1` 系の expected エラーで終了(env 注入なしでも import / argparse 通る)
3. `gcloud builds submit --config cloudbuild_draft_body_editor.yaml` が成功(Artifact Registry に image push 確認)
4. 既存 WSL cron 042 行 / src / tests / .env / crontab に変更なし

### 不可触

- WSL crontab(042 / PUB-004-C / 095 / gemini_audit 全行)
- src / tests / requirements*.txt(本 ticket では Dockerfile + cloudbuild yaml のみ追加)
- .env / secrets
- 既存 GCP Cloud Run services(giants-*)
- 既存 Cloud Scheduler jobs
- baseballwordpress repo
- Codex Desktop automation
- WordPress / X / Cloud Run env / scheduler / RUN_DRAFT_ONLY

### Hard constraints

- `git add -A` 禁止、stage は `Dockerfile.draft_body_editor` + `cloudbuild_draft_body_editor.yaml` + `doc/active/155-1a-deployment-notes.md`(+ 必要なら `.dockerignore`)だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 一切触らない
- `git push` 禁止(commit までで止める、Claude が push)
- `gcloud builds submit` の **実行は Codex の作業範囲外**(本 ticket は Dockerfile + yaml 作成と local docker build verify まで)
- 実 deploy / scheduler 設定 / secret 設定は 1b 以降の別 ticket で fire
- pytest baseline 1338 維持(本 ticket は code 触らないので影響しない見込、verify 必須)

### Tests

- 本 ticket は tests/ に touch しない
- ただし `python3 -m pytest --collect-only -q | tail -3` で baseline 1338 を確認(infra 追加で副作用ないこと verify)

### Verify 手順

```bash
cd /home/fwns6/code/wordpressyoshilover
# Dockerfile build verify
docker build -f Dockerfile.draft_body_editor -t draft-body-editor:local . 2>&1 | tail -10
# CLI smoke(env なしでも argparse 通ること)
docker run --rm draft-body-editor:local --help 2>&1 | head -10
# pytest 影響なし verify
python3 -m pytest --collect-only -q 2>&1 | tail -3  # 1338
# Cloud Build 設定 syntax 確認(実行はしない)
gcloud builds submit --config cloudbuild_draft_body_editor.yaml --no-source --dry-run 2>&1 | tail -5  # syntax error なし確認(dry-run flag 無いなら yaml lint で代替)
```

### Commit(stage 明示、push なし)

```bash
git add Dockerfile.draft_body_editor cloudbuild_draft_body_editor.yaml doc/active/155-1a-deployment-notes.md
# .dockerignore 追加なら git add .dockerignore も
git status --short
git commit -m "155-1a: Dockerfile + Cloud Build for draft-body-editor (image build verify pass、deploy は 1b)"
```

`.git/index.lock` で commit 拒否時 → plumbing 3 段(write-tree / commit-tree / update-ref)で fallback。

### 完了報告(必須形式)

```
- changed files: <list>
- pytest collect: 1338(変化なし verify)
- docker build: OK / NG(具体メッセージ)
- docker run --help: stdout 抜粋
- cloudbuild yaml syntax: OK / NG
- commit hash: <hash>
- WSL crontab / src / tests / .env: 全て未変更 verify
- live publish / WP write / push: 全て NO
- remaining risk: <if any>
- open question for Claude: <if any>
```

### stop 条件

- requirements.txt 不在 + vendor だけで import 通らない → 即停止 + 報告(別 ticket で deps 整備)
- Cloud Build syntax error → 修正、再 verify
- pytest baseline 1338 を割る(infra 追加で test 環境壊した)→ 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告

### 完了後の次便

Phase 1b(Cloud Run Job deploy + 手動 trigger smoke)を 156 として起票、Claude が次便 fire 判断。
