<?php
/**
 * Plugin Name: Yoshilover CSS Push
 * Description: REST endpoint for pushing SWELL 追加 CSS automatically. Claude Code front-deploy 用の REST PUT/GET を提供する。
 * Version:     0.2.0
 * Author:      yoshilover
 * License:     GPL-2.0+
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

add_action( 'rest_api_init', 'yoshilover_css_push_register_routes' );

function yoshilover_css_push_register_routes() {
    register_rest_route(
        'yoshilover/v1',
        '/custom-css',
        array(
            array(
                'methods'             => 'GET',
                'callback'            => 'yoshilover_css_push_get',
                'permission_callback' => 'yoshilover_css_push_permission',
            ),
            array(
                'methods'             => 'PUT',
                'callback'            => 'yoshilover_css_push_put',
                'permission_callback' => 'yoshilover_css_push_permission',
                'args'                => array(
                    'css' => array(
                        'type'     => 'string',
                        'required' => true,
                    ),
                    'stylesheet' => array(
                        'type'     => 'string',
                        'required' => false,
                    ),
                ),
            ),
        )
    );

    // option set/get endpoint (whitelisted な yoshilover option のみ許可)
    register_rest_route(
        'yoshilover/v1',
        '/option/(?P<name>[a-zA-Z0-9_-]+)',
        array(
            array(
                'methods'             => 'GET',
                'callback'            => 'yoshilover_option_get',
                'permission_callback' => 'yoshilover_css_push_permission',
            ),
            array(
                'methods'             => array( 'PUT', 'POST' ),
                'callback'            => 'yoshilover_option_put',
                'permission_callback' => 'yoshilover_css_push_permission',
                'args'                => array(
                    'value' => array(
                        'required' => true,
                    ),
                ),
            ),
        )
    );
}

/**
 * whitelist: Claude Code が REST 経由で触っていい option 名のみ許可
 */
function yoshilover_option_whitelist() {
    return array(
        'yoshilover_063_x_follow_cta',
        'yoshilover_063_tag_nav_hot',
        'yoshilover_063_topic_hub',
        'yoshilover_063_sidebar_popular',
        'yoshilover_063_breaking_strip',
    );
}

function yoshilover_option_get( WP_REST_Request $request ) {
    $name = (string) $request->get_param( 'name' );
    if ( ! in_array( $name, yoshilover_option_whitelist(), true ) ) {
        return new WP_Error( 'forbidden_option', 'Option not in whitelist: ' . $name, array( 'status' => 403 ) );
    }
    $value = get_option( $name, null );
    return rest_ensure_response(
        array(
            'name'  => $name,
            'value' => $value,
        )
    );
}

function yoshilover_option_put( WP_REST_Request $request ) {
    $name = (string) $request->get_param( 'name' );
    if ( ! in_array( $name, yoshilover_option_whitelist(), true ) ) {
        return new WP_Error( 'forbidden_option', 'Option not in whitelist: ' . $name, array( 'status' => 403 ) );
    }
    $value = $request->get_param( 'value' );
    $ok    = update_option( $name, $value );
    return rest_ensure_response(
        array(
            'ok'    => true,
            'name'  => $name,
            'value' => get_option( $name, null ),
            'updated' => (bool) $ok,
        )
    );
}

function yoshilover_css_push_permission() {
    return current_user_can( 'edit_theme_options' ) || current_user_can( 'edit_css' );
}

function yoshilover_css_push_get( WP_REST_Request $request ) {
    $stylesheet = $request->get_param( 'stylesheet' );
    if ( empty( $stylesheet ) ) {
        $stylesheet = get_stylesheet();
    }
    $css = wp_get_custom_css( $stylesheet );
    return rest_ensure_response(
        array(
            'stylesheet' => $stylesheet,
            'bytes'      => strlen( $css ),
            'sha1'       => sha1( $css ),
            'css'        => $css,
        )
    );
}

function yoshilover_css_push_put( WP_REST_Request $request ) {
    $css = $request->get_param( 'css' );
    if ( ! is_string( $css ) ) {
        return new WP_Error( 'invalid_css', 'css must be a string', array( 'status' => 400 ) );
    }

    if ( ! function_exists( 'wp_update_custom_css_post' ) ) {
        return new WP_Error(
            'core_helper_missing',
            'wp_update_custom_css_post() is unavailable',
            array( 'status' => 500 )
        );
    }

    $stylesheet = $request->get_param( 'stylesheet' );
    if ( empty( $stylesheet ) ) {
        $stylesheet = get_stylesheet();
    }

    $result = wp_update_custom_css_post( $css, array( 'stylesheet' => $stylesheet ) );
    if ( is_wp_error( $result ) ) {
        return $result;
    }

    if ( function_exists( 'wp_cache_flush' ) ) {
        wp_cache_flush();
    }

    // SWELL 側 cache もあれば flush (optional hooks)
    do_action( 'yoshilover_css_push_after_save', $css, $stylesheet, $result );

    $post_id = isset( $result->ID ) ? (int) $result->ID : 0;
    return rest_ensure_response(
        array(
            'ok'         => true,
            'stylesheet' => $stylesheet,
            'bytes'      => strlen( $css ),
            'sha1'       => sha1( $css ),
            'post_id'    => $post_id,
            'updated_at' => gmdate( 'c' ),
        )
    );
}
