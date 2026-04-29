# 246-MKT today giants fan guide

## meta

- number: 246-MKT
- type: marketing / front UX parent
- status: HOLD_DESIGN
- priority: P0.5
- owner: Meeting Codex / Claude planning
- implementation_owner: Codex A or front-scope Codex after GO
- lane: Front-Claude / Codex A after design approval
- created: 2026-04-29
- related: 245, 234 contract, 244 numeric guard, 195/197 article footer share

## one-line contract

検討は網羅。実装は最小。目的は記事一覧ではなく、巨人ファンの観戦ガイド。デグレ厳禁。

## purpose

YOSHILOVER のトップページに、巨人ファンが今日の試合・選手・二軍を追うための **今日の巨人ファン観戦ガイド** を作る。

これは新着記事一覧ではない。読者が 10 秒で以下を判断できる導線にする。

- 今日まず何を見ればいいか
- 試合前にどこを見れば楽しめるか
- 試合後に何を読めば気持ちを整理できるか
- 若手・二軍・復帰組で誰を追えばいいか

## marketing position

この施策は単なるトップページ改修ではない。
YOSHILOVER を **巨人ファンが試合前後に寄る場所** にするためのマーケ施策である。

| 場所 | 役割 |
|---|---|
| 公式サイト | 事実・発表・試合情報 |
| スポーツ紙 | 速報・コメント・ニュース |
| X | 感情・反応・雑談 |
| YOSHILOVER | 今日の見方を整理し、巨人ファンが試合を楽しむための導線 |

本 MVP の本質は、記事を見せることではなく、**巨人ファンの試合前後の気持ちを受け止める導線を作ること**。

## HOLD condition

現時点では UX 仕様を固める段階であり、現場 Claude / Codex への実装依頼は HOLD。

実装前に以下を確定する。

1. 読者に見せる価値
2. 表示してよい記事タイプ
3. 表示しない記事タイプ
4. 汎用タイトル・弱いタイトルの除外条件
5. notice 系の扱い
6. `今見る1本` の選定ルール
7. `today_giants_pick=main/hide` を MVP v0 に入れるか
8. 既存 `today giants box` との二重表示回避方法

## MVP v0 UX

### 表示構成

1. `今見る1本`
2. `まず見る`
3. `試合後に読む`
4. `若手・二軍を追う`
5. `今日のチェック` optional / 小さめ

### 読者シーン

#### 試合前の朝から昼

- 今日試合があるか
- 予告先発は誰か
- 見どころは何か
- 公示や復帰で試合の見方が変わるか
- 二軍や若手で追うべき選手がいるか

#### スタメン発表後

- 今日のスタメン
- 打順の注目
- 先発投手
- 誰が戻った / 外れたか

#### 試合直前

- 何を見れば試合が面白くなるか
- 今日の注目選手
- スタメンの意味
- 直前の変更があるか

#### 試合後すぐ

- 勝った / 負けた理由
- 分岐点
- 監督 / 選手コメント
- 明日どう見るか
- 二軍や若手の収穫

#### 翌朝

- 昨日の試合をどう整理すればいいか
- 今日の試合に何がつながるか
- 二軍 / 若手で見落としがないか

#### 試合がない日

- 今日は何を追えばいいか
- 二軍、若手、復帰組、公示、番組
- 次の試合に向けた材料

## Display rules

### 表示してよい subtype

- `まず見る`: `lineup`, `pregame`, `probable_starter`
- `試合後に読む`: `postgame`, `game_result`, `coach_comment`, `player_comment`
- `若手・二軍を追う`: `farm_lineup`, `farm_result`, `farm_player_result`, `farm`
- `今日のチェック`: `roster_notice`, `injury_recovery_notice`, `program_notice`

### 表示しない

- `default`
- `default_review`
- `article`
- `notice` 単体
- subtype 不明
- review / hold / 要確認系
- source 確認が弱い記事
- センシティブ判定あり
- 内部カテゴリ / 自動投稿カテゴリ
- `today_giants_pick=hide`

## 今見る1本

`今見る1本` は最新記事ではない。編集意図である。

優先順位:

1. `today_giants_pick=main`
2. スタメン発表後なら `lineup`
3. 試合前なら `probable_starter` / `pregame`
4. 試合後なら `postgame` / `game_result`
5. 試合がない日なら `farm_result` / `farm_player_result` / `program_notice`
6. notice 系は条件付き

## Reader labels

subtype 名は読者に見せない。

