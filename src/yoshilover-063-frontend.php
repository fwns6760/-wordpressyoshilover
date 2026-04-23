<?php
/**
 * Plugin Name: Yoshilover 063 Frontend (topic hub / SNS reactions / Phase 1 noindex)
 * Description: 062 contract §2 §3 §5 の front impl。トップ中央 topic hub(手動表示) + 記事下 SNS 反応 block(公式 X / 中の人 X が per-post meta にある時だけ) + Phase 1 noindex。既存 SWELL コメント欄は触らない。
 * Version: 0.1.0
 * Author: yoshilover
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

add_action( 'rest_api_init', 'yoshilover_063_register_admin_routes' );

/* ------------------------------------------------------------
 * 1) トップ中央 topic hub (062 §2 / 063 §1)
 *
 *    手動表示前提。固定ページ / トップページに
 *    [yoshilover_topic_hub] shortcode を貼るか、
 *    `.yoshi-topic-hub` ネームスペースの HTML を直接書く。
 *
 *    shortcode で出す場合、hub item は下記のいずれかで渡す:
 *      (a) WP option `yoshilover_topic_hub_items` (array)
 *      (b) filter `yoshilover_topic_hub_items`
 *
 *    item の shape:
 *      array(
 *        'title' => string (必須),
 *        'url'   => string (必須、canonical URL),
 *        'lead'  => string (任意、1 行リード),
 *        'badge' => string (任意、短いタグ文字),
 *      )
 *
 *    最大 5 件まで。空なら shortcode は空文字を返す。
 * ---------------------------------------------------------- */

add_shortcode( 'yoshilover_topic_hub', 'yoshilover_063_render_topic_hub' );

function yoshilover_063_get_topic_hub_items() {
    $items = get_option( 'yoshilover_topic_hub_items', array() );
    if ( ! is_array( $items ) ) {
        $items = array();
    }
    $items = apply_filters( 'yoshilover_topic_hub_items', $items );
    if ( ! is_array( $items ) ) {
        return array();
    }
    return array_slice( $items, 0, 5 );
}

function yoshilover_063_sanitize_topic_hub_items( $items ) {
    if ( ! is_array( $items ) ) {
        return array();
    }

    $sanitized = array();
    foreach ( $items as $item ) {
        if ( ! is_array( $item ) ) {
            continue;
        }
        $title = isset( $item['title'] ) ? trim( (string) $item['title'] ) : '';
        $url   = isset( $item['url'] ) ? trim( (string) $item['url'] ) : '';
        $lead  = isset( $item['lead'] ) ? trim( (string) $item['lead'] ) : '';
        $badge = isset( $item['badge'] ) ? trim( (string) $item['badge'] ) : '';

        if ( $title === '' || $url === '' ) {
            continue;
        }

        $sanitized[] = array(
            'title' => $title,
            'url'   => esc_url_raw( $url ),
            'lead'  => $lead,
            'badge' => $badge,
        );
    }

    return array_slice( $sanitized, 0, 5 );
}

function yoshilover_063_render_topic_hub( $atts = array() ) {
    $atts = shortcode_atts(
        array(
            'heading' => '今週の話題',
        ),
        $atts,
        'yoshilover_topic_hub'
    );

    $items = yoshilover_063_get_topic_hub_items();
    if ( empty( $items ) ) {
        return '';
    }

    $html  = '<aside class="yoshi-topic-hub" aria-label="topic hub" data-yoshi-phase="1">';
    $html .= '<h2 class="yoshi-topic-hub__heading">' . esc_html( $atts['heading'] ) . '</h2>';
    $html .= '<ul class="yoshi-topic-hub__items">';

    foreach ( $items as $item ) {
        if ( ! is_array( $item ) ) {
            continue;
        }
        $title = isset( $item['title'] ) ? trim( (string) $item['title'] ) : '';
        $url   = isset( $item['url'] )   ? trim( (string) $item['url'] )   : '';
        $lead  = isset( $item['lead'] )  ? trim( (string) $item['lead'] )  : '';
        $badge = isset( $item['badge'] ) ? trim( (string) $item['badge'] ) : '';

        if ( $title === '' || $url === '' ) {
            continue;
        }

        $html .= '<li class="yoshi-topic-hub__item">';
        $html .= '<a class="yoshi-topic-hub__link" href="' . esc_url( $url ) . '" rel="nofollow">';
        if ( $badge !== '' ) {
            $html .= '<span class="yoshi-topic-hub__badge">' . esc_html( $badge ) . '</span>';
        }
        $html .= '<span class="yoshi-topic-hub__title">' . esc_html( $title ) . '</span>';
        if ( $lead !== '' ) {
            $html .= '<span class="yoshi-topic-hub__lead">' . esc_html( $lead ) . '</span>';
        }
        $html .= '</a>';
        $html .= '</li>';
    }

    $html .= '</ul>';
    $html .= '</aside>';

    return $html;
}

