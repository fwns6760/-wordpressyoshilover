# 016 — Claude Code / Codex A / Codex B のチケット分担表

**フェーズ：** 巨人版レーン運用の実行分担  
**担当：** Claude Code  
**依存：** 010〜015

---

## 概要

巨人版のチケットを、`Claude Code`、`Codex A`、`Codex B` に明確に割り振る。
目的は、会議室で止まらず、現場の 3 役が同時に動けるようにすること。

---

## 前提

- `Claude Code` = 管理人
- `Codex A` = 開発本線
- `Codex B` = 記事品質改善
- user は最終判断のみ

## 担当固定

### Claude Code

担当チケット:
- `010-giants-lane-routing.md`
- `011-fixed-lane-templates.md`
- `014-source-trust-and-taxonomy.md`
- `015-observation-and-acceptance.md`

責務:
- レーン分離の定義
- Gemini Flash 固定版の対象定義
- source trust / カテゴリ / タグ設計
- Observation Ticket 設計
- accept / reject
- Codex A / B への fire

### Codex A

担当チケット:
- `012-game-id-state-model.md`

責務:
- game_id / source_id 束ね
- 試合前 / 試合中 / 試合後 ステート管理
- 更新OSの土台になる実装

### Codex B

担当チケット:
- `013-agent-lane-review-loop.md`

責務:
- AIエージェント版レーンの review / repair ループ
- 高リスク記事の整形・修正の実装
- 既存 quality-monitor / draft-body-editor / quality-gmail との接続点整理

## 同時並走ルール

- Claude Code は常に 1 本の管理便だけを持つ
- Codex A と Codex B は同時に 1 本ずつまで fire できる
- 同じ write scope を同時に触らせない
- Claude Code は docs-only で止まらず、必要なら A/B どちらかに次便を流す

## 自動連鎖ルール

- `010` が accept + commit 完了したら、Claude Code は user 指示を待たずに `012` を `Codex A` へ fire する
- `011` が accept + commit 完了したら、Claude Code は user 指示を待たずに `013` を `Codex B` へ fire する
- 上流 ticket の完了確認は次の 3 条件で行う
  - TODO `【】` が 0
  - 対象 ticket の commit が完了
  - blocker が無い
- 上流 ticket が完了しても、同一 write scope 衝突がある場合だけ Claude Code は次便を保留できる
- 保留した場合は、理由と再開条件を handoff に短く残す

## 優先順位

1. `010` を確定し、完了後ただちに `012` を `Codex A` へ流す
2. `011` を確定し、完了後ただちに `013` を `Codex B` へ流す
3. `014` を taxonomy / source trust の管理仕様として固める
4. `015` で観測と accept / reject を固定する
5. `016` は役割表として運用実態に追随更新する

## TODO

【×】Claude Code の担当チケットを固定した  
【×】Codex A の担当チケットを固定した  
【×】Codex B の担当チケットを固定した  
【×】同時並走ルールを固定した  
【×】自動連鎖ルールを固定した  
【×】優先順位を固定した  

---

## 成功条件

- チケット単位で担当が明確  
- Claude Code / Codex A / Codex B の役割が重ならない  
- どのチケットを誰に流すか迷わない
