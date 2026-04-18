<?php
/**
 * Plugin Name: Yoshilover Exclude Old Articles
 * Description: 「旧記事」カテゴリ（ID=672）をTOPページ・フィード・検索から除外する。
 * Version: 1.1
 */

define( 'YOSHILOVER_EXCLUDE_CAT', 672 );

/**
 * アプローチ1: pre_get_posts — メインクエリ＋サブクエリ両方を対象に。
 * SWELLはフロントページで is_main_query()=false のサブクエリを使う場合があるため
 * is_main_query() チェックを外してフロントページ・フィード全般に適用する。
 * また、ログイン中のAdmin閲覧時も非公開(private)記事を表示しないよう publish 限定にする。
 */
add_action( 'pre_get_posts', function( WP_Query $query ) {
    // REST リクエスト中はこのプラグインを効かせない（collection query の status フィルタ保護）
    if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) {
        return;
    }

    if ( is_admin() ) {
        return;
    }

    // フロントページ（最新投稿）・フィード・アーカイブ全般で除外
    // is_front_page() も追加（show_on_front=posts の場合 is_home() と同義だが念のため）
    $on_front = $query->is_home()
             || $query->is_front_page()
             || $query->is_feed()
             || ( ! $query->is_singular() && ! $query->is_admin && $query->is_main_query() );

    if ( ! $on_front ) {
        return;
    }

    // 旧記事カテゴリを除外
    $exclude = $query->get( 'category__not_in' );
    if ( ! is_array( $exclude ) ) {
        $exclude = array_filter( (array) $exclude );
    }
    if ( ! in_array( YOSHILOVER_EXCLUDE_CAT, $exclude, true ) ) {
        $exclude[] = YOSHILOVER_EXCLUDE_CAT;
        $query->set( 'category__not_in', $exclude );
    }

    // 非公開・下書き記事を除外（ログイン中のAdmin閲覧時も含む）
    $query->set( 'post_status', 'publish' );
}, 1 ); // priority=1: 他フックより早く実行

/**
 * アプローチ2: posts_where フィルタ — SQLレベルで完全除外（フォールバック）。
 * pre_get_posts が効かないSWELL独自クエリにも対応。
 */
add_filter( 'posts_where', function( $where, $query ) {
    global $wpdb;

    if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) {
        return $where;
    }

    if ( is_admin() ) {
        return $where;
    }

    // フロントページ・フィードのみ
    if ( ! ( $query->is_home() || $query->is_front_page() || $query->is_feed() ) ) {
        return $where;
    }

    // すでに category__not_in で除外されている場合は追加しない（重複JOIN防止）
    $not_in = $query->get( 'category__not_in' );
    if ( is_array( $not_in ) && in_array( YOSHILOVER_EXCLUDE_CAT, $not_in, true ) ) {
        return $where;
    }

    // cat 672 に属する投稿を WHERE で除外
    $tt_id = (int) $wpdb->get_var( $wpdb->prepare(
        "SELECT term_taxonomy_id FROM {$wpdb->term_taxonomy} WHERE term_id = %d AND taxonomy = 'category' LIMIT 1",
        YOSHILOVER_EXCLUDE_CAT
    ) );

    if ( $tt_id ) {
        $where .= $wpdb->prepare(
            " AND {$wpdb->posts}.ID NOT IN (
                SELECT object_id FROM {$wpdb->term_relationships}
                WHERE term_taxonomy_id = %d
            )",
            $tt_id
        );
    }

    return $where;
}, 10, 2 );