/* ------------------------------------------------------------
 * 2) 記事下 SNS 反応 block (062 §3 / 063 §2)
 *
 *    公式 X: per-post meta `_yoshilover_x_official_url`
 *    中の人 X: per-post meta `_yoshilover_x_insider_url`
 *
 *    - どちらも絶対 URL、x.com / twitter.com のみ
 *    - 両方空なら空 block を出さない(何も出力しない)
 *    - oEmbed で表示、取得失敗時はリンクフォールバック
 *    - singular post の本文末尾に自動挿入
 *    - shortcode でも手動配置可
 * ---------------------------------------------------------- */

add_shortcode( 'yoshilover_sns_reactions', 'yoshilover_063_render_sns_reactions' );
add_filter( 'the_content', 'yoshilover_063_auto_inject_sns_reactions', 20 );

function yoshilover_063_is_x_url( $url ) {
    if ( ! is_string( $url ) || $url === '' ) {
        return false;
    }
    $host = wp_parse_url( $url, PHP_URL_HOST );
    if ( ! $host ) {
        return false;
    }
    $host = strtolower( $host );
    $ok   = array( 'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com' );
    return in_array( $host, $ok, true );
}

function yoshilover_063_get_sns_reactions_for_post( $post_id ) {
    $post_id = (int) $post_id;
    if ( $post_id <= 0 ) {
        return array();
    }

    $official = trim( (string) get_post_meta( $post_id, '_yoshilover_x_official_url', true ) );
    $insider  = trim( (string) get_post_meta( $post_id, '_yoshilover_x_insider_url',  true ) );

    $reactions = array();
    if ( yoshilover_063_is_x_url( $official ) ) {
        $reactions[] = array(
            'role'  => 'official',
            'label' => '公式 X',
            'url'   => $official,
        );
    }
    if ( yoshilover_063_is_x_url( $insider ) ) {
        $reactions[] = array(
            'role'  => 'insider',
            'label' => '中の人 X',
            'url'   => $insider,
        );
    }
    return $reactions;
}

function yoshilover_063_render_sns_reactions( $atts = array() ) {
    $post_id = get_the_ID();
    if ( ! $post_id ) {
        return '';
    }

    $reactions = yoshilover_063_get_sns_reactions_for_post( $post_id );
    if ( empty( $reactions ) ) {
        return '';
    }

    $html  = '<section class="yoshi-sns-reactions" aria-label="SNS 反応" data-yoshi-phase="1">';
    $html .= '<h3 class="yoshi-sns-reactions__heading">SNS での反応</h3>';
    $html .= '<ul class="yoshi-sns-reactions__list">';

    foreach ( $reactions as $r ) {
        $html .= '<li class="yoshi-sns-reactions__item yoshi-sns-reactions__item--' . esc_attr( $r['role'] ) . '">';
        $html .= '<span class="yoshi-sns-reactions__label">' . esc_html( $r['label'] ) . '</span>';

        $embed = wp_oembed_get( $r['url'] );
        if ( $embed ) {
            $html .= '<div class="yoshi-sns-reactions__embed">' . $embed . '</div>';
        } else {
            $html .= '<a class="yoshi-sns-reactions__fallback" href="' . esc_url( $r['url'] )
                  . '" target="_blank" rel="noopener nofollow">' . esc_html( $r['url'] ) . '</a>';
        }
        $html .= '</li>';
    }

    $html .= '</ul>';
    $html .= '</section>';

    return $html;
}

function yoshilover_063_auto_inject_sns_reactions( $content ) {
    if ( is_admin() ) {
        return $content;
    }
    if ( ! in_the_loop() || ! is_main_query() ) {
        return $content;
    }
    if ( ! is_singular( 'post' ) ) {
        return $content;
    }

    $post_id = get_the_ID();
    if ( ! $post_id ) {
        return $content;
    }

    // 既に本文中に shortcode 由来の block がある場合は二重出力しない
    if ( strpos( (string) $content, 'yoshi-sns-reactions' ) !== false ) {
        return $content;
    }

    $reactions = yoshilover_063_get_sns_reactions_for_post( $post_id );
    if ( empty( $reactions ) ) {
        return $content;
    }

    return $content . yoshilover_063_render_sns_reactions();
}

