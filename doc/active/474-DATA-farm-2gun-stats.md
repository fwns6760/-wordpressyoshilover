# 474-DATA 選手ページに二軍(ファーム)今季成績

- status: GOING_LIVE / owner: Claude / 2026-06-05 / user「他の選手全員」「わかりやすく」
- 背景: 選手ページは一軍のみ(insight.db box score由来)。二軍主体の若手/育成/リハビリ選手が薄ページに。
- ソース確認: NPB公式 巨人ファーム個人成績 idb1_g.html(打)/idp1_g.html(投)。実取得OK(投27/打52名)。
- 実装:
  - src/data_site_farm_stats.py: giants_farm_map()でNPB公式から{名前:{batting,pitching}}取得(cache)
  - pillar: PillarPlayerInfo に farm_batting/farm_pitching、_build_farm_stats_html(緑系・一軍と別集計明示)
  - 一軍見出しを「今シーズン 一軍成績」に明記化(二軍と区別=わかりやすく)
  - publisher: _build_pillar_info で名前一致でファーム付与(無ければNone安全)
- UX: 🌱二軍(ファーム)ブロック、投手成績/打撃成績を分け、「一軍とは別集計」と明記
- 注意: 山﨑伊織は二軍も記録なし=故障/未登板で実態通り。データ無し選手はブロック非表示。
- 制約: 三軍は公式の標準統計公開が限定的で保留。
