<?php
/**
 * Plugin Name: Yoshilover CSS Push
 * Description: REST endpoint for pushing SWELL 追加 CSS automatically. Claude Code front-deploy 用の REST PUT/GET を提供する。
 * Version:     0.1.0
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
