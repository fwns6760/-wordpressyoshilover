# 040 — Codex repair playbook

**フェーズ：** Draft repair 運用の固定  
**担当：** Codex B  
**依存：** 030, 032, 033, 034, 036 accepted

---

## 概要

- Gemini 2.5 Flash / Gemini Flash の初稿に対して、Codex がどう直すかの実務手順を固定する。
- 目的は「名文への全面改稿」ではなく、**壊れた Draft をのもとけ型の安全なテンプレへ戻すこと**。
- fixed lane と agent lane で repair 権限を分け、`hallucination` を出さずに `accept_draft / repair_closed / escalated` を安定判定できる状態を作る。

## why_now

- 036 で prompt contract、038 で ledger / promotion loop は固まったが、その中間にある **Codex repair の実務手順** が未固定。
- 今のままだと、同じ fail tag でも便ごとに直し方が揺れ、`repair_closed` と `escalated` の判断が人依存になる。
- のもとけ型に寄せるには、文体模写ではなく **fact-first / template-first / source-first** の repair playbook が必要。

## purpose

- fail tag ごとの repair action を固定する。
- fixed lane は `minimum-diff`、agent lane は条件付き全文再構成可、という境界を固定する。
- title 修正や fact 修正時の `source 再確認 / 検索` ルールを固定し、`hallucination` を防ぐ。

## 決定事項

### repair の目的

- repair の目的は「読み物として美しくすること」ではなく、**再訪理由のある安全な Draft に戻すこと**。
- 優先順位は `事実整合 > title-body 整合 > テンプレ整合 > attribution > 可読性 > 文体` とする。
- source にない情報は追加しない。

### 正とするもの

- 正の基準は `source facts` と `subtype template`。
- title は本文核に従う。title が強くても本文核が弱ければ本文核を正とする。
- 本文は感想ではなく `fact block` の並びを正とする。

### lane 別 repair 権限

- **fixed lane**
  - `minimum-diff` を原則とする。
  - block / sentence / attribution / title の局所修正だけを許可する。
  - 全文書き直しは不可。
- **agent lane**
  - source が揃っていて `hallucination` が入らない場合に限り、全文再構成を許可する。
  - ただし、のもとけ型の `fact-first / template-first / source-first` を崩さない。
  - source 不在の補足や推測の肉付けは禁止。

### repair の順番

repair は必ず次の順で行う。

1. `subtype_boundary`
2. `fact_missing`
3. `title_body_mismatch`
4. `thin_body`
5. `attribution_missing`
6. `abstract_lead`
7. `ai_tone / close_marker / tags_category_minor`

### fail tag ごとの repair action

- `subtype_boundary`
  - template を正にして block を戻す。
  - 記事の核自体が別 subtype なら sentence 修正でごまかさず `escalated` 候補とする。
- `fact_missing`
  - source にある事実だけを補う。
  - 事実核が source 上で不足しているなら、補完せず reroll 判定へ進む。
- `title_body_mismatch`
  - まず本文核を確認する。
  - 本文核が正しければ title を合わせる。
  - 本文核が曖昧なら title 修正だけで閉じない。
- `thin_body`
  - required block を補う。
  - ただし説明を膨らませるのではなく、欠けた fact block を埋める。
- `attribution_missing`
  - 出典 block / attribution 文だけを追記する。
  - 本文の意味は書き換えない。
- `abstract_lead`
  - 冒頭 1〜2 文を fact-first に置換する。
  - 感想 / 抽象論 / 総括から始めない。
- `duplicate`
  - 本文修正しない。
  - `candidate_key / route / source_id` 側の問題として扱い、repair では閉じない。
- `low_assertability`
  - 推測補完しない。
  - safe fallback か `escalated` に回す。
- `close_marker`
  - 単発の文体修正で閉じず、038 / 035 の観測ルールに従う。

### source 再確認 / 検索ルール

- `title 修正`
  - 本文核と source が明確なら、検索なしで修正してよい。
  - 本文核が曖昧なら source を再確認する。
