# sample_postgame_3

- `post_id`: `63505`
- `backup_path`: `logs/cleanup_backup/63505_20260426T012330.json`
- `quality_flags`: `hero-name placeholder`, `result placeholder`, `fan voice overgrowth`, `long generic inference`

## 元本文

```text
巨人公式 / 巨人公式X
GIANTS GAME NOTE
【一軍】巨人 7-2 DeNA 本日のヒーロー✨ プロ初本塁打を放った 選手㊗️

【一軍】巨人 7-2 DeNA本日のヒーロー✨プロ初本塁打を放った 選手㊗️HERO IS HERE。

📌 関連ポスト
1. 巨人公式X
https://twitter.com/TokyoGiants/status/2047955420300656780
2. スポーツ報知巨人班X
https://twitter.com/hochi_giants/status/2047951775865749609

【試合結果】
読売ジャイアンツはDeNAに7-2で勝利しました。

📊 今日の試合結果
結果: 結果確認中
スコア: 7-2
相手: DeNA
決め手: 巨人 7-2 DeNA 本日のヒーロー✨ プロ初本塁打を放った 選手㊗️

👀 勝負の分岐点
- 得点の前後でベンチがどう動いたか。
- この内容が次戦にも続くか。

💬 この試合、どう見る？

【ハイライト】
本日の試合では、プロ初本塁打を放った選手がヒーローとなりました。この一打がチームの勝利を決定づける大きな要因となりました。

【選手成績】
本日のヒーローはプロ初本塁打を放った選手です。

【試合展開】
本日の試合では、プロ初本塁打を放った選手がヒーローに選ばれました。このプロ初本塁打は、チームに勢いをもたらし、勝利に大きく貢献したと解釈できます。この一打が今後の打線の活性化にどうつながるのか、次の試合での選手の打席に注目したいと思います。

💬 勝負の分岐点は？

💬 ファンの声（Xより）
https://twitter.com/FuQuiz_2912/status/2047955517533024410
https://twitter.com/wansukimaron/status/2047948693870117251
https://twitter.com/JjohTsuka/status/2047956216819994845
https://twitter.com/akitatokyoakita/status/2047649031925670103
https://twitter.com/skullhong___302/status/2047941757640597956
https://twitter.com/yuta_matsuyama_/status/2047952485701304654
https://twitter.com/Reminaciel24/status/2047943238183739537

【関連記事】
- 巨人ヤクルト戦 終盤の一打で何が動いたか
- 巨人3-4 敗戦の分岐点はどこだったか

💬 今日のMVPは？

参照元: 巨人公式 / 巨人公式X
```

## source/meta facts

- `article_subtype`: `postgame` (`GIANTS GAME NOTE`, `【試合結果】` ブロックから判定)
- `source_label`: `巨人公式 / 巨人公式X`
- `source_urls`:
  - `https://twitter.com/TokyoGiants/status/2047955420300656780`
  - `https://twitter.com/hochi_giants/status/2047951775865749609`
- `title.rendered`: `巨人7-2 試合を決めた主役は誰だったか`
- `source_title/body cue`: `【一軍】巨人 7-2 DeNA 本日のヒーロー`
- `score`: `7-2`
- `opponent`: `DeNA`
- `result`: `勝利`
- `confirmed_player_name`: `not present in source/meta body shown here`
- `modified`: `2026-04-25T17:30:28`
- `fetched_at`: `2026-04-26T01:23:30.081474+00:00`

## 修正文候補

```markdown
### 試合メモ
- 巨人がDeNAに7-2で勝利。
- 参照元の主題は「本日のヒーロー」。
- プロ初本塁打を放った選手がヒーローとして扱われている。
- 選手名は source/meta にないため補完しない。
```

## diff

```diff
--- original.normalized
+++ preview.det
@@
- 📊 今日の試合結果
- 結果: 結果確認中
- スコア: 7-2
- 相手: DeNA
- 決め手: 巨人 7-2 DeNA 本日のヒーロー✨ プロ初本塁打を放った 選手㊗️
- 👀 勝負の分岐点
- - 得点の前後でベンチがどう動いたか。
- - この内容が次戦にも続くか。
- 【ハイライト】
- 本日の試合では、プロ初本塁打を放った選手がヒーローとなりました。この一打がチームの勝利を決定づける大きな要因となりました。
- 【選手成績】
- 本日のヒーローはプロ初本塁打を放った選手です。
- 【試合展開】
- 本日の試合では、プロ初本塁打を放った選手がヒーローに選ばれました。このプロ初本塁打は、チームに勢いをもたらし、勝利に大きく貢献したと解釈できます。この一打が今後の打線の活性化にどうつながるのか、次の試合での選手の打席に注目したいと思います。
- 💬 ファンの声（Xより）
- 【関連記事】
- 💬 今日のMVPは？
+ ### 試合メモ
+ - 巨人がDeNAに7-2で勝利。
+ - 参照元の主題は「本日のヒーロー」。
+ - プロ初本塁打を放った選手がヒーローとして扱われている。
+ - 選手名は source/meta にないため補完しない。
```

## 適用 rule list

- placeholder削除 (`結果確認中`, `選手`)
- source にない optional section 削除 (`勝負の分岐点`, `ファンの声`, `関連記事`, CTA)
- 長文推測文の短文化
- `postgame hero-note` テンプレへ寄せ
- source/meta にない選手名は空欄のままではなく未記載扱い
