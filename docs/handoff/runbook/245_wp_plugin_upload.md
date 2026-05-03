# 245 WP plugin upload runbook

## Scope

- This document is for **manual WordPress admin upload preparation only**.
- No source edit, deploy, env change, scheduler change, or live upload is performed in this ticket.
- `USER_DECISION_REQUIRED`: the actual upload is a user-side manual step.
- Target package: `build/063-v9-wp-admin/yoshilover-063-frontend.zip`
- Paired manifest: `build/063-v9-wp-admin/manifest.json`
- Expected source commit: `46241ce`
- Expected plugin version: `0.9.0`

## Existing artifact verification summary

### v9 package observed in this workspace (2026-05-03 JST)

| item | observed value |
|---|---|
| zip path | `build/063-v9-wp-admin/yoshilover-063-frontend.zip` |
| zip size | `31,611 bytes` |
| zip mtime | `2026-05-02 22:33:53 JST` |
| manifest path | `build/063-v9-wp-admin/manifest.json` |
| manifest size | `353 bytes` |
| manifest `generated_at` | `2026-05-02T13:33:53.308292+00:00` |
| manifest `git_head` | `46241ce` |
| manifest `plugin_version` | `0.9.0` |
| manifest `plugin_source` | `src/yoshilover-063-frontend.php` |
| manifest `css_source` | `src/custom.css` |

### Important note about source commit vs local artifact

- `git show --stat 46241ce` reports **one modified file only**: `src/yoshilover-063-frontend.php`
- Diff size for `46241ce`: `33 insertions`, `8 deletions`
- The current workspace also contains **uncommitted** changes under `build/063-v9-wp-admin/`
- Treat `46241ce` as the source-of-truth for the PHP change, and treat the local v9 zip + manifest pair as the upload candidate that must be re-verified immediately before upload
- Do not assume an old remembered size is still correct; use the current file on disk and confirm it matches the manifest you are uploading

### 46241ce modified file list

| commit | files changed | scope |
|---|---|---|
| `46241ce` | `src/yoshilover-063-frontend.php` | hide internal auto-post category from sidebar / term names / front density |

## Previous artifact / rollback candidate summary

| package | plugin_version | manifest git_head | zip size on disk | notes |
|---|---|---|---|---|
| `build/063-v6-wp-admin/yoshilover-063-frontend.zip` | `0.6.0` | `7778334` | `15,946 bytes` | oldest packaged rollback candidate in repo |
| `build/063-v7-wp-admin/yoshilover-063-frontend.zip` | `0.7.0` | `7778334` | `16,710 bytes` | similar code generation line as v6 |
| `build/063-v8-wp-admin/yoshilover-063-frontend.zip` | `0.8.0` | `0deb077` | `19,542 bytes` | latest clearly versioned packaged baseline before v9 |
| `build/063-v9-wp-admin/yoshilover-063-frontend.zip` | `0.9.0` | `46241ce` | `31,611 bytes` | upload candidate for this runbook |

### Read-only diff overview across packaged versions

- `v6 -> v7`: same manifest head `7778334`, small package increment
- `v7 -> v8`: new manifest head `0deb077`, package grows, manifest explicitly mentions shortcode additions and version bump to `0.8.0`
- `v8 -> v9`: package is intended for the frontend-only internal-category hide change, with manifest now pointing to `46241ce`
- Preferred rollback target order:
  1. the live plugin backup captured immediately before overwrite
  2. `build/063-v8-wp-admin/yoshilover-063-frontend.zip`
  3. `build/063-v7-wp-admin/yoshilover-063-frontend.zip`
  4. `build/063-v6-wp-admin/yoshilover-063-frontend.zip`

## WP admin upload runbook

### 1. Local pre-check before opening WordPress

- Confirm both files exist:
  - `build/063-v9-wp-admin/yoshilover-063-frontend.zip`
  - `build/063-v9-wp-admin/manifest.json`
- Open `manifest.json` and confirm:
  - `git_head` is `46241ce`
  - `plugin_version` is `0.9.0`
  - `plugin_zip` points to `build/063-v9-wp-admin/yoshilover-063-frontend.zip`
- Confirm the zip you intend to upload is the same file you just verified
- If more repo work will continue before the upload session, first copy the intended zip to a dated temporary location so it cannot drift before manual upload

### 2. Baseline capture in WP admin

- Open the WP admin login URL and sign in
- Go to `プラグイン` and find the currently live `yoshilover-063-frontend` plugin row
- Record the currently displayed live version before overwrite
- Confirm the plugin is active before the change
- Check whether WP admin is already showing any plugin warning / fatal / maintenance banner before upload

