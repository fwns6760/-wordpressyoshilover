# 410-FRONT-ob-farm-category-display

## 1. ticket header

- **status**: DRAFT (408 / 409 の subtype 名 lock 確定後、 着手可能)
- **priority**: P3 (front 表示、 publish が先)
- **owner**: Claude / **lane**: Claude
- **依存**: [[407]] design lock + [[408]] subtype 名 / [[409]] subtype 名 lock
- **設計 anchor**: `docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md` §4.6

## 2. ゴール

WordPress フロント / 記事ページに OB / farm2 / farm3 subtype を可視化する。 category slug 新設 / subtype badge / 出典帯 format / archive page の設計と (READONLY での) 実装案確定。 **本 ticket では WP REST mutation は行わない、 設計と staging 目視 read-only のみ。**

## 3. 実装 scope

### 3.1 category slug 設計 (確定 → WP admin 作業は user 判断)

| category | slug | parent | noindex |
|---|---|---|---|
| OB / 元巨人 | `ob` | 既存 `column` 配下 or top-level (user 判断) | 維持 (現フェーズ noindex) |
| 2軍 | `farm2` | 既存 `farm` を維持 + その下に `farm2` を作るか、 `farm` を `farm2` に rename するかの 2 案 (user 判断) | 維持 |
| 3軍 | `farm3` | 既存 `farm` 配下 (新規) | 維持 |

- **本 ticket では WP admin 作業を実行しない**、 案を [[doc/active/CATEGORY-RESTRUCTURE-2026-05-08.md]] と並走する形で user 判断材料を整備する
- 既存 published 記事の category 一括書き換えは禁止 (WP REST mutation 禁止)

### 3.2 subtype badge 表示

WP テーマ側 (別 repo / WP admin) で、 記事ページに subtype badge を表示する設計:

- OB: `元巨人` badge (赤系)
- farm2_result: `2軍速報` badge (青系)
- farm2_lineup: `2軍スタメン` badge (青系)
- farm3_practice: `3軍練習` badge (緑系)
- farm3_player: `3軍選手` badge (緑系)

実装方式:
- (A) WordPress テーマの single.php で post_meta から subtype を読み、 PHP template で badge 生成
- (B) yoshilover-fetcher が draft 生成時に `<div class="nomotoke-subtype-badge">2軍速報</div>` を本文先頭に inject (CSS は既存テーマに追加)

推奨: **(B) draft 生成側で inject** (WP テーマ改修コストが低い、 既存 `nomotoke-source-excerpt__heading` と同パターン)

### 3.3 出典帯 format (本文末尾)

`src/source_attribution_validator.py` の format function で subtype 別に出典帯を構成:

```html
<div class="nomotoke-source-attribution nomotoke-source-attribution--ob">
  <span class="ob-label">元巨人 / 現所属 ◯◯</span>
  <span class="source-label">出典: ◯◯◯</span>
</div>

<div class="nomotoke-source-attribution nomotoke-source-attribution--farm2">
  <span class="farm-label">2軍 イースタン</span>
  <span class="source-label">出典: ◯◯◯</span>
</div>

<div class="nomotoke-source-attribution nomotoke-source-attribution--farm3">
  <span class="farm-label">3軍 (※非公式数値)</span>
  <span class="source-label">出典: ◯◯◯</span>
</div>
```

CSS は既存テーマに 3 class 追加。

### 3.4 archive page (`/category/<slug>/`)

- `/category/ob/` / `/category/farm2/` / `/category/farm3/` の archive page が **404 を返さない**ことを staging で目視確認
- 既存 `/category/farm/` は維持 (farm2 / farm3 の親 or alias)
- noindex meta は WP plugin (Gone Response 等は別件) で既存 noindex 設定を継承

### 3.5 関連記事 / 内部リンク

- OB 記事の関連記事に **同じ OB** の過去記事を優先表示 (現状 player_notice fallback 経路で薄い)
- farm3 記事の関連記事に **同じ育成選手** の過去 farm3 記事を優先 (2軍記事を混ぜない)
- 実装: `src/related_post_resolver.py` (or 相当 file) の subtype-aware 関連選定 logic に ob / farm2 / farm3 分岐追加 (既存 logic がある場合は path 特定 + 拡張、 ない場合は本 ticket では設計のみ → 別 ticket で実装)

## 4. 不可触範囲

- [[407]] §6 共通不可触範囲全部
- WP REST published 記事の category 一括書き換え
- WP admin category 作成 (user 判断、 本 ticket では案のみ)
- 既存 `/category/farm/` の archive 削除 (維持必須)
- WP テーマ PHP の改修 (推奨方式 B: draft 生成側 inject で WP テーマは触らない)
- index 解放 ([[251-SEO]] / 404→410 / [[project_seo_404_to_410_gone_response]] と整合、 本 ticket は noindex 維持)

## 5. 実行予定テスト

### 5.1 unit test (新規)

- `tests/test_subtype_badge_inject.py` (新規)
  - ob / farm2 / farm3 各 subtype で badge HTML が draft 本文先頭に挿入されるか
- `tests/test_source_attribution_format_ob_farm.py` (新規)
  - OB は「元巨人 / 現所属」併記、 farm3 は「3軍 (※非公式)」明示

### 5.2 regression

- 既存 subtype (postgame / lineup / player_notice 等) の本文構造に変化なし (badge 非対象 subtype は inject されない)
- 既存 source_attribution format の出力に変化なし

### 5.3 staging read-only

- staging WP で OB / farm2 / farm3 draft を 1 件ずつ生成 (RUN_DRAFT_ONLY 相当)
- 記事ページの badge / 出典帯 表示を目視確認
- archive page (`/category/farm/` 既存 + 新設候補) が 404 / blank を出さない
- **本番 WP は触らない**

## 6. STOP 条件

[[407]] §7 + 追加:

- WP テーマの PHP 改修が必要になった (推奨方式 B が破綻) → 即停止 + user 判断
- staging で badge / 出典帯 表示が崩れる → 即停止 + CSS 調整
- archive page が 404 を返す → WP admin 設定が必要 → user 判断
- 関連記事 logic が既存 file で見つからず scope 拡張が必要 → 設計のみで close、 実装は別 ticket

## 7. 受け入れ条件

- subtype badge inject の unit test 全 pass
- 出典帯 format の unit test 全 pass
- 既存 subtype の dry-run 出力に変化なし
- staging で OB / farm2 / farm3 draft の badge / 出典帯 が目視確認できる
- archive page 404 なし (staging)
- 本番 WP mutation なし
- commit 直列
