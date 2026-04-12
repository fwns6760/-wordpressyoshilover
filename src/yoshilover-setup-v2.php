<?php
/**
 * Plugin Name: Yoshilover Setup v2
 * Description: ジャイアンツカラー・CSS・noindex・テーマ設定を一括適用。有効化で即実行。完了後は削除してください。
 * Version: 2.0
 */

// ──────────────────────────────────────────────────────────
// 有効化フック + init + admin_init + REST API トリガー
// ──────────────────────────────────────────────────────────
register_activation_hook( __FILE__, 'yoshilover_v2_run' );

// init: REST APIリクエスト含むすべてのリクエストで実行
add_action( 'init', function() {
    if ( get_option( 'yoshilover_v2_done' ) !== '1' ) {
        yoshilover_v2_run();
    }
} );

// admin_init でも実行（フォールバック）
add_action( 'admin_init', function() {
    if ( get_option( 'yoshilover_v2_done' ) !== '1' ) {
        yoshilover_v2_run();
    }
} );

// REST APIから直接トリガーできるエンドポイント
add_action( 'rest_api_init', function() {
    register_rest_route( 'yoshilover/v1', '/setup-v2', [
        'methods'             => 'POST',
        'callback'            => function() {
            delete_option( 'yoshilover_v2_done' );
            yoshilover_v2_run();
            return [
                'done'  => get_option( 'yoshilover_v2_done' ),
                'time'  => get_option( 'yoshilover_v2_time' ),
                'css_id'=> get_theme_mod( 'custom_css_post_id' ),
            ];
        },
        'permission_callback' => function() {
            return current_user_can( 'manage_options' );
        },
    ] );

    // キャッシュクリア専用エンドポイント
    register_rest_route( 'yoshilover/v1', '/clear-cache', [
        'methods'             => 'POST',
        'callback'            => function() {
            $results = [];
            // WP Rocket
            if ( function_exists( 'rocket_clean_domain' ) ) {
                rocket_clean_domain();
                $results['wp_rocket'] = 'cleared';
            }
            // SWELL キャッシュクリア
            if ( function_exists( 'swell_clear_cache' ) ) {
                swell_clear_cache();
                $results['swell'] = 'cleared';
            }
            // WordPress標準: 全ページキャッシュ削除
            if ( function_exists( 'wp_cache_flush' ) ) {
                wp_cache_flush();
                $results['wp_object_cache'] = 'flushed';
            }
            return $results;
        },
        'permission_callback' => function() {
            return current_user_can( 'manage_options' );
        },
    ] );
} );

// ──────────────────────────────────────────────────────────
// メイン処理
// ──────────────────────────────────────────────────────────
function yoshilover_v2_run() {

    // ① SWELLテーマmod設定
    yoshilover_v2_theme_mods();

    // ② カスタムCSS を適用
    yoshilover_v2_apply_css();

    // ③ テスト記事10本に noindex を設定
    yoshilover_v2_set_noindex();

    // ④ 完了フラグ
    update_option( 'yoshilover_v2_done', '1' );
    update_option( 'yoshilover_v2_time', current_time( 'mysql' ) );
}


