# 250-QA manager/player quote strict subset

## meta

- number: 250-QA
- type: quality / strict template backlog
- status: HOLD
- priority: P0.5
- owner: Meeting Codex / Claude planning
- implementation_owner: Codex B after GO
- lane: B after GO
- created: 2026-04-29
- depends_on: 247-QA-amend, postgame strict game-day observation
- related: 247-QA, 234-impl-5, 244 numeric guard

## purpose

247-QA の postgame strict 結果を見た後、監督コメント・選手コメントを短い事実記事として分離できるか検討する。

これは今すぐ実装しない。
247-QA の postgame strict を試合日に観察してから判断する。

## background

postgame 記事では、試合結果・スコア・勝敗・投手成績・コメントが混ざると、LLM 自由作文でハルシネーションが起きやすい。

247-QA は postgame strict slot-fill POC として、source facts JSON 抽出 + 固定 template render を試す。
250-QA はその結果を踏まえ、コメント系だけを strict subset として分ける構想。

## candidate subtype

- `manager_quote`
- `player_quote`

## principle

- コメント本文は source にある発言だけ
- 解釈や感情補完をしない
- スコアや勝敗を source/meta から確認できない場合は書かない
- 短い事実記事として成立する場合だけ検討

## non-goals

- いま実装しない
- 247-QA に混ぜない
- postgame strict の観察前に GO しない
- LLM に自由本文を書かせない
- Gemini 追加呼び出しを増やさない
- コメントを煽り記事にしない

## GO condition

- 247-QA amend が完了
- postgame strict が試合日に動き、失敗/成功パターンが見える
- コメント系を分けることで本文品質が上がる見込みがある
- user が manager_quote / player_quote の分離を承認

## HOLD condition

- postgame strict の挙動がまだ不明
- コメント source が安定していない
- subtype 増加でテンプレ複雑化しそう
- 短い事実記事としての価値が弱い

## one-line contract

コメント系は魅力があるが、247-QA の試合日観察後。短い事実記事として分けられる時だけ。デグレ厳禁。
