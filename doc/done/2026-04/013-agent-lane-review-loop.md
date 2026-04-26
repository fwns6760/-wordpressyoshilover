# 013 — AIエージェント版レーンの review / repair ループ

**フェーズ：** 高リスク記事の安全運用  
**担当：** Codex B  
**依存：** 010, 011, 012

---

## 概要

高リスク記事は、Gemini 2.5 Flash の初稿をそのまま出さず、Codex の review / repair を通す。
Claude Code は route 判定、fire、accept / reject を持つ。
正本要件は `docs/handoff/giants_agile_requirements.md` §7 / §8 / §9。親チケットは `doc/010-giants-lane-routing.md`（commit `28d4968`）と `doc/011-fixed-lane-templates.md`（commit `4dc0b2b`）。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`

---

## 決定事項

### 対象記事

- ライブ速報アンカー:
  live state で 1 本を更新し続ける記事は、A4 `CORE_SUBTYPES` の `live_anchor` を使う AIエージェント版対象とする。`source_trust` が複数 source を含んでも primary tier 優先で本文整合を確認する。
- 試合中更新:
  試合中の差分追記は同じ `live_anchor` への部分更新、または派生 `fact_notice` として扱う AIエージェント版対象とする。打点 / 交代 / 公示は `source_id` 単位で差分確認し、固定版レーンへ戻さない。
- 試合後まとめ:
  試合後まとめは `CORE_SUBTYPES` の `postgame` を使う AIエージェント版対象とする。スコア / ハイライト / 選手コメントの統合を前提とし、`doc/011` の固定版レーン template から外れる複合記事として review を必須にする。
- 故障 / 昇降格 / 契約 / トレード:
  故障 / 昇降格 / 契約 / トレードは `CORE_SUBTYPES` の `fact_notice` を使う高リスク対象とする。primary tier source を必須とし、プライバシー / 差別 / 憶測の混入を Codex review で除去する。
- 複数 source 統合記事:
  公式 + X、primary + secondary など `source_trust` tier が混在する記事は AIエージェント版対象とする。rumor / unknown は採用せず、`source_id` で束ねた上で primary tier を本文優先順に置く。

### review / repair

- Codex review が見る観点:
  `source_trust` の primary / secondary / rumor / unknown の混在整合、A4 `CORE_SUBTYPES` の `pregame / postgame / farm / fact_notice / live_anchor` 境界、`doc/011` の固定版レーン本文ブロック順からの逸脱、title-body mismatch / thin body / AI tone / 感想 close、A7 `tag_category_guard` と `ALLOWED_CATEGORIES` 範囲、事実誤認 / プライバシー / 差別表現 / 著作権懸念を固定観点とする。
- Codex repair が触ってよい範囲:
  repair は Draft に限り、本文ブロック順の並び替え、title の再組み立て、A6 `src/source_id.py` の `source_id` と A7 `src/tag_category_guard.py` の範囲での source / tag / category 整理、冗長 / AI tone / 感想 close の除去までとする。source 不在の加筆、published 記事の書き換え、automation / env / secret の変更は不可とする。
- Claude Code の accept / reject 基準:
  accept は review 観点を全て満たし、primary tier 優先が保たれ、repair 後に fail pattern が残らないこと。reject は事実誤認 / プライバシー / 差別 / 著作権の疑義、または source が rumor / unknown のみの状態とし、境界案件だけを `stop / hold / publish / rollback` の最小判断で user へ上げる。

### 既存 chain との整合

- `quality-monitor` との接続:
  `quality-monitor` は既存の継続監査 job として現状維持し、本票では touch しない。AIエージェント版 review 結果は既存観測項目に干渉させず、consumer wiring 時の統合は `doc/015` 側で設計する。
- `draft-body-editor` との棲み分け:
  `draft-body-editor` は既存の本文編集補助 automation として現状維持し、本票では touch しない。AIエージェント版の review / repair は Flash 初稿の直後に回す別ループであり、`draft-body-editor` の後段ではなく、write scope も共有しない。
- `quality-gmail` への通知条件:
  `quality-gmail` は既存監査メール通知として現状維持し、本票では touch しない。AIエージェント版の reject 通知条件は将来の observation ticket として `doc/015` で定義し、この文書では「現状維持」を固定する。

---

## TODO

### 対象記事

【×】ライブ速報アンカーを AIエージェント版対象として定義する  
【×】試合中更新を AIエージェント版対象として定義する  
【×】試合後まとめを AIエージェント版対象として定義する  
【×】故障 / 昇降格 / 契約 / トレードを AIエージェント版対象として定義する  
【×】複数 source 統合記事を AIエージェント版対象として定義する  

### review / repair

【×】Codex review が見る観点を固定する  
【×】Codex repair が触ってよい範囲を固定する  
【×】Claude Code の accept / reject 基準を固定する  

### 既存 chain との整合

【×】`quality-monitor` とどう接続するかを明記する  
【×】`draft-body-editor` とどう棲み分けるかを明記する  
【×】`quality-gmail` への通知条件を明記する  

---

## 成功条件

- 高リスク記事がどのレーンを通るか明確  
- Codex review / repair の責務が明確  
- 既存 chain を壊さずに agent 版レーンへ接続できる
