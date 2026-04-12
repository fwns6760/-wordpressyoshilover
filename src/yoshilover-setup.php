<?php
/**
 * Plugin Name: Yoshilover Setup
 * Description: フェーズ①カラー・CSS自動設定プラグイン。有効化すると即実行。完了後は削除してください。
 * Version: 1.0
 */

// 有効化フックで実行
register_activation_hook( __FILE__, 'yoshilover_setup_run' );

// 念のため admin_init でも実行（有効化済みの場合）
add_action( 'admin_init', function() {
    if ( get_option( 'yoshilover_setup_done' ) !== '1' ) {
        yoshilover_setup_run();
    }
});

function yoshilover_setup_run() {

    // ── 1. SWELLカスタマイザー設定（theme_mods） ──────────────────────

    $theme = get_stylesheet(); // 'swell_child'

    // SWELL の theme_mods キー名はバージョンによって異なる場合があります。
    // 設定できなかった項目はカスタマイザーで手動設定してください。

    // メインカラー
    set_theme_mod( 'main_color', '#F5811F' );

    // テキストカラー
    set_theme_mod( 'text_color', '#333333' );

    // リンクカラー
    set_theme_mod( 'link_color', '#003DA5' );

    // 背景色
    set_theme_mod( 'background_color', 'F5F5F0' ); // WordPress標準（#なし）
    update_option( 'background_color', 'F5F5F0' );

    // ヘッダー背景色
    set_theme_mod( 'header_bg_color', '#1A1A1A' );
    set_theme_mod( 'header_color',    '#1A1A1A' );

    // SWELLの独自カラーキー（バージョンによる）
    $swell_mods = get_theme_mods();
    // デバッグ用：現在のtheme_modsキーを記録
    update_option( 'yoshilover_debug_mods', array_keys( (array) $swell_mods ) );

    // SWELL v4.x 以降のキー候補
    $color_candidates = [
        'swell_color_main'    => '#F5811F',
        'swell_color_text'    => '#333333',
        'swell_color_link'    => '#003DA5',
        'swell_color_bg'      => '#F5F5F0',
        'swell_header_bg'     => '#1A1A1A',
        'color_main'          => '#F5811F',
        'color_text'          => '#333333',
        'color_link'          => '#003DA5',
        'color_bg'            => '#F5F5F0',
        'header_bg'           => '#1A1A1A',
    ];
    foreach ( $color_candidates as $key => $val ) {
        set_theme_mod( $key, $val );
    }

    // ── 2. 記事一覧をリスト型に設定 ──────────────────────────────────

    // SWELL の記事一覧レイアウト設定キー候補
    $layout_candidates = [
        'archive_layout'        => 'list',
        'top_layout'            => 'list',
        'post_list_type'        => 'list',
        'swell_archive_layout'  => 'list',
        'list_style'            => 'list',
    ];
    foreach ( $layout_candidates as $key => $val ) {
        set_theme_mod( $key, $val );
    }

    // ── 3. カスタムCSSを適用 ──────────────────────────────────────────

    $css = <<<'CSS'
/* ============================================================
   YOSHILOVER — 追加CSS
   ============================================================ */

@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap');

:root {
  --orange:      #F5811F;
  --orange-light:#FFF3E8;
  --blue:        #003DA5;
  --black:       #1A1A1A;
  --dark-gray:   #333333;
  --mid-gray:    #666666;
  --light-gray:  #E8E8E8;
  --bg:          #F5F5F0;
  --white:       #FFFFFF;
}

/* ── ヘッダー ── */
.l-header {
  background: var(--black) !important;
  border-bottom: 4px solid var(--orange) !important;
  position: sticky !important;
  top: 0; z-index: 100;
}
.l-header a, .l-header .c-logo__text, .l-header .site-name-text { color: var(--white) !important; }
.l-header .c-logo__text, .l-header .site-name-text, .l-header .p-logo__title {
  font-family: 'Oswald', sans-serif !important;
  font-weight: 700 !important; font-size: 20px !important; letter-spacing: 1px;
}
.l-header .c-logo__desc, .l-header .p-logo__desc {
  font-size: 10px !important; color: var(--orange) !important; font-weight: 400 !important;
}

/* ── カテゴリナビ ── */
.c-gnav, .l-gnav {
  background: var(--white) !important;
  border-bottom: 1px solid var(--light-gray) !important;
  overflow-x: auto !important; -webkit-overflow-scrolling: touch;
}
.c-gnav::-webkit-scrollbar, .l-gnav::-webkit-scrollbar { display: none; }
.c-gnav__list, .l-gnav__list {
  display: flex !important; flex-wrap: nowrap !important;
  white-space: nowrap; padding: 0 8px;
}
.c-gnav__item > a, .l-gnav__item > a, .c-gnav .menu-item > a {
  display: inline-flex !important; align-items: center; gap: 4px;
  padding: 10px 14px !important; font-size: 13px !important; font-weight: 700 !important;
  color: var(--dark-gray) !important; text-decoration: none;
  border-bottom: 3px solid transparent; transition: all 0.2s; white-space: nowrap;
}
.c-gnav__item > a:hover, .l-gnav__item > a:hover,
.c-gnav .menu-item > a:hover,
.c-gnav .current-menu-item > a, .c-gnav .current_page_item > a {
  color: var(--orange) !important; border-bottom-color: var(--orange) !important;
  background: transparent !important;
}
.c-gnav .menu-item > a::before, .l-gnav .menu-item > a::before {
  content: ''; display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; flex-shrink: 0;
}
.menu-item.cat-all    > a::before { background: var(--orange); }
.menu-item.cat-jiai   > a::before { background: #F5811F; }
.menu-item.cat-senshu > a::before { background: #003DA5; }
.menu-item.cat-syuno  > a::before { background: #555555; }
.menu-item.cat-draft  > a::before { background: #2E8B57; }
.menu-item.cat-ob     > a::before { background: #7B4DAA; }
.menu-item.cat-hoko   > a::before { background: #E53935; }
.menu-item.cat-kyudan > a::before { background: #F9A825; }
.menu-item.cat-column > a::before { background: #1A1A1A; }
.c-gnav .sub-menu { display: none !important; }

/* ── 記事一覧（リスト型） ── */
.-type-list .p-postList, .p-postList.-list {
  display: flex; flex-direction: column; gap: 2px;
}
.-type-list .p-postList__item, .p-postList.-list .p-postList__item {
  background: var(--white); border-left: 4px solid transparent;
  transition: background 0.2s, border-left-color 0.2s;
  animation: fadeInUp 0.4s ease forwards; opacity: 0; transform: translateY(10px);
}
.-type-list .p-postList__item:hover, .p-postList.-list .p-postList__item:hover {
  background: var(--orange-light); border-left-color: var(--orange);
}
.-type-list .p-postList__item:nth-child(1)  { animation-delay: 0.05s; }
.-type-list .p-postList__item:nth-child(2)  { animation-delay: 0.10s; }
.-type-list .p-postList__item:nth-child(3)  { animation-delay: 0.15s; }
.-type-list .p-postList__item:nth-child(4)  { animation-delay: 0.20s; }
.-type-list .p-postList__item:nth-child(5)  { animation-delay: 0.25s; }
.-type-list .p-postList__item:nth-child(6)  { animation-delay: 0.30s; }
.-type-list .p-postList__item:nth-child(7)  { animation-delay: 0.35s; }
.-type-list .p-postList__item:nth-child(8)  { animation-delay: 0.40s; }
.-type-list .p-postList__item:nth-child(9)  { animation-delay: 0.45s; }
.-type-list .p-postList__item:nth-child(10) { animation-delay: 0.50s; }
@keyframes fadeInUp { to { opacity: 1; transform: translateY(0); } }

.-type-list .p-postList__item a, .p-postList.-list .p-postList__item a {
  display: flex; gap: 16px; align-items: flex-start;
  padding: 16px 20px; text-decoration: none; color: inherit;
}
.-type-list .p-postList__eyecatch, .p-postList.-list .p-postList__eyecatch {
  width: 120px !important; height: 80px !important;
  border-radius: 4px; overflow: hidden; flex-shrink: 0;
}
.-type-list .p-postList__eyecatch img, .p-postList.-list .p-postList__eyecatch img {
  width: 100%; height: 100%; object-fit: cover;
}
.-type-list .p-postList__body, .p-postList.-list .p-postList__body { flex: 1; min-width: 0; }
.-type-list .p-postList__cats .c-cat-label, .p-postList.-list .c-cat-label {
  font-size: 11px !important; font-weight: 700 !important;
  color: var(--white) !important; padding: 2px 8px !important; border-radius: 2px !important;
}
.-type-list .p-postList__date, .p-postList.-list .p-postList__date, .-type-list .c-meta__date {
  font-size: 11px; color: var(--mid-gray);
}
.-type-list .p-postList__ttl, .p-postList.-list .p-postList__ttl {
  font-size: 15px !important; font-weight: 700 !important; line-height: 1.5 !important;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-top: 4px; color: var(--dark-gray);
}

/* ── サイドバー ── */
.l-sidebar .widget { background: var(--white); border-radius: 4px; overflow: hidden; margin-bottom: 20px; }
.l-sidebar .widget-title, .l-sidebar .widgetTitle, .l-sidebar .c-widget__title {
  background: var(--black) !important; color: var(--white) !important;
  font-family: 'Oswald', sans-serif !important; font-size: 13px !important;
  font-weight: 700 !important; padding: 10px 16px !important;
  border-left: 4px solid var(--orange) !important; letter-spacing: 1px; margin: 0 !important;
}
.l-sidebar .widget ul { list-style: none; margin: 0; padding: 0; }
.l-sidebar .widget ul li { border-bottom: 1px solid var(--light-gray); }
.l-sidebar .widget ul li:last-child { border-bottom: none; }
.l-sidebar .widget ul li a {
  display: flex; align-items: center; gap: 8px; padding: 10px 16px;
  text-decoration: none; color: var(--dark-gray); font-size: 13px; transition: background 0.2s;
}
.l-sidebar .widget ul li a:hover { background: var(--orange-light); }
.l-sidebar .widget_categories .cat-item a { justify-content: space-between; }

/* ── Xバナー ── */
.sidebar-x-banner {
  display: block; background: var(--black); color: var(--white);
  text-align: center; padding: 16px; text-decoration: none; transition: background 0.2s;
}
.sidebar-x-banner:hover { background: #333; }
.sidebar-x-banner .x-handle { font-family: 'Oswald', sans-serif; font-size: 16px; font-weight: 700; color: var(--orange); }
.sidebar-x-banner .x-followers { font-size: 11px; color: #999; margin-top: 2px; }
.sidebar-x-banner .x-cta {
  display: inline-block; margin-top: 8px; background: var(--orange);
  color: var(--white); padding: 6px 20px; border-radius: 20px; font-size: 12px; font-weight: 700;
}

/* ── フッター ── */
.l-footer { background: var(--black) !important; border-top: 4px solid var(--orange) !important; color: #999 !important; margin-top: 40px; }
.l-footer a { color: #999 !important; font-size: 12px; transition: color 0.2s; }
.l-footer a:hover { color: var(--orange) !important; }
.l-footer .c-logo__text, .l-footer .site-name-text {
  font-family: 'Oswald', sans-serif !important; font-weight: 700 !important; color: var(--white) !important;
}

/* ── 記事内見出し ── */
.post_content h2, .entry-content h2 {
  background: var(--black); color: var(--white);
  padding: 12px 16px; border-left: 6px solid var(--orange);
}
.post_content h3, .entry-content h3 { border-bottom: 3px solid var(--orange); padding-bottom: 6px; }

/* ── レスポンシブ ── */
@media (max-width: 768px) {
  .-type-list .p-postList__eyecatch, .p-postList.-list .p-postList__eyecatch {
    width: 90px !important; height: 60px !important;
  }
  .-type-list .p-postList__ttl, .p-postList.-list .p-postList__ttl { font-size: 14px !important; }
  .-type-list .p-postList__item a, .p-postList.-list .p-postList__item a { padding: 12px 14px; }
}
CSS;

    // カスタムCSSを保存
    wp_update_custom_css_post( $css, array( 'stylesheet' => get_stylesheet() ) );

    // ── 4. 完了フラグを立てる ─────────────────────────────────────────
    update_option( 'yoshilover_setup_done', '1' );
    update_option( 'yoshilover_setup_time', current_time( 'mysql' ) );
}

// ── 管理画面に完了通知を表示 ────────────────────────────────────────────
add_action( 'admin_notices', function() {
    if ( get_option( 'yoshilover_setup_done' ) === '1' ) {
        $time = get_option( 'yoshilover_setup_time', '' );
        echo '<div class="notice notice-success"><p>';
        echo '<strong>✅ Yoshilover Setup 完了</strong>（' . esc_html( $time ) . '）<br>';
        echo 'CSS・カラー設定が適用されました。このプラグインは削除してください。<br>';
        echo '<small>※ SWELLのカラー設定はカスタマイザーで手動確認・保存することを推奨します。</small>';
        echo '</p></div>';
    }
});