// ──────────────────────────────────────────────────────────
// ① テーマmod設定（SWELLカスタマイザー設定）
// ──────────────────────────────────────────────────────────
function yoshilover_v2_theme_mods() {
    // WordPress 標準カラー設定
    set_theme_mod( 'background_color', 'F5F5F0' );
    update_option( 'background_color', 'F5F5F0' );

    // SWELL v4.x のカラーキー（複数候補を全部セット）
    $mods = [
        // メインカラー（オレンジ）
        'main_color'           => '#F5811F',
        'swell_color_main'     => '#F5811F',
        'color_main'           => '#F5811F',
        // テキストカラー
        'text_color'           => '#333333',
        'swell_color_text'     => '#333333',
        'color_text'           => '#333333',
        // リンクカラー
        'link_color'           => '#003DA5',
        'swell_color_link'     => '#003DA5',
        'color_link'           => '#003DA5',
        // 背景色
        'swell_color_bg'       => '#F5F5F0',
        'color_bg'             => '#F5F5F0',
        // ヘッダー背景（オレンジ）— color_header_bg がSWELLの正式キー
        'color_header_bg'      => '#F5811F',
        'header_bg_color'      => '#F5811F',
        'header_color'         => '#F5811F',
        'swell_header_bg'      => '#F5811F',
        'header_bg'            => '#F5811F',
        // フッター背景（オレンジ）
        'footer_bg_color'      => '#F5811F',
        'swell_footer_bg'      => '#F5811F',
        'footer_bg'            => '#F5811F',
        // 背景色（暖かみのあるオフホワイト）
        'color_bg'             => '#FFF8F0',
        // 見出しタグカラー
        'color_htag'           => '#F5811F',
        // 記事一覧レイアウト（リスト型）
        'archive_layout'       => 'list',
        'top_layout'           => 'list',
        'post_list_type'       => 'list',
        'swell_archive_layout' => 'list',
        'list_style'           => 'list',
    ];
    foreach ( $mods as $key => $val ) {
        set_theme_mod( $key, $val );
    }

    // SWELLのカスタマイザー設定を直接optionsに書く（バージョン対応）
    $swell_options = get_option( 'swell_theme_options', [] );
    if ( is_array( $swell_options ) ) {
        $swell_options = array_merge( $swell_options, [
            'color_main'       => '#F5811F',
            'color_link'       => '#003DA5',
            'color_bg'         => '#FFF8F0',
            'header_bg_color'  => '#F5811F',
            'footer_bg_color'  => '#F5811F',
            'list_type'        => 'list',
        ] );
        update_option( 'swell_theme_options', $swell_options );
    }
}


