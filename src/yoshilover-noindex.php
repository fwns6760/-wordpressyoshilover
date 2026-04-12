<?php
/**
 * Plugin Name: Yoshilover Noindex
 * Description: テスト記事10本に noindex を設定。有効化すると即実行。完了後は削除してください。
 * Version: 1.0
 */

// REST API への登録（将来の利用に備えて）
add_action( 'init', function() {
    register_post_meta( 'post', '_swell_no_index', [
        'type'          => 'integer',
        'single'        => true,
        'show_in_rest'  => true,
        'auth_callback' => function() { return current_user_can( 'edit_posts' ); },
    ] );
} );

// 有効化時に即実行
register_activation_hook( __FILE__, 'yoshilover_noindex_run' );

// admin_init でも実行（有効化済みの場合）
add_action( 'admin_init', function() {
    if ( get_option( 'yoshilover_noindex_done' ) !== '1' ) {
        yoshilover_noindex_run();
    }
} );

function yoshilover_noindex_run() {
    // テスト記事10本のID（2026-04-12 作成分）
    $test_post_ids = [ 61088, 61089, 61090, 61091, 61092, 61093, 61094, 61095, 61096, 61097 ];

    $done = 0;
    foreach ( $test_post_ids as $pid ) {
        $post = get_post( $pid );
        if ( ! $post ) continue;

        // SWELL noindex フラグ
        update_post_meta( $pid, '_swell_no_index', 1 );

        // フォールバック: WordPress標準 robots noindex（Yoast SEO 互換）
        update_post_meta( $pid, '_yoast_wpseo_meta-robots-noindex', 1 );

        $done++;
    }

    update_option( 'yoshilover_noindex_done', '1' );
    update_option( 'yoshilover_noindex_ids',  $test_post_ids );
    update_option( 'yoshilover_noindex_time', current_time( 'mysql' ) );
    update_option( 'yoshilover_noindex_count', $done );
}

// 管理画面に完了通知
add_action( 'admin_notices', function() {
    if ( get_option( 'yoshilover_noindex_done' ) !== '1' ) return;
    $count = get_option( 'yoshilover_noindex_count', 0 );
    $time  = get_option( 'yoshilover_noindex_time', '' );
    echo '<div class="notice notice-success"><p>';
    echo "<strong>✅ Yoshilover Noindex 完了</strong>（{$time}）<br>";
    echo "テスト記事 {$count}本 に noindex を設定しました。このプラグインは削除してください。";
    echo '</p></div>';
} );
