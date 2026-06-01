# 454 DATA-SITE 順位表 ETL(standings_snapshots を埋める)

> parent: 452 / status: READY_FOR_IMPL / owner: Claude Code / 作成: 2026-06-01
> 前提(実測): `standings_snapshots` **0 行**。 extractor `src/source_npb_standings_extractor.py`
> (`parse_npb_standings_html` / `find_giants_standings_row`)は**存在**するが、 `insight_nightly.py`
> から呼ばれていない(grep ヒット 0)= fetch+persist 未配線。

## 1. ゴール

セ・リーグ順位表(6球団 順位/勝/敗/分/ゲーム差)を毎日取得して `standings_snapshots` に upsert し、
データページ(cluster or 専用)に順位表セクションを解放する。

## 2. 実装スコープ

### Phase A: ETL 配線(本チケットの核)
- nightly(`insight_nightly.py` 等の定期 ingest)に standings 取得を追加:
  - NPB 順位表ページ HTML を fetch(source URL は extractor の想定元を実コードで確認してから確定。 推測しない)。
  - `parse_npb_standings_html(html)` → rows → `standings_snapshots` に upsert(`snap_date, team, rank, W, L, T, games_behind`)。
  - 冪等(同 snap_date 上書き)。
- 失敗時 silent skip(他 ingest を止めない)。

### Phase B: 表示(別便でも可)
- `data_site_query.py`: `fetch_standings(latest)` → 6 球団行。
- cluster ページ or 専用ページに順位表セクション(orange デザイン、 巨人行を強調)。

## 3. 触らない

- 既存 batting/pitching/lineups ETL ロジックは不可触(standings 追加のみ)。
- publish-notice / guarded-publish / x-post lane / WP mutation は不可触。
- env/secret は不可触。 deploy は別便・24h 観察。

## 4. 受け入れ

- 1 回 ingest 後 `standings_snapshots` に当日 6 球団行が入る。
- 巨人の順位/ゲーム差が NPB 公式と一致(verify)。
- 既存 ingest(batting 等)を壊さない(回帰)。

## 5. リスク

- source URL / HTML 構造変化で parse 失敗 → silent skip 設計で他を止めない。
- standings source が NPB 公式以外なら著作権・利用規約を確認(取得元確定時に再確認)。

## 6. next

- まず source URL を実コード(extractor の想定 input)で確定 → nightly 配線 → 1 回 ingest verify。
