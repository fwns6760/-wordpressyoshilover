# 450 MARKETING 動画・昔ネタ・懐かしネタ レーダー (発見導線)

## 1. ticket header

- **ticket id**: 450
- **status**: DOC_ONLY / DESIGN (整理のみ。 実装・deploy・env 変更なし)
- **owner**: Claude Code
- **lane**: marketing / discovery (X 投稿候補)
- **created**: 2026-06-01
- **related**: 448 (data split 候補) / 449 (data content types) / 385 (YouTube caption) / 多 source digest
- **priority**: P2 (インプ拡大の発見導線。 data コンテンツ型 449 と相補)

## 2. 目的

YOSHILOVER で、 インプが出やすい「公式動画・昔ネタ・懐かしネタ」を **安全に見つけて** X 投稿候補に
する仕組みを整理する。 **目的は動画の転載ではなく、 公式動画を見つけて巨人ファン向けの見どころ・
データ・文脈を添えて紹介すること**。

## 3. 不可触・制約 (本 ticket 全体)

- 動画の無断転載・切り抜き再投稿は **しない**
- 公式動画・公式 X・公式 YouTube・**埋め込み可能な動画** を前提にする
- 非公式切り抜きチャンネルは **原則使わない**(例外は §7 参照: 紹介・言及・リンクのみ、 転載しない)
- 実装しない / deploy しない / env 変更しない / X API 使わない / Gemini call 増やさない / SEO・index 設定触らない
- 既存 policy 継承: youtube_ob_sources.json「Video articles must use source embeds, not copied media」/
  マスコミ X 引用は oEmbed のみ / 生成文の過度な類似回避

## 4. 安全な動画ソース棚卸し (repo 実地確認 2026-06-01)

| ソース | 種別 | repo 上の所在 (evidence) | 安全度 | 用途 |
|---|---|---|---|---|
| 読売ジャイアンツ公式 YouTube | 球団公式 | `config/youtube_video_sources.json` / `youtube_ob_sources.json` (channel UCXxg0igSYUp0tqdd6luPEnQ, `@yomiuri_giants`, role=official, status=confirmed) | ◎ 最優先 | 公式ハイライト・名場面・選手企画 |
| 読売ジャイアンツ公式 X | 球団公式 | `@yomiuri_giants` (handle 既知)。oEmbed で埋め込み紹介 | ◎ | 公式動画ツイートの紹介・引用 |
| 読売ジャイアンツ公式 Instagram | 球団公式 | `config/instagram_sources.json`「読売ジャイアンツ公式」 | ○ | 写真・短尺。紹介・言及 |
| DRAMATIC BASEBALL (日テレ系中継) | 放送公式 | `youtube_video_sources.json` (UCpj_nD9850tykDqIrjtIXdg, `@ntv_baseball`) | ○ | 中継ハイライト。埋め込み紹介 |
| DAZN ベースボール | メディア公式 | `youtube_video_sources.json` (UCyeDNNizMGbVsn_8Ttc3FIw, `@DAZNJapanBaseball`) | ○ | 好プレー紹介。X handle `@DAZNJPNBaseball` と混同しない |
| GIANTS TV | 球団系番組 | `src/viral_topic_detector.py` `_PROGRAM_MARKERS`、`source_youtube_extractor.py` で言及 | ○ | 番組・配信の紹介 |
| NPB 公式 YouTube | リーグ公式 | repo 未登録 (候補)。channel_id を web verify してから追加 | ○ (要 verify) | 公式名場面・記録動画 |
| OB 棚 (上原浩治の雑談魂 等) | OB 個人 | `config/youtube_ob_sources.json` (status=candidate 多数) | △ candidate | 懐かしネタ。confirmed のみ使用 |
| Yahoo スポーツナビ | メディア | `src/source_yahoo_lineup_extractor.py` 等 | ○ | 文脈付け・出典 (動画転載はしない) |

注: `youtube_video_sources.json` は `run_nomotoke_rss_card_draft.py --sources-file=...` の **dry-run pool のみ**で、
`rss_fetcher.py` からは読まれない (本線 publish に直結しない安全棚)。将来自動化はこの既存 dry-run 経路の延長で設計可。
「Unknown channels are not silently confirmed」= channel_id は web verify してから confirmed にする。

## 5. インプが出やすい動画ネタ型

下表。 反応理由は「巨人ファンの感情トリガー(懐古・期待・驚き・記念)」を軸に整理。

