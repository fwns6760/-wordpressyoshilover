<?php
/**
 * Plugin Name: Yoshilover 063 Frontend (topic hub / SNS reactions / Phase 1 noindex)
 * Description: 062 contract §2 §3 §5 の front impl。topic hub / SNS block / noindex を基盤に、トップ速報帯・記事下回遊束・右カラム rail・上部密集ナビ・人気記事導線まで含めて SWELL front を高密度化する。既存 SWELL コメント欄は触らない。
 * Version: 0.7.0
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
add_shortcode( 'yoshilover_dense_nav', 'yoshilover_063_render_dense_nav' );
add_shortcode( 'yoshilover_breaking_strip', 'yoshilover_063_render_breaking_strip' );
add_shortcode( 'yoshilover_today_giants_box', 'yoshilover_063_render_today_giants_box' );
add_shortcode( 'yoshilover_sidebar_rail', 'yoshilover_063_render_sidebar_rail' );
add_action( 'dynamic_sidebar_before', 'yoshilover_063_auto_inject_sidebar_rail', 5, 2 );

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

function yoshilover_063_get_term_link_candidates( $taxonomy, $candidate_keys ) {
    $items = array();

    foreach ( (array) $candidate_keys as $candidate_key ) {
        $candidate_key = trim( (string) $candidate_key );
        if ( $candidate_key === '' ) {
            continue;
        }

        $term = get_term_by( 'slug', sanitize_title( $candidate_key ), $taxonomy );
        if ( ! $term instanceof WP_Term ) {
            $term = get_term_by( 'name', $candidate_key, $taxonomy );
        }
        if ( ! $term instanceof WP_Term ) {
            continue;
        }

        $url = get_term_link( $term );
        if ( is_wp_error( $url ) || ! is_string( $url ) || $url === '' ) {
            continue;
        }

        $items[] = array(
            'label' => $term->name,
            'url'   => $url,
        );
        break;
    }

    return $items;
}

function yoshilover_063_get_dense_nav_items() {
    $items = array(
        array(
            'label' => 'HOME',
            'url'   => home_url( '/' ),
            'tone'  => 'home',
        ),
        array(
            'label' => '全記事',
            'url'   => home_url( '/' ),
            'tone'  => 'all',
        ),
    );

    $maps = array(
        array(
            'label'      => '選手',
            'taxonomy'   => 'post_tag',
            'candidates' => array( '選手', 'player', 'players', '読売ジャイアンツ', '巨人' ),
            'tone'       => 'players',
        ),
        array(
            'label'      => '監督',
            'taxonomy'   => 'post_tag',
            'candidates' => array( '監督', '阿部慎之助', '阿部監督', 'manager' ),
            'tone'       => 'manager',
        ),
        array(
            'label'      => '公示',
            'taxonomy'   => 'category',
            'candidates' => array( '公示', 'notice', '支配下登録', '昇格', '抹消' ),
            'tone'       => 'notice',
        ),
        array(
            'label'      => '試合結果',
            'taxonomy'   => 'category',
            'candidates' => array( '試合結果', '試合後', 'postgame', '試合' ),
            'tone'       => 'postgame',
        ),
        array(
            'label'      => 'ドラフト',
            'taxonomy'   => 'category',
            'candidates' => array( 'ドラフト', 'draft' ),
            'tone'       => 'draft',
        ),
        array(
            'label'      => '球団情報',
            'taxonomy'   => 'category',
            'candidates' => array( '球団情報', '巨人', 'ジャイアンツ', 'team', '球団' ),
            'tone'       => 'team',
        ),
    );

    foreach ( $maps as $map ) {
        $matched = yoshilover_063_get_term_link_candidates( $map['taxonomy'], $map['candidates'] );
        if ( empty( $matched ) ) {
            continue;
        }

        $items[] = array(
            'label' => $map['label'],
            'url'   => $matched[0]['url'],
            'tone'  => $map['tone'],
        );
    }

    $items = apply_filters( 'yoshilover_063_dense_nav_items', $items );
    if ( ! is_array( $items ) ) {
        return array();
    }

    $seen = array();
    $sanitized = array();
    foreach ( $items as $item ) {
        if ( ! is_array( $item ) ) {
            continue;
        }

        $label = isset( $item['label'] ) ? trim( (string) $item['label'] ) : '';
        $url   = isset( $item['url'] ) ? trim( (string) $item['url'] ) : '';
        $tone  = isset( $item['tone'] ) ? sanitize_key( (string) $item['tone'] ) : 'default';
        if ( $label === '' || $url === '' ) {
            continue;
        }
        $key = $label . '|' . $url;
        if ( isset( $seen[ $key ] ) ) {
            continue;
        }
        $seen[ $key ] = true;
        $sanitized[]  = array(
            'label' => $label,
            'url'   => esc_url_raw( $url ),
            'tone'  => $tone !== '' ? $tone : 'default',
        );
    }

    return array_slice( $sanitized, 0, 10 );
}

function yoshilover_063_render_dense_nav( $atts = array() ) {
    $atts = shortcode_atts(
        array(
            'heading' => '回遊ナビ',
        ),
        $atts,
        'yoshilover_dense_nav'
    );

    $items = yoshilover_063_get_dense_nav_items();
    if ( empty( $items ) ) {
        return '';
    }

    $html  = '<nav class="yoshi-dense-nav" aria-label="' . esc_attr( $atts['heading'] ) . '" data-yoshi-phase="5">';
    $html .= '<div class="yoshi-dense-nav__scroll">';
    $html .= '<ul class="yoshi-dense-nav__list">';

    foreach ( $items as $item ) {
        $html .= '<li class="yoshi-dense-nav__item">';
        $html .= '<a class="yoshi-dense-nav__link yoshi-dense-nav__link--' . esc_attr( $item['tone'] ) . '" href="' . esc_url( $item['url'] ) . '">';
        $html .= '<span class="yoshi-dense-nav__label">' . esc_html( $item['label'] ) . '</span>';
        $html .= '</a>';
        $html .= '</li>';
    }

    $html .= '</ul>';
    $html .= '</div>';
    $html .= '</nav>';

    return $html;
}

function yoshilover_063_breaking_strip_target_subtypes() {
    return array(
        'live_update',
        'lineup',
        'notice',
        'probable_starter',
        'postgame',
    );
}

function yoshilover_063_get_breaking_strip_items( $limit = 5 ) {
    $limit = max( 1, min( 5, (int) $limit ) );
    $query = new WP_Query(
        array(
            'post_type'              => 'post',
            'post_status'            => 'publish',
            'posts_per_page'         => 24,
            'ignore_sticky_posts'    => true,
            'no_found_rows'          => true,
            'update_post_meta_cache' => true,
            'update_post_term_cache' => false,
        )
    );

    $items   = array();
    $targets = yoshilover_063_breaking_strip_target_subtypes();

    foreach ( $query->posts as $post ) {
        if ( ! ( $post instanceof WP_Post ) ) {
            continue;
        }

        $text    = yoshilover_063_front_density_text( $post );
        $blob    = yoshilover_063_normalize_front_density_text( $post->post_title . ' ' . $text );
        $subtype = yoshilover_063_resolve_front_density_subtype( $post, $text );

        if ( ! in_array( $subtype, $targets, true ) ) {
            continue;
        }

        $items[] = array(
            'subtype' => $subtype,
            'label'   => yoshilover_063_front_density_subtype_label( $subtype ),
            'title'   => trim( (string) $post->post_title ),
            'url'     => get_permalink( $post ),
            'phase'   => yoshilover_063_extract_front_density_phase( $blob ),
            'score'   => yoshilover_063_extract_front_density_score( $blob ),
            'time'    => yoshilover_063_format_compact_post_time( $post ),
        );

        if ( count( $items ) >= $limit ) {
            break;
        }
    }

    wp_reset_postdata();

    return $items;
}

function yoshilover_063_render_breaking_strip( $atts = array() ) {
    $atts = shortcode_atts(
        array(
            'heading' => '速報帯',
            'limit'   => 5,
        ),
        $atts,
        'yoshilover_breaking_strip'
    );

    $items = yoshilover_063_get_breaking_strip_items( (int) $atts['limit'] );
    if ( empty( $items ) ) {
        return '';
    }

    $html  = '<aside class="yoshi-breaking-strip" aria-label="速報帯" data-yoshi-phase="3">';
    $html .= '<div class="yoshi-breaking-strip__head">';
    $html .= '<h2 class="yoshi-breaking-strip__heading">' . esc_html( $atts['heading'] ) . '</h2>';
    $html .= '<span class="yoshi-breaking-strip__note">試合中 / スタメン / 公示 / 予告先発 / 試合後</span>';
    $html .= '</div>';
    $html .= '<ul class="yoshi-breaking-strip__list">';

    foreach ( $items as $item ) {
        $html .= '<li class="yoshi-breaking-strip__item yoshi-breaking-strip__item--' . esc_attr( $item['subtype'] ) . '">';
        $html .= '<a class="yoshi-breaking-strip__link" href="' . esc_url( $item['url'] ) . '">';
        $html .= '<span class="yoshi-breaking-strip__eyebrow">';
        $html .= '<span class="yoshi-breaking-strip__badge">' . esc_html( $item['label'] ) . '</span>';
        if ( $item['phase'] !== '' ) {
            $html .= '<span class="yoshi-breaking-strip__chip yoshi-breaking-strip__chip--phase">' . esc_html( $item['phase'] ) . '</span>';
        }
        if ( $item['score'] !== '' ) {
            $html .= '<span class="yoshi-breaking-strip__chip yoshi-breaking-strip__chip--score">' . esc_html( $item['score'] ) . '</span>';
        }
        if ( $item['time'] !== '' ) {
            $html .= '<time class="yoshi-breaking-strip__time">' . esc_html( $item['time'] ) . '</time>';
        }
        $html .= '</span>';
        $html .= '<span class="yoshi-breaking-strip__title">' . esc_html( $item['title'] ) . '</span>';
        $html .= '</a>';
        $html .= '</li>';
    }

    $html .= '</ul>';
    $html .= '</aside>';

    return $html;
}

function yoshilover_063_sidebar_primary_indexes() {
    return array(
        'sidebar-1',
        'sidebar',
        'swell_sidebar',
        'widget-area',
    );
}

function yoshilover_063_should_render_sidebar_rail() {
    if ( is_admin() || is_feed() || is_search() || is_404() ) {
        return false;
    }

    return is_front_page() || is_home() || is_singular( 'post' );
}

function yoshilover_063_is_primary_sidebar_index( $index ) {
    $index = strtolower( trim( (string) $index ) );
    if ( $index === '' ) {
        return false;
    }

    if ( in_array( $index, yoshilover_063_sidebar_primary_indexes(), true ) ) {
        return true;
    }

    return false !== strpos( $index, 'sidebar' ) && false === strpos( $index, 'footer' ) && false === strpos( $index, 'front_' );
}

function yoshilover_063_get_today_giants_box_items( $limit = 5 ) {
    $limit = max( 1, min( 5, (int) $limit ) );
    $items = array();
    $seen  = array();

    foreach ( yoshilover_063_get_breaking_strip_items( $limit ) as $item ) {
        $url = isset( $item['url'] ) ? trim( (string) $item['url'] ) : '';
        if ( $url === '' || isset( $seen[ $url ] ) ) {
            continue;
        }

        $items[]      = array(
            'type'    => 'news',
            'subtype' => isset( $item['subtype'] ) ? $item['subtype'] : 'article',
            'label'   => isset( $item['label'] ) ? $item['label'] : '話題',
            'title'   => isset( $item['title'] ) ? $item['title'] : '',
            'url'     => $url,
            'phase'   => isset( $item['phase'] ) ? $item['phase'] : '',
            'score'   => isset( $item['score'] ) ? $item['score'] : '',
            'time'    => isset( $item['time'] ) ? $item['time'] : '',
        );
        $seen[ $url ] = true;

        if ( count( $items ) >= $limit ) {
            return $items;
        }
    }

    foreach ( yoshilover_063_get_topic_hub_items() as $item ) {
        $url = isset( $item['url'] ) ? trim( (string) $item['url'] ) : '';
        if ( $url === '' || isset( $seen[ $url ] ) ) {
            continue;
        }

        $badge = isset( $item['badge'] ) ? trim( (string) $item['badge'] ) : '';
        $items[] = array(
            'type'    => 'topic',
            'subtype' => 'topic',
            'label'   => $badge !== '' ? $badge : '注目',
            'title'   => isset( $item['title'] ) ? trim( (string) $item['title'] ) : '',
            'url'     => $url,
            'phase'   => '',
            'score'   => '',
            'time'    => '',
        );
        $seen[ $url ] = true;

        if ( count( $items ) >= $limit ) {
            break;
        }
    }

    return $items;
}

function yoshilover_063_get_sidebar_topic_links( $limit = 4 ) {
    $items = array();
    foreach ( yoshilover_063_get_topic_hub_items() as $item ) {
        $title = isset( $item['title'] ) ? trim( (string) $item['title'] ) : '';
        $url   = isset( $item['url'] ) ? trim( (string) $item['url'] ) : '';
        if ( $title === '' || $url === '' ) {
            continue;
        }
        $items[] = array(
            'title' => $title,
            'url'   => $url,
            'badge' => isset( $item['badge'] ) ? trim( (string) $item['badge'] ) : '',
        );
        if ( count( $items ) >= $limit ) {
            break;
        }
    }
    return $items;
}

function yoshilover_063_get_sidebar_category_links( $limit = 6 ) {
    $limit      = max( 1, min( 8, (int) $limit ) );
    $categories = get_categories(
        array(
            'hide_empty' => true,
            'orderby'    => 'count',
            'order'      => 'DESC',
            'number'     => $limit + 4,
        )
    );

    $items = array();
    foreach ( $categories as $category ) {
        if ( ! ( $category instanceof WP_Term ) ) {
            continue;
        }

        if ( in_array( $category->slug, array( 'uncategorized', 'old-articles' ), true ) ) {
            continue;
        }

        $items[] = array(
            'name'  => $category->name,
            'url'   => get_category_link( $category ),
            'count' => (int) $category->count,
            'slug'  => (string) $category->slug,
        );
        if ( count( $items ) >= $limit ) {
            break;
        }
    }

    return $items;
}

function yoshilover_063_get_sidebar_popular_items( $limit = 8 ) {
    $limit = max( 1, min( 10, (int) $limit ) );
    $window_start = strtotime( '-3 days', current_time( 'timestamp' ) );

    $query = new WP_Query(
        array(
            'post_type'              => 'post',
            'post_status'            => 'publish',
            'posts_per_page'         => 24,
            'ignore_sticky_posts'    => true,
            'no_found_rows'          => true,
            'date_query'             => array(
                array(
                    'after'     => gmdate( 'Y-m-d H:i:s', $window_start ),
                    'inclusive' => true,
                    'column'    => 'post_date_gmt',
                ),
            ),
            'orderby'                => 'date',
            'order'                  => 'DESC',
            'update_post_meta_cache' => true,
            'update_post_term_cache' => true,
        )
    );

    $ranked = array();
    foreach ( $query->posts as $post ) {
        if ( ! ( $post instanceof WP_Post ) ) {
            continue;
        }

        $comment_count = max( 0, (int) $post->comment_count );
        $age_hours     = max( 1, (int) floor( ( current_time( 'timestamp' ) - get_post_timestamp( $post ) ) / HOUR_IN_SECONDS ) );
        $freshness     = max( 1, 72 - $age_hours );
        $score         = ( $comment_count * 10 ) + $freshness;
        $text          = yoshilover_063_front_density_text( $post );
        $subtype       = yoshilover_063_resolve_front_density_subtype( $post, $text );

        $ranked[] = array(
            'score'         => $score,
            'comment_count' => $comment_count,
            'time'          => yoshilover_063_format_compact_post_time( $post ),
            'label'         => yoshilover_063_front_density_subtype_label( $subtype ),
            'subtype'       => $subtype,
            'title'         => trim( (string) $post->post_title ),
            'url'           => get_permalink( $post ),
        );
    }

    wp_reset_postdata();

    usort(
        $ranked,
        function( $a, $b ) {
            if ( $a['score'] === $b['score'] ) {
                return strcmp( (string) $b['time'], (string) $a['time'] );
            }
            return $b['score'] <=> $a['score'];
        }
    );

    return array_slice( $ranked, 0, $limit );
}

function yoshilover_063_render_sidebar_popular_box( $atts = array() ) {
    $atts = shortcode_atts(
        array(
            'heading' => '最近3日間の人気記事',
            'limit'   => 8,
        ),
        $atts,
        'yoshilover_sidebar_popular'
    );

    $items = yoshilover_063_get_sidebar_popular_items( (int) $atts['limit'] );
    if ( empty( $items ) ) {
        return '';
    }

    $html  = '<section class="yoshi-sidebar-rail__section yoshi-sidebar-rail__section--popular" aria-label="人気記事" data-yoshi-phase="6">';
    $html .= '<h3 class="yoshi-sidebar-rail__title">' . esc_html( $atts['heading'] ) . '</h3>';
    $html .= '<ol class="yoshi-sidebar-rail__popular-list">';

    foreach ( $items as $index => $item ) {
        $html .= '<li class="yoshi-sidebar-rail__popular-item">';
        $html .= '<a class="yoshi-sidebar-rail__popular-link" href="' . esc_url( $item['url'] ) . '">';
        $html .= '<span class="yoshi-sidebar-rail__popular-rank">' . esc_html( (string) ( $index + 1 ) ) . '</span>';
        $html .= '<span class="yoshi-sidebar-rail__popular-body">';
        $html .= '<span class="yoshi-sidebar-rail__popular-meta">';
        $html .= '<span class="yoshi-sidebar-rail__popular-badge yoshi-sidebar-rail__popular-badge--' . esc_attr( $item['subtype'] ) . '">' . esc_html( $item['label'] ) . '</span>';
        if ( $item['comment_count'] > 0 ) {
            $html .= '<span class="yoshi-sidebar-rail__popular-comments">コメント ' . esc_html( (string) $item['comment_count'] ) . '</span>';
        }
        if ( $item['time'] !== '' ) {
            $html .= '<time class="yoshi-sidebar-rail__popular-time">' . esc_html( $item['time'] ) . '</time>';
        }
        $html .= '</span>';
        $html .= '<span class="yoshi-sidebar-rail__popular-title">' . esc_html( $item['title'] ) . '</span>';
        $html .= '</span>';
        $html .= '</a>';
        $html .= '</li>';
    }

    $html .= '</ol>';
    $html .= '</section>';

    return $html;
}

function yoshilover_063_render_today_giants_box( $atts = array() ) {
    $atts = shortcode_atts(
        array(
            'heading' => '今日の巨人',
            'limit'   => 5,
        ),
        $atts,
        'yoshilover_today_giants_box'
    );

    $items = yoshilover_063_get_today_giants_box_items( (int) $atts['limit'] );
    if ( empty( $items ) ) {
        return '';
    }

    $html  = '<section class="yoshi-today-giants" aria-label="今日の巨人" data-yoshi-phase="4">';
    $html .= '<div class="yoshi-today-giants__head">';
    $html .= '<h2 class="yoshi-today-giants__heading">' . esc_html( $atts['heading'] ) . '</h2>';
    $html .= '<span class="yoshi-today-giants__note">速報 / 公示 / 話題を右カラムで圧縮表示</span>';
    $html .= '</div>';
    $html .= '<ul class="yoshi-today-giants__list">';

    foreach ( $items as $item ) {
        $html .= '<li class="yoshi-today-giants__item yoshi-today-giants__item--' . esc_attr( $item['subtype'] ) . '">';
        $html .= '<a class="yoshi-today-giants__link" href="' . esc_url( $item['url'] ) . '">';
        $html .= '<span class="yoshi-today-giants__meta">';
        $html .= '<span class="yoshi-today-giants__badge yoshi-today-giants__badge--' . esc_attr( $item['subtype'] ) . '">' . esc_html( $item['label'] ) . '</span>';
        if ( $item['phase'] !== '' ) {
            $html .= '<span class="yoshi-today-giants__chip">' . esc_html( $item['phase'] ) . '</span>';
        }
        if ( $item['score'] !== '' ) {
            $html .= '<span class="yoshi-today-giants__chip yoshi-today-giants__chip--score">' . esc_html( $item['score'] ) . '</span>';
        }
        if ( $item['time'] !== '' ) {
            $html .= '<time class="yoshi-today-giants__time">' . esc_html( $item['time'] ) . '</time>';
        }
        $html .= '</span>';
        $html .= '<span class="yoshi-today-giants__title">' . esc_html( $item['title'] ) . '</span>';
        $html .= '</a>';
        $html .= '</li>';
    }

    $html .= '</ul>';
    $html .= '</section>';

    return $html;
}

function yoshilover_063_render_sidebar_rail( $atts = array() ) {
    $today_box   = yoshilover_063_render_today_giants_box();
    $popular_box = yoshilover_063_render_sidebar_popular_box();
    $topics      = yoshilover_063_get_sidebar_topic_links( 4 );
    $categories  = yoshilover_063_get_sidebar_category_links( 6 );

    if ( $today_box === '' && $popular_box === '' && empty( $topics ) && empty( $categories ) ) {
        return '';
    }

    $html  = '<aside class="yoshi-sidebar-rail" aria-label="右カラム導線" data-yoshi-phase="4">';
    if ( $today_box !== '' ) {
        $html .= $today_box;
    }

    if ( $popular_box !== '' ) {
        $html .= $popular_box;
    }

    if ( ! empty( $topics ) ) {
        $html .= '<section class="yoshi-sidebar-rail__section yoshi-sidebar-rail__section--topics" aria-label="注目トピック">';
        $html .= '<h3 class="yoshi-sidebar-rail__title">注目トピック</h3>';
        $html .= '<ul class="yoshi-sidebar-rail__topic-list">';
        foreach ( $topics as $item ) {
            $html .= '<li class="yoshi-sidebar-rail__topic-item">';
            $html .= '<a class="yoshi-sidebar-rail__topic-link" href="' . esc_url( $item['url'] ) . '">';
            if ( $item['badge'] !== '' ) {
                $html .= '<span class="yoshi-sidebar-rail__topic-badge">' . esc_html( $item['badge'] ) . '</span>';
            }
            $html .= '<span class="yoshi-sidebar-rail__topic-title">' . esc_html( $item['title'] ) . '</span>';
            $html .= '</a>';
            $html .= '</li>';
        }
        $html .= '</ul>';
        $html .= '</section>';
    }

    if ( ! empty( $categories ) ) {
        $html .= '<section class="yoshi-sidebar-rail__section yoshi-sidebar-rail__section--categories" aria-label="カテゴリ導線">';
        $html .= '<h3 class="yoshi-sidebar-rail__title">カテゴリ導線</h3>';
        $html .= '<div class="yoshi-sidebar-rail__category-chips">';
        foreach ( $categories as $item ) {
            $html .= '<a class="yoshi-sidebar-rail__category-chip yoshi-sidebar-rail__category-chip--' . esc_attr( $item['slug'] ) . '" href="' . esc_url( $item['url'] ) . '">';
            $html .= '<span class="yoshi-sidebar-rail__category-name">' . esc_html( $item['name'] ) . '</span>';
            $html .= '<span class="yoshi-sidebar-rail__category-count">' . esc_html( (string) $item['count'] ) . '</span>';
            $html .= '</a>';
        }
        $html .= '</div>';
        $html .= '</section>';
    }

    $html .= '</aside>';

    return $html;
}

function yoshilover_063_auto_inject_sidebar_rail( $index, $has_widgets ) {
    static $rendered = false;

    if ( $rendered ) {
        return;
    }
    if ( ! yoshilover_063_should_render_sidebar_rail() ) {
        return;
    }
    if ( ! yoshilover_063_is_primary_sidebar_index( $index ) ) {
        return;
    }

    $rail = yoshilover_063_render_sidebar_rail();
    if ( $rail === '' ) {
        return;
    }

    echo $rail; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
    $rendered = true;
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
add_shortcode( 'yoshilover_article_bundles', 'yoshilover_063_render_article_bundles' );
add_shortcode( 'yoshilover_x_follow_cta', 'yoshilover_063_render_x_follow_cta' );
add_filter( 'the_content', 'yoshilover_063_auto_inject_sns_reactions', 20 );
add_filter( 'the_content', 'yoshilover_063_auto_inject_article_bundles', 21 );
add_filter( 'the_content', 'yoshilover_063_auto_inject_x_follow_cta', 22 );

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

function yoshilover_063_render_article_bundles( $atts = array() ) {
    $post = get_post();
    if ( ! ( $post instanceof WP_Post ) || $post->post_type !== 'post' ) {
        return '';
    }

    $groups = yoshilover_063_build_article_bundles_for_post( $post );
    if ( empty( $groups ) ) {
        return '';
    }

    $html  = '<section class="yoshi-article-bundles" aria-label="次に読みたい記事" data-yoshi-phase="3">';
    $html .= '<div class="yoshi-article-bundles__head">';
    $html .= '<h3 class="yoshi-article-bundles__heading">次に読みたい記事</h3>';
    $html .= '<p class="yoshi-article-bundles__lead">同じ試合・同じ選手・同じ話題で続けて追える束だけを出します。</p>';
    $html .= '</div>';
    $html .= '<div class="yoshi-article-bundles__groups">';

    foreach ( $groups as $group ) {
        if ( empty( $group['items'] ) ) {
            continue;
        }
        $html .= '<section class="yoshi-article-bundles__group yoshi-article-bundles__group--' . esc_attr( $group['key'] ) . '">';
        $html .= '<h4 class="yoshi-article-bundles__group-heading">' . esc_html( $group['heading'] ) . '</h4>';
        $html .= '<ul class="yoshi-article-bundles__list">';

        foreach ( $group['items'] as $item ) {
            $html .= '<li class="yoshi-article-bundles__item">';
            $html .= '<a class="yoshi-article-bundles__link" href="' . esc_url( $item['url'] ) . '">';
            $html .= '<span class="yoshi-article-bundles__meta">';
            if ( $item['label'] !== '' ) {
                $html .= '<span class="yoshi-article-bundles__badge yoshi-article-bundles__badge--' . esc_attr( $item['subtype'] ) . '">' . esc_html( $item['label'] ) . '</span>';
            }
            if ( $item['phase'] !== '' ) {
                $html .= '<span class="yoshi-article-bundles__chip">' . esc_html( $item['phase'] ) . '</span>';
            }
            if ( $item['score'] !== '' ) {
                $html .= '<span class="yoshi-article-bundles__chip yoshi-article-bundles__chip--score">' . esc_html( $item['score'] ) . '</span>';
            }
            if ( $item['time'] !== '' ) {
                $html .= '<time class="yoshi-article-bundles__time">' . esc_html( $item['time'] ) . '</time>';
            }
            $html .= '</span>';
            $html .= '<span class="yoshi-article-bundles__title">' . esc_html( $item['title'] ) . '</span>';
            if ( $item['summary'] !== '' ) {
                $html .= '<span class="yoshi-article-bundles__summary">' . esc_html( $item['summary'] ) . '</span>';
            }
            $html .= '</a>';
            $html .= '</li>';
        }

        $html .= '</ul>';
        $html .= '</section>';
    }

    $html .= '</div>';
    $html .= '</section>';

    return $html;
}

function yoshilover_063_auto_inject_article_bundles( $content ) {
    if ( is_admin() ) {
        return $content;
    }
    if ( ! in_the_loop() || ! is_main_query() ) {
        return $content;
    }
    if ( ! is_singular( 'post' ) ) {
        return $content;
    }

    $post = get_post();
    if ( ! ( $post instanceof WP_Post ) || $post->post_type !== 'post' ) {
        return $content;
    }

    if ( strpos( (string) $content, 'yoshi-article-bundles' ) !== false ) {
        return $content;
    }

    $bundles = yoshilover_063_render_article_bundles();
    if ( $bundles === '' ) {
        return $content;
    }

    return $content . $bundles;
}

/**
 * X フォロー CTA block 設定取得。
 *
 * option `yoshilover_063_x_follow_cta` で以下キーを受け付ける:
 *   - enabled (bool): default false (opt-in)
 *   - handle  (string): X のアカウント (既定 yoshilover6760)
 *   - lead    (string): 上部小ラベル (既定 FOLLOW ON X)
 *   - title   (string): メイン訴求文 (既定「最新情報を X で追いかけよう」)
 *   - btn     (string): ボタン文言 (既定 FOLLOW)
 */
