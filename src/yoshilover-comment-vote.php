<?php
/**
 * Plugin Name: Yoshilover Comment Vote
 * Description: コメントに「グータッチ！/ 喝！」投票ボタンを追加。名前のみでコメント可能。
 * Version: 1.0
 */

if ( ! defined( 'ABSPATH' ) ) exit;

// ──────────────────────────────────────────────────────────
// コメント設定：メール不要・匿名OK
// ──────────────────────────────────────────────────────────
add_filter( 'comment_form_default_fields', function( $fields ) {
    unset( $fields['email'] );
    unset( $fields['url'] );
    unset( $fields['cookies'] );
    $fields['author'] = '<p class="comment-form-author">
        <input id="author" name="author" type="text" placeholder="ニックネーム（任意）" size="30" maxlength="245">
    </p>';
    return $fields;
} );

add_filter( 'comment_form_defaults', function( $defaults ) {
    $defaults['title_reply']         = 'コメントする';
    $defaults['label_submit']        = '書き込む';
    $defaults['comment_notes_before'] = '';
    $defaults['comment_notes_after']  = '';
    $defaults['comment_field'] = '<p class="comment-form-comment">
        <textarea id="comment" name="comment" cols="45" rows="4" placeholder="巨人への熱い思いを書いてください！" required></textarea>
    </p>';
    return $defaults;
} );

// メール必須を外す
add_filter( 'pre_comment_approved', function( $approved, $commentdata ) {
    return $approved;
}, 10, 2 );

// 名前が空の場合「名無しファン」にする
add_filter( 'preprocess_comment', function( $commentdata ) {
    if ( empty( trim( $commentdata['comment_author'] ) ) ) {
        $commentdata['comment_author'] = '名無しファン';
    }
    if ( empty( $commentdata['comment_author_email'] ) ) {
        $commentdata['comment_author_email'] = '';
    }
    return $commentdata;
} );

// メールアドレス必須バリデーションを無効化
add_filter( 'comment_form_field_email', '__return_empty_string' );
remove_filter( 'comment_post', 'wp_new_comment_notify_moderator' );

// ──────────────────────────────────────────────────────────
// DB テーブル作成（プラグイン有効化時）
// ──────────────────────────────────────────────────────────
register_activation_hook( __FILE__, 'ylcv_create_table' );

function ylcv_create_table() {
    global $wpdb;
    $table = $wpdb->prefix . 'comment_votes';
    $charset = $wpdb->get_charset_collate();
    $sql = "CREATE TABLE IF NOT EXISTS {$table} (
        id bigint(20) NOT NULL AUTO_INCREMENT,
        comment_id bigint(20) NOT NULL,
        vote tinyint(1) NOT NULL COMMENT '1=グータッチ, -1=喝',
        voter_ip varchar(45) NOT NULL,
        created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY unique_vote (comment_id, voter_ip),
        KEY comment_id (comment_id)
    ) {$charset};";
    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    dbDelta( $sql );
}

// ──────────────────────────────────────────────────────────
// 投票数取得ヘルパー
// ──────────────────────────────────────────────────────────
function ylcv_get_votes( $comment_id ) {
    global $wpdb;
    $table = $wpdb->prefix . 'comment_votes';
    $good = (int) $wpdb->get_var( $wpdb->prepare(
        "SELECT COUNT(*) FROM {$table} WHERE comment_id = %d AND vote = 1", $comment_id
    ) );
    $bad  = (int) $wpdb->get_var( $wpdb->prepare(
        "SELECT COUNT(*) FROM {$table} WHERE comment_id = %d AND vote = -1", $comment_id
    ) );
    return [ 'good' => $good, 'bad' => $bad ];
}

// ──────────────────────────────────────────────────────────
// 投票ボタンHTML
// ──────────────────────────────────────────────────────────
function ylcv_vote_buttons( $comment_id ) {
    $votes = ylcv_get_votes( $comment_id );
    $nonce = wp_create_nonce( 'ylcv_vote_' . $comment_id );
    return sprintf(
        '<div class="ylcv-buttons" data-comment-id="%d">
            <button class="ylcv-btn ylcv-good" data-vote="1" data-nonce="%s">
                <span class="ylcv-icon">👊</span> グータッチ！
                <span class="ylcv-count">%d</span>
            </button>
            <button class="ylcv-btn ylcv-bad" data-vote="-1" data-nonce="%s">
                <span class="ylcv-icon">📣</span> 喝！
                <span class="ylcv-count">%d</span>
            </button>
        </div>',
        $comment_id, $nonce, $votes['good'], $nonce, $votes['bad']
    );
}

// コメントに投票ボタンを追加
add_filter( 'comment_text', function( $text, $comment ) {
    if ( is_admin() ) return $text;
    return $text . ylcv_vote_buttons( $comment->comment_ID );
}, 10, 2 );

// ──────────────────────────────────────────────────────────
// Ajax: 投票処理
// ──────────────────────────────────────────────────────────
add_action( 'wp_ajax_ylcv_vote',        'ylcv_handle_vote' );
add_action( 'wp_ajax_nopriv_ylcv_vote', 'ylcv_handle_vote' );

