<?php
/**
 * quick-post.php — 手動即時投稿ページ（スマホ対応）
 * 設置先: yoshilover.com/quick-post.php
 */

define('QP_PASSWORD', 'sebata1413');
define('WP_API_URL',  'https://yoshilover.com/wp-json/wp/v2');
define('WP_USER',     'user');
define('WP_APP_PASS', 'Hs4X TczM i0yq 4Z8l npaq X3j7');

session_start();

// ── ログイン処理 ──
if (isset($_POST['qp_login'])) {
    if ($_POST['qp_password'] === QP_PASSWORD) {
        $_SESSION['qp_auth'] = true;
    } else {
        $login_error = 'パスワードが違います';
    }
}
if (isset($_POST['qp_logout'])) {
    session_destroy();
    header('Location: ' . $_SERVER['PHP_SELF']);
    exit;
}

$authed = !empty($_SESSION['qp_auth']);

// ── カテゴリ一覧 ──
$categories = [
    '試合速報', '選手情報', '首脳陣',
    'ドラフト・育成', 'OB・解説者', '補強・移籍', '球団情報', 'コラム'
];

// ── 投稿処理 ──
$result = null;
if ($authed && isset($_POST['qp_submit'])) {
    $title    = trim($_POST['title'] ?? '');
    $body     = trim($_POST['body']  ?? '');
    $category = trim($_POST['category'] ?? '試合速報');

    if (empty($title)) {
        $result = ['error' => 'タイトルを入力してください'];
    } else {
        // カテゴリID取得
        $cat_res  = wp_api_get('/categories?search=' . urlencode($category) . '&per_page=1');
        $cat_id   = !empty($cat_res) ? (int)$cat_res[0]['id'] : 0;

        // WP投稿
        $content  = $body ? "<p>{$body}</p>" : '<p>詳細はこちらをご覧ください。</p>';
        $post_data = [
            'title'      => $title,
            'content'    => $content,
            'status'     => 'publish',
            'categories' => $cat_id ? [$cat_id] : [],
        ];
        $post = wp_api_post('/posts', $post_data);

        if (!empty($post['id'])) {
            $post_url = $post['link'];
            // X投稿をPython経由で実行
            $escaped_title = escapeshellarg($title);
            $escaped_cat   = escapeshellarg($category);
            $script_dir    = '/home/fwns6760/yoshilover.com/script/yoshilover';
            $cmd = "/usr/bin/python3.6 {$script_dir}/src/x_api_client.py post --post-id {$post['id']} 2>&1";
            $x_output = shell_exec($cmd);
            $result = [
                'success'   => true,
                'post_url'  => $post_url,
                'post_id'   => $post['id'],
                'x_output'  => $x_output,
            ];
        } else {
            $result = ['error' => 'WP投稿に失敗しました: ' . json_encode($post)];
        }
    }
}

// ── WP REST API ヘルパー ──
function wp_api_get($endpoint) {
    $ch = curl_init(WP_API_URL . $endpoint);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_USERPWD        => WP_USER . ':' . WP_APP_PASS,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
        CURLOPT_SSL_VERIFYPEER => false,
    ]);
    $res = curl_exec($ch);
    curl_close($ch);
    return json_decode($res, true);
}