function yoshilover_063_get_x_follow_cta_settings() {
    $defaults = array(
        'enabled' => false,
        'handle'  => 'yoshilover6760',
        'lead'    => 'FOLLOW ON X',
        'title'   => '最新情報を X で追いかけよう',
        'btn'     => 'FOLLOW',
    );
    $raw = get_option( 'yoshilover_063_x_follow_cta', array() );
    if ( ! is_array( $raw ) ) {
        $raw = array();
    }
    return array_merge( $defaults, $raw );
}

function yoshilover_063_render_x_follow_cta( $atts = array() ) {
    $atts = shortcode_atts(
        array(
            'handle' => '',
            'lead'   => '',
            'title'  => '',
            'btn'    => '',
        ),
        $atts,
        'yoshilover_x_follow_cta'
    );

    $settings = yoshilover_063_get_x_follow_cta_settings();
    $handle   = $atts['handle'] !== '' ? $atts['handle'] : $settings['handle'];
    $lead     = $atts['lead']   !== '' ? $atts['lead']   : $settings['lead'];
    $title    = $atts['title']  !== '' ? $atts['title']  : $settings['title'];
    $btn      = $atts['btn']    !== '' ? $atts['btn']    : $settings['btn'];

    $handle = ltrim( (string) $handle, '@' );
    if ( $handle === '' ) {
        return '';
    }
    $url = 'https://x.com/' . rawurlencode( $handle );

    $html  = '<aside class="yoshi-x-follow-cta" aria-label="X フォロー CTA" data-yoshi-phase="7">';
    $html .= '<span class="yoshi-x-follow-cta__logo" aria-hidden="true">𝕏</span>';
    $html .= '<div class="yoshi-x-follow-cta__body">';
    $html .= '<div class="yoshi-x-follow-cta__lead">' . esc_html( $lead ) . '</div>';
    $html .= '<div class="yoshi-x-follow-cta__title">' . esc_html( $title ) . ' <span style="color:var(--orange);font-weight:700;">@' . esc_html( $handle ) . '</span></div>';
    $html .= '</div>';
    $html .= '<a class="yoshi-x-follow-cta__btn" href="' . esc_url( $url ) . '" rel="noopener" target="_blank">' . esc_html( $btn ) . '</a>';
    $html .= '</aside>';

    return $html;
}

