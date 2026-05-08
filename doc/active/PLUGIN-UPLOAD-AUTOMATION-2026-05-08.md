# PLUGIN-UPLOAD-AUTOMATION-2026-05-08

| field | value |
|---|---|
| ticket_id | PLUGIN-UPLOAD-AUTOMATION-2026-05-08 |
| priority | P2(future 自動化、現運用は user 手動)|
| status | DESIGN_REQUIRED(user 判断) |
| owner | user(方針判断)→ Claude/Codex(実装) |
| lane | FRONTEND / OPS |
| created | 2026-05-08 |
| doc_path | doc/active/PLUGIN-UPLOAD-AUTOMATION-2026-05-08.md |
| origin | 2026-05-08 PM、user「Wordpress の API あるよ」→ WP REST 検証 → 標準 API では custom plugin zip upload 不可と判明 |
| cost | ¥0 |
| regression risk | option による(A: 中、B: 低、C: 0) |

## 1. 問題

Claude が plugin 更新を完結できない。WP plugin v12 → v13(`build/063-v13-wp-admin/yoshilover-063-frontend.zip`)を deploy するため、user が WP admin から zip upload 手作業が必要。

将来的に plugin 更新 cycle が頻発した場合、user 作業負荷増加 + Claude の自動化範囲制約。

## 2. 検証結果(2026-05-08 PM)

### WP REST `/wp/v2/plugins` — custom zip upload 不可

```bash
$ curl -u user:$WP_APP_PASSWORD https://yoshilover.com/wp-json/wp/v2/plugins
[{"plugin":"akismet/akismet","status":"active",...}, ...]  # 22 plugins
```

- ✅ GET: list 動作(yoshilover-063-frontend も list される)
- ✅ DELETE: plugin 削除
- ✅ PUT/PATCH: activate / deactivate
- ❌ **POST custom zip**: WordPress.org slug 限定、ローカル zip は受け付けない

### Yoshilover 既存 admin REST(`/yoshilover-063/v1/admin`)— plugin upload action なし

src/yoshilover-063-frontend.php:4106-4151 で 9 actions 登録:
- get_theme_mods / search_options / set_theme_mod / update_custom_css /
  set_topic_hub_items / set_front_top_topic_hub_widget /
  set_front_top_widget_stack / set_post_meta / get_post_meta /
  clear_cache

→ plugin self-update / upload action は **存在しない**。

### WP admin の `/wp-admin/update.php?action=upload-plugin` — REST 経由不可

- form submission(multipart)
- nonce 必須
- admin **cookie session** 必要(app password は REST 用、この path で使えない)
- → REST API クライアントから直接叩けない

## 3. 可能な path 3 つ

### Option A: yoshilover plugin に self-update endpoint を追加(v14)

新 REST action `upload_self_plugin` を `yoshilover_063_handle_admin_request` に追加:

```python
case 'upload_self_plugin':
    # multipart で zip 受領、検証、wp-content/plugins/ 内に展開、
    # 既存 plugin file を置換、自動 activate
    return yoshilover_063_rest_upload_self_plugin($request);
```

**chicken-and-egg**: v14 を最初 1 回は WP admin 手動 upload 必要。以降の更新(v15, v16, ...)は curl 1 回で完結。

セキュリティ:
- `permission_callback`: `current_user_can('manage_options')` 既存
- + nonce 検証必須(REST 標準で `_wpnonce`)
- + zip 名 strict 検証(yoshilover-063-frontend.zip 限定)
- + zip 内容 signature 検証(SHA256 hash 事前登録 等)
- + activate 失敗時 rollback path

工数: 2-3h(endpoint + zip 検証 + 解凍 + activate + tests)、cost ¥0
risk: 中(任意 plugin 置換可能性、auth 厳格化必要)

### Option B: SFTP / WP-CLI 経由

- yoshilover.com の WP server に SSH / SFTP access が必要
- 現状 Claude / Cloud Run 双方とも creds なし
- user が SFTP creds を Secret Manager に保存 → Cloud Run job 経由で zip 配置 → reload
- 工数: 5-30 分(creds 取扱次第)、cost ¥0(既存 SSH infra 流用)
- risk: 低(SFTP は読み書き、明確な scope)
- 不可触: SSH/SFTP creds の安全保管、user 管轄

### Option C: WP admin から user 手動 upload(現状)

- WP admin → プラグイン → 新規追加 → アップロード → zip 選択 → インストール → 有効化
- 30 秒、user の 1 回作業 / plugin update
- 安全(WP 標準 path)
- 私(Claude)実装範囲外
- 工数: user 30 秒 / update、cost ¥0
- risk: 0

## 4. 比較表

| | A self-update | B SFTP | C user 手動 |
|---|---|---|---|
| 初期作業 | v14 を user 手動 upload 1 回 | SFTP creds 設定 1 回 | (なし、現状)|
| 以後の plugin update | curl 1 回(Claude) | Claude が SFTP 経由 | user 手動 30 秒 |
| security | nonce + role + zip 検証必要 | SFTP creds 漏洩 risk | WP 標準で安全 |
| 工数 | 2-3h | 5-30 分 + creds 設定 | 0 |
| cost | ¥0 | ¥0 | ¥0 |
| user 作業頻度 | 初回のみ | 初回のみ | 毎 update |

## 5. 推奨

**user 判断項目**: plugin update 頻度 / 自動化価値 / security 受容範囲
**Claude 推奨**: Option A(self-update endpoint)

理由:
- 初回 1 回の user 手動 upload で永続的に自動化される
- security は既存 yoshilover admin REST と同等(`manage_options` capability)+ nonce + zip 検証
- SFTP creds 等の外部依存追加なし、WP 内で完結
- WP 標準 path(plugin REST)の足りない部分を yoshilover 専用拡張で補う、合理的

ただし plugin update 頻度が低い(年数回)なら Option C(user 手動)で十分。**頻度次第**。

## 6. 実装すべき場合の scope(Option A 採用時)

- src/yoshilover-063-frontend.php に新 action `upload_self_plugin` 追加
- POST `/yoshilover-063/v1/admin` body:
  - `action=upload_self_plugin`
  - `zip` multipart file
  - `_wpnonce` (REST nonce header)
- 処理:
  1. permission_callback で `manage_options` + nonce 検証
  2. zip ファイル名 / size / mime type 検証(yoshilover-063-frontend.zip 限定、< 5MB 等)
  3. zip 内 entry 検証(yoshilover-063-frontend/yoshilover-063-frontend.php のみ許可)
  4. 旧 plugin file backup → 新 zip 展開 → 既存 file 置換
  5. 失敗時 rollback(backup から復元)
  6. response: { ok: true, version: "0.14.0" }
- tests:
  - permission deny without manage_options
  - nonce missing → 403
  - wrong filename → 400
  - successful upload → file replaced + plugin still active
- ドキュメント: 自動化 curl example を README に

## 7. 参照

- 親:`SIDEBAR-WIDGETS-2026-05-08`(plugin v13 + 今後の v14, v15 deploy)
- 関連:`MANUAL-INTAKE-QUALITY-PARITY-2026-05-08`(plugin 経由の改善 cycle)
- 既存 admin REST: src/yoshilover-063-frontend.php:4106-4151
- 既存 build script: scripts/build_063_wp_admin_bundle.py
- 既存 build artifact: build/063-vXX-wp-admin/yoshilover-063-frontend.zip
