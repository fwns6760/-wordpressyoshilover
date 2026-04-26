# 167 gcp-billing-alert(GCP migration 残リスク #3)

## meta

- number: 167
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / billing / safeguard
- status: **READY**(独立、即 fire 可、156 deploy と並走可)
- priority: P1(GCP 課金暴走防止 = MVP §17 cost 制約)
- lane: A
- created: 2026-04-26
- parent: 155 / 165 残リスク #3

## 背景

GCP 移行後、何らかの bug や rate limit 暴発で **意図せず月額が膨らむ**リスク(例: Cloud Run Job が 5min 周期で error retry 暴走 / Cloud Logging 大量出力 / Cloud Run egress 暴走)。

Gemini Flash 課金は別管理(API 側、user 既に許容済 $5-10/月)。GCP infra 側の暴走を **早期検知 + 自動 alert** したい。

## ゴール

GCP project `baseballsite` に **月額 $10 / $30 / $50 の 3 段 budget alert** を作成し、超過時 fwns6760@gmail.com に mail。

## 仕様

### 経路

```
GCP Billing
    ↓
Cloud Billing Budget(月額予算)
    ↓ (50% / 90% / 100% threshold)
Pub/Sub topic + Email notification
    ↓
fwns6760@gmail.com
```

### Budget 設定(3 段)

| Budget 名 | 金額 | 想定 |
|---|---|---|
| `yoshilover-budget-warn` | **$10/月** | 通常運用上限近辺、early warning |
| `yoshilover-budget-investigate` | **$30/月** | 想定 3 倍、要調査 |
| `yoshilover-budget-emergency` | **$50/月** | 想定 5 倍、緊急停止判断 |

各 budget に threshold 50% / 90% / 100% で計 9 通の alert(同事象重複は GCP 側 dedup)。

### 成果物

- `gcloud billing budgets create` shell script(`scripts/setup_billing_alerts.sh`)
- `doc/active/167-billing-alert-deployment-notes.md`(billing account ID / budget 名 / alert 確認手順)
- 既存 src / tests / .env / WSL crontab / Dockerfile / cloudbuild yaml: 一切変更なし

### 動作確認(end-to-end smoke 不要、設定確認のみ)

```bash
# Budget 確認
gcloud billing budgets list --billing-account=<BILLING_ID> --format="table(displayName,amount.specifiedAmount.units)"
# 3 budget 存在 verify
```

実際の alert 発火は month-end / 課金累計到達時にしか起きない(smoke できない)。**設定が GCP に登録された状態を完了とする**。

## 不可触

- 既存 src / tests / requirements*.txt / .env / secrets / crontab
- baseballwordpress repo
- 既存 GCP services / schedulers
- WordPress / X / Cloud Run env
- 既存 billing account の payment method 変更

## acceptance

1. 3 budget が `gcloud billing budgets list` で確認できる
2. 各 budget に 50/90/100% threshold + email notification 設定済
3. setup script が repo に commit
4. doc に billing account ID(masked)/ budget 名 / 確認手順あり
5. live publish / WP write / push: 全て NO
6. budget 金額 / threshold は本 ticket 仕様通り(自由変更禁止)

## Hard constraints

- billing account ID / 課金額(現状 / 履歴)は **chat / log / commit に絶対残さない**(masked のみ doc 可)
- **並走 task `bkvwmw5wy`(156 042 deploy)が touching する file 触らない**: `doc/active/156-*` / Cloud Run Job `draft-body-editor`
- `git add -A` 禁止、stage は **`scripts/setup_billing_alerts.sh` + `doc/active/167-billing-alert-deployment-notes.md`** だけ
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest 影響なし(code 触らない)
- Gemini API 課金は別管理(本 ticket は GCP infra のみ、Gemini 側 budget は別 ticket)

## Verify

```bash
# Budget 一覧
BILLING_ID=$(gcloud billing accounts list --format="value(name)" --filter="open=true" | head -1 | sed 's|billingAccounts/||')
gcloud billing budgets list --billing-account=$BILLING_ID --format="table(displayName,amount.specifiedAmount.units,thresholdRules.thresholdPercent)" 2>&1 | head -10
# repo 状態 verify
cd /home/fwns6/code/wordpressyoshilover
git status --short
git diff src/ tests/ requirements.txt 2>&1 | head -3  # 空であるべき
```

## Commit

```bash
git add scripts/setup_billing_alerts.sh doc/active/167-billing-alert-deployment-notes.md
git status --short
git commit -m "167: GCP billing alert setup ($10/$30/$50 budget × 50/90/100% threshold, email notification)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: scripts/setup_billing_alerts.sh, doc/active/167-billing-alert-deployment-notes.md
- 3 budget created: yes/no(displayName 列挙)
- threshold rules: 50/90/100% verify
- notification channel: fwns6760@gmail.com verify
- billing account ID: <masked>
- live publish / WP write / push: 全て NO
- commit hash: <hash>
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- billing account access permission なし → 即停止 + 報告(user op で IAM grant 必要)
- existing budget で同名衝突 → suffix 付与 or 停止 + 報告
- gcloud auth fail → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告

## 完了後の次便

168(RSS source health check)起票 + fire 判断。