function yoshilover_063_auto_inject_x_follow_cta( $content ) {
    if ( is_admin() ) {
        return $content;
    }
    if ( ! in_the_loop() || ! is_main_query() ) {
        return $content;
    }
    if ( ! is_singular( 'post' ) ) {
        return $content;
    }

    $settings = yoshilover_063_get_x_follow_cta_settings();
    if ( empty( $settings['enabled'] ) ) {
        return $content;
    }

    if ( strpos( (string) $content, 'yoshi-x-follow-cta' ) !== false ) {
        return $content;
    }

    $cta = yoshilover_063_render_x_follow_cta();
    if ( $cta === '' ) {
        return $content;
    }

    return $content . $cta;
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
add_action( 'wp_enqueue_scripts', 'yoshilover_063_enqueue_front_density_assets' );

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
 * 4) トップ一覧の情報密度強化 (063-V2)
 *
 *    - front page / posts page の一覧カードにだけ補助 meta を差し込む
 *    - src route / pickup / validator には触らない
 *    - subtype / 試合状況 / 要約 1 行を client-side で安全に後付けする
 * ---------------------------------------------------------- */

function yoshilover_063_should_enhance_front_density() {
    if ( is_admin() ) {
        return false;
    }
    if ( is_feed() || is_singular() ) {
        return false;
    }
    return is_front_page() || is_home();
}

