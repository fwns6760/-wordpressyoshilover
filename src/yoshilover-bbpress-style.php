<?php
/**
 * Plugin Name: Yoshilover bbPress Style
 * Description: bbPressを巨人カラー（オレンジ＋黒）にスタイリング
 * Version: 1.0
 */
if ( ! defined( 'ABSPATH' ) ) exit;

add_action( 'wp_head', function() {
    if ( ! function_exists( 'is_bbpress' ) ) return;
    ?>
<style>
/* ========= bbPress 巨人カラー ========= */
#bbpress-forums .bbp-forum-title a,
#bbpress-forums .bbp-topic-title a {
    color: #F5811F !important;
    font-weight: bold;
}
#bbpress-forums #new-post,
#bbpress-forums .bbp-submit-wrapper button,
#bbpress-forums a.button {
    background-color: #F5811F !important;
    color: #fff !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 8px 20px !important;
    font-weight: bold !important;
}
#bbpress-forums li.bbp-header {
    background-color: #1a1a1a !important;
    color: #fff !important;
    padding: 10px 15px !important;
}
#bbpress-forums li.bbp-header span { color: #fff !important; }
#bbpress-forums ul.bbp-topics li,
#bbpress-forums ul.bbp-forums li {
    border-left: 3px solid #F5811F;
    margin-bottom: 4px;
    padding-left: 10px;
}
#bbpress-forums div.bbp-reply-author,
#bbpress-forums div.bbp-topic-author {
    background-color: #1a1a1a !important;
    color: #fff !important;
    border-radius: 4px 0 0 4px;
}
#bbpress-forums div.bbp-reply-author .bbp-author-name a,
#bbpress-forums div.bbp-topic-author .bbp-author-name a {
    color: #F5811F !important;
    font-weight: bold;
}
#bbpress-forums div.bbp-reply-content,
#bbpress-forums div.bbp-topic-content {
    border-left: 3px solid #F5811F;
    padding-left: 15px;
}
#bbpress-forums .bbp-breadcrumb {
    background-color: #f8f8f8;
    padding: 8px 12px;
    border-radius: 4px;
    border-left: 4px solid #F5811F;
    margin-bottom: 16px;
}
#bbpress-forums .bbp-pagination .bbp-pagination-links a,
#bbpress-forums .bbp-pagination .bbp-pagination-links span {
    border: 1px solid #F5811F;
    color: #F5811F;
    border-radius: 3px;
    padding: 3px 8px;
}
#bbpress-forums .bbp-pagination .bbp-pagination-links .current {
    background-color: #F5811F;
    color: #fff;
}
</style>
    <?php
} );
