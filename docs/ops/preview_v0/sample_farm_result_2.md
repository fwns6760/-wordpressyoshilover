# sample_farm_result_2

- `post_id`: `63249`
- `backup_path`: `logs/cleanup_backup/63249_20260426T030552.json`
- `quality_flags`: `title restatement only`, `empty sections`, `generic filler`

## 元本文

```text
報知新聞 / スポーツ報知巨人班X
GIANTS FARM WATCH
【巨人】萩尾匡也が１軍合流 ファームで打率３割３分３厘 大卒４年目外野手

【巨人】萩尾匡也が１軍合流 ファームで打率３割３分３厘 大卒４年目外野手。

📌 関連ポスト
https://twitter.com/hochi_giants/status/2046812011795796027

【二軍結果・活躍の要旨】

💬 このニュース、どう見る？

【巨人】萩尾匡也が１軍合流 ファームで打率３割３分３厘 大卒４年目外野手。

【ファームのハイライト】
二軍戦では得点の動きと投手の内容を先に押さえると全体像が見えやすくなります。
ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。

【二軍個別選手成績】

【一軍への示唆】
二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。

💬 先に予想を書く？

💬 みんなの本音は？

参照元: 報知新聞 / スポーツ報知巨人班X
```

## source/meta facts

- `article_subtype`: `farm_result` (`GIANTS FARM WATCH`, `【二軍結果・活躍の要旨】` ブロックから判定)
- `source_label`: `報知新聞 / スポーツ報知巨人班X`
- `source_url`: `https://twitter.com/hochi_giants/status/2046812011795796027`
- `title.rendered`: `萩尾匡也が１軍合流 ファームで打率３割３分３厘 大卒４年目外野手`
- `confirmed_players`: `萩尾匡也`
- `confirmed_fact_1`: `1軍合流`
- `confirmed_fact_2`: `ファームで打率3割3分3厘`
- `confirmed_fact_3`: `大卒4年目外野手`
- `score`: `not present in source/meta`
- `modified`: `2026-04-22T14:01:08`
- `fetched_at`: `2026-04-26T03:05:52.568018+00:00`

## 修正文候補

```markdown
### 二軍メモ
- 萩尾匡也が1軍合流。
- ファームで打率3割3分3厘。
- 大卒4年目の外野手。
- 試合結果や追加成績は source/meta にないため広げない。
```

## diff

```diff
--- original.normalized
+++ preview.det
@@
- 【二軍結果・活躍の要旨】
- 【巨人】萩尾匡也が１軍合流 ファームで打率３割３分３厘 大卒４年目外野手。
- 【ファームのハイライト】
- 二軍戦では得点の動きと投手の内容を先に押さえると全体像が見えやすくなります。
- ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。
- 【二軍個別選手成績】
- 【一軍への示唆】
- 二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。
- 💬 先に予想を書く？
- 💬 みんなの本音は？
+ ### 二軍メモ
+ - 萩尾匡也が1軍合流。
+ - ファームで打率3割3分3厘。
+ - 大卒4年目の外野手。
+ - 試合結果や追加成績は source/meta にないため広げない。
```

## 適用 rule list

- 空見出し削除 (`【二軍個別選手成績】`)
- source にない optional section 削除 (`一軍への示唆`, CTA)
- 一般論フィラー削除
- `farm_result roster-note` テンプレへ寄せ
- source/meta にない試合結果・追加成績の補完禁止