function yoshilover_063_enqueue_front_density_assets() {
    if ( ! yoshilover_063_should_enhance_front_density() ) {
        return;
    }

    $cards = yoshilover_063_build_front_density_cards();
    if ( empty( $cards ) ) {
        return;
    }

    wp_register_script( 'yoshilover-063-front-density', false, array(), '0.7.0', true );
    wp_enqueue_script( 'yoshilover-063-front-density' );

    $payload = array(
        'cards' => $cards,
    );

    $script = <<<'JS'
(() => {
  const config = window.yoshilover063FrontDensity || {};
  const cards = config.cards || {};
  const normalizePath = (href) => {
    try {
      const url = new URL(href, window.location.origin);
      const path = (url.pathname || '').replace(/\/+$/, '');
      return path || '/';
    } catch (error) {
      return href || '';
    }
  };
  const createNode = (tag, className, text) => {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
  };
  const injectCard = (item, meta) => {
    if (!item || !meta || item.dataset.yoshiFrontDensity === '1') {
      return;
    }
    const body = item.querySelector('.p-postList__body');
    const title = body ? body.querySelector('.p-postList__title, .p-postList__ttl, h2') : null;
    if (!body || !title) {
      return;
    }

    const metaRow = document.createElement('div');
    metaRow.className = 'yoshi-front-card__meta';

    if (meta.label) {
      metaRow.appendChild(createNode('span', `yoshi-front-card__badge yoshi-front-card__badge--${meta.subtype || 'generic'}`, meta.label));
    }
    if (meta.phase) {
      metaRow.appendChild(createNode('span', 'yoshi-front-card__chip yoshi-front-card__chip--phase', meta.phase));
    }
    if (meta.score) {
      metaRow.appendChild(createNode('span', 'yoshi-front-card__chip yoshi-front-card__chip--score', meta.score));
    }
    if (meta.comment_count && Number(meta.comment_count) > 0) {
      metaRow.appendChild(createNode('span', 'yoshi-front-card__chip yoshi-front-card__chip--comments yoshi-sidebar-rail__popular-comments', `💬 ${meta.comment_count}`));
    }
    if (meta.primary_player) {
      metaRow.appendChild(createNode('span', 'yoshi-front-card__chip yoshi-front-card__chip--player', meta.primary_player));
    }
    if (meta.read_length_label) {
      metaRow.appendChild(createNode('span', `yoshi-front-card__chip yoshi-front-card__chip--read yoshi-front-card__chip--read-${meta.read_length_tone || 'mid'}`, meta.read_length_label));
    }
    if (meta.chain) {
      metaRow.appendChild(createNode('span', 'yoshi-front-card__chip yoshi-front-card__chip--chain', meta.chain));
    }
    const detailRow = document.createElement('div');
    detailRow.className = 'yoshi-front-card__detail';
    if (meta.is_new) {
      detailRow.appendChild(createNode('span', 'yoshi-front-card__detail-chip yoshi-front-card__detail-chip--new', 'NEW'));
    }
    if (meta.relative_time) {
      detailRow.appendChild(createNode('time', 'yoshi-front-card__detail-chip yoshi-front-card__detail-chip--time', meta.relative_time));
    }
    if (meta.opponent) {
      detailRow.appendChild(createNode('span', 'yoshi-front-card__detail-chip yoshi-front-card__detail-chip--opponent', meta.opponent));
    }
    if (meta.primary_category) {
      detailRow.appendChild(createNode('span', 'yoshi-front-card__detail-chip yoshi-front-card__detail-chip--category', meta.primary_category));
    }
    if (meta.primary_tag) {
      detailRow.appendChild(createNode('span', 'yoshi-front-card__detail-chip yoshi-front-card__detail-chip--tag', meta.primary_tag));
    }
    if (meta.summary) {
      const summary = createNode('p', 'yoshi-front-card__summary', meta.summary);
      title.insertAdjacentElement('afterend', summary);
      if (detailRow.childNodes.length > 0) {
        summary.insertAdjacentElement('afterend', detailRow);
      }
    } else if (detailRow.childNodes.length > 0) {
      title.insertAdjacentElement('afterend', detailRow);
    }
    if (metaRow.childNodes.length > 0) {
      title.insertAdjacentElement('beforebegin', metaRow);
    }

    item.dataset.yoshiFrontDensity = '1';
    item.classList.add('is-yoshi-front-density');
    if (meta.subtype) {
      item.classList.add(`is-yoshi-subtype-${meta.subtype}`);
    }
  };

  document.querySelectorAll('.p-postList__item').forEach((item) => {
    const link = item.querySelector('a[href]');
    if (!link) {
      return;
    }
    const meta = cards[normalizePath(link.href)];
    if (meta) {
      injectCard(item, meta);
    }
  });
})();
JS;

    wp_add_inline_script(
        'yoshilover-063-front-density',
        'window.yoshilover063FrontDensity = ' . wp_json_encode( $payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES ) . ';',
        'before'
    );
    wp_add_inline_script( 'yoshilover-063-front-density', $script, 'after' );
}

