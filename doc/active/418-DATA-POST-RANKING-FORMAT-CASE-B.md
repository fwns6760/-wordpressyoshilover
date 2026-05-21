# 418 DATA-POST ranking format case B (1-10位 + 🟧巨人🟧 強調 + 改行)

## 1. meta

- **ticket id**: 418
- **GH Issue**: (起票後追記)
- **owner**: Claude Code (session 2026-05-21)
- **priority**: P2
- **status**: IN_FLIGHT
- **lane**: x-post-mail data ranking
- **created**: 2026-05-21
- **related ticket**: 417 (X-POST-MAIL Hochi/Sanspo piggyback)
- **related memory**: project_data_insight_aggressive_publishing / feedback_data_insight_user_preferences_2026_05_15

## 2. 背景

user 2026-05-21: 「選手のデータ post、 もっと表形式など使って出せないの？ post としては弱い」

現状 (`format_as_x_post.py`):
```
セ・リーグ・打率 ランキング 📊

1. 山田（東京）.328
2. 岡本（読売）.315 ← 巨人
3. 田中（広島）.298

#プロ野球 #巨人
```

弱い理由 (推定):
- header が控えめ (期間 / サンプル size が前に出てない)
- 順位 1/2/3 が点付きで視覚弱い
- 巨人強調が文末 「← 巨人」 のみで埋もれる
- 期間 context (「直近 5 試合 30+打席」) が見えない

## 3. 採用 format (case B)

```
📊 セ・リーグ 打率 TOP10 ⚾
直近5試合 / 30+打席

1位 山田（東京）.328
2位 岡本（読売）.315 🟧巨人🟧
3位 田中（広島）.298
4位 鈴木（横浜）.292
5位 佐藤（中日）.285
6位 高橋（DeNA）.281
7位 渡辺（神宮）.276
8位 中村（甲子園）.272
9位 木村（読売）.268 🟧巨人🟧
10位 林（ナゴヤ）.265

#プロ野球 #巨人 #セリーグ
```

**変更ポイント** (from 現状):
- header に 「TOP10」 + 期間 + サンプル を明示
- ranking 「1.」 → 「1位」 表記に変更 (= 視覚的に「順位」 と即認識)
- 巨人 player → 末尾 ← 巨人 → `🟧巨人🟧` で囲んで強調 (data post は rule-based なので 414 LLM 禁則 対象外)
- TOP3 → TOP10 拡張
- 期間 / サンプル を header 2 行目に分離

## 4. 不可触条件

- 既存 LLM voice post path (`x_post_branding_gen.py` の フーガ/缶詰) **完全不変**
- ticket 417 の rss_fetcher hook / queue / on-queue flow **不変**
- `_metric_label` / `_position_label` 等の既存 label dict **不変**
- 数値 format (`_format_value`) の precision rule (.345 / 2.85 等) **不変**
- DB query / rank result schema **不変**
- 280 字 hard cap (`_truncate_to_x_limit`) **不変**

## 5. 実行予定テスト

1. `_build_header` が新 format で TOP10 / 期間 / サンプル を出す
2. `_build_ranking_body` が 「1位/2位/.../10位」 で並ぶ
3. 巨人 player に `🟧巨人🟧` marker が付く、 非巨人は付かない
4. 280 字超過時の truncation 動作 (10 位まで入らないなら 5 位や 7 位に縮む)
5. focus_player (個別 player query) は変更なし (= ranking body 不適用、 既存 `_build_focus_body` 流用)
6. emoji `📊 ⚾ 🟧` が hashtag block と一緒に並ぶ

## 6. STOP 条件

1. 280 字 cap 内に TOP10 + header + hashtag が収まらない (大半の case で truncation 発生) → format 縮小
2. 既存 test (test_format_as_x_post.py 等) が新 format で fail し fixture 一斉修正が必要
3. user から「emoji 多すぎ」「順位表記変えて」 等の追加修正

## 7. 禁止事項

- 既存 LLM voice prompt 触らない
- ranking 以外の post type (focus_player / 単記事) format 変えない
- 数値 precision rule (.345 / 2.85 等) 触らない
- DB query 触らない
- WP REST API への書込みなし

## 8. 想定デグレ

- D1. 10 位までで 280 字超え → truncation で末尾欠ける → TOP6-7 までに自動縮小、 case B intent 維持
- D2. 巨人 player が複数行 `🟧巨人🟧` で hashtag 直前で truncate → 巨人 player が落ちる
- D3. 既存 ranking test の fixture が古い format 想定で全部 fail
- D4. `_format_value` で長い数値 (例: ER 100+ 等の counting stat) で 1 行 30 字超え → column 揃わない

## 9. 作業ログ

- `2026-05-21 17:50 JST | 418 起票 + IN_FLIGHT | next: format_as_x_post.py 修正`

## 10. Regression Memo

(着手後追記)

---

# 作業後 追記欄

(実装完了後埋める)
