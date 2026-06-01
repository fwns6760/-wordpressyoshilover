# 452 DATA-SITE 未取得データ 仕様書(データギャップ棚卸し + 構築計画)

> 種別: 仕様書 (umbrella) / status: DRAFT
> 作成: 2026-06-01 / owner: Claude Code
> ルール: 本 doc は **実確認した事実のみ**記載 (推測で埋めない / [[feedback_spec_doc_evidence_only_2026_05_27]])
> 検証: production insight.db (GCS copy) + src grep。 行数・列・呼び出し有無は 2026-06-01 実測。

## 1. 目的

データページの「綺麗 + 情報を増やす」(ブランディング)に向け、 **まだ取得できていないデータを作る**。
本 doc はギャップを棚卸しし、 build できるもの / source-blocked / 既起票 を仕分けて、 子チケットへ落とす。

## 2. データギャップ棚卸し(実測 2026-06-01)

| データ | insight.db 実測 | 原因(実コード確認) | 対応 |
|---|---|---|---|
| **リーグ順位**(打率◯位/N人中) | `advanced_metric_snapshots` **312,657 行**。列に `league_rank / league_total / position_rank / position_total` あり、 値も入っている(例: 平山 AVG last_7d rank=12/127) | **計算済・取得済**。 データページが表示していないだけ | **453**(表示配線のみ。 build 軽い) |
| **順位表**(セ6球団 順位/勝敗/ゲーム差) | `standings_snapshots` **0 行** | extractor `src/source_npb_standings_extractor.py` (`parse_npb_standings_html`) は**存在**するが、 `insight_nightly.py` から**呼ばれていない**(grep ヒット 0)= 未配線で fetch+persist されていない | **454**(nightly に fetch→parse→upsert 配線) |
| **守備**(PO/A/E/DP/守備率) | `fielding_logs` **0 行** | `insight_etl.py` は fielding_logs を対象に含む(L198-202)が、 注記 L875「**NPB 公式 box に守備 stat が無い場合 fielding_logs は空**」= **source(NPB公式box)に守備statが無い** | **source-blocked**。 別source(守備データ提供元)の調査が前提 → 455 (research, 着手保留) |
| **得点圏/走者状況/カウント/vs左右** | `at_bat_details` 1,478 行だが `batter_canonical` **全件 NULL** | 既知 = **447 Phase A**(canonical backfill)で解決予定 | **447** 既起票(参照) |

## 3. build 順(子チケット)

1. **453 rank-badges**(最優先・軽い・データ有): `advanced_metric_snapshots` の league_rank をデータページに「打率 セ◯位/N人中」バッジ表示。read-side only、 ETL 不要。
2. **454 standings-etl**(buildable): `source_npb_standings_extractor` を nightly に配線 → `standings_snapshots` を毎日 upsert → 順位表セクション解放。
3. **447 Phase A**(既起票): at_bat_details.batter_canonical backfill → RISP/count/vs左右 解放。
4. **455 fielding-source**(保留・research): NPB公式box に守備statが無いため、 守備データの取得元を先に確定する必要あり。 source 不明のうちは build しない。

## 4. デザイン(別軸・進行中)

- データページ HTML の orange デザインシステム刷新(カード/オレンジ表/split バー/順位バッジ/モバイル)は別途進行中(`data_site_template_pillar.py`、 style block 投入済)。
- 上記 453(rank badge)は **デザインの `.ys-tag` バッジ部品**に乗せる(データ + 見た目を同時に上げる)。

## 5. 触らない / 制約

- insight.db schema breaking 変更はしない(既存 NULL/空を埋める方向のみ)。
- ETL deploy は別便・24h 観察(コスト/無料枠維持)。
- 守備(455)は source 未確定のまま実装しない(推測で source を決めない)。

## 6. 採番メモ(housekeeping)

- `448` が 2 本(`448-XPOST-data-split-surprise-candidate` と `448-MARKETING-yoshilover-value-and-x-selection`)= 番号衝突。 別便で片方を採番し直す(MARKETING を 448 に残す案)。

## 7. next action

- (user 判断) 453 → 454 → (447) の順で build 着手してよいか。 455(守備)は source 調査を先にやるか保留か。