function yoshilover_063_build_front_density_cards() {
    global $wp_query;

    $source_posts = array();
    if ( $wp_query instanceof WP_Query && ! empty( $wp_query->posts ) && is_array( $wp_query->posts ) ) {
        foreach ( $wp_query->posts as $post ) {
            if ( $post instanceof WP_Post && $post->post_type === 'post' ) {
                $source_posts[] = $post;
            }
        }
    }

    if ( empty( $source_posts ) ) {
        $fallback_query = new WP_Query(
            array(
                'post_type'           => 'post',
                'post_status'         => 'publish',
                'posts_per_page'      => max( 6, (int) get_option( 'posts_per_page', 10 ) ),
                'ignore_sticky_posts' => true,
                'paged'               => max( 1, (int) get_query_var( 'paged' ) ),
            )
        );
        $source_posts = is_array( $fallback_query->posts ) ? $fallback_query->posts : array();
        wp_reset_postdata();
    }

    if ( empty( $source_posts ) ) {
        return array();
    }

    $cards    = array();
    $contexts = array();

    foreach ( $source_posts as $post ) {
        if ( ! ( $post instanceof WP_Post ) ) {
            continue;
        }

        $card = yoshilover_063_build_front_density_card( $post );
        if ( empty( $card['path'] ) ) {
            continue;
        }

        $path = $card['path'];
        unset( $card['path'] );
        $cards[ $path ] = $card;

        if ( ! empty( $card['context_key'] ) ) {
            $contexts[] = $card['context_key'];
        }
    }

    if ( ! empty( $contexts ) ) {
        $counts = array_count_values( $contexts );
        foreach ( $cards as $path => $card ) {
            $context_key = isset( $card['context_key'] ) ? $card['context_key'] : '';
            $count       = $context_key && isset( $counts[ $context_key ] ) ? (int) $counts[ $context_key ] : 0;
            if ( $count > 1 && isset( $card['subtype'] ) && $card['subtype'] === 'live_update' ) {
                $cards[ $path ]['chain'] = '連投 ' . $count . '本';
            }
        }
    }

    foreach ( array_keys( $cards ) as $path ) {
        unset( $cards[ $path ]['context_key'] );
    }

    return $cards;
}

function yoshilover_063_build_front_density_card( $post ) {
    $path             = yoshilover_063_normalize_front_card_path( get_permalink( $post ) );
    $text             = yoshilover_063_front_density_text( $post );
    $subtype          = yoshilover_063_resolve_front_density_subtype( $post, $text );
    $combined_text    = $post->post_title . ' ' . $text;
    $phase            = yoshilover_063_extract_front_density_phase( $combined_text );
    $score            = yoshilover_063_extract_front_density_score( $combined_text );
    $summary          = yoshilover_063_build_front_density_summary( $post, $text, $phase );
    $categories       = yoshilover_063_get_post_term_names( $post->ID, 'category' );
    $tags             = yoshilover_063_get_post_term_names( $post->ID, 'post_tag' );
    $comment_count    = max( 0, (int) get_comments_number( $post->ID ) );
    $relative_time    = yoshilover_063_format_relative_post_time( $post );
    $compact_time     = yoshilover_063_format_compact_post_time( $post );
    $primary_category = ! empty( $categories[0] ) ? (string) $categories[0] : '';
    $primary_player   = yoshilover_063_front_density_primary_player( $post );
    $primary_tag      = yoshilover_063_front_density_primary_tag( $tags, $primary_player );
    $read_length      = yoshilover_063_front_density_read_length( $post, $subtype );
    $opponent         = yoshilover_063_front_density_extract_opponent( $combined_text );

    return array(
        'path'             => $path,
        'subtype'          => $subtype,
        'label'            => yoshilover_063_front_density_subtype_label( $subtype ),
        'phase'            => $phase,
        'score'            => $score,
        'summary'          => $summary,
        'is_new'           => yoshilover_063_is_recent_post( $post, DAY_IN_SECONDS ),
        'relative_time'    => $relative_time !== '' ? $relative_time : $compact_time,
        'comment_count'    => $comment_count,
        'primary_player'   => $primary_player,
        'read_length_label' => isset( $read_length['label'] ) ? (string) $read_length['label'] : '',
        'read_length_tone' => isset( $read_length['tone'] ) ? (string) $read_length['tone'] : '',
        'primary_category' => $primary_category,
        'primary_tag'      => $primary_tag,
        'opponent'         => $opponent,
        'context_key'      => yoshilover_063_front_density_context_key( $post, $subtype, $combined_text ),
    );
}

function yoshilover_063_normalize_front_card_path( $url ) {
    $path = wp_parse_url( (string) $url, PHP_URL_PATH );
    if ( ! is_string( $path ) || $path === '' ) {
        return '';
    }
    $path = '/' . ltrim( $path, '/' );
    $path = rtrim( $path, '/' );
    return $path === '' ? '/' : $path;
}

function yoshilover_063_front_density_text( $post ) {
    $excerpt = trim( (string) $post->post_excerpt );
    $source  = $excerpt !== '' ? $excerpt : (string) $post->post_content;
    $source  = strip_shortcodes( $source );
    $source  = preg_replace( '/<!--[\s\S]*?-->/', ' ', $source );
    $source  = wp_strip_all_tags( $source, true );
    return yoshilover_063_normalize_front_density_text( $source );
}

function yoshilover_063_front_density_primary_player( $post ) {
    if ( ! ( $post instanceof WP_Post ) ) {
        return '';
    }

    $term_groups = array(
        get_the_tags( $post->ID ),
        get_the_category( $post->ID ),
    );

    foreach ( $term_groups as $terms ) {
        if ( ! is_array( $terms ) ) {
            continue;
        }

        foreach ( $terms as $term ) {
            if ( ! ( $term instanceof WP_Term ) ) {
                continue;
            }

            $name = trim( (string) $term->name );
            $slug = trim( (string) $term->slug );
            if ( $name === '' || yoshilover_063_front_density_is_generic_player_term( $name, $slug ) ) {
                continue;
            }
            if ( yoshilover_063_looks_like_player_token( $name ) ) {
                return yoshilover_063_strip_person_suffix( $name );
            }
        }
    }

    return '';
}

function yoshilover_063_front_density_is_generic_player_term( $name, $slug = '' ) {
    $blocked = array(
        'player',
        'players',
        '選手',
        '選手情報',
        '巨人',
        'ジャイアンツ',
        '読売',
        '東京ドーム',
        '試合速報',
        '首脳陣',
        '球団情報',
        'コラム',
        'ドラフト',
        '育成',
        'ドラフト・育成',
        '補強・移籍',
        'ob・解説者',
        'ファーム',
        '二軍',
        '公示',
        'スタメン',
        '予告先発',
    );

    $name_norm = yoshilover_063_normalize_lookup_token( $name );
    $slug_norm = yoshilover_063_normalize_lookup_token( $slug );

    return in_array( $name_norm, $blocked, true ) || in_array( $slug_norm, $blocked, true );
}

function yoshilover_063_front_density_primary_tag( $tags, $primary_player = '' ) {
    $player_norm = yoshilover_063_normalize_lookup_token( yoshilover_063_strip_person_suffix( $primary_player ) );

    foreach ( (array) $tags as $tag ) {
        $tag      = trim( (string) $tag );
        $tag_norm = yoshilover_063_normalize_lookup_token( yoshilover_063_strip_person_suffix( $tag ) );
        if ( $tag === '' ) {
            continue;
        }
        if ( $player_norm !== '' && $tag_norm === $player_norm ) {
            continue;
        }
        return $tag;
    }

    return '';
}

function yoshilover_063_front_density_read_length( $post, $subtype = '' ) {
    if ( (string) $subtype === 'live_update' ) {
        return array(
            'label' => '',
            'tone'  => '',
        );
    }

    $content = wp_strip_all_tags( (string) get_the_content( null, false, $post ), true );
    $content = trim( preg_replace( '/\s+/u', ' ', $content ) );
    $length  = function_exists( 'mb_strlen' ) ? mb_strlen( $content ) : strlen( $content );

    if ( $length < 500 ) {
        return array(
            'label' => '短',
            'tone'  => 'short',
        );
    }
    if ( $length <= 1500 ) {
        return array(
            'label' => '中',
            'tone'  => 'mid',
        );
    }

    return array(
        'label' => '長',
        'tone'  => 'long',
    );
}

