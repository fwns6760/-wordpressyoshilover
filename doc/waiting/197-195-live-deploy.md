# 197 / 195 article footer X share corner live deploy(canary disabled start)

- priority: P0.5
- status: READY_FOR_AUTH_EXECUTOR
- owner: Codex / Claude follow-up
- lane: Front-Claude
- parent: 195 / 176

## Background

- `26fc0ca` で `src/yoshilover-063-frontend.php` に article footer の manual X share corner 実装は着地済み
- current repo `HEAD` は `c4fc838`
- 195 の toggle contract:
  - WP option `yoshilover_063_manual_x_share_corner`
  - env override `YOSHILOVER_063_MANUAL_X_SHARE_CORNER`
  - precedence は `env override > WP option > default(true)`
- goal は live frontend へ安全に反映し、初期は disabled のまま deploy、確認後に enable すること
- 202 policy により、この ticket は `BLOCKED_USER` ではなく `READY_FOR_AUTH_EXECUTOR` として扱う

## Scope

- `doc/waiting/197-195-live-deploy.md`
- `doc/README.md`
- `doc/active/assignments.md`

## Deploy Route Findings

### 1. 既存の確定済み経路

- repo 内の strongest documented route は **WP admin からの plugin ZIP 上書き** か **Xserver 上の plugin file 直接置換**
- 根拠:
  - `docs/handoff/codex_requests/2026-04-24_063-V1-deploy-prep.md`
  - `docs/handoff/codex_requests/2026-04-24_063-V2-wp-admin-deploy.md`
  - `doc/done/2026-04/063-comment-first-topic-hub-impl.md`
- 配置先 contract は `wp-content/plugins/yoshilover-063-frontend/yoshilover-063-frontend.php`

### 2. repo から直接 live へ上げる自動経路

- **見つからず**
- `bin/push_custom_css.sh` は 063 admin REST endpoint 経由で custom CSS を更新する helper だが、plugin file upload は扱わない
- `src/yoshilover-063-frontend.php` の admin REST route には以下はある:
  - `search_options`
  - `set_theme_mod`
  - `update_custom_css`
  - `set_topic_hub_items`
  - `set_post_meta`
- **generic `set_option` / plugin upload route は無い**

### 3. canary disabled start に必要な前提

- 195 の default は `enabled=true`
- したがって **deploy 前に** `yoshilover_063_manual_x_share_corner.enabled=false` を WP 側へ書ける手段が必要
- current repo だけではこの option を remote write する安全な既存 route が無い
- disabled start を守るなら、**remote shell + WP-CLI** か、user 側の WP admin / option editor / phpMyAdmin 操作が必要

### 4. build artifact 状態

- tracked artifact `build/063-v9-wp-admin/yoshilover-063-frontend.zip` は **現 `HEAD` と不一致**
- local verify:
  - `src_sha256`: `17e079b29506b842330c4ce346b6a1c46d358b8585b87175cb38beaf59863d06`
  - `zip_sha256`: `85b25f74c12ed0e9addef3a490754764b0cd72269c5f2ac613907cede641eeba`
  - zip 内に `yoshilover_063_manual_x_share_corner` / `yoshi-x-share-corner` は **未収録**
- つまり WP admin upload route を使う場合も、**先に最新 zip を再生成**しないと 195 は反映されない

## Adopted Strategy

- **Option A** を採用
- 理由:
  - default enabled のまま upload すると即 visible になり、mobile/layout smoke 前に live へ出る
  - 195 の canary toggle は「初期 false を先に書ける」場合にだけ安全に使える
- ただし、この sandbox からは remote shell / WP admin upload / option write を完結できないため、**runbook 出力で停止**
- この停止理由は policy 上の `READY_FOR_AUTH_EXECUTOR` であり、repo 実装 failure ではない

## Why Deploy Stopped

- Xserver の real SSH host / user / WP root path が repo に無い
- `~/.ssh/config` には `github-yoshilover` のみで、Xserver alias は未登録
- network は不安定:
  - `curl -I https://yoshilover.com` は `2026-04-27 10:06:24 JST` 時点で `HTTP/2 200`
  - 直後の `curl https://yoshilover.com/?p=63663` と authenticated REST POST は `Could not resolve host` / `NameResolutionError`
- よって live verify も remote write も、この sandbox では安定実行不能

## Runbook

### Preferred path: remote shell + WP-CLI available

1. 最新 bundle をローカル生成

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 scripts/build_063_wp_admin_bundle.py
php -l src/yoshilover-063-frontend.php
```

2. canary option を false で先置き

```bash
ssh -p 10022 <xserver-user>@<xserver-host> \
  "cd <wp-root> && wp option update yoshilover_063_manual_x_share_corner --format=json '{\"enabled\":false,\"heading\":\"この記事を X でシェア\"}'"
```

3. plugin file を置換

```bash
scp -P 10022 \
  /home/fwns6/code/wordpressyoshilover/src/yoshilover-063-frontend.php \
  <xserver-user>@<xserver-host>:<wp-root>/wp-content/plugins/yoshilover-063-frontend/yoshilover-063-frontend.php
```

4. disabled mode verify

```bash
curl -sS "https://yoshilover.com/?p=<published_post_id>" | grep -c 'yoshi-x-share-corner'
```

- expected: `0`

5. browser smoke

- desktop 1 記事
- mobile 1 記事
- fatal / layout 崩れ / comment/share 既存要素の欠落が無いこと

6. enable

```bash
ssh -p 10022 <xserver-user>@<xserver-host> \
  "cd <wp-root> && wp option update yoshilover_063_manual_x_share_corner --format=json '{\"enabled\":true,\"heading\":\"この記事を X でシェア\"}'"
```

7. enabled verify

```bash
curl -sS "https://yoshilover.com/?p=<published_post_id>" | grep -c 'yoshi-x-share-corner'
```

- expected: `1+`

### Fallback path: WP admin upload only

- current repo には **option false を先に入れる route が無い**
- したがって WP admin upload だけで進めると **Option B(default enabled)** になる
- 本 ticket の safety contract は Option A なので、**WP-CLI / option editor / phpMyAdmin などで false を先置きできないなら deploy しない**

## Verify Snapshot

- `php -l src/yoshilover-063-frontend.php` => pass
- live HTML verify => **not stable from sandbox**
- authenticated admin REST verify => **not stable from sandbox**
- plugin live write => **not executed**
- WP option write => **not executed**

## Rollback

### if disabled-mode deploy 済みで不具合

```bash
ssh -p 10022 <xserver-user>@<xserver-host> \
  "cd <wp-root> && wp option update yoshilover_063_manual_x_share_corner --format=json '{\"enabled\":false,\"heading\":\"この記事を X でシェア\"}'"
```

### if file rollback も必要

- `src/yoshilover-063-frontend.php` を 195 前の live 版に戻す
- ただし repo 側に「現在 live の exact plugin binary」は残っていない可能性があるため、remote backup を先に取る

```bash
ssh -p 10022 <xserver-user>@<xserver-host> \
  "cp <wp-root>/wp-content/plugins/yoshilover-063-frontend/yoshilover-063-frontend.php <wp-root>/wp-content/plugins/yoshilover-063-frontend/yoshilover-063-frontend.php.bak.$(date +%Y%m%d%H%M%S)"
```

## Guardrails Held

- `src/yoshilover-063-frontend.php` edit: NO
- Python / tests / requirements edit: NO
- WP REST article POST/PUT: NO
- git push: NO
- live plugin deploy: NO
