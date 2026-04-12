<?php
/**
 * Plugin Name: Yoshilover Colors
 * Description: SWELLカラー設定。有効化後すぐ削除してください。
 * Version: 1.0
 */

register_activation_hook( __FILE__, 'yoshilover_colors_run' );
add_action( 'admin_init', function() {
    if ( get_option('yoshilover_colors_done') !== '1' ) {
        yoshilover_colors_run();
    }
});

function yoshilover_colors_run() {
    // SWELLのカラーtheme_mods（CSSソースで確認済みのキー名）
    set_theme_mod( 'color_main',  '#F5811F' );  // メインカラー（オレンジ）
    set_theme_mod( 'color_text',  '#333333' );  // テキスト
    set_theme_mod( 'color_link',  '#003DA5' );  // リンク（ジャイアンツブルー）
    set_theme_mod( 'color_htag',  '#1A1A1A' );  // 見出し
    set_theme_mod( 'color_bg',    '#F5F5F0' );  // 背景色

    // ヘッダー背景（SWELLキー候補）
    set_theme_mod( 'header_bg_color',   '#1A1A1A' );
    set_theme_mod( 'color_header_bg',   '#1A1A1A' );
    set_theme_mod( 'header_color',      '#1A1A1A' );

    // グラデーション色もリセット（デフォルトの水色を消す）
    set_theme_mod( 'color_gradient1', '#F5811F' );
    set_theme_mod( 'color_gradient2', '#FFA040' );

    update_option( 'yoshilover_colors_done', '1' );
}

add_action( 'admin_notices', function() {
    if ( get_option('yoshilover_colors_done') === '1' ) {
        echo '<div class="notice notice-success"><p><strong>✅ カラー設定完了</strong> — このプラグインを削除してください。</p></div>';
    }
});