### 3. Backup the currently live plugin before overwrite

- Preferred backup: download or copy the exact currently live plugin files before replacing them
- Acceptable backup methods:
  - WP admin plugin backup/export flow if available
  - hosting file manager / FTP / SSH copy of the live plugin directory
  - a previously verified rollback zip, if the exact live plugin cannot be exported quickly
- Save the backup with a timestamped name so you can identify it in under 30 seconds during rollback
- Do not skip this step

### 4. Upload the v9 package

- In WP admin, go to `プラグイン -> 新規追加 -> プラグインのアップロード`
- Select `build/063-v9-wp-admin/yoshilover-063-frontend.zip`
- Click `今すぐインストール`
- If WordPress asks whether to replace the existing plugin, choose the overwrite / replace option
- Wait for the install result page and confirm the upload completed without a PHP fatal or filesystem error

### 5. Activation confirmation

- If WordPress deactivated the plugin during replacement, click `有効化`
- Return to the plugin list and confirm `yoshilover-063-frontend` is active
- If the plugin screen shows a version number, confirm it is now `0.9.0`
- If version display is ambiguous, continue with the functional verify checklist below rather than guessing

### 6. Immediate functional verification

- Run the checklist in the next section before leaving WP admin
- If every required check passes, keep v9 live
- If any fatal, obvious category regression, or broad layout break appears, rollback immediately

### 7. Rollback if the verify checklist fails

- Reopen `プラグイン -> 新規追加 -> プラグインのアップロード`
- Upload the backup zip captured in step 3
- If no fresh backup is available, upload the preferred repo rollback candidate in this order: `v8`, then `v7`, then `v6`
- Overwrite the live plugin again and reactivate if needed
- Re-run the short verification subset:
  - top page
  - one category archive
  - one single post
  - WP error log / admin fatal banner

## Rollback targets

### No-env / no-image confirmation

- env rollback target: none
- Cloud Run image rollback target: none
- Scheduler rollback target: none
- This change is isolated to the WordPress plugin file layer

### Immediate live rollback target

- Primary target: the exact live plugin backup taken right before overwrite
- Secondary target: `build/063-v8-wp-admin/yoshilover-063-frontend.zip`
- Tertiary targets: `build/063-v7-wp-admin/yoshilover-063-frontend.zip`, then `build/063-v6-wp-admin/yoshilover-063-frontend.zip`
- Rollback action: re-upload the chosen zip from WP admin and overwrite the plugin again
- Expected manual rollback time: about `3 minutes`

### Repo-level rollback target

If v9 is rejected at the code level later, the repo rollback command is:

```bash
git revert 46241ce
```

- That repo revert is **not** required for the immediate live rollback
- The immediate live rollback is the faster path when the site behavior is wrong after upload

## Post-upload verify checklist

### Frontend pages to check

- [ ] Top page desktop: no visible `自動投稿` / `auto-post` category label or chip
- [ ] Top page mobile: layout is intact and no internal category chip appears
- [ ] Category archive page such as `試合速報` or `コラム`: sidebar does not expose `自動投稿`
- [ ] Single post page that still has the internal category assigned in WP admin: public category label does not show `自動投稿`
- [ ] Search results page: no `自動投稿` tag / chip / category text leaks into the result UI
- [ ] One more non-auto-post category archive or article card rail: ordinary categories still render normally

### Acceptance checks

- [ ] WP category assignment itself is unchanged in the admin data layer
- [ ] The change is frontend display-layer only; no category deletion or reassignment happened
- [ ] Non-internal categories such as `試合速報`, `コラム`, `選手情報` still display normally
- [ ] `yoshilover-exclude-cat` or other category-related plugins show no visible conflict
- [ ] No new PHP fatal / warning spike appears in WP admin, hosting PHP error log, or Site Health
- [ ] Sidebar, article meta, related/front-density surfaces all hide the internal category consistently
- [ ] Page load feels normal; if you have a baseline, confirm no obvious Lighthouse or page-load regression

### Fast rollback triggers

- Roll back immediately if any of these occur:
  - plugin activation fails
  - WP admin shows a fatal error banner
  - ordinary public categories disappear together with `自動投稿`
  - top page or single page layout breaks in a visible way
  - the internal category is still displayed after a hard refresh and cache clear

## USER_DECISION_REQUIRED decision batch

`OK: 上記 runbook 手順で v9 zip を WP admin 上書き upload し、post-upload verify を実施する | HOLD: 後日まで待機し、現在 live の WP plugin を維持する | REJECT: v9 は採用せず、必要なら repo で git revert 46241ce を検討し、v9 zip は live 適用しない`
