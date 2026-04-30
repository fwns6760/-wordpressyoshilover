---
session_date: 2026-04-30
topic: PM session 短縮サマリ(次セッション 1 分で読める)
purpose: 長い session log の代わり、起動直後の認知負荷低減
---

# 2026-04-30 PM session 短縮サマリ

## 5 行サマリ

1. **P0 publish/mail 復旧状況**: silent skip 真因(post_gen_validate 22 件/trigger silent)を 289-OBSERVE で見える化、本日 16:55 以降 `【要review｜post_gen_validate】` mail 配信開始(cap=10/run、dedup 動作、Team Shiny From 維持)、既存 publish/review/hold 通知導線も維持(17:10 sent=1 post_id=64104 確認)
2. **289-OBSERVE live 状態**: fetcher `:4be818d` rev `00175-c8c` + publish-notice `:4be818d`、`ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` 両方、24h 安定観察中
3. **290-QA push 済 / 未 deploy**: commit `c14e269`、GH Actions success、A/B 7 候補 rescue は **flag OFF default で本番挙動 0**(deploy + `ENABLE_WEAK_TITLE_RESCUE=1` で初めて publish 化、明朝 user 判断)
4. **次の active 最大 3 件**: (a) **293-COST preflight skip visible notification 起票 + Codex fire**(282-COST flag ON の鍵)/ (b) **290-QA deploy + flag ON**(rescue 効果反映)/ (c) **24h 観察まとめ**(289 / 281 farm_result <24h positive case / 277 効果 / codex-shadow PAUSE 後の publish-mail 不変 verify)
5. **HOLD 中の重要 ticket**: 282-COST flag ON(293 待ち)/ 296-OBSERVE codex-shadow redesign(297-OPS PAUSE 後)/ 295-QA subtype 誤分類 fix / 264-QA cleanup mutation / 288 source coverage / 278/279/280 / 284-287 MKT / 229-COST C / Scheduler 頻度変更 / live_update / SEO / X / Team Shiny From 全部

## 起動時の必読 sequence

1. 本 file 読了(1 分)
2. `docs/handoff/session_logs/2026-04-30_next_action_queue.md` 読了(具体 queue + 解除条件)
3. 不足あれば `docs/handoff/session_logs/2026-04-30_p0_publish_recovery_observation.md` 参照(本日 incident 詳細)
4. read-only 観察(`git fetch` / `gh run list` / `gcloud run services describe` / `gcloud scheduler jobs describe`)
5. 5 点要約(active / observe / hold / done / 次の 1 手)を user に提示

## 本日 done(参考)

276-QA / 277-QA / 281-QA / 282-COST(flag OFF deploy)/ 283-MKT / 289-OBSERVE / 290-QA push / 297-OPS PAUSE

## 不変方針(常時継承)

- `ENABLE_LIVE_UPDATE_ARTICLES=0` 維持
- Team Shiny From `y.sebata@shiny-lab.org` 維持
- SEO/noindex/canonical/301 不変
- X 自動投稿 OFF
- 新 subtype 追加なし
- duplicate guard 全解除なし
- Scheduler 頻度変更なし(autonomous 進めない)

## 緊急時 quick reference

- 289 通知爆発時:`gcloud run services update yoshilover-fetcher ... --remove-env-vars=ENABLE_POST_GEN_VALIDATE_NOTIFICATION` + `gcloud run jobs update publish-notice ... --remove-env-vars=ENABLE_POST_GEN_VALIDATE_NOTIFICATION`
- codex-shadow 再開:`gcloud scheduler jobs resume codex-shadow-trigger --location=asia-northeast1 --project=baseballsite`
- publish 停止検知時:guarded-publish image revert(前 image `:a175f24`)
