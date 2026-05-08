# 5/9 朝検証 verification packet (2026-05-08 PM 作成)

**目的**: 5/9 朝 06:00-07:00 で本日 deploy 全部の効果を実機検証 + 失敗時 rollback 即実行する手順 packet。Claude 朝 session で逐次実行、user は Gmail 受信確認のみ。

---

## 0. 本日(5/8 PM)deploy したもの一覧(rollback target 識別用)

| 階層 | 内容 | revision/image | rollback 単位 |
|---|---|---|---|
| **fetcher service** | E2 + hochi/daily scraper + YouTube scraper + X 4 account | yoshilover-fetcher-00255-gs6 / image:7a85167 | revision rollback to 00251 系 |
| **guarded-publish job** | review-only title prefix filter | guarded-publish:2487abf | image rollback |
| **publish-notice job** | BURST_THRESHOLD=50 / heartbeat 3 段 / 朝 fix 系 | (前回 deploy のまま) | env single-revert |
| **fetcher env** | TRUSTED_BYPASS_FULL=0 / REVIEW_DRAFT=1 / STALE_RSS_TRUSTED_BYPASS=1 / WINDOW_TRUSTED_HOURS=48 / TAG_PAGE_SCRAPER=1 | (各単独 env で revert 可) | env single-revert |

---

## 1. 5/9 朝検証 timeline

