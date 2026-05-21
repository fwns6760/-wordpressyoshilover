# DIGEST-DAILY-MORNING-2026-05-08

| field | value |
|---|---|
| ticket_id | DIGEST-DAILY-MORNING-2026-05-08 |
| priority | P1(MVP 直結、運用ループ閉鎖)|
| status | PHASE_1_3_LANDED (renderer + CLI publish flow 完成、 scheduler trigger Phase 2 のみ未) |
| owner | Claude/Codex(narrow impl)|
| lane | INGEST / FRONTEND |
| created | 2026-05-08 |
| doc_path | doc/active/DIGEST-DAILY-MORNING-2026-05-08.md |
| cost | ¥0(既存 block 集約のみ、Gemini 不要、外部 API 増加なし)|
| regression risk | 低(新 subtype 追加、既存 publish path に影響なし)|
| 工数 | 4-6h |

## 1. 目的

ファンが **朝起きて 1 記事だけ読めば前日 + 当日が追える** 状態を作る。
のもとけ式の「朝刊」概念を直接体現。

## 2. 既存 block を集約するだけ(¥0)

既存実装済の block:
- `_build_recent_games_block` - 直近 5 試合 W-L
- `_build_next_game_block` - 次戦予定(Yahoo schedule)
- `_build_standings_block` - 現在順位(NPB)
- `_build_x_embeds_block` - 公式 X 引用

これらを **新 renderer `render_digest_daily_morning()`** で 1 article に集約。

## 3. 内容(typical 600-1200 chars)

```
朝まとめ 5月9日(金)

📋 事実カード
- 前日試合: 巨人 3-2 阪神(サヨナラ勝利、9 連勝)
- 本日試合: 18:00 開始、東京ドーム vs 中日(先発: ウィットリー)
- 順位: 1 位、貯金 8

📊 戦況
- 直近 5 試合: ●●○○○(2 勝 3 敗から 3 連勝)
- セ・リーグ首位を維持

📅 次の注目
- 中日との 3 連戦初戦
- ウィットリー 中 5 日、対 中日 通算 2 勝 1 敗
- 5/10 先発予想: 山崎伊織

💬 ファンの声
[X embed × 2-3 件、巨人公式 / スポーツ報知 / 球団]

🔗 出典記事
- Yahoo Sportsnavi(試合結果 / 翌日予定)
- NPB 公式(順位)
```

## 4. 出力 path

- WP category: 「コラム」(または新 category 「朝まとめ」)
- WP subtype meta: `digest_daily`
- WP slug: `morning-digest-YYYYMMDD`
- 1 日 1 本(冪等性: 既に当日分 publish 済なら skip)

## 5. 実装 scope

### A. 新 renderer

`src/tools/digest_daily_morning.py`(新規):
- 既存 block helper を import
- 集約 → HTML 生成
- nomotoke-card- marker を付与(enrichment が走る body)

### B. 起動経路

既存 `giants-morning-catchup`(Cloud Run scheduler `30 4 * * *`)の中で **追加 1 article 生成**。

- yoshilover-fetcher の `/run` endpoint に `--mode=digest_daily` 追加
- または別 trigger で 06:00 に起動(scheduler 1 つ追加、ただし scheduler 追加は user 同意境界 → 既存 catchup 内に組み込む方が既定)

### C. WP publish

通常 `_create_post` 経由、subtype meta `digest_daily` 付与。

### D. 冪等性

- 当日 0:00 以降に既に `digest_daily` の post が WP にあれば skip
- WP REST query で `slug=morning-digest-YYYY-MM-DD` 検索

## 6. 制約 / 不可触

- env / Secret / Scheduler 変更しない(catchup 内に組み込む)
- 新 Cloud Run resource 作らない
- Gemini call 増やさない(集約のみ、本文生成不要)
- 外部 API 増やさない(既存 fetch を再利用)
- WP publish 触る(新 category と subtype 1 つ追加するが、既存 publish path の挙動は変えない)

## 7. 成功条件

- [x] `render_digest_daily_morning()` (実装は `build_digest_body()`) 単体テストで 600+ chars 出力 — commit `8f92055`、 dry-run 1692 chars 確認 (2026-05-21)
- [x] 既存 block helper で生成された data の集約が成立 — recent_games / standings / next_game / x_embeds 全 4 block 集約
- [x] 冪等性:同日 2 回呼んでも 1 記事のみ — `is_digest_already_published_today(wp)` で WP slug query
- [ ] live 翌朝(本 ticket 着地後の最初の 06:00 catchup)で 1 article publish 確認 — **Phase 2 scheduler 統合 + Phase 4 deploy 後に観察**
- [ ] H3 統一 ticket の 12 set に従う — H3-STRUCTURE-UNIFY-2026-05-08 ticket と統合

## 7.1 実装 verify (2026-05-21)

- src/tools/digest_daily_morning.py: 232 lines + main() CLI + 4 block 集約 path
- tests/test_digest_daily_morning.py: 11 tests pass (TestBodyComposition / TestIdempotency / etc.)
- fetcher image `enrich-gate-1f9df8b` 以降 (`8f92055` 含む) で全 deploy 済
- dry-run smoke (2026-05-21): title=「📰 朝まとめ 5月21日 — 巨人 順位 / 前日試合 / 翌日予定」、 slug=`morning-digest-2026-05-21`、 body=1692 chars、 standings + next_game + X embeds 3 block 出力確認 (recent_games は local キャッシュ無で空)

## 8. phase 分割

1. **Phase 1**: 新 renderer 単体実装(集約 logic + 単体テスト、2-3h)
2. **Phase 2**: 起動経路統合(catchup 内 wire-in、1-2h)
3. **Phase 3**: 冪等性 + WP publish 統合(1-2h)
4. **Phase 4**: live 反映(image rebuild + redeploy、別判断)

## 9. 親 / 関連

- 親: `doc/active/MANUAL-INTAKE-QUALITY-PARITY-2026-05-08.md`(parity 改善の延長)
- 関連: `doc/active/H3-STRUCTURE-UNIFY-2026-05-08.md`(本記事の H3 も統一 set 適用)
