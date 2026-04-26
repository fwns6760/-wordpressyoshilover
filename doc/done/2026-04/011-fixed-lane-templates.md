# 011 — 固定版レーンの対象記事・テンプレート固定

**フェーズ：** 固定版レーン設計  
**担当：** Claude Code  
**依存：** 010

---

## 概要

Gemini 2.5 Flash で高速に Draft 化するため、固定版レーンに入れる記事タイプとテンプレートを固定する。
定型記事はここへ寄せ、Codex の消費を抑える。
正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §7 / §9。親チケットは `doc/010-giants-lane-routing.md`（commit `28d4968`）。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`

---

## 決定事項

### 対象記事

- 番組情報:
  巨人公式と関連番組 RSS の primary tier source を使う固定版レーン対象とする。
- 公示:
  `npb.jp` 公示と `giants.jp` お知らせの primary tier source を使う固定版レーン対象とする。
- 予告先発:
  `npb.jp` 予告先発と `giants.jp` の primary tier source を使う固定版レーン対象とする。
- 野球データ:
  NPB 公式スタッツと巨人公式の primary tier source を使う固定版レーン対象とする。
- 二軍成績 / 二軍結果:
  `giants.jp` の二軍試合情報と二軍順位の primary tier source を使う固定版レーン対象とする。
- 定型の試合前まとめ:
  `giants.jp` / `npb.jp` と前日試合要約を前提に、試合前状態の primary tier source で扱う固定版レーン対象とする。

### テンプレート

- 入力 source:
  A5 `src/source_trust.py` の `source_trust` は全記事で primary tier を前提とし、consumer wiring 時は A6 `src/source_id.py` の `source_id` 正規化を使って source を固定する。
- 番組情報:
  title は `[放送日MM/DD] [番組名] 放送予定`。本文は `日時 → 放送局 → 出演者 → 見どころ → 出典リンク`。最小タグは `番組名 / 放送日 / 番組`。
- 公示:
  title は `[選手名] [公示種別]`。本文は `選手名 → 公示種別 → 対象日 → 影響 → 出典リンク`。最小タグは `選手名 / 公示種別 / 公示 / 日付`。
- 予告先発:
  title は `[試合日MM/DD] 予告先発 巨人[投手] vs [対戦][対戦投手]`。本文は `日時 → 対戦カード → 両軍予告先発 → 直近成績 → 出典リンク`。最小タグは `投手名 / 対戦相手 / 試合日 / 予告先発`。
- 野球データ:
  title は `[軸: 選手名 or チーム] [統計指標]`。本文は `軸 → データ要点 → 補足解説 → 出典リンク`。最小タグは `選手名（該当時） / 統計種別 / 野球データ`。
- 二軍成績 / 二軍結果:
  title は `二軍 [日付] [対戦] [スコア]`。本文は `試合結果 → 好投打 → 次戦 → 出典リンク`。最小タグは `選手名 / 対戦相手 / 日付 / ファーム`。
- 定型の試合前まとめ:
  title は `[試合日MM/DD] 巨人[対戦カード]`。本文は `日時 → 対戦 → 予告先発 → 見どころ → 出典リンク`。最小タグは `対戦相手 / 日付 / 試合前`。
- タグと category:
  A7 `src/tag_category_guard.py` の `tag_category_guard` に合わせ、タグは target_low 15 以上かつ上限 20、category は `ALLOWED_CATEGORIES` の `試合結果 / スタメン / 選手情報 / その他` に収める。

### 運用

- Flash 単独で通す条件:
  すべての source が primary tier で、本文が既定テンプレートのブロック順に収まり、タグ数が 15〜20、category が `ALLOWED_CATEGORIES` 内、subtype が `CORE_SUBTYPES` の `pregame / postgame / farm / fact_notice / live_anchor` に確定していること。
- 固定版レーンでの subtype 運用:
  本チケットの 6 型は固定版レーンのうち `pregame / farm / fact_notice` を主対象とし、`postgame / live_anchor` は型安定と単一 source が満たせる場合のみ例外的に同条件で扱う。
- AIエージェント版へ差し戻す条件:
  `source_trust` が rumor / unknown を含む、`source_id` の統合が 1 本に定まらない、タグが 15 未満または 20 超、category が `ALLOWED_CATEGORIES` 外、subtype 境界が揺れる、複数 source 統合や post 文面整合が必要、title が template fallback になる場合は AIエージェント版へ回す。

---

## TODO

### 対象記事

【×】番組情報を固定版レーン対象として定義する  
【×】公示を固定版レーン対象として定義する  
【×】予告先発を固定版レーン対象として定義する  
【×】野球データを固定版レーン対象として定義する  
【×】二軍成績 / 二軍結果を固定版レーン対象として定義する  
【×】定型の試合前まとめを固定版レーン対象として定義する  

### テンプレート

【×】各記事タイプの入力 source を決める  
【×】各記事タイプの title template を決める  
【×】各記事タイプの本文ブロック順を決める  
【×】タグ付与の最小ルールを決める  

### 運用

【×】固定版レーンを Gemini 2.5 Flash 単独で通してよい条件を明記する  
【×】固定版レーンから AIエージェント版へ差し戻す条件を明記する  

---

## 成功条件

- 固定版レーンへ最初から入れる記事タイプが列挙されている  
- 各記事タイプのテンプレート項目が分かる  
- どこまで Gemini Flash 単独で通すかが明記されている