| subtype | 表示ラベル |
|---|---|
| `lineup` | スタメン確認 |
| `pregame` | 試合前の見どころ |
| `probable_starter` | 予告先発 |
| `postgame` | 試合後の整理 |
| `game_result` | 試合結果 |
| `coach_comment` | ベンチの見方 |
| `player_comment` | 選手コメント |
| `farm_result` | 二軍結果 |
| `farm_lineup` | 二軍スタメン |
| `farm_player_result` | 若手・二軍メモ |
| `farm` | 二軍・若手 |
| `roster_notice` | 登録・抹消 |
| `injury_recovery_notice` | 復帰・コンディション |
| `program_notice` | 番組・配信 |

## Weak title exclusion

MVP ではタイトルを書き換えない。AI で補完しない。

明らかに弱い title は非表示にする。

- 12文字未満
- `実戦で何を見せるか`
- `何を見せるか`
- `注目ポイント`
- `今後に注目`
- `詳しくはこちら`
- `試合の詳細はこちら`
- `結果のポイント` だけに近い
- `選手の適時打`
- `先発の 投手`
- 空の `【】`
- `速報` だけ
- `まとめ` だけ
- 巨人 / 選手名 / 対戦相手 / 公示語 / 試合語のどれもない

## Wireframe

```text
今日の巨人
今日見る記事を、試合前・試合後・若手でまとめました。

今見る1本
[ラベル] [HH:mm] 記事タイトル

まず見る
[HH:mm] スタメン確認 記事タイトル
[HH:mm] 予告先発 記事タイトル
[HH:mm] 試合前の見どころ 記事タイトル

試合後に読む
[HH:mm] 試合結果 記事タイトル
[HH:mm] ベンチの見方 記事タイトル
[HH:mm] 選手コメント 記事タイトル

若手・二軍を追う
[HH:mm] 二軍結果 記事タイトル
[HH:mm] 若手・二軍メモ 記事タイトル
[HH:mm] 復帰・コンディション 記事タイトル

今日のチェック
[HH:mm] 登録・抹消 記事タイトル
[HH:mm] 番組・配信 記事タイトル
```

## Degrade prevention

- 既存の記事生成フローに影響させない
- 既存の通知フローに影響させない
- 既存の X 投稿候補生成に影響させない
- Cloud Run / Gemini / X API / Gmail / Scheduler に差分を出さない
- `src/yoshilover-063-frontend.php` だけで済むか優先確認
- 既存 `today giants box` と二重表示しない
- `php -l src/yoshilover-063-frontend.php` 必須
- SP 表示崩れを必ず確認
- 空データ時にトップが壊れないことを確認
- title は書き換えない
- excerpt / AI要約 / AI見出し再生成は使わない

## Claude management prompt

```text
246-MKT は会議室Codexで作成済みの UX / marketing parent ticket です。

目的:
YOSHILOVER を「巨人ファンが試合前後に寄る場所」にする。
新着記事一覧ではなく、読者が10秒で今日の見方を判断できる観戦ガイドを作る。

Claude の役割:
- 開発しない
- src/testsを編集しない
- commitしない
- UX仕様のHOLD/GOを管理する
- user承認後に Codex A / front-scope へ実装依頼する
- scope外に逸れたら差し戻す

HOLD:
- userがUX仕様を承認するまで現場実装に出さない

GO後の管理:
- 実装scopeは src/yoshilover-063-frontend.php を最優先
- Cloud Run / Scheduler / Gemini / X API / Gmail / publish gate は触らせない
- 既存 today giants box と二重表示させない
- php -l を必須にする
- SP表示確認を必須にする

合言葉:
検討は網羅。実装は最小。目的は記事一覧ではなく、巨人ファンの観戦ガイド。デグレ厳禁。
```

## Codex implementation prompt (use only after UX GO)

```text
246-MKT: 今日の巨人ファン観戦ガイド v0 を実装してください。

重要:
これは新着記事一覧ではありません。
巨人ファンが試合前後に「今日どこを見ればいいか」を10秒で判断するための観戦ガイドです。

対象:
- src/yoshilover-063-frontend.php を最優先
- 既存の yoshilover_063_get_today_giants_box_items()
- 既存の yoshilover_063_render_today_giants_box()
- 既存の yoshilover_063_resolve_front_density_subtype()

禁止:
- Gemini追加呼び出し
- X API
- X自動投稿
- AI要約生成
- AI見出し再生成
- excerpt使用
- Cloud Run / Scheduler / Secret変更
- 投稿ステータス変更
- 既存記事本文変更
- Gmail通知変更
- publish gate変更
- 大規模UI改修

検証:
- php -l src/yoshilover-063-frontend.php
- トップで表示確認
- single記事で出ないこと
- 空データ時に非表示
- SPで崩れないこと
- 同じ記事が重複表示されないこと
- 既存 today giants box と二重表示しないこと

デグレ厳禁。
```
