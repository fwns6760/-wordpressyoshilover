# 470 — X インプ・ブランディング計画 v2(Codex版 + Claude 追加)

- status: DESIGN → IN_FLIGHT
- owner: Claude
- created: 2026-06-03
- 関連: Codex v1 = mkdocs `spec/x-impression-plan`(12施策)/ 445 SNS realtime / 451 buzz radar / 469 schedule / x-post-mail-lane
- 目的: X インプレッション向上を、**既存スケジュール相乗り・¥0(新規 scheduler/Job/API 無し、Gemini は per-fire 上限8で頭打ち)** で実装する。Codex v1 は維持し、その上に Claude の新規角度を上乗せ。

## 不変のコスト方針(Codex v1 と一致)
- 新規 Cloud Scheduler / Cloud Run Job を作らない。
- X API 自動投稿/Basic tier に上げない(手動投稿のまま)。
- Gemini コール数を増やさない(per-fire 上限8内で配分が変わるだけ)。
- 既存 x-post-mail-lane の fire(469 で再構成: 7,9,11,13,15,16,17 + 試合18-21 15分 + 22)に相乗り。

## Claude 追加案(Codex v1 への上乗せ)

### ① 「今伸びてる投稿」momentum ランキング ★P1
- 各 fire は既に RSSHub buzz を取得済。**mention velocity(前日比/急上昇)で並べ替え**、候補メールに「今伸びてる投稿 TOP3」を注記。
- 人が集まってる投稿の下に入る=インプ最大化。velocity は SNS realtime state(`sns_realtime_topic_state`)が既に計算 → 流用。
- 実装: `build_video_radar_candidates` の buzz_counts に prev counts を渡し、候補に `momentum`(↑N)を付与。Gemini 不使用=¥0。

### ② 差別化テイク reply(媒体が書いてない data 視点)★P1
- reply 生成プロンプト(`build_quote_rt_comment`)に「**元投稿が触れていない data 視点を1つ足す**」指示 + 当該選手の insight.db fact を注入。
- 「報知は◯と書くが、直近5試合の数字はむしろ…」型。最も反応を生む「新視点」。
- 実装: `build_quote_rt_comment` に db_fact 引数 + プロンプト追記。**コール数同じ**=¥0。

### ③ ブランド画像 視覚一貫性 ★済(半分)
- B card(`x_post_brand_image`)を**シリーズ別に固定の見た目**で。「数字で見る巨人」「報知コメント深掘り」等に専用カード変種。視覚×言語の series identity でブランド想起。
- 実装: 既存 render に series variant 引数。PIL=¥0。

### ④ イベント・サージ・ライド(≤15分) ★P2
- 大プレー(HR/サヨナラ/初勝利/節目)発生 → **試合中15分fire**が次サイクルで buzz を拾い、reply 候補を優先。
- 「即」は新トリガ(=新infra/¥)を避け **「≤15分」**(既存15分fire)で実現。
- 実装: data-insight/postgame のイベント検知 signal を buzz 候補の優先度に反映。¥0。

### ⑤ ファンへのリプ(媒体だけでない)★P2
- 高エンゲージの**ファン投稿**にもヨシラバー視点でリプ → 媒体リプより自然にファン会話へ。
- **試合外 fire のみ**にファン source 追加(試合中は3ソース絞りを維持=コストキープ)。
- 実装: off-game の buzz handles にファン account を追加(config)。RSSHub 既存=¥0。

### ⑥ 1タップ効果記録 ★P1(摩擦ゼロ測定)
- Codex の手動「伸びた/普通/弱い」記録を、**候補ごとに1タップの mailto/計測リンク**に。週次で「効いた型」を集計→出す型を自動調整。
- API 不要・既存メールHTMLに足すだけ=¥0。Codex 案の「手動=続かない」弱点を補強。

## 実装順序
- P1: ⑥(1タップ記録、最も独立・低リスク)→ ①(momentum 並べ替え)→ ②(差別化テイク prompt)
- P2: ④(イベント優先度)→ ⑤(ファン source、off-game)→ ③(series variant card)
- 各 step: 改修 → test → x-post-mail-lane 1回 build/deploy → dry-run/翌日 verify。

## 不可触 / NG(Codex v1 準拠)
- 報知への大量リプ / 毎投稿に長い自己reply / 引用RT乱発 / ハッシュタグ増量 = 禁止(test/prompt に NG例)。
- 自動投稿は解禁しない(手動投稿のまま)。
- 試合中の3ソース絞り(469)を崩さない。

## 効果測定
- ⑥で「型別の伸び」を user 1タップ記録 → 週次で出す型を寄せる(API なし)。
- billing は不変(¥0 設計)を翌日実測で確認。
