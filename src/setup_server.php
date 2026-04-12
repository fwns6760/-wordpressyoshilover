<?php
$password = "sebata1413";
if (!isset($_GET['key']) || $_GET['key'] !== $password) {
    die("Access denied");
}

$action = $_GET['action'] ?? 'info';
$home   = '/home/fwns6760';
$base   = "{$home}/yoshilover.com/script/yoshilover";

// python3のパスを探す
$python = '/usr/bin/python3.6';
foreach (['/usr/bin/python3.6', '/usr/bin/python3', '/usr/local/bin/python3.6', '/usr/local/bin/python3'] as $p) {
    if (file_exists($p)) { $python = $p; break; }
}

echo "<pre>";

if ($action === 'info') {
    echo "=== Python path: {$python} ===\n";
    echo shell_exec("{$python} --version 2>&1");
    echo "\n=== rss_fetcher.py 先頭20行 ===\n";
    echo shell_exec("head -20 {$base}/src/rss_fetcher.py 2>&1");
    echo "\n=== vendor 確認 ===\n";
    echo shell_exec("ls {$base}/vendor/ 2>&1 | head -10");

} elseif ($action === 'extract') {
    // 旧vendorを削除してから展開
    echo "=== 旧vendor削除中 ===\n";
    echo shell_exec("rm -rf {$base}/vendor 2>&1");
    echo "=== vendor.tar.gz を展開中 ===\n";
    echo shell_exec("cd {$base} && tar xzf vendor.tar.gz 2>&1");
    echo "\n=== urllib3バージョン確認 ===\n";
    echo shell_exec("head -5 {$base}/vendor/urllib3/__init__.py 2>&1");
    echo "\n=== 展開内容 ===\n";
    echo shell_exec("ls {$base}/vendor/ 2>&1");
    echo "\n完了！\n";

} elseif ($action === 'test') {
    echo "=== wp_client テスト ===\n";
    echo shell_exec("HOME={$home} {$python} {$base}/src/wp_client.py --test 2>&1");

} elseif ($action === 'rss') {
    echo "=== rss_fetcher dry-run ===\n";
    echo shell_exec("HOME={$home} {$python} {$base}/src/rss_fetcher.py --dry-run 2>&1");

} elseif ($action === 'rss_run') {
    echo "=== rss_fetcher 本番実行 ===\n";
    echo shell_exec("HOME={$home} {$python} {$base}/src/rss_fetcher.py 2>&1");
}

echo "</pre>";
