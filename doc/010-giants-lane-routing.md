# 010 — 巨人版レーン分離設計

**フェーズ：** 巨人版アジャイル運用の基礎  
**担当：** Claude Code  
**依存：** 001〜009 完了済みの既存基盤

---

## 概要

巨人版速報サイトを、`固定版レーン` と `AIエージェント版レーン` に分けて運用するための親チケット。
今の環境と体制を変えずに、どの記事をどちらへ流すかの基準を固定する。
正本要件は `docs/handoff/giants_agile_requirements.md` §7 / §8。本チケットはその巨人版チケット化。
※ handoff docs は別 repo `/home/fwns6/code/baseballwordpress/docs/handoff/` にある。

---

## 決定事項

### レーン定義

- 固定版レーンの目的:
  定型で安定した記事を Gemini 2.5 Flash 単独で高速に Draft 化する。
- 固定版レーンの目的:
  source 単一・型安定・subtype 固定の記事を review 無しで通す。
- 固定版レーンの目的:
  Codex の消費を抑え、AIエージェント版に review 資源を集中させる。
- 固定版レーンの対象:
  番組情報、公示、予告先発、野球データ、二軍成績 / 二軍結果、型が安定した試合前まとめ。
- AIエージェント版レーンの目的:
  揺れる記事・高リスク記事・複数 source を束ねる記事を Codex review / repair 通しで安全化する。
- AIエージェント版レーンの目的:
  Gemini 2.5 Flash 初稿 → Codex review → 必要なら repair の順で回す。
- AIエージェント版レーンの目的:
  Claude Code は route 判定・fire・accept / reject・次便起票を持つ。
- AIエージェント版レーンの対象:
  ライブ速報アンカー、試合中更新、試合後まとめ、故障 / 昇降格 / 契約 / トレード、複数 source 統合記事、subtype 境界が怪しい記事、post 文面整合が重要な記事。
- 役割固定:
  Claude Code は管理として route / fire / accept / reject / 起票 / handoff 更新を持つ。
- 役割固定:
  Codex A は開発本線として game_id / source_id / state / home 導線を担当する。
- 役割固定:
  Codex B は記事品質改善として review / repair / subtype 境界 / source trust 実装を担当する。
- 役割固定:
  user は stop / hold / publish / rollback / 方針分岐 / コスト増の最終判断だけを持つ。

### ルーティング

- 固定版レーンへ流す条件:
  5 テンプレ内であり、source が 1〜2 系統で明確であること。
- 固定版レーンへ流す条件:
  title / body / category / tag の型が安定し、subtype 境界が揺れていないこと。
- 固定版レーンへ流す条件:
  過去の fail pattern が少なく、定型のまま高速 Draft 化できること。
- AIエージェント版レーンへ流す条件:
  subtype 境界が怪しい、または source が複数であること。
- AIエージェント版レーンへ流す条件:
  タイトルだけ強く本文が弱くなりやすい、または X 依存が強いこと。
- AIエージェント版レーンへ流す条件:
  試合前 / 中 / 後の連鎖に含まれる、または post 文面も同時に整合確認したいこと。
- 保守ルール:
  曖昧記事、境界判定できない記事、subtype 境界が揺れる記事は必ず AIエージェント版レーンへ回す。
- 保守ルール:
  route 判定で迷った場合は安全側を優先し、固定版レーンには送らない。

### 非機能制約

- 既存メール設定:
  Gmail / SMTP / sendmail / 宛先 / prompt / scheduler / env / secret は今回触らない。
- automation 範囲:
  `quality-gmail` / `quality-monitor` / `draft-body-editor` の automation は今回触らない。
- published の扱い:
  published write は Phase 4 まで対象外とし、このチケットでは Draft 以前の route 固定だけを扱う。
- 追加変更の禁止:
  新しい abstraction / 新 flag / 新 config は追加しない。

### handoff

- handoff 反映先:
  Epic / Work Ticket 表の参照先は `/home/fwns6/code/baseballwordpress/docs/handoff/master_backlog.md`。
- handoff 反映先:
  今の焦点の参照先は `/home/fwns6/code/baseballwordpress/docs/handoff/current_focus.md`。
- handoff 運用:
  本チケットは参照先を明記するのみとし、handoff docs 自体の更新は Claude Code 側で扱う。

---

## TODO

### レーン定義

【×】固定版レーンの目的を 3 行で定義する  
【×】AIエージェント版レーンの目的を 3 行で定義する  
【×】Claude Code / Codex / user の役割をこのチケット上で固定する  

### ルーティング

【×】固定版レーンへ流す条件を箇条書きで固定する  
【×】AIエージェント版レーンへ流す条件を箇条書きで固定する  
【×】曖昧な記事を AIエージェント版へ送る保守ルールを明記する  

### 非機能制約

【×】既存メール設定を触らないことを明記する  
【×】`quality-gmail` / `quality-monitor` / `draft-body-editor` の automation を今回触らないことを明記する  
【×】published write をこの段階では対象外にすることを明記する  

### handoff

【×】結果を handoff に反映する対象ファイルを決める  

---

## 成功条件

- `固定版` と `AIエージェント版` の境界が文章で説明できる  
- どの記事がどちらへ流れるかを Claude Code が判断できる  
- 既存 mail / monitor / draft の chain を壊さない
