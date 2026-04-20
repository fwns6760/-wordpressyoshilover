# game_id schema

## Scope
- This note defines the read-time schema and derivation rule for `game_id` and `source_id`.
- A1 is dry-run only. No WordPress meta field is created or written in this step.

## Canonical form
- `game_id`: `YYYYMMDD-<home_team_code>-<away_team_code>`
- Doubleheader only: append `-1` or `-2`
- Date is the scheduled game date in JST, not publish time and not `modified_gmt` as-is
- Example: `20260421-giants-tigers`, `20260423-giants-marines-2`

## Team code enum
- Use full English slugs, not 2-char abbreviations. Reason: readable in logs and unambiguous across NPB.

| team_code | Main aliases accepted at derivation time |
| --- | --- |
| `giants` | 巨人, ジャイアンツ, 読売, yomiuri |
| `tigers` | 阪神, タイガース, hanshin |
| `dragons` | 中日, ドラゴンズ, chunichi |
| `swallows` | ヤクルト, スワローズ, tokyo yakult |
| `baystars` | deNA, dena, ベイスターズ, 横浜 |
| `carp` | 広島, カープ, hiroshima |
| `buffaloes` | オリックス, バファローズ, orix |
| `marines` | ロッテ, マリーンズ, chiba lotte |
| `hawks` | ソフトバンク, ホークス, fukuoka softbank |
| `eagles` | 楽天, イーグルス, tohoku rakuten |
| `fighters` | 日本ハム, 日ハム, ファイターズ, hokkaido nippon-ham |
| `lions` | 西武, ライオンズ, saitama seibu |

## source_id canonical form
- `rss:<normalized_url>`
  - For RSS/news article URLs. Normalize by lowercasing scheme/host, removing fragment, trimming trailing slash, preserving the remaining query string only if present.
  - Example: `rss:https://hochi.news/articles/20260421-oht1t51123.html`
- `x:<status_id>`
  - For `x.com`, `twitter.com`, `i/web/status/...`. Ignore handle changes and host differences.
  - Example: `x:1912345678901234567`
- `npb:<provider_game_id>:<page>`
  - For Yahoo/NPB game URLs like `/npb/game/<id>/top`, `/score`, `/index`.
  - Example: `npb:2026042101:top`
- `official:<team_code>:<yyyymmdd>:<section>`
  - For official team pages like `https://www.giants.jp/game/20260421/preview/`.
  - Example: `official:giants:20260421:preview`
- Fallback only when family parsing fails: keep the family prefix and the normalized URL payload.

## Draft -> game_id mapping rule
1. Determine subtype.
   - Prefer `meta.article_subtype`.
   - If absent, infer from title + body:
     - `postgame`: result/score/final markers
     - `live_update` or `live_anchor`: inning-progress markers
     - `lineup`: lineup markers
     - `farm`: farm/2軍 markers
     - else `pregame` if the text still describes a match preview
2. Reject subtypes that are not match-bound. Return `null`.
3. Collect source URLs from:
   - `meta.source_urls[]`
   - source URL meta aliases already used by the repo
   - links embedded in the body HTML
4. Canonicalize each source URL into `source_id`.
5. Resolve scheduled date in this priority order:
   - `npb:<provider_game_id>:...` -> first 8 digits of the provider id
   - `official:<team_code>:<yyyymmdd>:...`
   - explicit `YYYY年M月D日` or `M月D日` in title/body
   - last resort: `modified_gmt` converted to JST date
6. Resolve participating teams.
   - Parse team aliases from title/body/source URLs.
   - If exactly one non-`giants` team is found in a Giants match subtype, inject `giants` as the second team.
   - If the opponent is still unknown, return `null`.
7. Resolve home/away.
   - First priority: venue aliases in title/body. Home team is the team whose home stadium appears.
   - Second priority: explicit home/visitor markers if present.
   - If order is still ambiguous, return `null`. This schema intentionally prefers `null` over a guessed home/away.
8. Resolve doubleheader suffix.
   - `第1試合`, `第一試合`, `game 1`, `dh1` -> `-1`
   - `第2試合`, `第二試合`, `game 2`, `dh2` -> `-2`
   - If no marker exists, do not append a suffix.
9. Compose `YYYYMMDD-home-away[-suffix]`.

## Subtype policy
- MUST carry `game_id`
  - `pregame`
  - `lineup`
  - `live_update`
  - `live_anchor`
  - `postgame`
  - `farm`
  - `farm_lineup`
- MUST NOT carry `game_id`
  - public notices unrelated to a match
  - `notice` / `player_notice`
  - `general` / `game_note`
  - `manager`
  - `player` / `player_recovery`
  - `roster`
  - `social` / `social_news`

## Null-return contract
- `subtype_not_match_bound`
- `date_not_found`
- `opponent_not_found`
- `home_away_ambiguous`

## Notes for later write便
- A later migration can write `game_id` into WP meta only after the null-rate and ambiguity cases are reviewed.
- `source_id` should be written alongside `game_id`; it remains one-per-source while `game_id` is one-per-scheduled-match.

## 管理人判断 (2026-04-21)
1. `farm` と `farm_lineup` は同じ二軍試合を指すため、両方とも `game_id` を付与する。
2. `live_anchor` は E3/E4 で新設予定の subtype として schema に保留記載する。当面 `game_id` を付与するのは `live_update` のみとし、`live_anchor` への書き込みは新設便で行う。
3. 日付と対戦相手だけが判明し venue / home-visitor marker が欠ける場合、`game_id` は null を維持する。trusted source で確定した時点で後便が upsert する(narrowing fallback は導入しない)。
