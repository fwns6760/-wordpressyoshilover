# 2026-06-11 試合後データ鮮度チェーン (scheduler 変更)

user 観察「データを知りたいのは試合後。最新化されたデータでファンが盛り上がるポストにインプがある。スケジュール変わるよね」

## 診断 (read-only)

- insight-nightly (ETL+データ候補生成、所要 ~2分) の最終便が **21:00** で、試合終了 (20:45〜22:30) 後の確定データが翌朝 05:00 まで入らなかった
- mail flush 側は game-1/game-2 で 21-22時台 15分間隔が既存 → **22時台の便は 21:00 時点の試合中 stale データを配っていた**
- 欠けていたのは ETL 側のみ

## 変更 (2026-06-11 12:40 JST)

- 12:40 JST | create | `data-insight-postgame-2155` (55 21 * * *) → insight-nightly | 試合終了直後 ETL | done
- 12:40 JST | create | `data-insight-postgame-2240` (40 22 * * *) → insight-nightly | 延長/長試合 cover | done
- 12:41 JST | update | `x-post-mail-flush` cron `0 7,9,11,13,15,16,17,22` → `5 7,9,11,13,15,16,17,22,23` | 23時便追加 + :05 シフトで同時刻 ETL (15/17時) との race 解消 | done

## チェーン完成形

試合終了 → ETL 21:55 (done ~21:57) → flush 22:05/22:15/22:30/22:45 → ETL 22:40 (done ~22:42) → flush 22:45/23:05

- PRIME_HOURS 窓 (JST17-23) 内なので X 文案は 3.5-flash 優先のまま
- 鮮度ゲート (f7c13c01) が stale 候補を弾くため、postgame 確定データ便と整合
- コスト: +2 executions/日 × ~2分 (Cloud Run job-minutes、無料枠内)、新規 Gemini path なし

## 残課題 / 観察

- 翌日以降、22時台 mail の候補が「当日確定データ」になっているか実物 verify
- デーゲーム (土日 13/14時開始、~17時終了) は 17:00 ETL + 17:05 flush で概ね cover、不足が見えたら 16:30 ETL 追加を検討
- rollback: 新規 2 trigger delete + flush cron 戻しで即時復元可
