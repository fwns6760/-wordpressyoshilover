---
ticket: 248-MKT-2
title: single 記事下部「この試合の関連記事」(同 game 導線、PHP front-only narrow)
status: READY
owner: Codex A (front-scope)
priority: P1
lane: A
ready_for: codex_a_fire
created: 2026-04-29
related: 246-MKT v0 (top page 観戦ガイド、CLOSED)、245 (auto-post hide、CLOSED)
---

## 目的

短い事実記事を、**同じ試合単位で複数読める導線**にする。
集客施策ではなく、サイト品質と回遊の改善(のもとけ型「短い事実記事 × 同 game 回遊」の第一歩)。

## scope (narrow、PHP 1 file のみ)

### 1. 新規 helper / render(`src/yoshilover-063-frontend.php`)

#### 1-A. game_key 構築 helper(疑似 gid fallback)

```php
function yoshilover_063_resolve_game_key( $post ) {
    // 1段目: post meta game_id (既存 yoshilover_063_first_non_empty_meta reuse)
    $game_id = yoshilover_063_first_non_empty_meta( $post->ID, array( 'game_id', '_game_id' ) );
    if ( $game_id ) {
        return array( 'key' => (string) $game_id, 'source' => 'meta' );
    }
    // 2段目(fallback): 疑似 gid = date + opponent
    $blob = $post->post_title . ' ' . $post->post_excerpt;
    $opponent = yoshilover_063_front_density_extract_opponent( $blob );
    if ( ! $opponent ) {
        return null;  // opponent 不明 → silent skip
    }
    return array(
        'key' => get_the_date( 'Ymd', $post ) . ':' . $opponent,
        'source' => 'pseudo',
    );
}
```

#### 1-B. 同 game 記事収集 helper

```php
function yoshilover_063_get_same_game_articles( $post_id, $limit = 5 ) {
    $current_post = get_post( $post_id );
    if ( ! $current_post ) return array();
    $game_key = yoshilover_063_resolve_game_key( $current_post );
    if ( ! $game_key ) return array();

    // game_id meta 一致(優先)+ 疑似 gid 一致(補助)で WP_Query
    // gameish subtype のみ、自分除外、default/default_review/article/notice 単体/review 系除外
    // publish_time 新着順、最大 $limit 件
    // 既存 yoshilover_063_is_gameish_subtype + yoshilover_063_filter_front_category_terms (auto-post 除外) reuse
}
```

#### 1-C. render 関数

```php
function yoshilover_063_render_same_game_articles_box( $post_id ) {
    if ( ! is_singular( 'post' ) ) return '';
    $items = yoshilover_063_get_same_game_articles( $post_id, 5 );
    if ( empty( $items ) ) return '';  // 0件 → 非表示
    // 「この試合の関連記事」見出し + 3-5 件 list
    // class: yoshi-front-same-game-articles* (既存 prefix 整合)
    // mobile breakpoint inline CSS
}
```

#### 1-D. the_content filter で single 記事下部に注入

```php
function yoshilover_063_inject_same_game_articles( $content ) {
    if ( ! is_singular( 'post' ) || ! in_the_loop() || ! is_main_query() ) return $content;
    $box = yoshilover_063_render_same_game_articles_box( get_the_ID() );
    return $content . $box;
}
add_filter( 'the_content', 'yoshilover_063_inject_same_game_articles', 50 );
```

### 2. 既存 helper reuse(必ず)

- `yoshilover_063_first_non_empty_meta()` (game_id 取得)
- `yoshilover_063_front_density_extract_opponent()` (opponent 抽出)
- `yoshilover_063_is_gameish_subtype()` (line 3633、対象 subtype 判定)
- `yoshilover_063_filter_front_category_terms()` (245、auto-post 除外)
- `get_the_date('Ymd', $post)` (疑似 gid 構築)

### 3. 表示順

- MVP: **publish_time 新着順**(WP_Query orderby=date DESC)
- subtype 順 編集ロジックは後段(別 ticket)

### 4. game_id 優先 / 疑似 gid 補助

- WP_Query は 2 段:
  - 段 1: meta_query で `game_id` exact match → 該当 list 集約
  - 段 2: 該当 0 件なら 疑似 gid (date + opponent) で再 query(meta_query 拡張 or title contain)
  - 段 1 結果 + 段 2 結果 を merge dedupe(post_id 重複除外)
- game_id ある記事を最優先、疑似 gid は補助扱い

## 不可触 (絶対に touch しない)

- src/rss_fetcher.py / src/python 系すべて
- src/tools/* / tests/* (PHP unit test なし、php -l + 手動 SP のみ)
- src/yoshilover-063-frontend.php 以外の PHP file
- WP DB / category 削除 / 投稿本文 / 投稿ステータス変更
- WP コメント機能本格 enable / コメント数 badge 追加(本 ticket scope 外、user 明示)
- 246-MKT 観戦ガイドへの混入(top page 系、本 ticket は single 系で disjoint)
- 大規模 UI 改修
- Cloud Run / Scheduler / Gemini / X API / Gmail / publish gate / WP REST 設定変更
- env / Secret / RUN_DRAFT_ONLY
- 247-QA / 247-QA-amend と同 file 触らない(disjoint)

## デグレ防止 contract

- single 記事下部のみ(`is_singular('post')` guard 必須)
- top page / archive / sidebar / 246-MKT 観戦ガイド表示に影響 0
- 0 件で graceful hide(空 box / 見出しだけ残らない)
- 自分自身除外(post_id 重複除外)
- 疑似 gid 誤マッチング抑止: game_id ある記事 優先 + 疑似 gid 補助
- mobile 崩れ防止: 既存 `yoshi-front-` prefix CSS 整合 + inline mobile breakpoint
- 既存 fixture / WP 動作 影響 0
- php -l 0 error
- 247-QA amend と差分衝突なし(別 file scope)

## acceptance (3 点 contract)

1. **着地**: 1 commit に src/yoshilover-063-frontend.php のみ stage、git add -A 禁止
2. **挙動**: php -l pass、single 記事下部にのみ表示、0 件で非表示、自分自身除外、gameish 限定、notice 単体・review 除外、mobile 崩れなし
3. **境界**: 247-QA amend / Python / Cloud Run / Scheduler / Gemini / X API / Gmail / publish gate / WP REST すべて不変、246-MKT / sidebar / top page 表示変化なし

## commit message

`248-MKT-2: same-game articles linking on single post (PHP front-only, game_id meta + pseudo gid fallback)`

## 完了後の Claude 判断事項

- pytest なし(PHP のみ)、php -l + 既存 helper 関数 signature 不変 確認のみ
- push
- live 反映: WP plugin reload 不要、PHP OPcache 残留時のみ purge
- 実 SP 表示確認は user 手動

## non-goals

- top page / 246-MKT 観戦ガイドへの混入
- コメント数 badge / コメント機能 enable
- subtype 順 編集ロジック(MVP は新着順、別 ticket)
- 疑似 gid の精度向上(現 date + opponent で十分、長期は game_id 普及で疑似不要に)
- WP category 新規作成
- PHP unit test 追加(WP 環境必須、scope 外)
