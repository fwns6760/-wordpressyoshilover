# 082 Fan Reaction Precision Hardening

## 契約

- precision over recall
- no noisy reserve fill
- fan reaction は optional garnish
- 文脈一致が取れなければ 0 件でよい

## 目的

Yahoo リアルタイム検索由来の `fan reaction` で、今回の記事と無関係な投稿を無理に埋めない。
同名選手の雑談、首脳陣記事の一般応援、補強・移籍記事の名前一致だけの chatter よりも、空配列を優先する。

## 改修点

1. `_build_fan_reaction_queries(...)`
- `選手情報` / `首脳陣` / `補強・移籍` では subject 単体 query を出さない
- `subject + focus term` / `subject + quote term` / `subject + status term` / `subject + 巨人` を主軸にする

2. `_reaction_can_fill_shortage(...)`
- `_reaction_has_subject_context(...)` だけでは reserve に入れない
- reserve 採用には `topical hit` / `quote hit` / `status hit` / `category hit` のいずれかを必須にする
- 一般応援、誕生日、名前一致だけの雑談は reserve で補充しない

3. `_source_requires_precise_fan_reactions(...)`
- 誤拾いしやすい `首脳陣` / `補強・移籍` では precise context を常時要求する
- `選手情報` は既存どおり `X` / `公式` source を strict 対象に残す

4. テスト
- 同名でも話題不一致なら落とす
- 首脳陣の一般コメントを落とす
- 補強・移籍の名前一致 chatter を落とす
- 明確な quote / usage / transfer context は残す
- precise match が足りないときは空配列を返す