function yoshilover_063_normalize_front_density_text( $text ) {
    $text = html_entity_decode( (string) $text, ENT_QUOTES, 'UTF-8' );
    $text = preg_replace( '/[\x{00A0}\s]+/u', ' ', $text );
    $text = preg_replace( '/\s+([、。！？】])/u', '$1', $text );
    $text = preg_replace( '/([【（(])\s+/u', '$1', $text );
    $text = preg_replace( '/\s+(投手|選手|監督)/u', '$1', $text );
    return trim( (string) $text );
}

function yoshilover_063_resolve_front_density_subtype( $post, $text ) {
    $meta_keys = array(
        'article_subtype',
        '_article_subtype',
        'subtype',
        'article_type',
        '_article_type',
    );

    foreach ( $meta_keys as $meta_key ) {
        $value = trim( (string) get_post_meta( $post->ID, $meta_key, true ) );
        if ( $value !== '' ) {
            return yoshilover_063_normalize_front_density_subtype( $value );
        }
    }

    $haystack = yoshilover_063_normalize_front_density_text( $post->post_title . ' ' . $text );

    if ( preg_match( '/(試合終了|サヨナラ|敗戦|勝利|終盤)/u', $haystack ) ) {
        return 'postgame';
    }
    if ( preg_match( '/(回表|回裏|連投|登板|無失点)/u', $haystack ) ) {
        return 'live_update';
    }
    if ( preg_match( '/(スタメン|先発投手|試合開始)/u', $haystack ) ) {
        return 'lineup';
    }
    if ( preg_match( '/(公示|登録|抹消|昇格|降格|合流)/u', $haystack ) ) {
        return 'notice';
    }
    if ( preg_match( '/(予告先発)/u', $haystack ) ) {
        return 'probable_starter';
    }
    if ( preg_match( '/(試合前)/u', $haystack ) ) {
        return 'pregame';
    }
    if ( preg_match( '/(二軍|ファーム)/u', $haystack ) ) {
        return 'farm';
    }
    return 'article';
}

function yoshilover_063_normalize_front_density_subtype( $value ) {
    $value = strtolower( trim( (string) $value ) );
    $value = str_replace( array( '-', ' ' ), '_', $value );

    $map = array(
        'postgame_result'   => 'postgame',
        'live_anchor'       => 'live_update',
        'lineup_notice'     => 'lineup',
        'farm_lineup'       => 'farm',
        'fact_notice'       => 'article',
        'probablestarter'   => 'probable_starter',
        'probable_starter'  => 'probable_starter',
        'notice'            => 'notice',
        'comment_notice'    => 'notice',
        'roster_notice'     => 'notice',
        'transaction'       => 'notice',
    );

    return isset( $map[ $value ] ) ? $map[ $value ] : $value;
}

function yoshilover_063_front_density_subtype_label( $subtype ) {
    $labels = array(
        'live_update'      => '試合中',
        'lineup'           => 'スタメン',
        'postgame'         => '試合後',
        'pregame'          => '試合前',
        'probable_starter' => '予告先発',
        'notice'           => '公示',
        'farm'             => '二軍',
        'article'          => '話題',
    );

    return isset( $labels[ $subtype ] ) ? $labels[ $subtype ] : '話題';
}

function yoshilover_063_extract_front_density_phase( $text ) {
    if ( preg_match( '/【([^】]{1,20})】/u', (string) $text, $matches ) ) {
        return trim( (string) $matches[1] );
    }
    if ( preg_match( '/(試合終了|試合開始|延長\d+回|[一二三四五六七八九十0-9]+回[表裏])/u', (string) $text, $matches ) ) {
        return trim( (string) $matches[1] );
    }
    return '';
}

function yoshilover_063_extract_front_density_score( $text ) {
    if ( preg_match( '/(\d+)\s*[-－]\s*(\d+)/u', (string) $text, $matches ) ) {
        return $matches[1] . '-' . $matches[2];
    }
    return '';
}

function yoshilover_063_build_front_density_summary( $post, $text, $phase ) {
    $summary = trim( (string) $text );

    if ( $phase !== '' ) {
        $summary = preg_replace( '/^【' . preg_quote( $phase, '/' ) . '】/u', '', $summary );
    }
    $summary = preg_replace( '/^📌\s*関連ポスト/u', '', $summary );
    $summary = trim( (string) $summary );

    $sentences = preg_split( '/(?<=[。！？])/u', $summary, -1, PREG_SPLIT_NO_EMPTY );
    if ( is_array( $sentences ) && ! empty( $sentences[0] ) ) {
        $summary = trim( (string) $sentences[0] );
    }

    if ( $summary === '' ) {
        $summary = trim( (string) $post->post_title );
    }

    if ( function_exists( 'mb_strimwidth' ) ) {
        $summary = mb_strimwidth( $summary, 0, 120, '…', 'UTF-8' );
    } else {
        $summary = substr( $summary, 0, 120 );
    }

    return yoshilover_063_normalize_front_density_text( $summary );
}

function yoshilover_063_front_density_context_key( $post, $subtype, $text ) {
    if ( $subtype !== 'live_update' ) {
        return '';
    }

    $opponent = yoshilover_063_front_density_extract_opponent( $text );
    if ( $opponent === '' ) {
        return '';
    }

    return get_the_date( 'Ymd', $post ) . ':' . $subtype . ':' . $opponent;
}

function yoshilover_063_opponent_team_names() {
    return array(
        'ヤクルト',
        '阪神',
        '広島',
        'DeNA',
        '横浜',
        '中日',
        '西武',
        'ソフトバンク',
        '日本ハム',
        'ロッテ',
        'オリックス',
        '楽天',
    );
}

function yoshilover_063_front_density_extract_opponent( $text ) {
    foreach ( yoshilover_063_opponent_team_names() as $team ) {
        if ( false !== mb_strpos( (string) $text, $team ) ) {
            return $team;
        }
    }

    return '';
}

function yoshilover_063_format_compact_post_time( $post ) {
    $timestamp = (int) get_post_time( 'U', true, $post );
    if ( $timestamp <= 0 ) {
        return '';
    }

    $now    = function_exists( 'current_time' ) ? (int) current_time( 'timestamp', true ) : time();
    $format = wp_date( 'Ymd', $timestamp ) === wp_date( 'Ymd', $now ) ? 'H:i' : 'm/d H:i';
    return wp_date( $format, $timestamp );
}

function yoshilover_063_is_recent_post( $post, $window = DAY_IN_SECONDS ) {
    $timestamp = (int) get_post_time( 'U', true, $post );
    if ( $timestamp <= 0 ) {
        return false;
    }

    $now = function_exists( 'current_time' ) ? (int) current_time( 'timestamp', true ) : time();
    return ( $now - $timestamp ) <= (int) $window;
}

function yoshilover_063_format_relative_post_time( $post ) {
    $timestamp = (int) get_post_time( 'U', true, $post );
    if ( $timestamp <= 0 ) {
        return '';
    }

    $now   = function_exists( 'current_time' ) ? (int) current_time( 'timestamp', true ) : time();
    $diff  = max( 0, $now - $timestamp );
    $day   = DAY_IN_SECONDS;
    $hour  = HOUR_IN_SECONDS;
    $min   = MINUTE_IN_SECONDS;

    if ( $diff > $day ) {
        return '';
    }
    if ( $diff < $hour ) {
        $minutes = max( 1, (int) floor( $diff / $min ) );
        return $minutes . '分前';
    }

    $hours = max( 1, (int) floor( $diff / $hour ) );
    return $hours . '時間前';
}

function yoshilover_063_first_non_empty_meta( $post_id, $keys ) {
    foreach ( (array) $keys as $key ) {
        $value = trim( (string) get_post_meta( (int) $post_id, (string) $key, true ) );
        if ( $value !== '' ) {
            return $value;
        }
    }
    return '';
}

function yoshilover_063_is_gameish_subtype( $subtype ) {
    return in_array(
        (string) $subtype,
        array( 'live_update', 'lineup', 'postgame', 'pregame', 'probable_starter', 'farm' ),
        true
    );
}

function yoshilover_063_get_post_term_names( $post_id, $taxonomy ) {
    $terms = wp_get_post_terms( (int) $post_id, (string) $taxonomy );
    if ( is_wp_error( $terms ) || ! is_array( $terms ) ) {
        return array();
    }

    $names = array();
    foreach ( $terms as $term ) {
        if ( ! ( $term instanceof WP_Term ) ) {
            continue;
        }
        $name = trim( (string) $term->name );
        if ( $name !== '' ) {
            $names[] = $name;
        }
    }

    return yoshilover_063_unique_tokens( $names );
}

function yoshilover_063_normalize_lookup_token( $token ) {
    $token = trim( (string) $token );
    if ( $token === '' ) {
        return '';
    }
    if ( function_exists( 'mb_strtolower' ) ) {
        return mb_strtolower( $token, 'UTF-8' );
    }
    return strtolower( $token );
}

function yoshilover_063_unique_tokens( $tokens ) {
    $unique = array();
    foreach ( (array) $tokens as $token ) {
        $token = trim( (string) $token );
        $norm  = yoshilover_063_normalize_lookup_token( $token );
        if ( $norm === '' ) {
            continue;
        }
        if ( ! isset( $unique[ $norm ] ) ) {
            $unique[ $norm ] = $token;
        }
    }
    return array_values( $unique );
}

