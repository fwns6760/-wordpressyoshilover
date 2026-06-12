# 2026-06-12 /data/notable 再設計

- 16:00 JST | impl+test+commit | notable-redesign | 2fbb535f | 5セクション化(連続記録/好調/順位表/リーダー/関連リンク)、カード最小表示、サバメ指数除外、items 8→16
- 16:02 JST | deploy+verify | data-site-publisher | image notable-redesign-2fbb535f, exec fljqp Completed, items=12, live目視OK | user決定: XデータポストへのURL付与はしない(インプ低下)、導線はX外形(固定ポスト等)
- 16:15 JST | eyecatch | notable page 86527 | ed54fcbd | featured_media=66536(坂本勇人) REST即時設定+code恒久化、image notable-eyecatch-ed54fcbd job反映、og:image verify済 | 用途=X固定ポストOGP
- 16:40 JST | navline+cospa導線 | notable page | 97f774b6+73420879 | ヘッダー直下に「他の選手の記録はこちら→全選手/打撃R/投手R/💰年俸コスパ」、チップに年俸コスパ分析追加。image notable-cospa-73420879、exec kbwgv、live verify済 | コスパは既設 /data/salary/salary-value を再利用(新規実装なし)
- 16:45 JST | 新ページ /data/mlb | 巨人発メジャーリーガー | 55d87fdd | 岡本和真(ブルージェイズ)+菅野智之(ロッキーズ)のMLB今季成績+直近試合、source=MLB公式statsapi(無料)。page_id 91111 created、トップに063 v0.23.6カード追加(REST deploy)、両方live verify済 | 毎日23時の publisher 本流に upsert 組込、image mlb-page-55d87fdd
- 17:00 JST | MLB選手別ページ+トップ独立枠+専用scheduler | 920fed51 | /data/mlb/okamoto-kazuma(67試合+直近打席ごとチップ) /data/mlb/sugano-tomoyuki(2025+2026全43登板・勝敗球数) 作成。063 v0.23.7でトップ「巨人発メジャーリーガー」独立枠(データ枠の直下・外、チップ撤去)。scheduler data-site-mlb-refresh(30 8,15 * * * JST, containerOverrides --only-mlb)新設、手動発火exec llr77 SUCCEEDED verify済 | image mlb-player-pages-920fed51
