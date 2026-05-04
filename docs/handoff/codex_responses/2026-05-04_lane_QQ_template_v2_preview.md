# 2026-05-04 Lane QQ body template v2 preview

Method:

- preview-only
- production / env / deploy / WP PUT なし
- `ENABLE_BODY_TEMPLATE_V2=0` と `=1` の repo render 比較
- `64443` は current publish body の WP REST GET が sandbox から不可のため、同 source title / summary に current social template を当てた representative render を before とする
- `64432` は Lane OO / NN で確認済みの incident-family fallback を before とする
- 他 subtype preview は generic / postgame representative を追加

## Summary

| case | source | before | after | H3 before | H3 after | removed strings | residual risk |
|---|---|---|---|---:|---:|---|---|
| `64443` | 報知巨人X / 田和廉 球団新記録 | social v1 representative | social v2 representative | 3 | 2 | `【発信内容の要約】`, `【文脈と背景】` | current live body 自体は未取得 |
| `64432` | サンスポ巨人X / subject unresolved recovery family | incident fallback | same body with v2 headings | 3 | 2 | `【発信内容の要約】`, `【文脈と背景】` | subject unresolved / empty section は残る |
| generic representative | OB / commentary family | generic v1 | generic v2 | 3 | 2 | `【ここに注目】` | baseball relevance は別 lane 判定 |
| postgame representative | strict postgame renderer | current heading levels | v2 heading levels | 3 | 2 | none | 文面自体は unchanged |

## 64443

Source:

- post id: `64443`
- source URL: `https://twitter.com/hochi_giants/status/2050891541141483536`
- note: current publish body は repo sandbox から read-only fetch 不可。before/after は **same source title + summary** を current / v2 template で render した representative preview

Before (`ENABLE_BODY_TEMPLATE_V2=0`):

```text
【話題の要旨】
報知新聞 / スポーツ報知巨人班XのX投稿として、田和廉が12試合連続無失点を球団新に伸ばし、7回2死満塁で中断後も降雨コールドで記録を継続した。
報知新聞 / スポーツ報知巨人班Xが伝えた要点を、最初に整理したい話題です。
【発信内容の要約】
田和廉が12試合連続無失点を球団新に伸ばし、7回2死満塁で中断後も降雨コールドで記録を継続した。
【文脈と背景】
球団やチームの状況のうち、元記事にある背景だけを整理する。
【ファンの関心ポイント】
巨人ファンにとっては、この発信が次の試合や起用、話題の広がりにどう動くかを見ておきたいところです。
発信内容そのものだけでなく、ここからどんな動きにつながるかを見たいところです。みなさんの意見はコメントで教えてください！
```

After (`ENABLE_BODY_TEMPLATE_V2=1`):

```text
【話題の要旨】
報知新聞 / スポーツ報知巨人班XのX投稿として、田和廉が12試合連続無失点を球団新に伸ばし、7回2死満塁で中断後も降雨コールドで記録を継続した。
報知新聞 / スポーツ報知巨人班Xが伝えた要点を、最初に整理したい話題です。
【投稿で出ていた内容】
田和廉が12試合連続無失点を球団新に伸ばし、7回2死満塁で中断後も降雨コールドで記録を継続した。
【この話が出た流れ】
球団やチームの状況のうち、元記事にある背景だけを整理する。
【ファンの関心ポイント】
巨人ファンにとっては、この発信が次の試合や起用、話題の広がりにどう動くかを見ておきたいところです。
発信内容そのものだけでなく、ここからどんな動きにつながるかを見たいところです。みなさんの意見はコメントで教えてください！
```

Check:

- removed strings:
  - `【発信内容の要約】`
  - `【文脈と背景】`
- preserved facts:
  - `田和廉`
  - `12試合連続無失点`
  - `7回2死満塁`
  - `降雨コールド`
- new fact: `0`
  - body sentence set は header rename のみで、player / number / event は同一
- H3/H4:
  - before = `H3 3 / H4 0`
  - after = `H3 2 / H4 1`
- residual risk:
  - current publish HTML そのものは未取得
  - v2 は wording / heading level だけを preview しており、live article の surrounding wrappers までは比較していない

## 64432

Source:

- post id: `64432`
- source URL: `https://twitter.com/sanspo_giants/status/2051101291485733322`
- note: before は Lane OO / NN で確認済みの incident-family fallback。subject recovery は Lane QQ の scope 外

