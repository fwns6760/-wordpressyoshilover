<?php
/**
 * Plugin Name: Yoshilover Post Noindex
 * Description: 個別記事はデフォルトnoindex。バズった記事はWP管理画面でインデックス許可できる。
 * Version: 1.2
 */

if ( ! defined( 'ABSPATH' ) ) exit;

// ── wp_robots フィルターで noindex をセット（SWELL等のSEO出力に上書きされない）──
add_filter( 'wp_robots', function( $robots ) {
    if ( is_single() ) {
        $post_id    = get_the_ID();
        $allow_index = get_post_meta( $post_id, '_yoshilover_index', true );
        if ( ! $allow_index ) {
            unset( $robots['index'] );
            $robots['noindex'] = true;
        }
    }
    return $robots;
} );

// ── 管理画面：記事編集画面にインデックス許可チェックボックスを追加 ──
add_action( 'add_meta_boxes', function() {
    add_meta_box(
        'yoshilover_index_box',
        '🔍 Googleインデックス設定',
        'yoshilover_index_meta_box',
        'post',
        'side',
        'high'
    );
} );

function yoshilover_index_meta_box( $post ) {
    $value = get_post_meta( $post->ID, '_yoshilover_index', true );
    wp_nonce_field( 'yoshilover_index_nonce', 'yoshilover_index_nonce' );
    ?>
    <label style="display:flex;align-items:center;gap:8px;font-weight:700;cursor:pointer;">
        <input type="checkbox" name="yoshilover_index" value="1" <?php checked( $value, '1' ); ?> style="width:18px;height:18px;">
        <span>この記事をGoogleにインデックスさせる</span>
    </label>
    <p style="color:#666;font-size:11px;margin-top:8px;">
        バズった記事・良質な記事にチェックを入れてください。<br>
        デフォルトはnoindex（Googleに表示されない）です。
    </p>
    <?php
}

add_action( 'save_post', function( $post_id ) {
    if ( ! isset( $_POST['yoshilover_index_nonce'] ) ) return;
    if ( ! wp_verify_nonce( $_POST['yoshilover_index_nonce'], 'yoshilover_index_nonce' ) ) return;
    if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) return;
    if ( ! current_user_can( 'edit_post', $post_id ) ) return;

    if ( isset( $_POST['yoshilover_index'] ) ) {
        update_post_meta( $post_id, '_yoshilover_index', '1' );
    } else {
        delete_post_meta( $post_id, '_yoshilover_index' );
    }
} );
