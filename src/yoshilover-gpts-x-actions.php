<?php
/**
 * Plugin Name: Yoshilover GPTs X Actions
 * Description: REST API for GPTs-assisted manual X posting. It never calls the X API or updates article content.
 * Version:     0.2.0
 * Author:      yoshilover
 * License:     GPL-2.0+
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! defined( 'YOSHILOVER_GPTS_X_STATUS_META' ) ) {
    define( 'YOSHILOVER_GPTS_X_STATUS_META', '_yoshilover_gpts_x_status' );
}
if ( ! defined( 'YOSHILOVER_GPTS_X_POSTED_AT_META' ) ) {
    define( 'YOSHILOVER_GPTS_X_POSTED_AT_META', '_yoshilover_gpts_x_posted_at' );
}
if ( ! defined( 'YOSHILOVER_GPTS_X_SKIPPED_AT_META' ) ) {
    define( 'YOSHILOVER_GPTS_X_SKIPPED_AT_META', '_yoshilover_gpts_x_skipped_at' );
}
if ( ! defined( 'YOSHILOVER_GPTS_X_SKIP_REASON_META' ) ) {
    define( 'YOSHILOVER_GPTS_X_SKIP_REASON_META', '_yoshilover_gpts_x_skip_reason' );
}
if ( ! defined( 'YOSHILOVER_GPTS_X_ACTIONS_API_KEY_OPTION' ) ) {
    define( 'YOSHILOVER_GPTS_X_ACTIONS_API_KEY_OPTION', 'yoshilover_gpts_x_actions_api_key' );
}

add_action( 'admin_init', 'yoshilover_gpts_x_actions_register_settings' );
add_action( 'admin_menu', 'yoshilover_gpts_x_actions_register_settings_page' );
add_action( 'rest_api_init', 'yoshilover_gpts_x_actions_register_routes' );

function yoshilover_gpts_x_actions_register_settings() {
    register_setting(
        'yoshilover_gpts_x_actions',
        YOSHILOVER_GPTS_X_ACTIONS_API_KEY_OPTION,
        array(
            'type'              => 'string',
            'sanitize_callback' => 'yoshilover_gpts_x_actions_sanitize_api_key',
            'default'           => '',
        )
    );
}

function yoshilover_gpts_x_actions_register_settings_page() {
    add_options_page(
        'Yoshilover GPTs X Actions',
        'GPTs X Actions',
        'manage_options',
        'yoshilover-gpts-x-actions',
        'yoshilover_gpts_x_actions_render_settings_page'
    );
}

function yoshilover_gpts_x_actions_sanitize_api_key( $value ) {
    return sanitize_text_field( (string) $value );
}

function yoshilover_gpts_x_actions_render_settings_page() {
    if ( ! current_user_can( 'manage_options' ) ) {
        wp_die( esc_html__( 'You do not have permission to manage this setting.', 'yoshilover-gpts-x-actions' ) );
    }

    $option_name = YOSHILOVER_GPTS_X_ACTIONS_API_KEY_OPTION;
    $api_key     = get_option( $option_name, '' );
    if ( ! is_string( $api_key ) ) {
        $api_key = '';
    }
    ?>
    <div class="wrap">
        <h1><?php echo esc_html__( 'Yoshilover GPTs X Actions', 'yoshilover-gpts-x-actions' ); ?></h1>
        <form method="post" action="options.php">
            <?php settings_fields( 'yoshilover_gpts_x_actions' ); ?>
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row">
                        <label for="yoshilover_gpts_x_actions_api_key"><?php echo esc_html__( 'Bearer API key', 'yoshilover-gpts-x-actions' ); ?></label>
                    </th>
                    <td>
                        <input
                            type="password"
                            id="yoshilover_gpts_x_actions_api_key"
                            name="<?php echo esc_attr( $option_name ); ?>"
                            value="<?php echo esc_attr( $api_key ); ?>"
                            class="regular-text"
                            autocomplete="off"
                        />
                        <p class="description"><?php echo esc_html__( 'Used only for GPTs Actions Authorization: Bearer authentication. This plugin does not call the X API.', 'yoshilover-gpts-x-actions' ); ?></p>
                    </td>
                </tr>
            </table>
            <?php submit_button(); ?>
        </form>
    </div>
    <?php
}

function yoshilover_gpts_x_actions_register_routes() {
    register_rest_route(
        'yoshilover/v1',
        '/x-candidates',
        array(
            'methods'             => WP_REST_Server::READABLE,
            'callback'            => 'yoshilover_gpts_x_actions_get_candidates',
            'permission_callback' => 'yoshilover_gpts_x_actions_permission',
            'args'                => array(
                'limit' => array(
                    'type'              => 'integer',
                    'required'          => false,
                    'default'           => 10,
                    'sanitize_callback' => 'absint',
                    'validate_callback' => function( $value ) {
                        return absint( $value ) >= 1;
                    },
                ),
            ),
        )
    );

    register_rest_route(
        'yoshilover/v1',
        '/x-candidates/(?P<id>\d+)/intent-link',
        array(
            'methods'             => WP_REST_Server::CREATABLE,
            'callback'            => 'yoshilover_gpts_x_actions_create_intent_link',
            'permission_callback' => 'yoshilover_gpts_x_actions_permission',
            'args'                => array(
                'id' => array(
                    'type'              => 'integer',
                    'required'          => true,
                    'sanitize_callback' => 'absint',
                ),
                'text' => array(
                    'type'     => 'string',
                    'required' => true,
                ),
            ),
        )
    );

    register_rest_route(
        'yoshilover/v1',
        '/x-candidates/(?P<id>\d+)/posted',
        array(
            'methods'             => WP_REST_Server::CREATABLE,
            'callback'            => 'yoshilover_gpts_x_actions_mark_posted',
            'permission_callback' => 'yoshilover_gpts_x_actions_permission',
            'args'                => array(
                'id' => array(
                    'type'              => 'integer',
                    'required'          => true,
                    'sanitize_callback' => 'absint',
                ),
            ),
        )
    );

    register_rest_route(
        'yoshilover/v1',
        '/x-candidates/(?P<id>\d+)/skip',
        array(
            'methods'             => WP_REST_Server::CREATABLE,
            'callback'            => 'yoshilover_gpts_x_actions_skip_candidate',
            'permission_callback' => 'yoshilover_gpts_x_actions_permission',
            'args'                => array(
                'id' => array(
                    'type'              => 'integer',
                    'required'          => true,
                    'sanitize_callback' => 'absint',
                ),
                'reason' => array(
                    'type'     => 'string',
                    'required' => false,
                ),
            ),
        )
    );
}

function yoshilover_gpts_x_actions_expected_api_key() {
    $key = '';

    if ( defined( 'YOSHILOVER_GPTS_X_ACTIONS_API_KEY' ) ) {
        $key = (string) constant( 'YOSHILOVER_GPTS_X_ACTIONS_API_KEY' );
    }

    if ( '' !== trim( $key ) ) {
        return trim( $key );
    }

    $option_key = get_option( YOSHILOVER_GPTS_X_ACTIONS_API_KEY_OPTION, '' );
    if ( is_string( $option_key ) ) {
        $key = $option_key;
    }

    return trim( $key );
}

function yoshilover_gpts_x_actions_extract_bearer_token( WP_REST_Request $request ) {
    $authorization = (string) $request->get_header( 'authorization' );
    if ( ! preg_match( '/^Bearer\s+(.+)$/i', $authorization, $matches ) ) {
        return '';
    }

    return trim( (string) $matches[1] );
}

function yoshilover_gpts_x_actions_permission( WP_REST_Request $request ) {
    $expected = yoshilover_gpts_x_actions_expected_api_key();
    if ( '' === $expected ) {
        return new WP_Error(
            'gpts_x_api_key_unconfigured',
            'API key is not configured.',
            array( 'status' => 401 )
        );
    }

    $provided = yoshilover_gpts_x_actions_extract_bearer_token( $request );
    if ( '' === $provided || ! hash_equals( $expected, $provided ) ) {
        return new WP_Error(
            'gpts_x_api_key_invalid',
            'Invalid API key.',
            array( 'status' => 401 )
        );
    }

    return true;
}

function yoshilover_gpts_x_actions_get_candidates( WP_REST_Request $request ) {
    $limit = absint( $request->get_param( 'limit' ) );
    if ( $limit < 1 ) {
        $limit = 10;
    }
    $limit = min( $limit, 20 );

    $query = new WP_Query(
        array(
            'post_type'           => 'post',
            'post_status'         => 'publish',
            'posts_per_page'      => $limit,
            'orderby'             => 'date',
            'order'               => 'DESC',
            'ignore_sticky_posts' => true,
            'no_found_rows'       => true,
            'meta_query'          => array(
                'relation' => 'OR',
                array(
                    'key'     => YOSHILOVER_GPTS_X_STATUS_META,
                    'compare' => 'NOT EXISTS',
                ),
                array(
                    'key'     => YOSHILOVER_GPTS_X_STATUS_META,
                    'value'   => array( 'posted', 'skip' ),
                    'compare' => 'NOT IN',
                ),
            ),
        )
    );

    $candidates = array();
    foreach ( $query->posts as $post ) {
        $candidates[] = yoshilover_gpts_x_actions_build_candidate( $post );
    }

    return rest_ensure_response(
        array(
            'candidates' => $candidates,
        )
    );
}

function yoshilover_gpts_x_actions_build_candidate( WP_Post $post ) {
    $post_id = (int) $post->ID;

    return array(
        'id'            => $post_id,
        'title'         => yoshilover_gpts_x_actions_clean_text( get_the_title( $post ) ),
        'url'           => get_permalink( $post ),
        'published_at'  => get_post_time( 'c', true, $post, false ),
        'category'      => yoshilover_gpts_x_actions_get_primary_category( $post_id ),
        'facts_summary' => yoshilover_gpts_x_actions_get_facts_summary( $post ),
        'source_url'    => yoshilover_gpts_x_actions_get_source_url( $post_id ),
        'status'        => 'candidate',
    );
}

function yoshilover_gpts_x_actions_get_primary_category( $post_id ) {
    $categories = get_the_category( $post_id );
    if ( empty( $categories ) || is_wp_error( $categories ) ) {
        return '';
    }

    $fallback = '';
    foreach ( $categories as $category ) {
        if ( ! isset( $category->name ) ) {
            continue;
        }

        $name = yoshilover_gpts_x_actions_clean_text( $category->name );
        if ( '' === $fallback ) {
            $fallback = $name;
        }
        $slug = isset( $category->slug ) ? (string) $category->slug : '';
        if ( in_array( $name, array( 'Uncategorized', 'uncategorized' ), true ) || in_array( $slug, array( 'uncategorized', 'auto-post', 'auto-generated' ), true ) ) {
            continue;
        }

        return $name;
    }

    return $fallback;
}

function yoshilover_gpts_x_actions_get_facts_summary( WP_Post $post ) {
    $excerpt = get_the_excerpt( $post );
    if ( ! is_string( $excerpt ) || '' === trim( $excerpt ) ) {
        return '';
    }

    return yoshilover_gpts_x_actions_trim_text( $excerpt, 180 );
}

function yoshilover_gpts_x_actions_get_source_url( $post_id ) {
    $source_url = get_post_meta( $post_id, '_yoshilover_source_url', true );
    if ( ! is_string( $source_url ) || '' === trim( $source_url ) ) {
        $source_url = get_post_meta( $post_id, 'yl_source_url', true );
    }
    if ( ! is_string( $source_url ) || '' === trim( $source_url ) ) {
        return '';
    }

    return esc_url_raw( $source_url );
}

function yoshilover_gpts_x_actions_create_intent_link( WP_REST_Request $request ) {
    $post = yoshilover_gpts_x_actions_get_open_candidate_post( absint( $request->get_param( 'id' ) ) );
    if ( is_wp_error( $post ) ) {
        return $post;
    }

    $text = $request->get_param( 'text' );
    if ( ! is_string( $text ) || '' === trim( $text ) ) {
        return new WP_Error(
            'gpts_x_text_required',
            'text is required.',
            array( 'status' => 400 )
        );
    }

    $text       = yoshilover_gpts_x_actions_clean_text( $text );
    $intent_url = 'https://twitter.com/intent/tweet?text=' . rawurlencode( $text );

    return rest_ensure_response(
        array(
            'id'         => (int) $post->ID,
            'text'       => $text,
            'intent_url' => $intent_url,
        )
    );
}

function yoshilover_gpts_x_actions_mark_posted( WP_REST_Request $request ) {
    $post = yoshilover_gpts_x_actions_get_open_candidate_post( absint( $request->get_param( 'id' ) ) );
    if ( is_wp_error( $post ) ) {
        return $post;
    }

    $posted_at = current_time( 'mysql', true );
    update_post_meta( $post->ID, YOSHILOVER_GPTS_X_STATUS_META, 'posted' );
    update_post_meta( $post->ID, YOSHILOVER_GPTS_X_POSTED_AT_META, $posted_at );

    return rest_ensure_response(
        array(
            'id'        => (int) $post->ID,
            'status'    => 'posted',
            'posted_at' => $posted_at,
        )
    );
}

function yoshilover_gpts_x_actions_skip_candidate( WP_REST_Request $request ) {
    $post = yoshilover_gpts_x_actions_get_open_candidate_post( absint( $request->get_param( 'id' ) ) );
    if ( is_wp_error( $post ) ) {
        return $post;
    }

    $reason     = $request->get_param( 'reason' );
    $reason     = is_string( $reason ) ? sanitize_text_field( $reason ) : '';
    $skipped_at = current_time( 'mysql', true );

    update_post_meta( $post->ID, YOSHILOVER_GPTS_X_STATUS_META, 'skip' );
    update_post_meta( $post->ID, YOSHILOVER_GPTS_X_SKIPPED_AT_META, $skipped_at );
    if ( '' !== $reason ) {
        update_post_meta( $post->ID, YOSHILOVER_GPTS_X_SKIP_REASON_META, $reason );
    }

    return rest_ensure_response(
        array(
            'id'         => (int) $post->ID,
            'status'     => 'skip',
            'skipped_at' => $skipped_at,
            'reason'     => $reason,
        )
    );
}

function yoshilover_gpts_x_actions_get_open_candidate_post( $post_id ) {
    $post = get_post( $post_id );
    if ( ! $post instanceof WP_Post || 'post' !== $post->post_type || 'publish' !== $post->post_status ) {
        return new WP_Error(
            'gpts_x_candidate_not_found',
            'Candidate was not found.',
            array( 'status' => 404 )
        );
    }

    $status = get_post_meta( $post_id, YOSHILOVER_GPTS_X_STATUS_META, true );
    if ( in_array( $status, array( 'posted', 'skip' ), true ) ) {
        return new WP_Error(
            'gpts_x_candidate_closed',
            'Candidate is already closed.',
            array( 'status' => 409 )
        );
    }

    return $post;
}

function yoshilover_gpts_x_actions_clean_text( $text ) {
    $text = html_entity_decode( (string) $text, ENT_QUOTES | ENT_HTML5, 'UTF-8' );
    $text = wp_strip_all_tags( strip_shortcodes( $text ) );
    $text = preg_replace( '/\s+/u', ' ', $text );

    return trim( (string) $text );
}

function yoshilover_gpts_x_actions_trim_text( $text, $max_length ) {
    $text       = yoshilover_gpts_x_actions_clean_text( $text );
    $max_length = absint( $max_length );
    if ( $max_length < 1 || '' === $text ) {
        return '';
    }

    if ( function_exists( 'mb_strlen' ) && function_exists( 'mb_substr' ) ) {
        if ( mb_strlen( $text, 'UTF-8' ) <= $max_length ) {
            return $text;
        }

        return rtrim( mb_substr( $text, 0, $max_length - 1, 'UTF-8' ) ) . '...';
    }

    if ( strlen( $text ) <= $max_length ) {
        return $text;
    }

    return rtrim( substr( $text, 0, $max_length - 3 ) ) . '...';
}