function yoshilover_063_shared_tokens( $left, $right ) {
    $right_map = array();
    foreach ( (array) $right as $token ) {
        $norm = yoshilover_063_normalize_lookup_token( $token );
        if ( $norm !== '' ) {
            $right_map[ $norm ] = trim( (string) $token );
        }
    }

    $shared = array();
    foreach ( (array) $left as $token ) {
        $norm = yoshilover_063_normalize_lookup_token( $token );
        if ( $norm !== '' && isset( $right_map[ $norm ] ) ) {
            $shared[ $norm ] = trim( (string) $token );
        }
    }

    return array_values( $shared );
}

function yoshilover_063_strip_person_suffix( $token ) {
    $token = trim( (string) $token );
    $token = preg_replace( '/(投手|選手|捕手|内野手|外野手)$/u', '', $token );
    return trim( (string) $token );
}

function yoshilover_063_looks_like_player_token( $token ) {
    $token = yoshilover_063_strip_person_suffix( $token );
    if ( $token === '' ) {
        return false;
    }

    $blocked = array_merge(
        array(
            '巨人',
            'ジャイアンツ',
            '読売',
            '東京ドーム',
            'セリーグ',
            'パリーグ',
            'スタメン',
            '予告先発',
            '公示',
            '試合前',
            '試合中',
            '試合後',
        ),
        yoshilover_063_opponent_team_names()
    );

    if ( in_array( $token, $blocked, true ) ) {
        return false;
    }

    return (bool) preg_match(
        "/^(?:[一-龠々]{2,4}|[ァ-ヴー]{2,12}|[A-Za-z][A-Za-z'\\- ]{1,20})$/u",
        $token
    );
}

function yoshilover_063_extract_player_tokens( $text, $tags = array() ) {
    $tokens = array();

    foreach ( (array) $tags as $tag ) {
        if ( yoshilover_063_looks_like_player_token( $tag ) ) {
            $tokens[] = yoshilover_063_strip_person_suffix( $tag );
        }
    }

    if ( preg_match_all( "/((?:[一-龠々]{2,4}|[ァ-ヴー]{2,12}|[A-Za-z][A-Za-z'\\- ]{1,20}))(?:投手|選手|捕手|内野手|外野手)/u", (string) $text, $matches ) ) {
        foreach ( $matches[1] as $match ) {
            if ( yoshilover_063_looks_like_player_token( $match ) ) {
                $tokens[] = yoshilover_063_strip_person_suffix( $match );
            }
        }
    }

    return array_slice( yoshilover_063_unique_tokens( $tokens ), 0, 4 );
}

function yoshilover_063_is_noise_topic_token( $token ) {
    $noise = array(
        'ニュース',
        '話題',
        '記事',
        '速報',
        '巨人',
        'ジャイアンツ',
        '読売',
        '試合速報',
        '未分類',
    );

    return in_array( trim( (string) $token ), $noise, true );
}

function yoshilover_063_extract_topic_tokens( $text, $tags = array(), $subtype = 'article', $player_tokens = array() ) {
    $tokens        = array();
    $player_lookup = array();

    foreach ( (array) $player_tokens as $player_token ) {
        $norm = yoshilover_063_normalize_lookup_token( $player_token );
        if ( $norm !== '' ) {
            $player_lookup[ $norm ] = true;
        }
    }

    $label = yoshilover_063_front_density_subtype_label( $subtype );
    if ( $label !== '' && $label !== '話題' ) {
        $tokens[] = $label;
    }

    foreach ( (array) $tags as $tag ) {
        $tag  = trim( (string) $tag );
        $norm = yoshilover_063_normalize_lookup_token( $tag );
        if ( $tag === '' || isset( $player_lookup[ $norm ] ) || yoshilover_063_is_noise_topic_token( $tag ) ) {
            continue;
        }
        $tokens[] = $tag;
    }

    $patterns = array(
        '/公示|登録|抹消|昇格|降格/u'   => '公示',
        '/予告先発/u'                    => '予告先発',
        '/スタメン/u'                    => 'スタメン',
        '/試合終了|サヨナラ|敗戦|勝利/u' => '試合後',
        '/回表|回裏/u'                    => '試合中',
        '/二軍|ファーム/u'                => '二軍',
        '/本塁打|打点|安打/u'             => '打撃',
        '/先発|登板|無失点|セーブ/u'       => '投手',
        '/故障|離脱|復帰/u'               => 'コンディション',
        '/ドラフト|育成/u'               => 'ドラフト',
    );

    foreach ( $patterns as $pattern => $label_token ) {
        if ( preg_match( $pattern, (string) $text ) ) {
            $tokens[] = $label_token;
        }
    }

    return array_slice( yoshilover_063_unique_tokens( $tokens ), 0, 6 );
}

function yoshilover_063_build_article_context( $post ) {
    if ( ! ( $post instanceof WP_Post ) ) {
        return array();
    }

    $text          = yoshilover_063_front_density_text( $post );
    $blob          = yoshilover_063_normalize_front_density_text( $post->post_title . ' ' . $text );
    $subtype       = yoshilover_063_resolve_front_density_subtype( $post, $text );
    $phase         = yoshilover_063_extract_front_density_phase( $blob );
    $categories    = yoshilover_063_get_post_term_names( $post->ID, 'category' );
    $tags          = yoshilover_063_get_post_term_names( $post->ID, 'post_tag' );
    $player_tokens = yoshilover_063_extract_player_tokens( $blob, $tags );

    return array(
        'id'         => (int) $post->ID,
        'post'       => $post,
        'subtype'    => $subtype,
        'label'      => yoshilover_063_front_density_subtype_label( $subtype ),
        'title'      => trim( (string) $post->post_title ),
        'url'        => get_permalink( $post ),
        'summary'    => yoshilover_063_build_front_density_summary( $post, $text, $phase ),
        'phase'      => $phase,
        'score'      => yoshilover_063_extract_front_density_score( $blob ),
        'time'       => yoshilover_063_format_compact_post_time( $post ),
        'timestamp'  => (int) get_post_time( 'U', true, $post ),
        'date_key'   => get_the_date( 'Ymd', $post ),
        'game_id'    => yoshilover_063_first_non_empty_meta( $post->ID, array( 'game_id', '_game_id' ) ),
        'opponent'   => yoshilover_063_front_density_extract_opponent( $blob ),
        'categories' => $categories,
        'topic_tags' => array_values(
            array_filter(
                $tags,
                function( $tag ) use ( $player_tokens ) {
                    return empty( yoshilover_063_shared_tokens( array( $tag ), $player_tokens ) ) && ! yoshilover_063_is_noise_topic_token( $tag );
                }
            )
        ),
        'players'    => $player_tokens,
        'topics'     => yoshilover_063_extract_topic_tokens( $blob, $tags, $subtype, $player_tokens ),
    );
}

function yoshilover_063_get_article_bundle_candidates( $exclude_post_id ) {
    $query = new WP_Query(
        array(
            'post_type'              => 'post',
            'post_status'            => 'publish',
            'post__not_in'           => array( (int) $exclude_post_id ),
            'posts_per_page'         => 36,
            'ignore_sticky_posts'    => true,
            'no_found_rows'          => true,
            'update_post_meta_cache' => true,
            'update_post_term_cache' => true,
        )
    );

    $contexts = array();
    foreach ( $query->posts as $post ) {
        if ( $post instanceof WP_Post ) {
            $contexts[] = yoshilover_063_build_article_context( $post );
        }
    }

    wp_reset_postdata();

    return $contexts;
}

function yoshilover_063_prepare_article_bundle_item( $context ) {
    return array(
        'post_id'  => (int) $context['id'],
        'url'      => (string) $context['url'],
        'title'    => (string) $context['title'],
        'summary'  => (string) $context['summary'],
        'subtype'  => (string) $context['subtype'],
        'label'    => (string) $context['label'],
        'phase'    => (string) $context['phase'],
        'score'    => (string) $context['score'],
        'time'     => (string) $context['time'],
    );
}

function yoshilover_063_finalize_article_bundle_selection( $ranked, &$used_ids, $limit = 3 ) {
    if ( empty( $ranked ) ) {
        return array();
    }

    usort(
        $ranked,
        function( $left, $right ) {
            if ( $left['score'] === $right['score'] ) {
                return (int) $right['context']['timestamp'] <=> (int) $left['context']['timestamp'];
            }
            return (int) $right['score'] <=> (int) $left['score'];
        }
    );

    $items = array();
    foreach ( $ranked as $row ) {
        $context = $row['context'];
        $post_id = isset( $context['id'] ) ? (int) $context['id'] : 0;
        if ( $post_id <= 0 || isset( $used_ids[ $post_id ] ) ) {
            continue;
        }
        $items[]            = yoshilover_063_prepare_article_bundle_item( $context );
        $used_ids[ $post_id ] = true;
        if ( count( $items ) >= $limit ) {
            break;
        }
    }

    return $items;
}