/* ------------------------------------------------------------
 * 3) Phase 1 noindex (062 §5 / 063 §3)
 *
 *    以下の URL / 文脈を Phase 1 では検索 index から外す:
 *      - topic hub 専用ページ (page meta `_yoshilover_topic_hub_page` = '1')
 *      - コメント pagination (cpage > 0)
 *      - replytocom 付き URL
 *      - comment feed
 *
 *    本体記事 (post) の robots meta は一切触らない。
 *    既存 `yoshilover-post-noindex.php` / SEO プラグインの `wp_robots` filter と
 *    自然に merge させるため wp_head 直接 echo を使わず wp_robots に相乗りする。
 *    これにより `<meta name="robots">` が 1 行に統合される。
 * ---------------------------------------------------------- */

add_filter( 'wp_robots', 'yoshilover_063_phase1_noindex_robots' );
add_action( 'send_headers', 'yoshilover_063_phase1_noindex_headers' );

function yoshilover_063_phase1_should_noindex() {
    if ( is_admin() ) {
        return false;
    }

    // hub 専用ページ(固定ページ側のフラグで制御)
    if ( is_page() ) {
        $flag = get_post_meta( get_the_ID(), '_yoshilover_topic_hub_page', true );
        if ( $flag === '1' ) {
            return true;
        }
    }

    // コメント pagination
    if ( is_singular() ) {
        $cpage = (int) get_query_var( 'cpage' );
        if ( $cpage > 0 ) {
            return true;
        }
    }

    // replytocom クエリ付き URL
    if ( isset( $_GET['replytocom'] ) && $_GET['replytocom'] !== '' ) {
        return true;
    }

    if ( function_exists( 'is_comment_feed' ) && is_comment_feed() ) {
        return true;
    }

    return false;
}

function yoshilover_063_phase1_noindex_robots( $robots ) {
    if ( ! is_array( $robots ) ) {
        $robots = array();
    }
    if ( ! yoshilover_063_phase1_should_noindex() ) {
        return $robots;
    }
    // 本体記事の index 指定を上書きせず、noindex/follow を足すだけの形にする
    unset( $robots['index'] );
    $robots['noindex'] = true;
    // follow は既存値があれば尊重、無ければ follow を足す(nofollow を上書きしない)
    if ( ! isset( $robots['nofollow'] ) ) {
        $robots['follow'] = true;
    }
    return $robots;
}

function yoshilover_063_phase1_noindex_headers() {
    if ( function_exists( 'is_comment_feed' ) && is_comment_feed() ) {
        header( 'X-Robots-Tag: noindex, follow' );
    }
}

/* ------------------------------------------------------------
 * 4) deploy / smoke helper (admin only)
 *
 *    live 反映は FTP upload 後に REST 経由で行う。
 *    公開フロントへの影響は manage_options 権限の POST に限定する。
 * ---------------------------------------------------------- */

function yoshilover_063_register_admin_routes() {
    register_rest_route(
        'yoshilover-063/v1',
        '/admin',
        array(
            'methods'             => 'POST',
            'callback'            => 'yoshilover_063_handle_admin_request',
            'permission_callback' => function() {
                return current_user_can( 'manage_options' );
            },
        )
    );
}

function yoshilover_063_handle_admin_request( $request ) {
    $action = sanitize_key( (string) $request->get_param( 'action' ) );

    switch ( $action ) {
        case 'get_theme_mods':
            return yoshilover_063_rest_get_theme_mods( $request );
        case 'search_options':
            return yoshilover_063_rest_search_options( $request );
        case 'set_theme_mod':
            return yoshilover_063_rest_set_theme_mod( $request );
        case 'update_custom_css':
            return yoshilover_063_rest_update_custom_css( $request );
        case 'set_topic_hub_items':
            return yoshilover_063_rest_set_topic_hub_items( $request );
        case 'set_front_top_topic_hub_widget':
            return yoshilover_063_rest_set_front_top_topic_hub_widget( $request );
        case 'set_post_meta':
            return yoshilover_063_rest_set_post_meta( $request );
        case 'get_post_meta':
            return yoshilover_063_rest_get_post_meta( $request );
        case 'clear_cache':
            return yoshilover_063_rest_clear_cache();
        default:
            return new WP_Error(
                'yoshilover_063_unknown_action',
                'Unknown action.',
                array( 'status' => 400 )
            );
    }
}

