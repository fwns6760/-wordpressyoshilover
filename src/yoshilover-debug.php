<?php
/**
 * Plugin Name: Yoshilover Debug
 * Description: SWELLオプション調査。確認後すぐ削除。
 * Version: 2.0
 */

add_action('rest_api_init', function() {

    // ── /debug : テーマモッズ・オプション確認 ──────────────────────
    register_rest_route('yoshilover/v1', '/debug', [
        'methods'  => 'GET',
        'callback' => function() {
            global $wpdb;
            $results = [];

            // theme_mods
            $results['theme_mods'] = get_theme_mods();

            // swell/yoshilover 関連オプション
            $results['swell_options'] = $wpdb->get_results(
                "SELECT option_name, LEFT(option_value, 300) as option_value
                 FROM {$wpdb->options}
                 WHERE option_name LIKE '%swell%'
                    OR option_name LIKE '%yoshilover%'
                    OR option_name LIKE '%ssp_%'
                    OR option_name LIKE '%rocket%'
                 LIMIT 60"
            );

            // SEO SIMPLE PACK ホームタイトル
            $ssp_general = get_option('ssp_settings_general');
            $results['ssp_settings_general'] = $ssp_general;

            // ブログ名・キャッチフレーズ・WP title
            $results['blogname']        = get_bloginfo('name');
            $results['blogdescription'] = get_bloginfo('description');
            $results['wp_title_option'] = get_option('blogname');

            // Active plugins
            $results['active_plugins'] = get_option('active_plugins');

            // post ID=61088 のメタ確認
            $results['test_post_meta'] = get_post_meta(61088);

            return $results;
        },
        'permission_callback' => '__return_true',
    ]);

    // ── /debug-query : TOPページのWP_Queryを模倣してカテゴリ672確認 ──
    register_rest_route('yoshilover/v1', '/debug-query', [
        'methods'  => 'GET',
        'callback' => function() {
            global $wpdb;
            $results = [];

            // pre_get_posts フックが登録されているか確認
            global $wp_filter;
            $hooks = isset($wp_filter['pre_get_posts']) ? 'registered' : 'NOT registered';
            $results['pre_get_posts_hook'] = $hooks;
            $callback_count = isset($wp_filter['pre_get_posts'])
                ? count($wp_filter['pre_get_posts']->callbacks)
                : 0;
            $results['pre_get_posts_priority_count'] = $callback_count;

            // フィルタなし: デフォルトTOPクエリを模倣
            $q_raw = new WP_Query([
                'post_type'      => 'post',
                'post_status'    => 'publish',
                'posts_per_page' => 15,
                'paged'          => 1,
            ]);
            $cat672_raw = 0;
            foreach ($q_raw->posts as $p) {
                $cats = wp_get_post_categories($p->ID);
                if (in_array(672, $cats, true)) $cat672_raw++;
            }
            $results['raw_query_total']    = $q_raw->found_posts;
            $results['raw_query_cat672']   = $cat672_raw;

            // フィルタあり: category__not_in=672 明示
            $q_excl = new WP_Query([
                'post_type'         => 'post',
                'post_status'       => 'publish',
                'posts_per_page'    => 15,
                'category__not_in'  => [672],
                'paged'             => 1,
            ]);
            $results['excl_query_total']  = $q_excl->found_posts;

            // DB直接: カテゴリ672の投稿数
            $count672 = $wpdb->get_var(
                "SELECT COUNT(DISTINCT tr.object_id)
                 FROM {$wpdb->term_relationships} tr
                 INNER JOIN {$wpdb->posts} p ON p.ID = tr.object_id
                 WHERE tr.term_taxonomy_id = (
                     SELECT tt.term_taxonomy_id FROM {$wpdb->term_taxonomy} tt WHERE tt.term_id = 672 LIMIT 1
                 )
                 AND p.post_status = 'publish'"
            );
            $results['db_cat672_post_count'] = (int)$count672;

            // DB直接: TOPページ表示されている投稿にカテゴリ672が混じっているか
            $recent_posts_sql = "
                SELECT p.ID, p.post_title, GROUP_CONCAT(tt.term_id) AS cat_ids
                FROM {$wpdb->posts} p
                LEFT JOIN {$wpdb->term_relationships} tr ON tr.object_id = p.ID
                LEFT JOIN {$wpdb->term_taxonomy} tt ON tt.term_taxonomy_id = tr.term_taxonomy_id AND tt.taxonomy = 'category'
                WHERE p.post_type = 'post' AND p.post_status = 'publish'
                GROUP BY p.ID
                ORDER BY p.post_date DESC
                LIMIT 15
            ";
            $recent = $wpdb->get_results($recent_posts_sql);
            $has672 = [];
            foreach ($recent as $r) {
                $cats = array_map('intval', explode(',', $r->cat_ids));
                if (in_array(672, $cats, true)) {
                    $has672[] = ['id' => $r->ID, 'title' => $r->post_title, 'cats' => $cats];
                }
            }
            $results['recent15_with_cat672'] = $has672;
            $results['recent15_count'] = count($recent);

            return $results;
        },
        'permission_callback' => '__return_true',
    ]);

    // ── /debug-title : タイトル関連オプション確認 ──────────────────
    register_rest_route('yoshilover/v1', '/debug-title', [
        'methods'  => 'GET',
        'callback' => function() {
            global $wpdb;
            $results = [];

            $results['blogname']         = get_option('blogname');
            $results['blogdescription']  = get_option('blogdescription');
            $results['page_on_front']    = get_option('page_on_front');
            $results['show_on_front']    = get_option('show_on_front');

            // SEO SIMPLE PACK 全設定
            $results['ssp_settings_general'] = get_option('ssp_settings_general');
            $results['ssp_settings_robots']  = get_option('ssp_settings_robots');

            // AIOSEO options full JSON
            $aioseo_raw = get_option('aioseo_options');
            if ($aioseo_raw) {
                $aioseo = json_decode($aioseo_raw, true);
                $results['aioseo_searchAppearance'] = isset($aioseo['searchAppearance'])
                    ? $aioseo['searchAppearance']
                    : 'not found in aioseo_options';
            } else {
                $results['aioseo_options_raw'] = $aioseo_raw;
            }

            // aioseo_options_localized (serialize)
            $localized = get_option('aioseo_options_localized');
            $results['aioseo_options_localized'] = $localized;

            // page 55385 の post meta (AIOSEO, Yoast, All-in-One)
            $results['page_55385_meta'] = get_post_meta(55385);

            // active_plugins
            $results['active_plugins'] = get_option('active_plugins');

            // SWELL SEO設定
            $swell_seo = $wpdb->get_results(
                "SELECT option_name, LEFT(option_value, 800) as option_value
                 FROM {$wpdb->options}
                 WHERE option_name LIKE '%aioseo%'
                    OR option_name LIKE '%wpseo%'
                 LIMIT 20"
            );
            $results['seo_plugin_options'] = $swell_seo;

            return $results;
        },
        'permission_callback' => '__return_true',
    ]);


    // ── /fix-title : SSP ssp_settings の home_title/home_desc を修正 ──
    register_rest_route('yoshilover/v1', '/fix-title', [
        'methods'  => 'POST',
        'callback' => function() {
            $new_title = 'YOSHILOVER｜読売ジャイアンツまとめ';
            $new_desc  = '球場のナイターの熱気をそのままに。ジャイアンツ情報まとめ';
            $results   = [];

            // ssp_settings (正しいオプション名) を更新
            $ssp = get_option('ssp_settings', []);
            if (!is_array($ssp)) $ssp = [];
            $ssp['home_title'] = $new_title;
            $ssp['home_desc']  = $new_desc; // SSPのキー名は home_desc
            update_option('ssp_settings', $ssp);
            $saved = get_option('ssp_settings');
            $results['ssp_settings_home_title'] = $saved['home_title'] ?? 'not set';
            $results['ssp_settings_home_desc']  = $saved['home_desc']  ?? 'not set';

            // blogname / blogdescription 確認
            $results['blogname']       = get_option('blogname');
            $results['blogdescription']= get_option('blogdescription');
            $results['page_on_front']  = get_option('page_on_front');
            $results['show_on_front']  = get_option('show_on_front');

            return $results;
        },
        'permission_callback' => '__return_true',
    ]);

});
