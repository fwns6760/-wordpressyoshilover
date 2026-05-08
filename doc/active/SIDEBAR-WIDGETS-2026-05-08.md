# SIDEBAR-WIDGETS-2026-05-08

| field | value |
|---|---|
| ticket_id | SIDEBAR-WIDGETS-2026-05-08 |
| priority | P1(ファン視点 / 来訪頻度直結)|
| status | READY_FOR_IMPL |
| owner | Claude/Codex(WP plugin 側 narrow impl)|
| lane | FRONTEND(WP plugin)|
| created | 2026-05-08 |
| doc_path | doc/active/SIDEBAR-WIDGETS-2026-05-08.md |
| cost | ¥0(既存 data sources、外部 API 増加なし)|
| regression risk | 0(新 widget、既存 plugin 機能に影響なし)|
| 工数 | 6-8h(5 widget 合計)|

## 1. 目的

ファンが yoshilover.com に来た時に **常時見える sidebar** で巨人の現在地を把握できるようにする。
のもとけ式の「sidebar 速報」コンセプトを実装。

## 2. 5 widget 設計

### W1. 直近 5 試合 W-L 帯

```
直近 5 試合
●●○○○  (2 勝 3 敗)
```

- 既存 `_build_recent_games_block`(`src/tools/manual_intake.py`)を WP plugin 側に移植 / 呼び出し
- WP REST で「試合速報」category の直近 5 publish を取得 → score / W-L 抽出
- 工数: 1-2h

### W2. 順位表

```
セ・リーグ
1 巨人  20-12  -
2 阪神  18-14  2.0
3 中日  17-15  3.0
...
```

- 既存 `_build_standings_block` の data source(NPB 公式)を WP plugin 側で利用
- daily 1 回 fetch、option に cache(24h)
- 工数: 2h

### W3. 連勝 / 連敗 streak badge

```
🔥 3 連勝中
```

または

```
😢 2 連敗中
```

- 直近 W-L から計算(W1 と data 共有)
- sidebar 上部に小 badge
- 工数: 1h

### W4. 次戦 widget

```
次戦
2026/5/10(日) 14:00
東京ドーム vs 中日
先発: 山崎伊織 - 高橋宏斗
中継: NHK BS / DAZN
```

- 既存 `_build_next_game_block`(Yahoo schedule)を WP plugin 側で利用
- daily 1 回 fetch
- 工数: 2h

### W5. 1 年前の今日

```
1 年前の今日(2025/5/8)
- 巨人、ヤクルトに 5-2 勝利
- 岡本和真が 10 号本塁打
[詳しく見る]
```

- WP REST query で 1 年前同日の publish 取得
- title + 抜粋 + link
- 工数: 1h

## 3. 実装 scope

### A. WP plugin 拡張

`src/yoshilover-063-frontend.php` に新 widget functions:

- `yoshilover_063_render_recent_games_widget()`
- `yoshilover_063_render_standings_widget()`
- `yoshilover_063_render_streak_badge()`
- `yoshilover_063_render_next_game_widget()`
- `yoshilover_063_render_this_day_in_history_widget()`

各 widget は `wp_register_widget_class` で登録、admin で sidebar に配置可能。

### B. data fetch helper

NPB / Yahoo の data を WP option に cache(24h):
- `yoshilover_063_get_npb_standings()` - NPB 順位
- `yoshilover_063_get_recent_games()` - WP REST query(自前)
- `yoshilover_063_get_next_game()` - Yahoo schedule(別 service 経由 or WP 内取得)
- `yoshilover_063_get_streak()` - W1 から計算
- `yoshilover_063_get_this_day_in_history()` - WP REST 1 年前 query

### C. cache 戦略

- W1, W3, W5: WP REST 自前 query、cache 不要(WP で query 完結)
- W2, W4: 外部 fetch、24h transient cache(NPB 公式 / Yahoo)
- cache の更新は cron(WP-Cron で daily)、手動 trigger も可

### D. styling

inline CSS で sidebar 内に収まる minimal design:
- 色は plugin の orange テーマ準拠
- font-size 12-14px
- mobile 対応(stack)

## 4. 制約 / 不可触

- env / Secret / Scheduler 変更しない
- Cloud Run service 触らない(WP plugin 完結)
- Gemini call なし
- 外部 API call は既存と同じ(NPB / Yahoo / WP REST)、増やさない
- 既存 plugin 機能(245 sidebar / footer-cta / hero / 等)に影響なし

## 5. 成功条件

- [ ] 5 widget が全て WP admin に登録される
- [ ] sidebar に配置 → live で render 確認
- [ ] data fetch が 24h cache で working
- [ ] mobile responsive
- [ ] 既存 plugin 機能 regression なし(php -l + WP admin 動作確認)

## 6. phase 分割

1. **Phase 1**: W1 + W3(直近 5 試合 + streak、WP REST 自前 query で完結)| 2h
2. **Phase 2**: W5(1 年前の今日、WP REST query)| 1h
3. **Phase 3**: W2(順位表、外部 fetch + cache)| 2h
4. **Phase 4**: W4(次戦、外部 fetch + cache)| 2h
5. **Phase 5**: build + WP plugin 再 deploy(別判断、現 v11 → v12)

各 phase 完了で commit + push。Phase 5 deploy は user 判断境界(plugin redeploy)。

## 7. 親 / 関連

- 関連: `doc/active/H3-STRUCTURE-UNIFY-2026-05-08.md`(article 内 H3 統一)
- 関連: `doc/active/DIGEST-DAILY-MORNING-2026-05-08.md`(朝まとめ article)
- 関連: `doc/active/FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08.md`
- plugin: 現行 `yoshilover-063-frontend v0.11.0`(`97394f6` で source sync 済)
