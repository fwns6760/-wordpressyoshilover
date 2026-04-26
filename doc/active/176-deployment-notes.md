# 176 deployment notes

## meta

- ticket: `176`
- date: `2026-04-26 JST`
- operator: `Codex`
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head_at_start: `cd550f6`
- scope: `share buttons Twitter / Facebook 空白 fix`

## phase 1 findings

- local repo custom CSS was styling X with `.c-shareBtns__item.-twitter` and `.c-shareBtns__item.-x` only.
- current public SWELL markup examples show:
  - Facebook item class: `.c-shareBtns__item.-facebook`
  - X item class: `.c-shareBtns__item.-twitter-x`
  - icon classes: `.icon-facebook`, `.icon-twitter-x`
  - button base style uses `background-color: currentcolor`.
- shell-side `curl https://yoshilover.com/?p=63663` / `?p=63668` could not be executed in this sandbox (`curl` exit `6`), so live HTML grep from this environment was not possible.
- publish links confirmed from local operational logs:
  - `https://yoshilover.com/?p=63663`
  - `https://yoshilover.com/?p=63668`

## case judgment

- case: `A`
- reason:
  - repo selector was pinned to older X class names and did not include `-twitter-x`.
  - current SWELL share buttons rely on item `color` + button `currentColor`, so a narrow selector update is the lowest-risk fix.
  - no evidence was found that WP admin share toggles were disabled, so case `C` was not selected.

## applied repo change

- file: `src/custom.css`
- change:
  - added `.c-shareBtns__item.-twitter-x`
  - set item `color` for X and Facebook so current SWELL `currentColor` styling still resolves correctly
  - set button `background-color` and `border-color` for X and Facebook as an explicit fallback
- untouched:
  - `src/yoshilover-063-frontend.php`
  - WP admin
  - live deploy

## pre-deploy verify evidence

- external SWELL reference used for current class confirmation:
  - `https://affilabo.com/wordpress/88158/`
  - search snippet showing live SWELL share row markup:
    - `<li class="c-shareBtns__item -facebook">`
    - `<li class="c-shareBtns__item -twitter-x">`
    - `<i class="snsicon c-shareBtns__icon icon-facebook">`
    - `<i class="snsicon c-shareBtns__icon icon-twitter-x">`
- local grep confirmed repo had no `-twitter-x` selector before this patch.

## not executed here

- live deploy: `NO`
- live browser smoke after deploy: `NO`
- WP admin setting change: `NO`

## suggested post-deploy smoke

```bash
curl -s "https://yoshilover.com/?p=63663" | grep -A3 "c-shareBtns__item" | head -40
curl -s "https://yoshilover.com/?p=63668" | grep -A3 "c-shareBtns__item" | head -40
```

Expected focus:

- X item class includes `-twitter-x` or other `twitter`-prefixed class
- Facebook item class remains `-facebook`
- Pocket / LINE / Copy markup remains unchanged
