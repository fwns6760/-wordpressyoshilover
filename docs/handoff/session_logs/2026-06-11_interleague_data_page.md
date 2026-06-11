# 2026-06-11 /data/interleague 交流戦成績一覧ページ新設

- 13:31 JST | commit | fd545112 | feat: /data/interleague (config+scraper+template+daily_refresh+tests) | push 済
- 13:33 JST | build | e666fb0c | rotation-updater:latest-job 再ビルド + jobs update | next: execute
- 13:35 JST | execute | rotation-updater-57rx5 | interleague created page_id=90404 publish 29711 bytes、既存3ページも正常更新 | next: live verify
- 13:36 JST | verify | https://yoshilover.com/data/interleague | title/開催中12球団順位表/暫定4位/優勝行/マトリクス/MVP 全 OK

## データ検証メモ (証拠)

- 履歴 2005-2025 は my-favorite-giants inter.htm 由来。順位・優勝チーム全20年を Wikipedia セ・パ交流戦と照合し全一致
- 補正 3 点: 2025引分 4→1 (NPB公式 std_c 2025 = 6勝11敗1分、チーム別内訳とも整合) / 2013 GB +1.5→+2.0、2016 +5.0→+4.5 (優勝チーム勝敗から再計算)
- ベンチマークの通算行は 2024 止まり (426試合)。当ページは 2025 込み 444 + 2026 live で自動加算
- 当年分は NPB公式 std_c/std_p の交流戦表 (2つ目 table) を毎朝 scrape (rotation-updater 07:30 JST)

## TODO (期限つき)

- **2026 交流戦終了後 (閉幕 2026-06-21 頃以降)**: 2026 確定値 (rank/W/L/D/avg/hr/sb/era/home/visitor/vs) を config/giants_interleague.json に final:true で焼き込む。焼き込まないと 2027 開幕後 (npb.jp の 2027 ページに 2026 交流戦表が無くなった時点) に 2026 年行がページから消える。avg/era 等は次回更新時にベンチマーク inter.htm の 2026 行から取得可

## 追記: 変更なしスキップ (user 指摘「交流戦以外は動かないデータ」対応)

- 13:48 JST | commit | d7f77475 | daily refresh _upsert に raw content 比較スキップ追加 (test 3本) | push 済 (並走レーン rebase 込み)
- 13:52 JST | execute | rotation-updater-2tqnz | 4ページ全て unchanged; skip 確認 (revision 肥大・無駄 write 解消) | 完了
