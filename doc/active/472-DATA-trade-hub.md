# 472-DATA 巨人トレード/移籍ページ /data/trade

- status: GOING_LIVE / owner: Claude / created: 2026-06-05
- user 2026-06-05「trading/ を見てトレード情報を書いて」
- benchmark: trading/change.htm(交換トレード) / all.htm(入退団一覧)
- scraper: src/tools/scrape_giants_trades.py → config/giants_trades.json
- 結果: 交換トレード100 / 入退団469。複数選手セルは ASCII空白で分割(姓名間の全角空白は維持)
- template: src/data_site_template_trade.py、slug=trade parent=cluster → /data/trade/(ungated 日次)
- 導線: /data/ に「🔄 トレード/移籍」チップ
- 注意: 選手名/守備位置は移籍時点。事実誤認NG。