| 型 | 使うソース | X で反応される理由 | 投稿例 (文脈・データ添え) | 権利リスク | 手動運用可否 | 将来自動化可否 |
|---|---|---|---|---|---|---|
| 昔の名場面回顧 | 球団公式YT / 公式X / NPB公式 | 懐古・世代の共有記憶。引用RTで会話が伸びる | 「{年}の{選手}{場面}。今日の{試合}を見て思い出した人も。▶公式動画(埋め込み)」 | 低(公式埋め込み) | ◎ | ◎ 公式YT過去動画を日付/選手で引当 |
| 今日の試合とつながる過去動画 | 公式YT / 中継公式 | 「今日の延長線」で文脈が刺さる | 「今日{選手}が{記録}。{年}の同種シーンが公式に残ってます ▶」 | 低 | ◎ | ○ 当日games×公式動画タイトル突合 |
| 若手の過去ハイライト | 公式YT / GIANTS TV | 昇格・活躍で「過去の片鱗」需要 | 「{若手}の二軍/ドラフト時ハイライト。今の活躍と見比べ ▶」 | 低 | ◎ | ○ 昇格/初出場 trigger×動画 |
| 復帰/昇格とつながる動画 | 公式YT / 公式X | ニュース性×懐古の二段ブースト | 「{選手}一軍復帰。前回の好プレー動画(公式) ▶ 文脈: 直近{data}」 | 低 | ◎ | ○ roster変動 trigger |
| 守備・走塁・一瞬のプレー | 公式YT / 中継公式 | 短尺・分かりやすさで拡散しやすい | 「この{守備/走塁}は何度見ても。{選手} ▶公式」 | 低 | ◎ | △ プレー分類が要手動 |
| 二軍ハイライト | 公式YT / GIANTS TV | コアファン濃い、競合少 | 「ファーム{選手}の{場面}。一軍待望論 ▶」 | 低〜中(二軍動画の有無次第) | ○ | △ 二軍動画ソース限定 |
| 記念日/誕生日/移籍/登録と絡む | 公式YT / 公式X / OB棚 | カレンダー性で定期投稿化しやすい | 「本日{選手}の誕生日。代表的な{場面}動画(公式) ▶」 | 低 | ◎ | ◎ 誕生日/記念日 calendar×動画 |
| 現役選手の過去比較 | 公式YT | データ×映像で「成長/変化」が刺さる(449 と相補) | 「{選手}の{年}と今。フォーム比較 ▶ data: {split}」 | 低 | ○ | △ 比較対象の選定要手動 |
| OB/レジェンド懐かしネタ | OB棚(confirmed) / 公式YT | 世代直撃の懐古。RT/コメント伸びやすい | 「{OB}の{名場面}。今見ても規格外 ▶」 | 中(OB個人ch は confirmed のみ) | ○ | △ confirmed channel 限定 |

権利リスクの原則: **公式埋め込み(oEmbed)= 低**。 自前で動画ファイル/切り抜きを再アップ = **不可**。
OB 個人チャンネルは confirmed のみ、 かつ「紹介・リンク」まで(転載しない)。

## 6. 将来の仕組み案 (実装しない・構想のみ)

**video-nostalgia-radar (案)**:
- 既存 `run_nomotoke_rss_card_draft.py` の dry-run video pool 経路を延長。
- 公式 YouTube RSS (`feeds/videos.xml?channel_id=...`) + 公式 X (oEmbed) を **巡回(read-only)**し、
  各動画から **タイトル / 投稿日 / 選手名 / 対戦相手 / 一軍-二軍 / 記念日該当** を抽出。
- 当日の `games` / `lineups` / roster 変動 / 誕生日 calendar と突合して「今日の文脈」スコアを付与。
- X 投稿候補メール(既存 x-post-mail-lane)に **「今日の動画候補 3 件」** セクションとして出す。
  - 各候補: 公式動画 URL(埋め込み) + 巨人ファン向けの見どころ/データ/文脈の下書き + 権利チェック印。
  - **公開 X 自動投稿はしない**(候補=メールまで、 user が手で投稿)。§11 user 判断で将来昇格。
- Gemini を増やさない方針なので、 文脈付けは template + 既存 data(insight.db)由来で構成(LLM 必須にしない)。
- 安全ゲート: confirmed channel のみ / 転載検出(自前再アップは候補化しない) / oEmbed 可否チェック。

## 7. 非公式の扱い (user 補足「非公式でもいい」への整理)

- 原則は公式優先。 非公式を使う場合も **「紹介・言及・公式元へのリンク」まで**で、
  非公式切り抜き動画を **自前で再投稿しない**。
- 非公式チャンネルの動画を「見どころ紹介」する場合は、 可能な限り **公式の同一場面**を探して
  そちらを一次として紹介する(切り抜き依存を避ける)。
- 権利・炎上リスクが少しでも読めない素材は候補化しない(safe-by-default)。

## 8. 今週やる最小施策 (1 つだけ)

**「今日とつながる公式過去動画を 1 日 1 本、手動で X 紹介」**:
- 読売ジャイアンツ公式 YouTube から、 当日の試合・選手・記念日に **つながる過去動画を 1 本**選ぶ。
- 巨人ファン向けの見どころ + 1 行 data 文脈(449/448 の split 等)を添えて、 公式動画を **埋め込み紹介**でポスト。
- 完全手動・転載なし・公式のみ。 反応(インプ/RT)を 1 週間メモして、 §5 のどの型が効くか観測。
- これで「動画導線の効果検証」を最小コスト・最小リスクで回し、 効いた型を §6 自動化の優先度に反映。

## 9. next action

- §6 自動化 = **ticket 化済 → `doc/active/451-XPOST-video-radar-impl.md`** (2026-06-01 user 「チケット」)。実装は user GO 後
- (user 判断) §8 最小施策を今週手動で試すかは任意 (451 と独立)
- (Claude 自律・別便) NPB 公式 YouTube の channel_id を web verify して棚に追加(read-only 調査便)
- 本 ticket は DOC_ONLY。 実装着手は別 ticket で user GO 後