- `fact 修正`
  - 事実修正は source 確認を前提とする。
  - source が記事材料に含まれているなら、その source を正とする。
  - source が弱い / 不足しているなら、同系統 source の再取得または再確認を行う。
- `検索してよい場面`
  - title と本文のどちらが正しいか判定できない
  - コメント記事で `誰が / どこで / 何を言ったか` が曖昧
  - 怪我状況で断定の強さが怪しい
  - スコア / 日付 / 対戦 / 公示種別などの fact が揺れている
- `検索不要の場面`
  - block 順の修正
  - attribution 追加
  - AI tone / abstract lead の除去
  - source が明示されている番組情報 / 公示 / 予告先発の title 整形
- `検索しても確定できない時`
  - 推測補完せず、`hold / reroll / escalated` に回す。
- `禁止`
  - 検索せずに推測で埋める
  - source にない背景補足を加える

### comment / injury 系の assertion

- コメント記事は fixed lane で `公式 source` / `主要媒体引用` / `TV・ラジオ発言まで` を許可する。
- コメント記事は **誰が / どこで / 何を言ったか** を本文先頭近くに明示する。
- 怪我状況の断定は fixed lane では `球団公式発表 + 監督・コーチコメントまで` とする。
- `主要紙報道` の怪我情報は agent lane 側へ回し、fixed lane では断定しない。

### title / body の要件

- title は `fact-first` を基本とし、少し引きのある表現は許可する。
- ただし煽りは禁止し、本文核から外れないことを条件にする。
- body はのもとけ型のように、先頭 2〜4 行で「何が起きたか」が分かることを正とする。

### reroll / accept / repair_closed / escalated

- `reroll` は中間 action であり、最終 outcome ではない。
- reroll 後に validator / review を満たせば `accept_draft` または `repair_closed`。
- 単発 fail は `repair_closed` で閉じる。
- 再発 fail、route 誤り、source 不足、subtype 不一致は `escalated` 候補とする。
- 1 Draft に対する Codex repair は原則 1 回までとし、同じ Draft を何度も人力でこね回さない。

### accept 条件

上位 3 条件は次で固定する。

1. `事実が合っている`
2. `titleと本文が一致`
3. `テンプレに収まる`

補助条件:

- コメント / 怪我記事は source が本文先頭近くで見える
- 記事に再訪理由がある
- のもとけ型の fact-first を外さない

### 非目標

- published 記事の改変
- SEO のための改稿
- source にない背景説明の追加
- reserve ticket の前倒し
- `hallucination` 込みの「それっぽい文章」生成

---

## TODO

【】repair の目的を `壊れた Draft を型へ戻すこと` と明記する  
【】`事実整合 > title-body 整合 > テンプレ整合 > attribution > 可読性 > 文体` の優先順を固定する  
【】fixed lane = `minimum-diff`、agent lane = 条件付き全文再構成可を固定する  
【】repair の順番を `subtype_boundary -> fact_missing -> title_body_mismatch -> thin_body -> attribution_missing -> abstract_lead -> ai_tone/close_marker` で固定する  
【】fail tag ごとの repair action を固定する  
【】title 修正 / fact 修正の source 再確認ルールを固定する  
【】検索してよい場面 / 検索不要の場面 / 確定できない時は直さない方針を固定する  
【】コメント記事の source 表示必須(本文先頭近く)を固定する  
【】怪我状況の断定範囲を `球団公式 + 監督・コーチコメントまで` に固定する  
【】`reroll` は中間 action、最終 outcome は `accept_draft / repair_closed / escalated` と明記する  
【】1 Draft に対する Codex repair は原則 1 回までと明記する  
【】accept 上位 3 条件(事実 / title-body / テンプレ)を固定する  

---

## 成功条件

- 別人の Codex が見ても同じ順番、同じ境界で repair を実行できる。
- fixed lane は局所補修、agent lane は条件付き全文再構成、という使い分けが一意に読める。
- `hallucination` を入れずに `repair_closed / escalated` を振り分けられる。
- title 修正や fact 修正で、いつ source 再確認が必要かが ticket 単体で読める。
- 036 の prompt hardening と 038 の ledger 運用の間を埋める正本 ticket になっている。