function yoshilover_063_rest_get_theme_mods( $request ) {
    $mods   = get_theme_mods();
    $needle = strtolower( trim( (string) $request->get_param( 'needle' ) ) );

    if ( $needle === '' ) {
        return array(
            'theme' => get_stylesheet(),
            'mods'  => $mods,
        );
    }

    $filtered = array();
    foreach ( $mods as $key => $value ) {
        if ( false !== strpos( strtolower( (string) $key ), $needle ) ) {
            $filtered[ $key ] = $value;
        }
    }

    return array(
        'theme'  => get_stylesheet(),
        'needle' => $needle,
        'mods'   => $filtered,
    );
}

function yoshilover_063_rest_search_options( $request ) {
    $needle = strtolower( trim( (string) $request->get_param( 'needle' ) ) );
    if ( $needle === '' ) {
        return new WP_Error(
            'yoshilover_063_missing_needle',
            'needle is required.',
            array( 'status' => 400 )
        );
    }

    $matches = array();
    foreach ( wp_load_alloptions() as $key => $value ) {
        if ( false === strpos( strtolower( (string) $key ), $needle ) ) {
            continue;
        }
        if ( is_scalar( $value ) || is_null( $value ) ) {
            $preview = (string) $value;
        } else {
            $preview = wp_json_encode( $value );
        }
        $matches[ $key ] = mb_substr( $preview, 0, 500 );
        if ( count( $matches ) >= 100 ) {
            break;
        }
    }

    return array(
        'needle'  => $needle,
        'matches' => $matches,
    );
}

function yoshilover_063_rest_set_theme_mod( $request ) {
    $key = trim( (string) $request->get_param( 'key' ) );
    if ( $key === '' ) {
        return new WP_Error(
            'yoshilover_063_missing_theme_mod_key',
            'key is required.',
            array( 'status' => 400 )
        );
    }

    $value = $request->get_param( 'value' );
    set_theme_mod( $key, $value );

    return array(
        'key'   => $key,
        'value' => get_theme_mod( $key ),
    );
}

function yoshilover_063_rest_update_custom_css( $request ) {
    $css    = trim( (string) $request->get_param( 'css' ) );
    $marker = trim( (string) $request->get_param( 'marker' ) );

    if ( $css === '' ) {
        return new WP_Error(
            'yoshilover_063_missing_css',
            'css is required.',
            array( 'status' => 400 )
        );
    }

    $current = function_exists( 'wp_get_custom_css' ) ? (string) wp_get_custom_css() : '';
    $merged  = yoshilover_063_merge_custom_css( $current, $css, $marker );
    $result  = wp_update_custom_css_post(
        $merged,
        array( 'stylesheet' => get_stylesheet() )
    );

    if ( is_wp_error( $result ) ) {
        return $result;
    }

    return array(
        'css_post_id'     => (int) $result,
        'contains_marker' => ( $marker !== '' && false !== strpos( $merged, $marker ) ),
        'length'          => strlen( $merged ),
    );
}

function yoshilover_063_merge_custom_css( $current, $section, $marker ) {
    $current = (string) $current;
    $section = trim( (string) $section );
    $marker  = trim( (string) $marker );

    if ( $section === '' ) {
        return $current;
    }

    if ( $marker !== '' ) {
        $marker_pos = strpos( $current, $marker );
        if ( false !== $marker_pos ) {
            $header_pos = strrpos( substr( $current, 0, $marker_pos ), '/*' );
            if ( false === $header_pos ) {
                $header_pos = $marker_pos;
            }
            $current = rtrim( substr( $current, 0, $header_pos ) );
        }
    }

    if ( $current === '' ) {
        return $section . "\n";
    }

    return $current . "\n\n" . $section . "\n";
}

function yoshilover_063_rest_set_topic_hub_items( $request ) {
    $items = yoshilover_063_sanitize_topic_hub_items( $request->get_param( 'items' ) );
    update_option( 'yoshilover_topic_hub_items', $items, false );

    return array(
        'count' => count( $items ),
        'items' => get_option( 'yoshilover_topic_hub_items', array() ),
    );
}

