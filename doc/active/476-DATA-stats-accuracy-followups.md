# 476-DATA 選手成績の正確性 残作業(PARKED)

- status: PARKED(user「残作業で残しといて」2026-06-05)
- owner: Claude / 親: 475(team_name='巨人'混入修正=完了)
- 着手前に: insight.db を実取得して証拠ベースで調査(推測で埋めない)

## 残課題

1. **主力の欠落(過少表示)**
   - 坂本勇人・岡本和真が batting_logs に不在 → ページが「記録なし」になる可能性
   - 原因候補: box取込の名前正規化ミス / 別canonicalで格納 / 実際に出場が少ない(故障・MLB等)
   - 確認: insight.db で巨人 team_name の全 player_canonical を列挙し roster と突合、欠落者を特定
2. **canonical 表記ゆれ**
   - 「増田 陸」と「増田陸」など全角/半角・空白ゆれが混在
   - 選手別クエリは REPLACE(... ,' ','') で吸収しているが、ゆれの棚卸しと正規化が望ましい
3. (参考)team_role 列は全球団に'giants'付与で無意味。使用禁止。team_name のみ信頼。

## 完了済(親475)
- 選手別statクエリ13箇所に team_name='巨人' 追加 → 他球団同名選手の混入を解消(山﨑伊織で検証)