function yoshilover_063_select_same_game_bundle_items( $context, $candidate_contexts, &$used_ids ) {
    if ( empty( $context['game_id'] ) && ( empty( $context['opponent'] ) || ! yoshilover_063_is_gameish_subtype( $context['subtype'] ) ) ) {
        return array();
    }

    $ranked = array();
    foreach ( $candidate_contexts as $candidate_context ) {
        if ( empty( $candidate_context['id'] ) || isset( $used_ids[ (int) $candidate_context['id'] ] ) ) {
            continue;
        }

        $score = 0;
        if ( $context['game_id'] !== '' && $candidate_context['game_id'] !== '' && $context['game_id'] === $candidate_context['game_id'] ) {
            $score = 100;
        } elseif (
            $context['opponent'] !== '' &&
            $candidate_context['opponent'] === $context['opponent'] &&
            yoshilover_063_is_gameish_subtype( $candidate_context['subtype'] ) &&
            abs( (int) $candidate_context['timestamp'] - (int) $context['timestamp'] ) <= ( DAY_IN_SECONDS * 2 )
        ) {
            $score = 75;
        }

        if ( $score <= 0 ) {
            continue;
        }
        if ( $candidate_context['subtype'] !== $context['subtype'] ) {
            $score += 4;
        }

        $ranked[] = array(
            'score'   => $score,
            'context' => $candidate_context,
        );
    }

    return yoshilover_063_finalize_article_bundle_selection( $ranked, $used_ids, 3 );
}

function yoshilover_063_select_same_player_bundle_items( $context, $candidate_contexts, &$used_ids ) {
    if ( empty( $context['players'] ) ) {
        return array();
    }

    $ranked = array();
    foreach ( $candidate_contexts as $candidate_context ) {
        if ( empty( $candidate_context['id'] ) || isset( $used_ids[ (int) $candidate_context['id'] ] ) ) {
            continue;
        }

        $shared_players = yoshilover_063_shared_tokens( $context['players'], $candidate_context['players'] );
        if ( empty( $shared_players ) ) {
            continue;
        }

        $score = 50 + ( count( $shared_players ) * 12 );
        if ( $candidate_context['subtype'] === $context['subtype'] ) {
            $score += 3;
        }

        $ranked[] = array(
            'score'   => $score,
            'context' => $candidate_context,
        );
    }

    return yoshilover_063_finalize_article_bundle_selection( $ranked, $used_ids, 3 );
}

function yoshilover_063_select_same_topic_bundle_items( $context, $candidate_contexts, &$used_ids ) {
    $ranked = array();
    foreach ( $candidate_contexts as $candidate_context ) {
        if ( empty( $candidate_context['id'] ) || isset( $used_ids[ (int) $candidate_context['id'] ] ) ) {
            continue;
        }

        $shared_topics     = yoshilover_063_shared_tokens( $context['topics'], $candidate_context['topics'] );
        $shared_topic_tags = yoshilover_063_shared_tokens( $context['topic_tags'], $candidate_context['topic_tags'] );
        $shared_categories = yoshilover_063_shared_tokens( $context['categories'], $candidate_context['categories'] );

        $score = ( count( $shared_topics ) * 6 ) + ( count( $shared_topic_tags ) * 4 ) + ( count( $shared_categories ) * 2 );
        if ( $candidate_context['subtype'] === $context['subtype'] ) {
            $score += 2;
        }

        if ( $score <= 0 ) {
            continue;
        }

        $ranked[] = array(
            'score'   => $score,
            'context' => $candidate_context,
        );
    }

    return yoshilover_063_finalize_article_bundle_selection( $ranked, $used_ids, 3 );
}

function yoshilover_063_build_article_bundles_for_post( $post ) {
    $context = yoshilover_063_build_article_context( $post );
    if ( empty( $context ) ) {
        return array();
    }

    $candidate_contexts = yoshilover_063_get_article_bundle_candidates( $post->ID );
    if ( empty( $candidate_contexts ) ) {
        return array();
    }

    $used_ids = array();
    $groups   = array();

    $same_game = yoshilover_063_select_same_game_bundle_items( $context, $candidate_contexts, $used_ids );
    if ( ! empty( $same_game ) ) {
        $groups[] = array(
            'key'     => 'same_game',
            'heading' => '同じ試合',
            'items'   => $same_game,
        );
    }

    $same_player = yoshilover_063_select_same_player_bundle_items( $context, $candidate_contexts, $used_ids );
    if ( ! empty( $same_player ) ) {
        $groups[] = array(
            'key'     => 'same_player',
            'heading' => '同じ選手',
            'items'   => $same_player,
        );
    }

    $same_topic = yoshilover_063_select_same_topic_bundle_items( $context, $candidate_contexts, $used_ids );
    if ( ! empty( $same_topic ) ) {
        $groups[] = array(
            'key'     => 'same_topic',
            'heading' => '同じ話題',
            'items'   => $same_topic,
        );
    }

    return $groups;
}

/* ------------------------------------------------------------
 * 5) deploy / smoke helper (admin only)
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
        case 'set_front_top_widget_stack':
            return yoshilover_063_rest_set_front_top_widget_stack( $request );
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

function yoshilover_063_extract_shortcode_tag( $shortcode ) {
    if ( preg_match( '/\[([a-z0-9_-]+)/i', (string) $shortcode, $matches ) ) {
        return sanitize_key( (string) $matches[1] );
    }
    return '';
}

function yoshilover_063_upsert_text_widget_shortcode( &$text_widgets, $shortcode ) {
    $widget_id = '';
    $tag       = yoshilover_063_extract_shortcode_tag( $shortcode );

    foreach ( $text_widgets as $number => $widget ) {
        if ( ! is_numeric( $number ) || ! is_array( $widget ) ) {
            continue;
        }
        $text = isset( $widget['text'] ) ? trim( (string) $widget['text'] ) : '';
        if ( $text === $shortcode || ( $tag !== '' && false !== strpos( $text, '[' . $tag ) ) ) {
            $widget_id = 'text-' . $number;
            $text_widgets[ $number ]['title']  = '';
            $text_widgets[ $number ]['text']   = $shortcode;
            $text_widgets[ $number ]['filter'] = true;
            $text_widgets[ $number ]['visual'] = false;
            break;
        }
    }

    if ( $widget_id !== '' ) {
        return $widget_id;
    }

    $max_number = 0;
    foreach ( array_keys( $text_widgets ) as $number ) {
        if ( is_numeric( $number ) ) {
            $max_number = max( $max_number, (int) $number );
        }
    }

    $next_number                  = $max_number + 1;
    $widget_id                    = 'text-' . $next_number;
    $text_widgets[ $next_number ] = array(
        'title'  => '',
        'text'   => $shortcode,
        'filter' => true,
        'visual' => false,
    );

    return $widget_id;
}

function yoshilover_063_ensure_front_top_widget_stack( $shortcodes ) {
    $sidebar_id = 'front_top';
    $sidebars   = get_option( 'sidebars_widgets', array() );
    if ( ! is_array( $sidebars ) ) {
        $sidebars = array();
    }

    $text_widgets = get_option( 'widget_text', array() );
    if ( ! is_array( $text_widgets ) ) {
        $text_widgets = array();
    }

    $shortcodes = array_values(
        array_filter(
            array_map(
                function( $shortcode ) {
                    return trim( (string) $shortcode );
                },
                (array) $shortcodes
            )
        )
    );

    $widget_ids = array();
    foreach ( $shortcodes as $shortcode ) {
        $widget_id = yoshilover_063_upsert_text_widget_shortcode( $text_widgets, $shortcode );
        if ( $widget_id !== '' ) {
            $widget_ids[] = $widget_id;
        }
    }

    update_option( 'widget_text', $text_widgets, false );

    $front_top = array();
    if ( isset( $sidebars[ $sidebar_id ] ) && is_array( $sidebars[ $sidebar_id ] ) ) {
        $front_top = $sidebars[ $sidebar_id ];
    }

    $front_top = array_values(
        array_filter(
            $front_top,
            function( $id ) use ( $widget_ids ) {
                return is_string( $id ) && ! in_array( $id, $widget_ids, true );
            }
        )
    );

    $sidebars[ $sidebar_id ] = array_merge( $widget_ids, $front_top );
    update_option( 'sidebars_widgets', $sidebars, false );

    return array(
        'sidebar'   => $sidebar_id,
        'widgets'   => $sidebars[ $sidebar_id ],
        'widget_ids'=> $widget_ids,
        'instance'  => get_option( 'widget_text', array() ),
    );
}

function yoshilover_063_rest_set_front_top_topic_hub_widget( $request ) {
    $shortcode = trim( (string) $request->get_param( 'shortcode' ) );
    if ( $shortcode === '' ) {
        $shortcode = '[yoshilover_topic_hub]';
    }

    $result              = yoshilover_063_ensure_front_top_widget_stack( array( $shortcode ) );
    $result['widget_id'] = ! empty( $result['widget_ids'][0] ) ? $result['widget_ids'][0] : '';
    return $result;
}

function yoshilover_063_rest_set_front_top_widget_stack( $request ) {
    $shortcodes = $request->get_param( 'shortcodes' );
    if ( ! is_array( $shortcodes ) || empty( $shortcodes ) ) {
        $shortcodes = array(
            '[yoshilover_dense_nav]',
            '[yoshilover_breaking_strip]',
            '[yoshilover_topic_hub]',
        );
    }

    return yoshilover_063_ensure_front_top_widget_stack( $shortcodes );
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
