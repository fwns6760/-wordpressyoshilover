---
ticket: 251-SEO
title: default noindex からの部分 index 解放戦略(後段相談、HOLD)
status: HOLD
owner: Claude (起票) / 後段 user 相談
priority: P2
lane: planning
ready_for: 247-QA 観察 + のもとけ型 段階展開後
created: 2026-04-29
related: 245 / 246-MKT v0 / 247-QA / 248-MKT-2 / 248-MKT-3a
---

## 背景

現状の noindex 構造:
- **`src/yoshilover-post-noindex.php`**: 個別記事 default noindex(WP post すべて)
- 編集者が `_yoshilover_index=true` meta を立てた記事だけ index 許可
- **`src/yoshilover-063-frontend.php` Phase 1**: hub page / comment pagination / replytocom / comment_feed の noindex(本体記事 robots は触らない方針)
- **`src/yoshilover-noindex.php`**: 限定 test 用補助

つまり実態は **「トップページ中心で index、記事単体は原則 noindex」** 運用。

## 現方針(2026-04-29 user 確認)

- のもとけ型「短い記事大量」は default noindex と SEO 面で相性悪い
- ただし 今は記事品質・導線・分類を整える段階、noindex 維持で問題なし
- index 解放を急ぐと弱記事 / review 系 / 短記事が検索に出る risk
- 後段 251-SEO で部分 index 解放戦略を別途相談

## 相談候補(HOLD、後段)

### A. どの subtype を index 候補にするか

候補:
- postgame strict 成功記事(247-QA observed PASS、fact 完備)
- game_result(scoreline 確定 + 試合終了 後)
- lineup(試合当日 + lineup 完備、ただし試合終了で stale)
- 編集者推奨記事(`_yoshilover_index=true` meta が既存 path)
- PV / コメント数閾値超え記事(WP analytics 連携必要)

### B. noindex 維持すべき記事

候補:
- default_review(review fallback 系)
- 弱 title 記事(`yoshilover_063_is_weak_title` true)
- review-flag 系(`【要確認】` prefix mail 倒し)
- short body(本文 < N 文字)
- auto-post カテゴリ
- subtype 不明 / unresolved
- past-date stale lineup
- 247-QA strict failure → review fallback の記事

### C. index 解放 trigger 設計

候補:
- 編集者手動(現状 `_yoshilover_index=true` meta)
- 自動 trigger:
  - 247-QA strict 成功 + body_validator pass
  - PV 一定閾値超(WP analytics or GSC 連携必要)
  - publish 後 N 時間経過 + コメント / SNS 反応あり
- 編集者承認 wait time(publish 直後は noindex、N 時間後 review してから index 解放)

### D. GSC(Google Search Console)観察方法

- 既存 GSC 連携状態確認
- index 状態 報告 / 検索パフォーマンス監視
- noindex 解放後の SEO 影響観察
- Search Analytics export → 集計 tool 化 検討

### E. 解放戦略の段階

候補 ramp:
1. 編集者推奨のみ(現状)
2. + 247-QA strict 成功 postgame
3. + game_result(scoreline 完備)
4. + farm_result(numeric 完備)
5. + lineup(試合当日)
6. + その他

### F. 具体実装案

- `src/yoshilover-post-noindex.php` の auto-index 判定追加
- 247-QA 成功 flag を post meta に保存し、index 候補化
- `_yoshilover_index_auto` meta(自動判定 path)+ `_yoshilover_index` meta(編集者 override)の 2 段
- WP 管理画面で「自動 index 候補」リスト表示

## 必須前提条件(HOLD 解除条件)

1. **247-QA observation 完了**(strict success rate / fact error rate / fallback rate 観察)
2. **のもとけ型 段階展開**(248-MKT-2 効果確認、248-MKT-3a 共通 helper 整備済)
3. **GSC 連携状態確認**(既存 search console データ取れるか)
4. **誤 index 解放時の rollback 経路明示**(`_yoshilover_index=false` 一括切替手順)

## 不可触

- 本 ticket は **HOLD planning only**、本日実装着手しない
- noindex policy / `yoshilover-post-noindex.php` / Phase 1 noindex は本日変更 0
- `_yoshilover_index` meta の自動付与は今は禁止
- GSC 連携 / SEO 設定変更は user GO 必須

## acceptance(将来本実装時、HOLD 解除後)

- 段階的 ramp(1 subtype ずつ index 解放、観察)
- 各段階で GSC 影響観察 1-2 週間
- false index 解放(弱記事を index した結果 SEO 悪化)1 件でも検出されたら即 rollback
- noindex 解除と同時に rollback 経路(`_yoshilover_index=false` 一括設定)を準備

## non-goals

- 本日 noindex policy 変更
- `_yoshilover_index` meta の自動付与実装
- GSC 連携の新規追加
- SEO 設定変更
- 247-QA / 246-MKT / 248-MKT-* と同時実装

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
