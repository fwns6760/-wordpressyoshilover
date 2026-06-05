# 475-FIX 選手成績の他球団混入を修正(team_name='巨人')

- status: GOING_LIVE / owner: Claude / 2026-06-05 / user「一軍でなげてない。2軍だよ。他の選手も間違えてない？正確第一」
- 事象: 山﨑伊織の選手ページが「今シーズン 一軍成績 登板2」表示。NPB公式は2026一軍登板0。
- 根本原因:
  - insight.db は NPB全12球団・全試合のboxスコアを保持(330試合、巨人入りは55のみ)
  - 選手別statクエリが player_canonical の名前一致のみで集計し team 未フィルタ
  - → 山﨑福也/颯一郎/康晃(他球団)や誤取込行が山﨑伊織に混入
  - team_role 列は全球団に'giants'が付く無意味列。信頼できるのは team_name のみ
- 修正: data_site_query の選手別クエリ13箇所に AND team_name='巨人' を追加
  (season/recent/splits、打撃・投球)
- 検証(ローカルinsight.db): 山﨑伊織→一軍0(NPB一致)/戸郷5維持/吉川25/丸10。tests 43 passed
- 残課題(別件): 坂本勇人・岡本和真が batting_logs に不在(主力欠落)。canonical表記ゆれ(増田 陸/増田陸)。
- 注意: NPB ranking 等の全球団集計クエリは意図的に未フィルタのまま。
