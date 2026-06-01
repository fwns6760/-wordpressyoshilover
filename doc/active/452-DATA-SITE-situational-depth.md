# 452 data-site 状況別データ深化 + データ堀の投資判断

## 1. ticket header

- **ticket id**: 452(450/451 は並行アクターの video-radar が使用中のため 452)
- **status**: DRAFT(user 受け入れ待ち)
- **owner**: Claude Code
- **lane**: data-site / insight.db(read-side)
- **created**: 2026-06-01
- **priority**: P2(data サイト差別化。443/444 Phase 1.5 の上に積む)
- **parent**: 444(data-site Phase 1.5)
- **spec**: `mkdocs_docs/spec/data-site-situational-splits.md`
- **関連**: 447(RISP/対左右 = Phase C 依存)

## 2. 背景(現物確認 2026-06-01)

ベンチ(`baseballdata.jp` / `my-favorite-giants.net`)を WebFetch で確認。両者は
**多年蓄積(2011〜)+ 守備 + 順位表 + 網羅的状況別**を持つ。一方 YOSHILOVER の
`insight.db` は現物 COUNT で:

- games = `2026-03-27`〜`2026-05-31`(今季のみ)
- `standings_snapshots` 0 / `fielding_logs` 0 / `at_bat_details.batter_canonical` 非NULL 0

user 方針:「見やすさ、データでも勝つ」。→ 2 フェーズに分解。

## 3. Phase B(本ticketの実装対象、追加source無し・¥0)

今季 box score から **追加取得なしで作れる状況別スプリット**を /data/ 選手ページに追加し、
「今季の細かさ + UI」でベンチに勝つ。

- 曜日別 / 月別 / 交流戦vsリーグ戦 別 打率(`games.game_date` + `game_id` の NPB コードから導出。
  導出可を岸田行倫の実データで verify 済: `f-g`=交流戦 / `g-t`=リーグ戦)
- 直近試合の1行ログ(`batting_logs`)
- 投手は既存(前回登板/防御率)維持、曜日/月別は対象外(サンプル不足)

詳細・受け入れ条件・UI・不可触は **spec** を正とする。

### 実装対象(想定)

- `src/data_site_query.py`: `fetch_weekday_split` / `fetch_month_split` / `fetch_interleague_split` / `fetch_recent_game_log`(全て read-only、`team_code='g'`/player_canonical 絞り)
- `src/data_site_template_pillar.py`: 対応 `_build_*_html` 4 section + assembly 配線
- `src/data_site_publisher.py`: PillarPlayerInfo 配線
- `tests/`: 各 split の集計 + 表示テスト

### 受け入れ(spec §4 準拠)

- 4 section が出場データのある選手で出る / 数字が DB と一致 / 打数0区分は非表示 /
  新規 source・Gemini・課金 増なし / 既存+新規テスト pass / live 1選手 verify。

## 4. Phase C(投資判断 = 別ticket化、本ticketでは着手しない)

「データ網羅でベンチに勝つ」に必要だが **現データゼロ**:

| 項目 | 現状 | 必要な投資 |
|---|---|---|
| 多年データ(2011〜) | 今季のみ | 過去年 box の取り込み source + ETL |
| 守備成績 | `fielding_logs` 0 | 守備データ source |
| 順位表/勝敗表 | `standings_snapshots` 0 | 順位 source or 算出 |
| 得点圏/対左右 | `at_bat batter_canonical` 0 | backfill(447) |

→ source拡張 + コスト(月単位)を伴うため **user 投資判断(§11 課金・scope)**。
別ticketで「どのデータ源をいくらで入れるか」を見積もってから着手。本ticketには含めない。

## 5. 次アクション

- user が **Phase B 着手を承認**したら、spec に沿って実装(¥0・read-only・deploy 1回)。
- Phase C は別途「データ源調査ticket」を起こし、source候補とコストを出してから user 判断。

## 6. 不可触(Phase B)

多年/守備/順位表/RISP / 投手曜日月別 / 既存 article path / Scheduler / featured_media / X lane。
