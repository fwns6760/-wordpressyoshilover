# 022 — 複数 source 統合記事の agent テンプレ

**フェーズ：** AIエージェント版の高リスク記事整形  
**担当：** Codex B  
**依存：** 013, 014, 020

---

## 概要

正本要件は `docs/handoff/giants_agile_requirements.md` §5 / §7 / §9。親チケットは `doc/011` (`4dc0b2b`) / `doc/012` (`d50a0dc`) / `doc/014` (`2d92405`) / `doc/020`。※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`。

のもとけ型では、1 本の話題を複数の source で束ねて出す記事が強い。
このチケットでは、`複数 source 統合記事` を AIエージェント版で安全に処理するためのテンプレを固定する。

---

## 決定事項

### 対象記事

- 代表パターン:
  複数媒体の同一話題整理、公式 + 媒体 + X の突き合わせ、契約 / 故障 / トレードなどの状況整理を対象にする。`postgame` の派生整理や `fact_notice` の状況整理でも使う。
- 境界:
  単一 `primary tier` で `doc/011` の固定版レーンに収まる記事はここへ入れず、複数 source の突き合わせが必要なものだけを AIエージェント版へ送る。`CORE_SUBTYPES` 自体は上位 doc に従い、本書では merge 対象の整形だけを固定する。

### テンプレ構造

- 事実核:
  `source_trust` は `doc/014` に従い、`primary tier` が存在する場合は title、主要事実、数字、見出しの正を `primary tier` に固定する。`rumor` / `unknown` は核に置かない。
- 追加 source:
  `secondary tier` は `primary tier` を上書きせず、補強引用と文脈補足だけに使う。`rumor` / `unknown` は単独採用禁止とし、`primary tier` 確認後の限定補足にとどめる。
- 重複排除:
  同一事実を複数 source が報じる場合は `source_id` で寄せ、同一群は最古 timestamp を親として 1 本化する。引用文の重複は statement 単位で整理し、同趣旨は 1 本に縮約する。
- 時系列整列:
  並び順は報道時刻ではなく事実発生時刻を優先する。情報追加は本文末尾への追記ではなく該当位置へ統合し、「続報」で節を分けるのは 1 日またぎだけにする。
- 本文ブロック順:
  `doc/011` の固定版テンプレとの整合を崩さず、`核事実 → primary 引用 → secondary 補足 → データ / 数値 → 出典ブロック → 関連タグ誘導 → まとめ` の順に置く。`doc/020` の `postgame` 派生でも同順を維持する。
- 断定禁止:
  `rumor` / `unknown` は断定せず、出典付きの限定表現にとどめる。出典ブロックには `primary tier` の URL + タイトル、`secondary tier` の URL + 媒体名だけを載せ、`rumor` / `unknown` は載せない。
- まとめ:
  読者が今何を理解すればよいかを最後に短く整理する。merge 後も 1 記事 1 核を崩さず、核を維持できない場合は `doc/020` の派生記事へ分離する。

### 非機能

- title だけ強く本文が薄い記事を作らない:
  merge しても本文は核事実、引用、補足、数値、出典までそろえ、素材メモ感の強い記事を作らない。
- 整合:
  `source_trust` は `doc/014`、固定版レーンとの差分は `doc/011`、`postgame` 派生と 1 核維持は `doc/020` を正本とする。本便で routing ルールや新 flag / 新 config は増やさない。
- 不可触:
  mail / automation / Gmail / SMTP / sendmail / scheduler / env / secret は触らない。`quality-monitor` / `quality-gmail` / `draft-body-editor` も不可触とし、published write はしない。

---

## TODO

### 対象記事

【×】複数 source 統合記事の代表パターンを列挙する  
【×】AIエージェント版で扱う境界を決める  

### テンプレ構造

【×】事実核の置き方を決める  
【×】secondary source の扱いを決める  
【×】rumor / unknown の断定禁止ルールを明記する  
【×】まとめ段落の役割を決める  

### 非機能

【×】title 先行で本文が薄くならない制約を明記する  
【×】014 との整合を明記する  
【×】mail / automation に触らないことを明記する  

---

## 成功条件

- 複数 source 記事の型が説明できる  
- source trust とテンプレが噛み合っている  
- AIエージェント版で扱う理由が明確  
