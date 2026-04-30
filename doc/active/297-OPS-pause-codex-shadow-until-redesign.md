# 297-OPS-pause-codex-shadow-until-redesign

| field | value |
|---|---|
| ticket_id | 297-OPS-pause-codex-shadow-until-redesign |
| priority | P1(現状リスク即時遮断、defensive) |
| status | READY_FOR_EXEC(user 明示 GO 済、Codex便で execute) |
| owner | Claude(管理) → Codex(execute、Claude write gcloud 禁止のため) |
| lane | OPS |
| ready_for | Codex便 fire 即時 |
| blocked_by | (なし、独立) |
| doc_path | doc/active/297-OPS-pause-codex-shadow-until-redesign.md |
| created | 2026-04-30 |

## 1. 結論

**codex-shadow-trigger を一時 PAUSE**(廃止ではない)。
296-OBSERVE で **read-only 監査 Bot として再設計** するまで、ブラックボックス稼働を止める。

## 2. 背景

296-OBSERVE 起票で確認された 3 軸リスク:

| 軸 | 現状 |
|---|---|
| デグレ | WP write 権限 ON / log 0 / 観察不能で本番事故源となり得る |
| コスト | Gemini API key bound、call 数不可視、*/5 × 24h 常時稼働 |
| 不可視 | application log 0 / GCS output 0 / src 不在 = 動作証拠 0 |

設置目的(記事修正候補 Bot)は良いが、**現状は debt = 設置目的に逆行**。
redesign 完了まで PAUSE が安全。

## 3. 目的

- 本番で何をしているか見えない処理を止める
- WP 勝手書き換えリスク遮断
- Gemini call 不可視リスク遮断
- 296-OBSERVE で役割再定義するまで安全側に倒す
- 後で再開できるように、理由 + 解除条件 + 手順を明記

## 4. GO 範囲(本 ticket impl scope)

1. `codex-shadow-trigger` の **PAUSE 実行**
2. PAUSE 前 scheduler status 記録
3. PAUSE 後 scheduler status 記録
4. 他 scheduler が変更されていないこと verify
5. rollback / re-enable 手順記録

## 5. 実行コマンド

### PAUSE
```bash
CLOUDSDK_CONFIG=/tmp/gcloud-codex gcloud scheduler jobs pause codex-shadow-trigger \
  --location=asia-northeast1 --project=baseballsite
```

### 再開(296-OBSERVE 完遂 + user 明示 GO 後)
```bash
CLOUDSDK_CONFIG=/tmp/gcloud-codex gcloud scheduler jobs resume codex-shadow-trigger \
  --location=asia-northeast1 --project=baseballsite
```

## 6. 絶対にやらないこと(本 ticket scope 外)

| やらない | 理由 |
|---|---|
| Cloud Run job 削除 | 復活不能、redesign 後に再利用 |
| image 削除 | 同上 |
| Secret 削除(`codex-auth-json`) | 同上、redesign で要再評価 |
| WP credential 削除 | 他 service が依存 |
| Gemini API key 削除 | fetcher 等が依存 |
| 他 scheduler 変更(giants-*, guarded-publish-trigger, publish-notice-trigger 等) | publish/mail 経路への影響 risk |
| publish-notice 変更 | mail 経路 |
| guarded-publish 変更 | publish 経路 |
| fetcher 変更 | source 取得経路 |
| SEO/noindex/canonical/301 変更 | 公開影響 |
| Team Shiny From 変更 | mail 経路 |
| X 自動投稿関連変更 | publish 経路 |

## 7. HOLD 解除条件(再開判断)

296-OBSERVE で以下 **全部** 完了 + user 明示 GO 後:

1. **source code が repo 管理されている**(現状 src 不在)
2. **stdout / log で何を見たか分かる**(post_id / detected_issue / repair_type / gemini_call_made を必須出力)
3. **GCS に `repair_candidates.jsonl` が出る**(GCS write fixture pass)
4. **WP write 権限 OFF**(`CODEX_WP_WRITE_ALLOWED=false`)
5. **Gemini call が OFF or cap 付きで可視化**(初期 binding 解除)
6. **手動 trigger or 低頻度**(*/5 復活禁止)
7. **Claude が出力を確認できる**(GCS pull で読める)
8. **rollback / disable が 1 コマンドで可能**
9. **デグレ試験 pass**(296-OBSERVE 9 軸全部)

## 8. 受け入れ条件(本 ticket 完了)

- [ ] `codex-shadow-trigger` が **PAUSED** になる
- [ ] 他 scheduler 変更なし(`giants-*` / `guarded-publish-trigger` / `publish-notice-trigger` / 等の state 不変 verify)
- [ ] publish/mail 導線に影響なし(本 ticket 完了直後 5min 以内に publish-notice / guarded-publish trigger 自然発火確認)
- [ ] P0 公開復旧に影響なし(289 post_gen_validate 通知導線維持)
- [ ] コスト悪化なし(逆に */5 × 24h 削減)
- [ ] 再開手順が doc に残る(本 ticket section 5)

## 9. 完了報告(Codex Final report 必須項目)

- ticket path: `doc/active/297-OPS-pause-codex-shadow-until-redesign.md`
- pause 前 status: `gcloud scheduler jobs describe codex-shadow-trigger ...` 結果
- pause 後 status: 同上
- 実行コマンド: section 5 通り
- 再開コマンド: section 5 通り
- 影響範囲:
  - codex-shadow-trigger 単独 state 変更
  - 他 scheduler 不変(全 scheduler list で diff 0 確認)
  - publish/mail 経路不変
- HOLD 解除条件: section 7

## 10. rollback 条件

PAUSE 自体に問題が出た場合(=他経路が codex-shadow に依存していた場合の予期せぬ影響):
```bash
CLOUDSDK_CONFIG=/tmp/gcloud-codex gcloud scheduler jobs resume codex-shadow-trigger \
  --location=asia-northeast1 --project=baseballsite
```
1 コマンドで即時 RESUME 可、可逆 100%。

## 11. 不変方針(継承)

- ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- Team Shiny From / SEO / X / Scheduler(他)/ 既存 publish-mail 導線 全部不変
- 新 subtype 追加なし
- 296-OBSERVE redesign 完了まで再開禁止(本 ticket HOLD 解除条件 9 項目)

## 12. 関連 ticket

- 296-OBSERVE-codex-shadow-role-redesign(本 PAUSE の理由 + 再開条件)
- 294-PROCESS-release-composition-gate(再開時 deploy で release composition verify)
