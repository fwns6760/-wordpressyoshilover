# sample_farm_result_1

- `post_id`: `63232`
- `backup_path`: `logs/cleanup_backup/63232_20260426T032533.json`
- `quality_flags`: `empty sections`, `generic filler`, `source-unbacked optional sections`

## 元本文

```text
報知新聞 / スポーツ報知巨人班X
GIANTS FARM WATCH
【巨人】石塚裕惺、試合開始１分前に長野の球場到着→代打出場…負傷の泉口に代わり緊…

【巨人】石塚裕惺、試合開始１分前に長野の球場到着→代打出場…負傷の泉口に代わり緊急昇格 ２ラン放った２軍戦途中で移動。

📌 関連ポスト
https://twitter.com/hochi_giants/status/2046593087502188994

【二軍結果・活躍の要旨】

💬 このニュース、どう見る？

【巨人】石塚裕惺、試合開始１分前に長野の球場到着→代打出場…負傷の泉口に代わり緊急昇格 ２ラン放った２軍戦途中で移動。

【ファームのハイライト】
二軍戦では得点の動きと投手の内容を先に押さえると全体像が見えやすくなります。
ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。

【二軍個別選手成績】

【一軍への示唆】
二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。

💬 先に予想を書く？

💬 ファンの声（Xより）
https://twitter.com/kanmahanma8/status/2046596834462953636
https://twitter.com/totorojump/status/2046589540065055218
https://twitter.com/ytytytyt0316/status/2046580496600379541
https://twitter.com/su_nupi/status/2046573215833849968
https://twitter.com/giabbit_2/status/2046596841681355083
https://twitter.com/j_ta_ro_jtr/status/2046589854063226934
https://twitter.com/hinatazaka_fpo/status/2046560979375575424

💬 みんなの本音は？

参照元: 報知新聞 / スポーツ報知巨人班X
```

## source/meta facts

- `article_subtype`: `farm_result` (`GIANTS FARM WATCH`, `【二軍結果・活躍の要旨】` ブロックから判定)
- `source_label`: `報知新聞 / スポーツ報知巨人班X`
- `source_url`: `https://twitter.com/hochi_giants/status/2046593087502188994`
- `title.rendered`: `石塚裕惺、試合開始１分前に長野の球場到着→代打出場…負傷の泉口に代わり緊急昇…`
- `confirmed_players`: `石塚裕惺`, `泉口`
- `confirmed_fact_1`: `試合開始1分前に長野の球場へ到着`
- `confirmed_fact_2`: `代打出場`
- `confirmed_fact_3`: `負傷の泉口に代わる緊急昇格`
- `confirmed_fact_4`: `2ランを放った二軍戦途中で移動`
- `score`: `not present in source/meta`
- `modified`: `2026-04-21T23:30:53`
- `fetched_at`: `2026-04-26T03:25:33.875705+00:00`

## 修正文候補

```markdown
### 二軍メモ
- 石塚裕惺が試合開始1分前に長野の球場へ到着し、代打で出場。
- 泉口の負傷に伴う緊急昇格。
- 2ランを放った二軍戦の途中で移動した。
- 試合結果や個別成績は source/meta にないため入れない。
```

## diff

```diff
--- original.normalized
+++ preview.det
@@
- 【二軍結果・活躍の要旨】
- 【巨人】石塚裕惺、試合開始１分前に長野の球場到着→代打出場…負傷の泉口に代わり緊急昇格 ２ラン放った２軍戦途中で移動。
- 【ファームのハイライト】
- 二軍戦では得点の動きと投手の内容を先に押さえると全体像が見えやすくなります。
- ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。
- 【二軍個別選手成績】
- 【一軍への示唆】
- 二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。
- 💬 ファンの声（Xより）
- 💬 みんなの本音は？
+ ### 二軍メモ
+ - 石塚裕惺が試合開始1分前に長野の球場へ到着し、代打で出場。
+ - 泉口の負傷に伴う緊急昇格。
+ - 2ランを放った二軍戦の途中で移動した。
+ - 試合結果や個別成績は source/meta にないため入れない。
```

## 適用 rule list

- 空見出し削除 (`【二軍個別選手成績】`)
- source にない optional section 削除 (`一軍への示唆`, `ファンの声`, CTA)
- 一般論フィラー削除
- `farm_result move-note` テンプレへ寄せ
- source/meta にない試合結果・個人成績の補完禁止
