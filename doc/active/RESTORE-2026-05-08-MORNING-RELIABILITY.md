# RESTORE 2026-05-08 — 朝メール / 自動公開信頼性改修 (本日 session の復元 ticket)

| field | value |
|---|---|
| ticket_id | RESTORE-2026-05-08-MORNING-RELIABILITY |
| priority | P0(復元情報、session 切れに備える) |
| status | LIVE_DEPLOYED, OBSERVATION_PENDING |
| owner | Claude (実装+deploy 済) → user (受け入れ + 翌朝検証) |
| lane | OPS / RELIABILITY |
| created | 2026-05-08 JST 朝 |
| 検証 | 2026-05-09 04:30-06:30 JST(翌朝の cron 完走で初めて勝敗確定) |

## 1. 背景

2026-05-08 朝 04:30-09:00、yoshilover-fetcher は cron 通り走ったが新規 publish=0、メール=0通。
原因: 8つの skip path + BURST 抑制 + RUN_DRAFT_ONLY hardcode + DISABLE_BURST_SUMMARY_MAIL=1 が重なり構造的に「0 publish 0 mail」になっていた。

## 2. 直したこと(commit / image / env / scheduler)

### code commits (master, push 済)

| commit | 内容 |
|---|---|
| `2076920` | publish-notice scanner を `after` → `modified_after` に切替(手動 flip 取りこぼし fix) |
| `bd35498` | wp_client に source_url body marker dedup fallback 追加 |
| `b432801` | 4 frontier CLI(postgame/broadcast/lineup/player_stats)に `--mode=publish` 追加 |
| `b2b3678` | post_gen_validate **trusted source bypass** 4 site + 06:00 JST heartbeat mail |
| `86a21a6` | `PUBLISH_NOTICE_BURST_THRESHOLD` env override(`-1` で BURST 抑制 OFF) |
| `55ae3c7` | trusted bypass を 4 追加 path(body_contract / social_too_weak / comment_required / pgv_recent)に拡張 |
| `44f4ed9` | rss_fetcher の `status="draft"` ハードコードを `RUN_DRAFT_ONLY` flag 連動に修正 |

### image deploy(本日朝 deploy 済)

| service / job | image tag |
|---|---|
| yoshilover-fetcher (service) | `yoshilover-fetcher:latest-fix`(=44f4ed9 build) |
| publish-notice (job) | `publish-notice:86a21a6-job` |
| manual-intake-service (service) | `manual-intake-service:b432801` |
| broadcast-auto / lineup-auto / postgame-auto (jobs) | `manual-intake-service:b432801` |

### prod env(本日設定済)

**yoshilover-fetcher service**:
- `RUN_DRAFT_ONLY=0`
- `ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS=1`

**publish-notice job**:
- `ENABLE_MORNING_HEARTBEAT_MAIL=1`(06:00 JST に 1通必ず送る)
- `DISABLE_BURST_SUMMARY_MAIL=0`(BURST 時は集約 1通配信)
- `PUBLISH_NOTICE_BURST_THRESHOLD=-1`(BURST 抑制 OFF、全部個別 mail)

### scheduler(本日変更)

| job | before | after | 意図 |
|---|---|---|---|
| publish-notice-trigger | `*/30 * * * *` | `0,30 0-3,6-23 * * *` | 04-06時 mail silence(寝起き直撃回避、user 同意) |
| giants-morning-catchup | `30 5 * * *` | `30 4 * * *` | 朝 04:00 公開記事を 30分以内に拾う(user 同意) |

### scheduler(本日変更したが**戻した**)

- giants-weekday-daytime: `0 6-16` → `0,15,30,45 6-16` に変更後、user 「変更するな」で `0 6-16` に戻し済

## 3. rollback 手順

### 緊急 rollback(全 fix を一気に元に戻す)

```bash
PROJECT=baseballsite REGION=asia-northeast1
# fetcher を昨日 image に戻す
gcloud run services update yoshilover-fetcher --project=$PROJECT --region=$REGION \
  --image=asia-northeast1-docker.pkg.dev/$PROJECT/yoshilover/yoshilover-fetcher:b72a2a8 \
  --remove-env-vars=ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS \
  --update-env-vars=RUN_DRAFT_ONLY=1
# publish-notice を昨日 image に戻す
gcloud run jobs update publish-notice --project=$PROJECT --region=$REGION \
  --image=asia-northeast1-docker.pkg.dev/$PROJECT/yoshilover/publish-notice:c61a894-job \
  --remove-env-vars=ENABLE_MORNING_HEARTBEAT_MAIL,PUBLISH_NOTICE_BURST_THRESHOLD \
  --update-env-vars=DISABLE_BURST_SUMMARY_MAIL=1
# scheduler を元に戻す
gcloud scheduler jobs update http publish-notice-trigger --project=$PROJECT --location=$REGION --schedule="*/30 * * * *"
gcloud scheduler jobs update http giants-morning-catchup --project=$PROJECT --location=$REGION --schedule="30 5 * * *"
```

### 部分 rollback(個別)

| 戻したい挙動 | 操作 |
|---|---|
| BURST 個別 mail を抑制したい | `gcloud run jobs update publish-notice --update-env-vars=PUBLISH_NOTICE_BURST_THRESHOLD=10` |
| heartbeat 止めたい | `gcloud run jobs update publish-notice --update-env-vars=ENABLE_MORNING_HEARTBEAT_MAIL=0` |
| trusted bypass 止めたい(gate 厳格に戻す) | `gcloud run services update yoshilover-fetcher --update-env-vars=ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS=0` |
| 04-06時 mail 受信したい(silence 解除) | scheduler を `*/30 * * * *` に戻す |

## 4. 翌朝(2026-05-09)の検証 checklist

- [ ] 06:00 JST に **heartbeat 1通**「【朝サマリー】5月9日 yoshilover 稼働中」届く
- [ ] 04:30-06:00 fetcher fire(`giants-morning-catchup` + `giants-weekday-daytime`)で publish が出る
- [ ] 06:00 publish-notice fire で per-post mail が複数届く
- [ ] (試合日なら)11:30 broadcast-auto で 5/9 試合中継 1本 publish
- [ ] heartbeat 以外 0通だった場合 → trusted bypass まだ未網羅 path あり、再調査要

## 5. 既知の未解決事項

1. **重複記事 live 残存**: 山野5勝 4本(64878/64879/64882/64883) / 5/6試合結果 2本(64983/64985) / 三塚二軍 2本(64861/64945)。user 判断で削除可。
2. **若手 17人 eyecatch 未存在**: 田和廉/平山功太/三塚琉生/小濱佑斗/田中瑛斗/石塚裕惺/竹丸和幸/泉口友汰/宮原駿介/松本剛/森田駿哉/ウィットリー他。WP media に upload で改善。
3. **trusted bypass の網羅性未確認**: 今朝(5/8)の bypass deploy 後 publish 3本確認できたが、5/9 朝の本格 catchup で追加 skip path 出る可能性。
4. **新若手選手 cache 固着**: `config/player_eyecatch_map.json` に「画像なし」キャッシュされた選手は再 lookup 走らない。upload 後 cache 行削除必要。

## 6. 参照

- 全 commit: `git log --oneline --since="2026-05-07 22:00"`
- 全 env: `gcloud run services describe yoshilover-fetcher` / `gcloud run jobs describe publish-notice`
- Scheduler: `gcloud scheduler jobs list --location=asia-northeast1`
