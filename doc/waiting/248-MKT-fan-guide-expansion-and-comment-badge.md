# 248-MKT fan guide expansion and comment badge

## meta

- number: 248-MKT
- type: marketing / fan engagement backlog
- status: HOLD
- priority: P1
- owner: Meeting Codex / Claude planning
- implementation_owner: TBD after 246-MKT observation
- lane: Front-Claude / Codex A after GO
- created: 2026-04-29
- depends_on: 247-QA-amend, postgame strict game-day observation, 246-MKT fan guide decision
- related: 246-MKT, 195/197, 244 numeric guard

## purpose

YOSHILOVER を「のもとけ型」に近づける段階構想として、ファンが読む・追う・反応する導線を検討する。

これは今すぐ実装しない。
247-QA amend 完了後、postgame strict の試合日観察を見てから、246-MKT の拡張として必要性を判断する。

## background

246-MKT は「今日の巨人ファン観戦ガイド」として、読者が今日読む順番を迷わないトップ導線を作る親チケット。
248-MKT はその次の拡張候補であり、記事一覧ではなくファンの滞在・回遊・会話を促す UX を検討する。

## candidate ideas

- コメント数 badge / 反応 badge
- 「よく読まれている」ではなく「今話したい」導線
- 試合前後の観戦ガイドから関連記事への回遊
- X 投稿から来た読者が次に読む記事への導線
- 二軍・若手・復帰組の継続ウォッチ導線

## caution

WP コメント本実装は moderation 負荷があるため慎重に扱う。

特に以下は HOLD:

- WP コメント欄の本格開放
- moderation queue 自動化
- 荒れやすい記事へのコメント誘導
- SNS 反応の自動収集
- X API 依存

## non-goals

- いま実装しない
- 246-MKT v0 に混ぜない
- 247-QA に混ぜない
- X API / インプレッション分析なし
- 高度な dashboard なし
- 機械学習なし
- 大規模 UI 改修なし

## GO condition

- 247-QA amend が完了
- postgame strict を試合日に観察
- 246-MKT v0 のトップ導線が「記事一覧」ではなく観戦ガイドとして成立
- user が「コメント/反応導線を検討してよい」と明示

## HOLD / rollback condition

- moderation 負荷が見えない
- コメント導線が煽りになりそう
- 記事品質がまだ安定していない
- 246-MKT が未検証
- user がマーケ導線より本文品質を優先している

## one-line contract

読む・追う・反応する導線は作る。ただし WP コメント本実装は慎重。デグレ厳禁。