function ylcv_handle_vote() {
    $comment_id = (int) ( $_POST['comment_id'] ?? 0 );
    $vote       = (int) ( $_POST['vote'] ?? 0 );
    $nonce      = sanitize_text_field( $_POST['nonce'] ?? '' );

    if ( ! wp_verify_nonce( $nonce, 'ylcv_vote_' . $comment_id ) ) {
        wp_send_json_error( 'invalid nonce' );
    }
    if ( ! in_array( $vote, [ 1, -1 ], true ) ) {
        wp_send_json_error( 'invalid vote' );
    }

    global $wpdb;
    $table  = $wpdb->prefix . 'comment_votes';
    $ip     = sanitize_text_field( $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0' );

    // 既に投票済みか確認
    $exists = $wpdb->get_var( $wpdb->prepare(
        "SELECT vote FROM {$table} WHERE comment_id = %d AND voter_ip = %s",
        $comment_id, $ip
    ) );

    if ( $exists !== null ) {
        if ( (int) $exists === $vote ) {
            // 同じ投票→取り消し
            $wpdb->delete( $table, [ 'comment_id' => $comment_id, 'voter_ip' => $ip ] );
        } else {
            // 別の投票→更新
            $wpdb->update( $table, [ 'vote' => $vote ], [ 'comment_id' => $comment_id, 'voter_ip' => $ip ] );
        }
    } else {
        $wpdb->insert( $table, [
            'comment_id' => $comment_id,
            'vote'       => $vote,
            'voter_ip'   => $ip,
        ] );
    }

    wp_send_json_success( ylcv_get_votes( $comment_id ) );
}

// ──────────────────────────────────────────────────────────
// JS + CSS
// ──────────────────────────────────────────────────────────
add_action( 'wp_enqueue_scripts', function() {
    if ( ! is_singular() ) return;

    wp_add_inline_script( 'jquery', '
    jQuery(function($) {
        $(document).on("click", ".ylcv-btn", function() {
            var $btn = $(this);
            var $wrap = $btn.closest(".ylcv-buttons");
            var commentId = $wrap.data("comment-id");
            var vote = $btn.data("vote");
            var nonce = $btn.data("nonce");

            $.post("' . admin_url('admin-ajax.php') . '", {
                action: "ylcv_vote",
                comment_id: commentId,
                vote: vote,
                nonce: nonce
            }, function(res) {
                if (res.success) {
                    $wrap.find(".ylcv-good .ylcv-count").text(res.data.good);
                    $wrap.find(".ylcv-bad .ylcv-count").text(res.data.bad);
                    $btn.addClass("ylcv-voted");
                    setTimeout(function(){ $btn.removeClass("ylcv-voted"); }, 600);
                }
            });
        });
    });
    ' );

    wp_add_inline_style( 'swell-styles', '
    /* ── コメントフォーム ── */
    #respond { background: #fff; border: 1px solid #e8e8e8; border-top: 3px solid #F5811F; padding: 20px; border-radius: 4px; margin-top: 32px; }
    #respond h3 { font-size: 16px; font-weight: 700; color: #1A1A1A; margin-bottom: 16px; }
    #respond textarea, #respond input[type="text"] {
        width: 100%; border: 1px solid #ddd; border-radius: 4px; padding: 10px 12px;
        font-size: 14px; transition: border-color 0.2s; box-sizing: border-box;
    }
    #respond textarea:focus, #respond input[type="text"]:focus { border-color: #F5811F; outline: none; }
    #respond textarea { height: 100px; resize: vertical; }
    #respond .form-submit { margin-top: 12px; }
    #respond #submit {
        background: #F5811F; color: #fff; border: none; padding: 10px 28px;
        font-size: 14px; font-weight: 700; border-radius: 4px; cursor: pointer;
        transition: opacity 0.2s;
    }
    #respond #submit:hover { opacity: 0.85; }
    .comment-form-author { margin-bottom: 10px; }

    /* ── コメント一覧 ── */
    .comment-list { list-style: none; padding: 0; margin: 0; }
    .comment-list .comment { background: #fff; border: 1px solid #e8e8e8; border-radius: 4px; padding: 14px 16px; margin-bottom: 8px; }
    .comment-list .comment-author { font-weight: 700; font-size: 13px; color: #1A1A1A; }
    .comment-list .comment-meta { font-size: 11px; color: #999; margin-bottom: 8px; }
    .comment-list .comment-content p { font-size: 14px; line-height: 1.7; margin: 0 0 10px; }

    /* ── 投票ボタン ── */
    .ylcv-buttons { display: flex; gap: 8px; margin-top: 8px; }
    .ylcv-btn {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 5px 14px; border: none; border-radius: 20px;
        font-size: 13px; font-weight: 700; cursor: pointer;
        transition: all 0.15s; user-select: none;
    }
    .ylcv-good { background: #FFF3E8; color: #F5811F; border: 2px solid #F5811F; }
    .ylcv-good:hover, .ylcv-good.ylcv-voted { background: #F5811F; color: #fff; }
    .ylcv-bad  { background: #f5f5f5; color: #666; border: 2px solid #ccc; }
    .ylcv-bad:hover, .ylcv-bad.ylcv-voted  { background: #333; color: #fff; border-color: #333; }
    .ylcv-count { font-size: 12px; opacity: 0.85; }
    .ylcv-icon { font-size: 14px; }
    ' );
} );

// ──────────────────────────────────────────────────────────
// メール認証なしでコメント承認
// ──────────────────────────────────────────────────────────
add_filter( 'comment_registration', '__return_false' );
