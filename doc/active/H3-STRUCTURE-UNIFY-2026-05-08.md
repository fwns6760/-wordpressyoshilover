# H3-STRUCTURE-UNIFY-2026-05-08

| field | value |
|---|---|
| ticket_id | H3-STRUCTURE-UNIFY-2026-05-08 |
| priority | P1(structure 改善、5/8 PM 監査で発見)|
| status | READY_FOR_IMPL |
| owner | Claude/Codex(narrow impl)|
| lane | QA / FRONTEND |
| created | 2026-05-08 |
| doc_path | doc/active/H3-STRUCTURE-UNIFY-2026-05-08.md |
| cost | ¥0(prompt + renderer + post-process filter のみ)|
| regression risk | 中-低(既存 H3 を変えるので live HTML が変わるが、統一方向のみ)|
| 工数 | 4-6h |

## 1. 背景

2026-05-08 PM の live post 監査(100 件 × 8 category)で、H3 が完全にバラバラ + 重複命名が判明:

- 「📣 関連投稿(...)」が **4 形式混在**(巨人公式X / スポーツ報知巨人班X / スポーツ報知 巨人 / 💬 ファンの声)
- Gemini 自由生成 H3 が **30+ 種類**(意味的に同じものが複数存在)
- category と H3 内容が一致せず(コラムに 📋事実カード / 中継予定 等が混入)

詳細監査: `doc/active/FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08.md` の関連 finding を参照。

## 2. 目標

全 article で **固定 12 H3 set** に正規化:

```
📋 事実カード     - 数字・スコア・選手名
📊 戦況          - 順位・連勝・直近 N 試合
🏆 注目選手      - 当日活躍
📣 発言内容      - 監督・選手 quote
📅 次の注目      - 次戦・次回登板・復帰見込み
💬 ファンの声    - X embed の見出し統一
🎬 中継予定      - 放送情報(broadcast 専用)
🔗 出典記事      - 出典明示(必須)
💉 怪我状況      - injury / recovery
🎯 注目対戦      - matchup / pitcher 対決
🆕 プロフィール  - 新外国人 / 新人 / 入団
🎟 試合詳細      - 球場 / チケット / アクセス
```

H3 の出現順は **subtype 別 sequence** に従う(後述 §5)。

## 3. 廃止される H3(例 30+ 種類)

| 旧 H3 | 統一先 |
|---|---|
| 📣 関連投稿(巨人公式X)| 💬 **ファンの声** |
| 📣 関連投稿(スポーツ報知巨人班X)| 💬 **ファンの声** |
| 📣 関連投稿(スポーツ報知 巨人)| 💬 **ファンの声** |
| 【ハイライト】/【ファームのハイライト】/【投稿で出ていた内容】/【発言内容】/【具体的な変更内容】 | 📣 **発言内容** or 📋 **事実カード** |
| 【ファンの関心ポイント】/【次の注目】/【今後の注目点】/【一軍への示唆】 | 📅 **次の注目** |
| 【試合展開】/【チームへの影響と今後の注目点】/【この変更が意味すること】 | 📋 **事実カード**(箇条書き) |
| 【スタメン一覧】 | 📋 **事実カード**(lineup subtype 内)|
| 【故障の詳細】| 💉 **怪我状況** |
| 【対象選手の基本情報】/【ニュースの整理】 | 📋 **事実カード** |
| 【注目ポイント】 | 📋 **事実カード** |
| 試合スコア | 📋 **事実カード** |
| 中継予定 | 🎬 **中継予定**(絵文字統一)|

## 4. 実装 scope(3 layer)

### Layer A: nomotoke renderer 統一

`src/nomotoke_card_renderer.py` の各 template で以下 H3 を直接統一:
- 「📣 関連投稿(...)」3 形式 → 「💬 ファンの声」
- 「中継予定」 → 「🎬 中継予定」
- 「📋 事実カード」「🔗 出典記事」「📋 事実カード」 → 既に統一(維持)

### Layer B: Gemini prompt 修正

`src/rss_fetcher.py` / 関連 prompt template で Gemini 生成記事に以下 rule 強制:

- 自由 H3 生成禁止
- 上記 12 H3 set からの **選択制**
- subtype-aware sequence(§5)に従う
- 旧形式の H3(【...】 等)を出した場合 retry or 弾く

### Layer C: post-process filter(既存 100 件にも適用)

新規 helper `_normalize_h3_to_unified_set()` を追加:
- 既存記事の H3 を正規化
- 旧 H3(全 30+ 種)→ 新 12 set に置換
- WP REST PUT で既存 publish の body を更新するか、render 時に on-the-fly normalize するかは別判断

## 5. subtype 別 H3 sequence(20 主要 subtype)

| subtype | H3 sequence |
|---|---|
| postgame_full | 📋 → 🏆 → 📊 → 📅 → 💬 → 🔗 |
| postgame_short | 📋 → 📅 → 🔗 |
| broadcast | 🎬 → 📋 → 🎟 → 🔗 |
| lineup | 📋 → 🏆 → 💬 → 🔗 |
| pregame_pitcher | 📋 → 🎯 → 📅 → 🔗 |
| player_comment | 📣 → 📅 → 💬 → 🔗 |
| player_news | 📋 → 📅 → 💬 → 🔗 |
| player_recovery | 💉 → 📋 → 📅 → 🔗 |
| player_injury | 💉 → 📋 → 📅 → 🔗 |
| player_stats | 📋 → 📊 → 🔗 |
| manager_comment | 📣 → 📅 → 💬 → 🔗 |
| manager_news | 📋 → 📅 → 🔗 |
| official_notice | 📋 → 📅 → 🔗 |
| club_announcement | 📋 → 🔗 |
| farm_result | 📋 → 🏆 → 📅 → 💬 → 🔗 |
| farm_news | 📋 → 📅 → 💬 → 🔗 |
| trade / contract | 📋 → 📅 → 💬 → 🔗 |
| foreign_signing | 🆕 → 📋 → 📅 → 💬 → 🔗 |
| ob_news | 📣 → 💬 → 🔗 |
| commentator_view | 📣 → 🔗 |

## 6. 不可触

- env / Secret / Scheduler 変更しない
- WP publish / X 投稿 触らない
- Gemini call 増やさない(prompt 修正のみ、call 数据据え置き)
- 外部 API 増やさない
- 既存 enrichment block の機能 disable はしない(改善方向のみ)

## 7. 成功条件

- [ ] Layer A: nomotoke renderer の H3 全 4 形式が「💬 ファンの声」に統一
- [ ] Layer B: Gemini prompt の H3 自由生成が制限、test fixture で旧 H3 を出さない
- [ ] Layer C: post-process filter unit test で 30+ 旧 H3 → 12 新 set 全ケース mapping 確認
- [ ] live 5 件 sample で新規記事の H3 が 12 set 内に収まる
- [ ] pytest baseline 維持

## 8. phase 分割(narrow に進める)

1. **Phase 1**: Layer A nomotoke renderer 統一(narrow、1-2h)
2. **Phase 2**: Layer C post-process filter(unit test、2-3h)
3. **Phase 3**: Layer B Gemini prompt 修正(test fixture 必要、2-3h)

各 phase 終了で commit + push、ただし live 反映は image rebuild + redeploy 必要(別判断)。

## 9. 親 / 関連

- 親: `doc/active/FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08.md`
- 関連: `doc/active/MANUAL-INTAKE-QUALITY-PARITY-2026-05-08.md`
- 関連: `doc/active/RESTORE-2026-05-08-MORNING-RELIABILITY.md`(明日朝検証 window)
