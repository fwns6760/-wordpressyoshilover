# yoshilover CSS / plugin rollback 手順

## CSS rollback (SWELL 追加 CSS を前 commit に戻す)

### 手順

1. git で戻したい commit を特定
   ```
   cd /home/fwns6/code/wordpressyoshilover
   git log --oneline src/custom.css | head -20
   ```
2. 戻したい commit の custom.css を取得
   ```
   git show <commit>:src/custom.css > /tmp/rollback_custom.css
   ```
3. REST PUT で live 反映
   ```bash
   python3 << 'PY'
   import json, base64, urllib.request
   env={}
   for l in open('.env'):
       l=l.strip()
       if not l or l.startswith('#') or '=' not in l: continue
       k,v=l.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
   auth = base64.b64encode(f"{env['WP_USER']}:{env['WP_APP_PASSWORD']}".encode()).decode()
   hdr = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}
   css = open('/tmp/rollback_custom.css').read()
   r = urllib.request.urlopen(urllib.request.Request(
       env['WP_URL']+'/wp-json/yoshilover/v1/custom-css',
       data=json.dumps({'css':css}).encode(),
       headers=hdr, method='PUT'
   ), timeout=30)
   print(r.status, r.read())
   PY
   ```
4. 確認: `curl` で inline `<style>` を再取得、差分なし確認

## Plugin (yoshilover-063-frontend) rollback

plugin 側のコード変更は REST で上書きできないので、**前 version の zip を再 upload**する。

### 手順

1. 前の plugin version の zip を git log から特定
   ```
   git log --oneline --all -- build/063-*-wp-admin/yoshilover-063-frontend.zip
   ```
2. 該当 commit の zip を取り出す
   ```
   git show <commit>:build/063-v7-wp-admin/yoshilover-063-frontend.zip > /tmp/rollback.zip
   ```
3. WP admin で上書き install + 有効化

## Plugin (yoshilover-css-push) rollback

css-push を壊すと Claude Code の自動 deploy ができなくなるため注意。

### 手順

1. 該当 commit の src を取り出す
   ```
   git show <commit>:src/plugin-css-push/yoshilover-css-push.php > /tmp/rollback-csspush.php
   ```
2. zip 化
   ```
   python3 -c "import zipfile; z=zipfile.ZipFile('/tmp/csspush_rollback.zip','w'); z.write('/tmp/rollback-csspush.php', arcname='yoshilover-css-push/yoshilover-css-push.php'); z.close()"
   ```
3. WP admin で上書き install + 有効化

## Option reset (yoshilover_063_* の値を戻す)

```bash
# 個別 option reset (例: x-follow-cta 無効化)
python3 << 'PY'
import json, base64, urllib.request
env={}
for l in open('.env'):
    l=l.strip()
    if not l or l.startswith('#') or '=' not in l: continue
    k,v=l.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
auth = base64.b64encode(f"{env['WP_USER']}:{env['WP_APP_PASSWORD']}".encode()).decode()
hdr = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}
payload = json.dumps({'value': {'enabled': False}}).encode()
r = urllib.request.urlopen(urllib.request.Request(
    env['WP_URL']+'/wp-json/yoshilover/v1/option/yoshilover_063_x_follow_cta',
    data=payload, headers=hdr, method='PUT'
), timeout=15)
print(r.status, r.read())
PY
```

whitelist (css-push v0.2.0):
- `yoshilover_063_x_follow_cta`
- `yoshilover_063_tag_nav_hot`
- `yoshilover_063_topic_hub`
- `yoshilover_063_sidebar_popular`
- `yoshilover_063_breaking_strip`
- `yoshilover_063_meta_line` (v0.9.0〜)

## 緊急 emergency: CSS 全クリア

live の custom_css を空にする:

```
curl -X PUT -u user:APP_PW -H 'Content-Type: application/json' \
  -d '{"css": ""}' \
  https://yoshilover.com/wp-json/yoshilover/v1/custom-css
```

## 緊急 emergency: plugin 全停止

WP admin → プラグイン一覧 → yoshilover-063-frontend / yoshilover-css-push を「停止」

## 回帰防止チェックリスト(大きな変更後)

- `curl https://yoshilover.com/` でトップ取得、inline `<style>` サイズが想定範囲か
- `curl https://yoshilover.com/{post_id}` で記事取得、主要 DOM 存在確認
  - `yoshi-topic-hub` / `yoshi-breaking-strip` / `yoshi-article-bundles` / `yoshi-sns-reactions` / `yoshilover-related-posts`
- モバイル UA で取得、header min-height が 48px 以下になってるか
- AdSense 広告が想定通り (non-public = 全殺し / public = 表示)