// ──────────────────────────────────────────────────────────
// ② カスタムCSS 適用
// ──────────────────────────────────────────────────────────
function yoshilover_v2_apply_css() {
    $css = <<<'ENDCSS'
/* ============================================================
   YOSHILOVER — 追加CSS v3（ジャイアンツカラー：オレンジ主役）
   ============================================================ */

@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap');

:root {
  /* yoshilover 独自変数 */
  --orange:       #F5811F;
  --orange-dark:  #E06D0A;
  --orange-light: #FFF3E8;
  --orange-mid:   #FFA040;
  --black:        #1A1A1A;
  --dark-gray:    #333333;
  --mid-gray:     #666666;
  --light-gray:   #E8E8E8;
  --bg:           #FFF8F0;
  --white:        #FFFFFF;

  /* SWELLのネイティブ変数をオレンジで上書き（インラインCSS対策） */
  --color_main:       #F5811F;
  --color_header_bg:  #F5811F;
  --color_footer_bg:  #F5811F;
  --color_htag:       #F5811F;
  --color_bg:         #FFF8F0;
  --swl-header-bg:    #F5811F;
}

/* ── ベース ── */
body { background: var(--bg) !important; }
a { color: var(--orange-dark); }

/* ====================================================
   ヘッダー：オレンジ背景＋白文字
   ==================================================== */
.l-header,
.l-header__inner,
.l-header__content {
  background: var(--orange) !important;
  border-bottom: 4px solid var(--orange-dark) !important;
}

/* サイト名・ロゴ */
.l-header .c-logo__text,
.l-header .site-name-text,
.l-header .p-logo__title,
.l-header .c-logo__link,
.l-header .p-logo__link {
  color: var(--white) !important;
  font-family: 'Oswald', sans-serif !important;
  font-weight: 700 !important;
  font-size: 22px !important;
  letter-spacing: 2px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

/* キャッチフレーズ */
.l-header .c-logo__desc,
.l-header .p-logo__desc {
  color: rgba(255,255,255,0.85) !important;
  font-size: 11px !important;
}

/* ヘッダー内のすべてのリンク・アイコン */
.l-header a { color: var(--white) !important; }
.l-header a:hover { color: var(--black) !important; }

/* 検索・ハンバーガーアイコン */
.l-header .p-headerSearch__icon,
.l-header .c-searchIcon,
.l-header .p-headerIcons__icon { color: var(--white) !important; }
.l-header .c-hamburger span,
.l-header .p-hamburger span { background: var(--white) !important; }

/* ====================================================
   グローバルナビ（カテゴリナビ）：濃いオレンジ＋白文字
   ==================================================== */
.c-gnav,
.l-gnav,
.p-gnav,
.l-header__nav {
  background: var(--orange-dark) !important;
  border-bottom: none !important;
}

.c-gnav::-webkit-scrollbar,
.l-gnav::-webkit-scrollbar { display: none; }

.c-gnav__list,
.l-gnav__list,
.p-gnav__list {
  display: flex !important;
  flex-wrap: nowrap !important;
  padding: 0 4px;
  gap: 0;
}

/* ナビリンク */
.c-gnav .menu-item > a,
.l-gnav .menu-item > a,
.p-gnav .menu-item > a,
.c-gnav__item > a,
.l-gnav__item > a {
  color: var(--white) !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  padding: 10px 14px !important;
  border-bottom: 3px solid transparent;
  background: transparent !important;
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

/* ホバー・アクティブ */
.c-gnav .menu-item > a:hover,
.l-gnav .menu-item > a:hover,
.c-gnav .current-menu-item > a,
.c-gnav .current_page_item > a,
.l-gnav .current-menu-item > a {
  color: var(--black) !important;
  border-bottom-color: var(--white) !important;
  background: rgba(0,0,0,0.15) !important;
}

/* サブメニュー非表示 */
.c-gnav .sub-menu,
.l-gnav .sub-menu { display: none !important; }

/* ====================================================
   記事一覧（リスト型）
   ==================================================== */
.-type-list .p-postList,
.p-postList.-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.-type-list .p-postList__item,
.p-postList.-list .p-postList__item {
  background: var(--white);
  border-left: 4px solid var(--orange);
  transition: background 0.2s;
  animation: yoshiloFadeInUp 0.35s ease forwards;
  opacity: 0;
  transform: translateY(8px);
}

.-type-list .p-postList__item:hover,
.p-postList.-list .p-postList__item:hover {
  background: var(--orange-light);
}

.-type-list .p-postList__item:nth-child(1)  { animation-delay: 0.04s; }
.-type-list .p-postList__item:nth-child(2)  { animation-delay: 0.08s; }
.-type-list .p-postList__item:nth-child(3)  { animation-delay: 0.12s; }
.-type-list .p-postList__item:nth-child(4)  { animation-delay: 0.16s; }
.-type-list .p-postList__item:nth-child(5)  { animation-delay: 0.20s; }
.-type-list .p-postList__item:nth-child(6)  { animation-delay: 0.24s; }
.-type-list .p-postList__item:nth-child(7)  { animation-delay: 0.28s; }
.-type-list .p-postList__item:nth-child(8)  { animation-delay: 0.32s; }
.-type-list .p-postList__item:nth-child(9)  { animation-delay: 0.36s; }
.-type-list .p-postList__item:nth-child(10) { animation-delay: 0.40s; }

@keyframes yoshiloFadeInUp {
  to { opacity: 1; transform: translateY(0); }
}

/* リスト内リンク */
.-type-list .p-postList__item a,
.p-postList.-list .p-postList__item a {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 18px;
  text-decoration: none;
  color: inherit;
}

/* サムネイル */
.-type-list .p-postList__eyecatch,
.p-postList.-list .p-postList__eyecatch {
  width: 120px !important;
  height: 80px !important;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}
.-type-list .p-postList__eyecatch img,
.p-postList.-list .p-postList__eyecatch img {
  width: 100%; height: 100%; object-fit: cover;
}

/* カテゴリバッジ：オレンジ背景＋白文字 */
.-type-list .c-cat-label,
.p-postList.-list .c-cat-label,
.c-cat-label {
  background: var(--orange) !important;
  color: var(--white) !important;
  font-size: 11px !important;
  font-weight: 700 !important;
  padding: 2px 8px !important;
  border-radius: 2px !important;
}

/* 日付：オレンジ */
.-type-list .p-postList__date,
.p-postList.-list .p-postList__date,
.c-meta__date,
.p-postList__date {
  font-size: 11px;
  color: var(--orange-dark) !important;
  font-weight: 600;
}

/* タイトル */
.-type-list .p-postList__ttl,
.p-postList.-list .p-postList__ttl {
  font-size: 15px !important;
  font-weight: 700 !important;
  line-height: 1.5 !important;
  color: var(--dark-gray) !important;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-top: 4px;
}

/* ====================================================
   ページネーション
   ==================================================== */
.wp-pagenavi a, .wp-pagenavi span,
.p-pagination a, .p-pagination .current,
.p-pager a {
  border-color: var(--orange) !important;
  color: var(--orange) !important;
  font-weight: 700;
  border-radius: 4px;
}
.wp-pagenavi a:hover, .p-pagination a:hover {
  background: var(--orange) !important;
  color: var(--white) !important;
}
.wp-pagenavi span.current, .p-pagination .current {
  background: var(--orange) !important;
  color: var(--white) !important;
  border-color: var(--orange) !important;
}

.p-loadMoreBtn, .c-loadMore__btn {
  display: block; width: 100%;
  background: var(--orange) !important;
  border: none !important;
  color: var(--white) !important;
  font-size: 14px !important; font-weight: 700 !important;
  padding: 13px !important;
  text-align: center; border-radius: 4px; cursor: pointer; margin-top: 16px;
  transition: background 0.2s;
  font-family: 'Oswald', sans-serif !important;
  letter-spacing: 1px;
}
.p-loadMoreBtn:hover, .c-loadMore__btn:hover {
  background: var(--orange-dark) !important;
}

/* ====================================================
   サイドバー：オレンジ見出しバー
   ==================================================== */
.l-sidebar .widget {
  background: var(--white);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 20px;
}

.l-sidebar .widget-title,
.l-sidebar .widgetTitle,
.l-sidebar .c-widget__title,
.l-sidebar .widget_title {
  background: var(--orange) !important;
  color: var(--white) !important;
  font-family: 'Oswald', sans-serif !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  padding: 10px 16px !important;
  border-left: none !important;
  letter-spacing: 1px;
  margin: 0 !important;
}

.l-sidebar .widget ul { list-style: none; margin: 0; padding: 0; }
.l-sidebar .widget ul li { border-bottom: 1px solid var(--light-gray); }
.l-sidebar .widget ul li:last-child { border-bottom: none; }
.l-sidebar .widget ul li a {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; text-decoration: none;
  color: var(--dark-gray); font-size: 13px; font-weight: 600;
  transition: background 0.15s, color 0.15s;
}
.l-sidebar .widget ul li a:hover {
  background: var(--orange-light);
  color: var(--orange-dark);
}

.l-sidebar .widget_categories .cat-item a::before {
  content: '';
  display: inline-block; width: 6px; height: 6px;
  border-radius: 50%; background: var(--orange); flex-shrink: 0;
}

/* ====================================================
   フッター：オレンジ背景＋白文字
   ==================================================== */
.l-footer,
.l-footer__inner {
  background: var(--orange) !important;
  border-top: 4px solid var(--orange-dark) !important;
  color: var(--white) !important;
  margin-top: 40px;
}

.l-footer a {
  color: var(--white) !important;
  font-size: 13px;
  transition: color 0.2s;
}
.l-footer a:hover { color: var(--black) !important; }

.l-footer .c-logo__text,
.l-footer .site-name-text,
.l-footer .p-logo__title {
  font-family: 'Oswald', sans-serif !important;
  font-weight: 700 !important;
  color: var(--white) !important;
  font-size: 18px !important;
  letter-spacing: 2px;
}

.l-footer .c-copy,
.l-footer__copyright {
  color: rgba(255,255,255,0.75) !important;
  font-size: 11px;
  border-top: 1px solid rgba(255,255,255,0.3) !important;
  padding-top: 16px;
}

/* ====================================================
   ボタン・バッジ類
   ==================================================== */
.wp-block-button .wp-block-button__link,
.c-btn,
.swell-block-button a {
  background: var(--orange) !important;
  color: var(--white) !important;
  border-color: var(--orange) !important;
  border-radius: 4px !important;
  font-weight: 700 !important;
  transition: background 0.2s !important;
}
.wp-block-button .wp-block-button__link:hover,
.c-btn:hover { background: var(--orange-dark) !important; }

.p-scrollTopBtn,
.c-scrollTopBtn {
  background: var(--orange) !important;
  color: var(--white) !important;
  border-radius: 4px !important;
}

/* NEWバッジ */
.p-postList__new, .c-newBadge, .new-badge, .p-postCard__new {
  display: inline-block;
  background: var(--black) !important;
  color: var(--white) !important;
  font-size: 10px !important; font-weight: 700 !important;
  padding: 1px 6px !important; border-radius: 2px !important;
  margin-right: 6px; vertical-align: middle; line-height: 1.6; flex-shrink: 0;
}

/* ====================================================
   カテゴリアーカイブヘッダー
   ==================================================== */
.p-catHead,
.l-archiveHead,
.p-archiveHeader {
  border-left: 6px solid var(--orange);
  padding: 12px 16px;
  background: var(--white);
  margin-bottom: 16px;
}
.p-catHead__title,
.l-archiveHead__title { font-size: 18px; font-weight: 700; color: var(--dark-gray); }
.p-catHead__desc      { font-size: 13px; color: var(--mid-gray); margin-top: 4px; }

/* ====================================================
   記事内見出し
   ==================================================== */
.post_content h2, .entry-content h2 {
  background: var(--orange) !important;
  color: var(--white) !important;
  padding: 12px 16px !important;
  border-left: none !important;
  border-bottom: none !important;
  font-size: 17px; line-height: 1.4;
}
.post_content h3, .entry-content h3 {
  border-bottom: 3px solid var(--orange) !important;
  padding-bottom: 6px !important;
}
.post_content h4, .entry-content h4 {
  border-left: 4px solid var(--orange);
  padding-left: 10px;
}

/* ====================================================
   ブロッククォート
   ==================================================== */
.wp-block-quote,
.post_content blockquote,
.entry-content blockquote {
  border-left: 4px solid var(--orange) !important;
  background: var(--orange-light) !important;
  padding: 16px 20px !important;
}

/* ====================================================
   スマホメニュー
   ==================================================== */
.p-spNav, .l-spMenu {
  background: var(--orange-dark) !important;
}
.p-spNav a, .l-spMenu a { color: var(--white) !important; }
.p-spNav a:hover, .l-spMenu a:hover { color: var(--black) !important; }
.p-spNav__item, .l-spMenu__item { border-bottom: 1px solid rgba(255,255,255,0.2) !important; }

/* ====================================================
   レスポンシブ
   ==================================================== */
@media (max-width: 768px) {
  .l-header .c-logo__text,
  .l-header .site-name-text { font-size: 18px !important; }
  .-type-list .p-postList__eyecatch,
  .p-postList.-list .p-postList__eyecatch { width: 90px !important; height: 60px !important; }
  .-type-list .p-postList__ttl,
  .p-postList.-list .p-postList__ttl { font-size: 14px !important; }
  .-type-list .p-postList__item a,
  .p-postList.-list .p-postList__item a { padding: 12px 12px; }
}
ENDCSS;

    wp_update_custom_css_post( $css, [ 'stylesheet' => get_stylesheet() ] );
}


// ──────────────────────────────────────────────────────────
// ③ テスト記事10本に noindex 設定
// ──────────────────────────────────────────────────────────
function yoshilover_v2_set_noindex() {
    $test_ids = [ 61088, 61089, 61090, 61091, 61092, 61093, 61094, 61095, 61096, 61097 ];
    foreach ( $test_ids as $pid ) {
        if ( ! get_post( $pid ) ) continue;
        update_post_meta( $pid, '_swell_no_index',                    1 );
        update_post_meta( $pid, '_yoast_wpseo_meta-robots-noindex',  1 );
        update_post_meta( $pid, '_robots_noindex',                    1 );
    }
}

// ──────────────────────────────────────────────────────────
// 管理画面通知
// ──────────────────────────────────────────────────────────
add_action( 'admin_notices', function() {
    if ( get_option( 'yoshilover_v2_done' ) !== '1' ) return;
    $t = get_option( 'yoshilover_v2_time', '' );
    echo '<div class="notice notice-success is-dismissible"><p>';
    echo "<strong>✅ Yoshilover Setup v2 完了</strong>（{$t}）<br>";
    echo "CSS・テーマカラー・noindex を適用しました。このプラグインは削除してください。<br>";
    echo '<small>※ SWELLのカラー・ヘッダー設定はカスタマイザーで手動確認・保存することを推奨します。</small>';
    echo '</p></div>';
} );