function wp_api_post($endpoint, $data) {
    $ch = curl_init(WP_API_URL . $endpoint);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => json_encode($data),
        CURLOPT_USERPWD        => WP_USER . ':' . WP_APP_PASS,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
        CURLOPT_SSL_VERIFYPEER => false,
    ]);
    $res = curl_exec($ch);
    curl_close($ch);
    return json_decode($res, true);
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex,nofollow">
<title>クイック投稿 — YOSHILOVER</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, sans-serif; background: #1A1A1A; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
.card { background: #fff; border-radius: 8px; padding: 24px; width: 100%; max-width: 480px; border-top: 4px solid #F5811F; }
h1 { font-size: 18px; font-weight: 700; color: #1A1A1A; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }
h1 span { color: #F5811F; }
label { display: block; font-size: 13px; font-weight: 700; color: #333; margin-bottom: 6px; }
input[type="text"], input[type="password"], textarea, select {
    width: 100%; border: 1px solid #ddd; border-radius: 6px; padding: 12px;
    font-size: 16px; transition: border-color 0.2s; appearance: none;
}
input:focus, textarea:focus, select:focus { border-color: #F5811F; outline: none; }
textarea { height: 80px; resize: vertical; }
.field { margin-bottom: 16px; }
.btn {
    width: 100%; background: #F5811F; color: #fff; border: none;
    padding: 14px; font-size: 16px; font-weight: 700; border-radius: 6px;
    cursor: pointer; transition: opacity 0.2s; margin-top: 4px;
}
.btn:active { opacity: 0.8; }
.btn-logout { background: #666; margin-top: 12px; font-size: 13px; padding: 10px; }
.error { background: #fff0f0; border: 1px solid #ffcccc; border-radius: 6px; padding: 12px; color: #c00; font-size: 14px; margin-bottom: 16px; }
.success { background: #f0fff0; border: 1px solid #90EE90; border-radius: 6px; padding: 16px; margin-bottom: 16px; }
.success a { color: #F5811F; font-weight: 700; word-break: break-all; }
.success p { font-size: 14px; margin-top: 8px; color: #333; }
.cats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.cat-btn { background: #f5f5f5; border: 2px solid #ddd; border-radius: 6px; padding: 10px 8px; font-size: 13px; font-weight: 700; cursor: pointer; text-align: center; transition: all 0.15s; }
.cat-btn.active { background: #FFF3E8; border-color: #F5811F; color: #F5811F; }
</style>
</head>
<body>
<div class="card">

<?php if (!$authed): ?>
<!-- ログインフォーム -->
<h1>🔐 <span>YOSHILOVER</span> 管理</h1>
<?php if (!empty($login_error)): ?>
<div class="error"><?= htmlspecialchars($login_error) ?></div>
<?php endif; ?>
<form method="post">
    <div class="field">
        <label>パスワード</label>
        <input type="password" name="qp_password" placeholder="パスワードを入力" autofocus>
    </div>
    <button class="btn" type="submit" name="qp_login">ログイン</button>
</form>

<?php else: ?>
<!-- 投稿フォーム -->
<h1>⚡ <span>クイック投稿</span></h1>

<?php if (!empty($result['error'])): ?>
<div class="error"><?= htmlspecialchars($result['error']) ?></div>
<?php endif; ?>

<?php if (!empty($result['success'])): ?>
<div class="success">
    <strong>✅ 投稿完了！</strong><br>
    <a href="<?= htmlspecialchars($result['post_url']) ?>" target="_blank">
        <?= htmlspecialchars($result['post_url']) ?>
    </a>
    <p>X投稿: <?= nl2br(htmlspecialchars($result['x_output'] ?? '')) ?></p>
</div>
<?php endif; ?>

<form method="post" id="postForm">
    <div class="field">
        <label>タイトル ※必須</label>
        <input type="text" name="title" placeholder="例: 岡本3号逆転弾！🔥" autofocus
               value="<?= htmlspecialchars($_POST['title'] ?? '') ?>">
    </div>
    <div class="field">
        <label>本文（省略可）</label>
        <textarea name="body" placeholder="詳細メモがあれば..."><?= htmlspecialchars($_POST['body'] ?? '') ?></textarea>
    </div>
    <div class="field">
        <label>カテゴリ</label>
        <input type="hidden" name="category" id="categoryInput" value="<?= htmlspecialchars($_POST['category'] ?? '試合速報') ?>">
        <div class="cats">
            <?php foreach ($categories as $cat): ?>
            <div class="cat-btn <?= (($_POST['category'] ?? '試合速報') === $cat) ? 'active' : '' ?>"
                 onclick="selectCat(this, '<?= $cat ?>')">
                <?= htmlspecialchars($cat) ?>
            </div>
            <?php endforeach; ?>
        </div>
    </div>
    <button class="btn" type="submit" name="qp_submit">🚀 公開 + X投稿</button>
</form>

<form method="post">
    <button class="btn btn-logout" type="submit" name="qp_logout">ログアウト</button>
</form>

<?php endif; ?>
</div>

<script>
function selectCat(el, cat) {
    document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('categoryInput').value = cat;
}
</script>
</body>
</html>
