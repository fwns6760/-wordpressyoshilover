# 176 deploy deployment notes

## meta

- ticket: 176-deploy
- date: 2026-04-26 JST
- operator: Codex
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head_at_note_update: `1eda8dd`
- target_css: `src/custom.css`
- target_article: `https://yoshilover.com/?p=63663`
- target_endpoint: `https://yoshilover.com/wp-json/yoshilover-063/v1/admin`

## status

Stopped before live deploy completed.

- blocker: sandbox DNS resolution failure for `yoshilover.com`
- remote WP state changed: no
- WP option / setting write reached host: no

## added script

- `bin/push_custom_css.sh`
  - reads `src/custom.css`
  - derives the merge marker from the existing header comment
  - POSTs `action=update_custom_css`, `marker`, and `css` to the 063 admin REST endpoint
  - requires `WP_URL`, `WP_USER`, and `WP_APP_PASSWORD` in the environment
  - validates `HTTP 200`, `css_post_id`, and `contains_marker=true`

Static verification:

```bash
bash -n bin/push_custom_css.sh
ls -la bin/push_custom_css.sh
```

## attempted deploy command

Because `.env` contains a WordPress app password format that is not shell-safe to `source` directly, the live attempt loaded only the required `WP_*` values via Python without printing them:

```bash
python3 - <<'PY'
import os
import subprocess
from pathlib import Path

env_path = Path('.env')
needed = {'WP_URL', 'WP_USER', 'WP_APP_PASSWORD'}
for raw_line in env_path.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    key = key.strip()
    if key not in needed:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    os.environ[key] = value

subprocess.run(['bin/push_custom_css.sh'], check=True)
PY
```

Observed result at `2026-04-26T19:13:32+09:00`:

```text
curl: (6) Could not resolve host: yoshilover.com
```

Interpretation:

- the request did not reach WordPress
- auth was not exercised against the remote host
- the 063 endpoint was not able to return an HTTP status code
- `wp_get_custom_css()` / `wp_update_custom_css_post()` were not invoked remotely from this sandbox

## smoke command

Attempted smoke command:

```bash
curl -sS "https://yoshilover.com/?p=63663" | grep -A2 "c-shareBtns__item" | head -20
```

Observed result:

```text
curl: (6) Could not resolve host: yoshilover.com
```

Verification status:

- share row HTML fetched: no
- `-twitter-x` class verified on live article: no
- `-facebook` class verified on live article: no

## scope / safety verification

- touched files for this ticket:
  - `bin/push_custom_css.sh`
  - `doc/active/176-deploy-deployment-notes.md`
- existing `src/custom.css` content was not edited in this ticket
- no tests, requirements, cron, env files, or parallel-task files were modified
- secrets printed to chat/log/doc: none
- live deploy count: `0` successful, `1` attempted pre-connect failure
- WP write scope intended by script: `custom.css` only via `action=update_custom_css`

## next operator step

Run the prepared script from an environment with outbound DNS/network access to `yoshilover.com`, then rerun the article smoke command to confirm `c-shareBtns__item.-twitter-x` and `c-shareBtns__item.-facebook` render on the live page.