| JST | event | 期待 |
|---|---|---|
| **04:30** | giants-morning-catchup → fetcher /run(初実機) | drafts_created > 0、scraper 動作 |
| **06:00** | publish-notice fire(heartbeat #1) | heartbeat mail 1 通必着 |
| **06:00** | publish-notice fire(per-post)| 04:30 catchup の publish 分 mail |
| **06:30** | publish-notice fire(heartbeat #2 retry) | heartbeat 取りこぼし保険 |
| **07:00** | publish-notice fire(heartbeat #3 retry)| 同上 |
| **07:00 以降** | user /clear で新 session | Claude が観察 commands 実行、結果報告 |

---

## 2. user が確認すること(06:00-07:00 Gmail で)

| | 期待 | 失敗 signal |
|---|---|---|
| heartbeat mail | subject `【朝サマリー】5月9日 yoshilover 稼働中` 1 通 | 0 通 → publish-notice 死亡 |
| per-post mail | subject `【公開済｜...】` or `【要確認｜...】` 5-10 通 | 0 通 → fetcher 死亡 / publish path 死亡 |
| 【要review｜post_gen_validate】publish | **0 件**(WP UI で確認) | 1 件以上あれば guarded-publish filter bypass = 致命的 |
| Gmail spam fold | 別途 spam 判定されてないか check | spam 入りなら通知到達せず |

---

## 3. Claude 朝 session 観察 commands(07:00 以降 /clear 後)

### 3.1 scheduler state(全 ENABLED 必須)

```bash
gcloud scheduler jobs list --location=asia-northeast1 --filter="state=PAUSED" --format="value(ID)"
```
→ **空(全 ENABLED) が期待値**。PAUSED 出たら問題、特に publish-notice-trigger / giants-morning-catchup / guarded-publish-trigger。

### 3.2 04:30 morning-catchup の実機効果

```bash
# 04:30 fetcher fire の flow_summary
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND textPayload:"rss_fetcher_run_summary" AND timestamp>="2026-05-08T19:25:00Z" AND timestamp<="2026-05-08T19:40:00Z"' --limit=2 --format="value(timestamp,textPayload)"
```
**期待値**:
- drafts_created > 5(catchup なので多め)
- skip_filter < 100
- error_count = 0

**失敗 signal**:
- drafts_created = 0 → fetcher 死亡 = 5/8 朝と同じ事故 → 即 rollback

### 3.3 06:00 heartbeat 確認

```bash
# 06:00 / 06:30 / 07:00 の publish-notice fire
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND textPayload:"heartbeat" AND timestamp>="2026-05-08T21:00:00Z"' --limit=10 --format="value(timestamp,textPayload)"
```
**期待値**: heartbeat 3 段 retry のいずれか 1 つ以上で `heartbeat_mail_sent` event 出現。

**失敗 signal**: 3 段全 fire で heartbeat event 0 件 → publish-notice job 死亡。

### 3.4 per-post mail 配信率

```bash
# 5/9 06:00-07:00 で publish された post 数
cd /home/fwns6/code/wordpressyoshilover && python3 -c "
import os, requests, base64
from dotenv import load_dotenv
load_dotenv('.env')
url = os.environ.get('WP_URL','').rstrip('/')
auth = base64.b64encode(f\"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}\".encode()).decode()
hdr = {'Authorization': f'Basic {auth}'}
r = requests.get(f'{url}/wp-json/wp/v2/posts?status=publish&after=2026-05-08T19:30:00&before=2026-05-08T22:00:00&per_page=30&_fields=id,date,title', headers=hdr, timeout=20)
print('publish 5/9 04:30-07:00 JST count:', len(r.json()))
"
```
- publish-notice の per-post mail 件数(`status=sent`)と比較
- 配信率 = sent / publish_count
- 期待: 80%+(私の earlier 「50-70%」は controllable factor 改善前の見積もり、heartbeat 3 段 retry 効くなら 80%+ 期待可能)

### 3.5 「【要review｜post_gen_validate】」prefix の publish 化チェック

```bash
cd /home/fwns6/code/wordpressyoshilover && python3 -c "
import os, requests, base64
from dotenv import load_dotenv
load_dotenv('.env')
url = os.environ.get('WP_URL','').rstrip('/')
auth = base64.b64encode(f\"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}\".encode()).decode()
hdr = {'Authorization': f'Basic {auth}'}
r = requests.get(f'{url}/wp-json/wp/v2/posts?status=publish&search=%E8%A6%81review&per_page=20&_fields=id,date,title', headers=hdr, timeout=20)
print('publish with [要review] in title:', len(r.json()))
for p in r.json():
    print(f\"  {p['id']} | {p['date']} | {p['title']['rendered'][:80]}\")
"
```
**期待値**: 65046 1 件のみ(本日 incident、user trash 推奨)。新規追加 0 件。

**失敗 signal**: 65046 以外に「【要review】」publish 化 → guarded-publish filter bypass = 致命的、即 image rollback。

### 3.6 D bypass full event 0 件確認

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-05-08T19:25:00Z" AND textPayload:"full_axes"' --limit=5
```
**期待**: 0 件(D 無効化されてる証)。

### 3.7 review draft 蓄積数

```bash
cd /home/fwns6/code/wordpressyoshilover && python3 -c "
import os, requests, base64
from dotenv import load_dotenv
load_dotenv('.env')
url = os.environ.get('WP_URL','').rstrip('/')
auth = base64.b64encode(f\"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}\".encode()).decode()
hdr = {'Authorization': f'Basic {auth}'}
r = requests.get(f'{url}/wp-json/wp/v2/posts?status=draft&search=%E8%A6%81review&per_page=100&_fields=id', headers=hdr, timeout=20)
print('draft with [要review] count:', len(r.json()))
"
```
**期待**: 5/8 PM 時点 5 件 + 04:30 catchup 分 +10-30 件 = 計 15-35 件 draft 蓄積。

50 件超えたら P2-1 auto-archive job 実装 priority up。

### 3.8 scraper 動作確認

```bash
# 04:30 fire で hochi/daily/YouTube それぞれ取得済か
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND textPayload:"取得中:" AND timestamp>="2026-05-08T19:25:00Z" AND timestamp<="2026-05-08T19:40:00Z"' --limit=20 --format="value(textPayload)"
```
**期待**:
- 「取得中: スポーツ報知 巨人 tag」(hochi)
- 「取得中: デイリー 巨人 index」(daily)
- 「取得中: 読売ジャイアンツYouTube公式」(YouTube 1)
- 各 X / RSS source も全部出る

**失敗 signal**: hochi / daily / YouTube が出ない → scraper 死亡。env `ENABLE_TAG_PAGE_SCRAPER=0` で revert。

---

## 4. 失敗パターン → rollback 順序(段階的)

### Tier 1 失敗(致命): heartbeat 3 段全 fail / drafts_created 0 / 大量 致命的 publish

```bash
# Step 1: scheduler 即停止(被害拡大防止)
gcloud scheduler jobs pause publish-notice-trigger --location=asia-northeast1
gcloud scheduler jobs pause giants-morning-catchup --location=asia-northeast1
gcloud scheduler jobs pause giants-weekday-daytime --location=asia-northeast1
gcloud scheduler jobs pause guarded-publish-trigger --location=asia-northeast1

# Step 2: fetcher revision rollback (前 stable = 00251 系)
gcloud run services update-traffic yoshilover-fetcher --region=asia-northeast1 --to-revisions=yoshilover-fetcher-00251-29x=100

# Step 3: guarded-publish image rollback
# (image:2487abf → 旧 image)
gcloud run jobs describe guarded-publish --region=asia-northeast1 --format="value(template.template.spec.containers[0].image)"
# 旧 image 確認後 update

# Step 4: env all revert
gcloud run services update yoshilover-fetcher --region=asia-northeast1 \
  --update-env-vars="ENABLE_TAG_PAGE_SCRAPER=0,ENABLE_POST_GEN_VALIDATE_REVIEW_DRAFT=0,ENABLE_STALE_RSS_TRUSTED_BYPASS=0"

# Step 5: scheduler 再 ENABLE
gcloud scheduler jobs resume publish-notice-trigger --location=asia-northeast1
gcloud scheduler jobs resume giants-morning-catchup --location=asia-northeast1
gcloud scheduler jobs resume giants-weekday-daytime --location=asia-northeast1
gcloud scheduler jobs resume guarded-publish-trigger --location=asia-northeast1
```

### Tier 2 失敗(中): per-post mail 50% 未満 / scraper 部分死亡

env 単独 revert で対処:
```bash
# 例: hochi scraper だけ無効化
gcloud run services update yoshilover-fetcher --region=asia-northeast1 \
  --update-env-vars="ENABLE_TAG_PAGE_SCRAPER=0"
```

### Tier 3 失敗(軽): review draft 多すぎ(50 件超)

env で E flag 一旦 OFF:
```bash
gcloud run services update yoshilover-fetcher --region=asia-northeast1 \
  --update-env-vars="ENABLE_POST_GEN_VALIDATE_REVIEW_DRAFT=0"
```

---

## 5. 5/9 朝検証 GO/HOLD/ROLLBACK 判定

| 判定 | 条件 |
|---|---|
| **GO** | heartbeat 1 通必着 + per-post mail 5+ + 致命的 publish 0 + scraper 全動作 |
| **HOLD** | heartbeat OK だが per-post mail 50% 未満 → 観察 1 日延長、Tier 3 rollback で対処 |
| **ROLLBACK** | heartbeat 0 通 / drafts_created 0 / 「【要review】」publish 1 件以上 / scraper 死亡 → Tier 1 rollback 即実行 |

---

## 6. 既知の不確定要素(私が事前に表明した uncertainty)

| 項目 | uncertainty | 5/9 朝で確定する |
|---|---|---|
| heartbeat 配信確率 | 99%+ 想定(3 段 retry) | yes |
| per-post mail 配信率 | 50-70% 想定(私 honest 表明) | yes、本番で初測定 |
| hochi/daily/YouTube scraper の rate limit / IP block | 未検証 | yes |
| review draft 蓄積量 | 1 日 20-40 件想定 | yes、初実機 |
| BURST_THRESHOLD=50 の効果 | 累積 50 超で集約 mail | 17-21 game time で測定可能 |
| F stale 48h 副作用(古記事 publish) | 観察必要 | yes |
| 65046 同様 anomaly | filter で防止のはず | filter deploy 検証 |

---

## 7. 残課題(5/9 朝検証 GO 後の P2)

| # | 内容 | priority |
|---|---|---|
| P2-1 | review draft 7 日経過 auto-archive job | 蓄積 50 超で P0 化 |
| P2-2 | sponichi / sanspo 代替 source 探索 | 流量改善余地 30-40% |
| P2-3 | YouTube channel 追加(残 OB / 川﨑 / 清原 等) | 余地大 |
| P2-4 | YouTube Data API v3 切替検討 | scraper DOM 依存解消 |
| P2-5 | D code scope 限定実装(env=0 不要に) | 設計堅牢化 |
| P2-6 | sponichi/sanspo ChannelRSS / Yahoo News partner 経路探索 | 流量改善 |
| P2-7 | E2 critical axes filter の境界精緻化 | 軽微/致命 line 観察 |

---

## 8. user / Claude / 自動 の責任分担

| who | 何を |
|---|---|
| **user** | Gmail 受信確認(06:00-07:00)、65046 trash 判断、5/9 朝検証 GO/HOLD/ROLLBACK 最終判断 |
| **Claude(朝 session)** | observation commands 実行、結果集計、判定提案、rollback 実行(user OK 後) |
| **自動(scheduler / Cloud Run)** | catchup fire / heartbeat / per-post mail 全て自律稼働 |
