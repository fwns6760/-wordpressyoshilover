# 471-DATA 巨人FAページ /data/fa

- status: GOING_LIVE（scrape完了・本番公開）
- owner: Claude / created: 2026-06-05
- user 2026-06-05「巨人FA獲得選手・FA有資格選手をトピックスで」
- benchmark: player/fa.htm（FA獲得）/ player/fa-right.htm（FA有資格）
- scraper: `src/tools/scrape_giants_fa.py` → `config/giants_fa.json`
- 結果: FA獲得31 / FA有資格57（asof 2024・出典スナップショット明記）
- template: `src/data_site_template_fa.py`、slug=fa parent=cluster → /data/fa/（ungated, 日次upsert）
- 導線: /data/ に「🤝 FA選手」チップ
- 注意: FA有資格は年で変動するスナップショット。事実誤認NG、推測で埋めない。
