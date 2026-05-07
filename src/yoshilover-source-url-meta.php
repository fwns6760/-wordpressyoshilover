<?php
/**
 * Plugin Name: Yoshilover Source URL Meta
 * Description: Register the article-creator post meta keys with the
 *              REST API so the Python fetcher can persist + read back
 *              the source URL of each ingested article. Without this
 *              registration WP silently drops the meta on REST POST,
 *              breaking source_url-based dedup and surfacing duplicate
 *              publishes (e.g. the 64860 / 64951 dup observed
 *              2026-05-07).
 * Version:     1.0
 * Author:      yoshihiro
 *
 * Cost: zero. Pure WP API registration; no external calls; no DB
 * migration. Activation just enables existing meta keys for REST
 * read+write.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

add_action( 'init', function() {
    $auth_callback = function() {
        return current_user_can( 'edit_posts' );
    };

    // Primary key written by src/wp_client.py (SOURCE_URL_META_KEY).
    register_post_meta( 'post', '_yoshilover_source_url', [
        'type'              => 'string',
        'single'            => true,
        'show_in_rest'      => true,
        'auth_callback'     => $auth_callback,
        'sanitize_callback' => 'esc_url_raw',
    ] );

    // Legacy alias (SOURCE_URL_META_ALIASES) — kept readable so old
    // posts written under the alias still pair-match for dedup.
    register_post_meta( 'post', 'yl_source_url', [
        'type'              => 'string',
        'single'            => true,
        'show_in_rest'      => true,
        'auth_callback'     => $auth_callback,
        'sanitize_callback' => 'esc_url_raw',
    ] );

    // Sibling: source published-at timestamp (SOURCE_PUBLISHED_AT_META_KEY).
    register_post_meta( 'post', '_yoshilover_source_published_at', [
        'type'              => 'string',
        'single'            => true,
        'show_in_rest'      => true,
        'auth_callback'     => $auth_callback,
        'sanitize_callback' => 'sanitize_text_field',
    ] );
} );
