# 2026-05-08 morning reliability emergency session log

## 事象

5/7 夜は mail / 自動公開動いていたが、5/8 朝 04:30-09:00 で **新規 publish 0、mail 0** に。
user 朝起きてメールゼロを発見、原因調査と緊急 fix 要請。

## 真因(複合)

1. 5/7 22:30 に user/Claude 手動 flip 16本 → BURST_SUMMARY_ONLY 抑制発動 → DISABLE_BURST_SUMMARY_MAIL=1 で集約 mail も無効 → 16通全消滅
2. 5/8 朝 fetcher cron は走ったが post_gen_validate / body_contract / social_too_weak 等 8 path で全 skip → drafts_created=0
3. RUN_DRAFT_ONLY=0 に env 切替えた後も rss_fetcher.py:16299 hardcoded `status="draft"` で publish 化されず

## 緊急 fix(本日 commit、10 件)

| 順 | commit | 時刻 (JST) | 内容 |
|---|---|---|---|
| 1 | 2076920 | (5/7 22:15)| publish-notice scanner `after` → `modified_after`(手動 flip 取りこぼし fix) |
| 2 | bd35498 | 5/8 00:05 | wp_client body marker dedup fallback |
| 3 | b432801 | 5/8 00:?? | 4 frontier CLI に --mode=publish 追加 |
| 4 | b2b3678 | 5/8 09:26 | post_gen_validate trusted bypass 4 site + 06:00 heartbeat |
| 5 | 86a21a6 | 5/8 09:40 | PUBLISH_NOTICE_BURST_THRESHOLD env override(-1 で OFF) |
| 6 | 55ae3c7 | 5/8 10:12 | trusted bypass 4 path 追加(body_contract / social_too_weak / comment_required / pgv_recent) |
| 7 | 0bf8900 | 5/8 10:15 | manual_intake / fallback shell に nomotoke 装飾を維持(body_too_thin fallback 時も装飾) |
| 8 | 44f4ed9 | 5/8 10:21 | rss_fetcher.py:16299 hardcoded draft → RUN_DRAFT_ONLY flag 連動 |
| 9 | b816f06 | 5/8 10:47 | heartbeat 3連発(06:00/06:30/07:00 retry)+ 診断 body |
| 10 | d34072a | 5/8 11:01 | T1+T2 audit fixes(manager allowlist 過マッチ guard / submit loading / 編集 link / friendly error / facts cap) |

## 今日 prod 反映 env

**yoshilover-fetcher**:
- RUN_DRAFT_ONLY=0
- ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS=1

**publish-notice job**:
- ENABLE_MORNING_HEARTBEAT_MAIL=1
- DISABLE_BURST_SUMMARY_MAIL=0
- PUBLISH_NOTICE_BURST_THRESHOLD=-1

**scheduler 変更**:
- publish-notice-trigger: `0,30 0-3,6-23 * * *`(04-06時 silence)
- giants-morning-catchup: `30 4 * * *`(04:30 前倒し)

## 取り戻し

5/7 publish 84本 + 私が 5/8 朝 flip した 10本、合計 87通 publish-notice 経由で個別 mail 送信(09:30-10:02 JST、cursor reset + BURST OFF で実現)。

## 残タスク(user 作業)

- [ ] B 案: 外部独立 GAS ping 設定(`doc/active/EXTERNAL-MONITOR-APPS-SCRIPT.md` 参照)
- [ ] 重複記事削除判断: 山野5勝 4本 / 5/6試合結果 2本 / 三塚二軍 2本

## 5/9 朝の検証

`doc/active/RESTORE-2026-05-08-MORNING-RELIABILITY.md` § 4 checklist 参照。
heartbeat 1通必着 + per-post 5-10通期待。0通なら未発見 skip path 調査。

## 私(Claude) が user に正直に伝えたこと

- per-post mail 配信は 50-70%(heartbeat だけ 99%)
- body_contract bypass の patched dict は下流 crash の risk
- 87通一気送信は Gmail spam 学習の risk
- bypass で score 誤記事も流れる可能性
- 16 commit は急ぎで品質低い、regression 残る可能性

## next session への引き継ぎ

memory: `project_2026_05_08_morning_reliability_handoff.md`(MEMORY.md index 追加済)