function yoshilover_063_rest_set_front_top_topic_hub_widget( $request ) {
    $shortcode = trim( (string) $request->get_param( 'shortcode' ) );
    if ( $shortcode === '' ) {
        $shortcode = '[yoshilover_topic_hub]';
    }

    $sidebar_id = 'front_top';
    $sidebars   = get_option( 'sidebars_widgets', array() );
    if ( ! is_array( $sidebars ) ) {
        $sidebars = array();
    }

    $text_widgets = get_option( 'widget_text', array() );
    if ( ! is_array( $text_widgets ) ) {
        $text_widgets = array();
    }

    $widget_id = '';
    foreach ( $text_widgets as $number => $widget ) {
        if ( ! is_numeric( $number ) || ! is_array( $widget ) ) {
            continue;
        }
        $text = isset( $widget['text'] ) ? trim( (string) $widget['text'] ) : '';
        if ( $text === $shortcode || false !== strpos( $text, '[yoshilover_topic_hub' ) ) {
            $widget_id = 'text-' . $number;
            $text_widgets[ $number ]['title']  = '';
            $text_widgets[ $number ]['text']   = $shortcode;
            $text_widgets[ $number ]['filter'] = true;
            $text_widgets[ $number ]['visual'] = false;
            break;
        }
    }

    if ( $widget_id === '' ) {
        $max_number = 0;
        foreach ( array_keys( $text_widgets ) as $number ) {
            if ( is_numeric( $number ) ) {
                $max_number = max( $max_number, (int) $number );
            }
        }

        $next_number                = $max_number + 1;
        $widget_id                  = 'text-' . $next_number;
        $text_widgets[ $next_number ] = array(
            'title'  => '',
            'text'   => $shortcode,
            'filter' => true,
            'visual' => false,
        );
    }

    update_option( 'widget_text', $text_widgets, false );

    $front_top = array();
    if ( isset( $sidebars[ $sidebar_id ] ) && is_array( $sidebars[ $sidebar_id ] ) ) {
        $front_top = $sidebars[ $sidebar_id ];
    }

    $front_top = array_values(
        array_filter(
            $front_top,
            function( $id ) use ( $widget_id ) {
                return is_string( $id ) && $id !== $widget_id;
            }
        )
    );
    array_unshift( $front_top, $widget_id );
    $sidebars[ $sidebar_id ] = $front_top;
    update_option( 'sidebars_widgets', $sidebars, false );

    return array(
        'sidebar'   => $sidebar_id,
        'widget_id' => $widget_id,
        'widgets'   => $sidebars[ $sidebar_id ],
        'instance'  => get_option( 'widget_text', array() ),
    );
}

function yoshilover_063_rest_allowed_meta_keys() {
    return array(
        '_yoshilover_x_official_url',
        '_yoshilover_x_insider_url',
        '_yoshilover_topic_hub_page',
    );
}

function yoshilover_063_rest_set_post_meta( $request ) {
    $post_id = absint( $request->get_param( 'post_id' ) );
    $key     = trim( (string) $request->get_param( 'key' ) );
    $delete  = rest_sanitize_boolean( $request->get_param( 'delete' ) );
    $value   = $request->get_param( 'value' );

    if ( $post_id <= 0 || $key === '' ) {
        return new WP_Error(
            'yoshilover_063_missing_meta_target',
            'post_id and key are required.',
            array( 'status' => 400 )
        );
    }

    if ( ! in_array( $key, yoshilover_063_rest_allowed_meta_keys(), true ) ) {
        return new WP_Error(
            'yoshilover_063_meta_key_not_allowed',
            'meta key is not allowed.',
            array( 'status' => 400 )
        );
    }

    if ( ! current_user_can( 'edit_post', $post_id ) ) {
        return new WP_Error(
            'yoshilover_063_cannot_edit_post',
            'You cannot edit this post.',
            array( 'status' => 403 )
        );
    }

    if ( $delete ) {
        delete_post_meta( $post_id, $key );
        $stored = '';
    } else {
        update_post_meta( $post_id, $key, (string) $value );
        $stored = get_post_meta( $post_id, $key, true );
    }

    return array(
        'post_id' => $post_id,
        'key'     => $key,
        'value'   => $stored,
        'deleted' => $delete,
    );
}

function yoshilover_063_rest_get_post_meta( $request ) {
    $post_id = absint( $request->get_param( 'post_id' ) );
    if ( $post_id <= 0 ) {
        return new WP_Error(
            'yoshilover_063_missing_post_id',
            'post_id is required.',
            array( 'status' => 400 )
        );
    }

    $meta = array();
    foreach ( yoshilover_063_rest_allowed_meta_keys() as $key ) {
        $meta[ $key ] = get_post_meta( $post_id, $key, true );
    }

    return array(
        'post_id' => $post_id,
        'meta'    => $meta,
    );
}

function yoshilover_063_rest_clear_cache() {
    $results = array();

    if ( function_exists( 'rocket_clean_domain' ) ) {
        rocket_clean_domain();
        $results['wp_rocket'] = 'cleared';
    }
    if ( function_exists( 'swell_clear_cache' ) ) {
        swell_clear_cache();
        $results['swell'] = 'cleared';
    }
    if ( function_exists( 'wp_cache_flush' ) ) {
        wp_cache_flush();
        $results['wp_object_cache'] = 'flushed';
    }

    return $results;
}