Before (`ENABLE_BODY_TEMPLATE_V2=0` family):

```text
【話題の要旨】
右アキレス腱炎からの復帰を目指す投手がブルペン投球を実施した。
【発信内容の要約】

【文脈と背景】
元記事の内容を確認中です。
【ファンの関心ポイント】
次の実戦につながるか気になります。
```

After (`ENABLE_BODY_TEMPLATE_V2=1` family):

```text
【話題の要旨】
右アキレス腱炎からの復帰を目指す投手がブルペン投球を実施した。
【投稿で出ていた内容】

【この話が出た流れ】
元記事の内容を確認中です。
【ファンの関心ポイント】
次の実戦につながるか気になります。
```

Check:

- removed strings:
  - `【発信内容の要約】`
  - `【文脈と背景】`
- preserved facts:
  - `右アキレス腱炎`
  - `復帰を目指す`
  - `ブルペン投球を実施`
- new fact: `0`
  - unresolved subject を補完していない
  - placeholder sentence も維持している
- H3/H4:
  - before = `H3 3 / H4 0`
  - after = `H3 2 / H4 1`
- residual risk:
  - `subject_still_unconfirmed_from_source_only`
  - empty section / placeholder family は別 lane 対応のまま
  - publishable rescue ではなく、phrase/H3 family 修正だけ

## Generic Representative

Source:

- theme: OB / commentary family
- representative title: `元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘れるくらい」`

Before:

```text
【ニュースの整理】
まずは今回のニュースで押さえておきたいポイントから整理します。
ボクシング世界戦を見て、ラウンド中に息をするのも忘れるくらいだったと語った。
【ここに注目】
元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘れるくらい」というテーマが、今回の見たいポイントです。
【次の注目】
ここで見ておきたいのは、単なる事実確認だけでなく、この動きが次の試合や起用にどうつながるかという点です。
ここでは元記事の事実を土台に論点を整理しました。続報が出れば見え方も変わるので、みなさんの意見はコメントで教えてください！
```

After:

```text
【ニュースの整理】
まずは今回のニュースで押さえておきたいポイントから整理します。
ボクシング世界戦を見て、ラウンド中に息をするのも忘れるくらいだったと語った。
【今回のポイント】
元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘れるくらい」というテーマが、今回の見たいポイントです。
【次の注目】
ここで見ておきたいのは、単なる事実確認だけでなく、この動きが次の試合や起用にどうつながるかという点です。
ここでは元記事の事実を土台に論点を整理しました。続報が出れば見え方も変わるので、みなさんの意見はコメントで教えてください！
```

Check:

- removed strings:
  - `【ここに注目】`
- preserved facts:
  - `上原浩治氏`
  - `井上尚弥`
  - `中谷潤人`
- new fact: `0`
  - summary sentence は unchanged
- H3/H4:
  - before = `H3 3 / H4 0`
  - after = `H3 2 / H4 1`
- residual risk:
  - baseball relevance / OB non-baseball 判定は Lane QQ scope 外

## Postgame Representative

Source:

- renderer: `src/rss_fetcher._render_postgame_strict_html`
- representative body:

```text
【試合結果】
4月21日、巨人が阪神に3-2で勝利しました。
【ハイライト】
岡田悠希が終盤に決勝打を放ちました。
【選手成績】
先発は7回2失点でまとめました。
【試合展開】
更新があれば見たいところです。
```

Check:

- removed strings:
  - none
- preserved facts:
  - `4月21日`
  - `巨人`
  - `阪神`
  - `3-2`
  - `岡田悠希`
  - `7回2失点`
- new fact: `0`
  - body text is unchanged; only heading level changes
- H3/H4:
  - before = `H3 3 / H4 0`
  - after = `H3 2 / H4 1`
- residual risk:
  - helper-card を含む full game article では wrapper 側の card heading も H4 化される。ここでは strict postgame renderer 単体 preview を示した

## Conclusion

- `ENABLE_BODY_TEMPLATE_V2=1` で social / generic / postgame representative のいずれも `H3<=2` を満たす
- forbidden heading family の rename は:
  - `【発信内容の要約】` → `【投稿で出ていた内容】`
  - `【文脈と背景】` → `【この話が出た流れ】`
  - `【ここに注目】` → `【今回のポイント】`
- fact / number / player name の追加は preview 上 `0`
- `64432` family の subject unresolved / empty section は未解消で、Lane QQ は意図通り template wording / heading level のみを直す
