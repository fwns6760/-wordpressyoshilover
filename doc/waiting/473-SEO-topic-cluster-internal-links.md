# 473-SEO トピッククラスター内部リンク（編成クラスタ）

- status: READY_FOR_AUTH_EXECUTOR / owner: Codex B / 2026-07-31 / user「全部GO」
- 目的: SEO強化。data表の選手名→選手ページ内部リンク + 編成クラスタ(draft/fa/trade)横リンク + 構造化データ
- 実装:
  - src/data_site_internal_link.py: linkify(名前→/data/<slug>/、ページ有る人だけ) / roster_moves_nav(クラスタ横リンク) / breadcrumb_jsonld
  - src/tools/build_player_slug_map.py → config/data_site_player_slugs.json(977キー、WP全選手ページ name→slug)
  - draft/fa/trade テンプレに linkify 適用 + 横リンクバー + JSON-LD
- 効果(render実測): 内部リンク draft400 / fa35 / trade743 ≈1,178本新規。legendsは既に名前リンク済。
- クラスタ地図: ピラー=/data/、編成クラスタ=draft↔fa↔trade 相互リンク、各表名→選手ページ(縦リンク)
- 運用: 選手ページ増時は build_player_slug_map 再実行→config更新→再ビルド

## 2026-07-31 全内部リンク監査・恒久修正

### live read-only baseline

- sitemap: 1,135 URL、sitemap外の内部リンク先: 267 URL
- sitemap掲載ページの 4xx/5xx: **0**
- 内部リンク先の 404: **27**
  - 全ページ共通の旧運営者URL `/?page_id=1980`: 1 target / 1,132 page
  - 選手名・旧slugから生成された存在しない `/data/...`: 20 targets
  - 存在しない人物tag archive: 6 targets
- indexable orphan: 4 (`about-yoshilover` / `data/opening-pitchers` /
  `giants-sns-realtime-1gun` / `home-dashboard`)
- 直近記事5本で、無関係なロシア語bbPress topicが記事ごと2リンク表示されることを確認。

### repo implementation

- `build_player_slug_map.py`: `2026年成績・打率/防御率` をtitleから除去し、現行canonical slugを優先。
- `data_site_player_slugs.json`: current player名で再生成（坂本勇人、竹丸和幸、浦田俊輔等を正しくlink化）。
- `data_site_template_team.py` / `data_site_template_farm.py` /
  `data_site_template_cluster.py`: `player_slug()` の未知名fallbackを廃止し、
  WP実在page mapを使う `linkify()` に統一。
- `data_site_template_salary_value.py`: duplicate旧slug (`whitley-26`) よりcurrent slug (`whitley`) を優先。
- `sns_realtime_topic.py` / template: data child pagesを100件で打ち切らず全page取得。
  実在pageがない人物は未検証tag URLへfallbackせずplain text表示。
- `yoshilover-063-frontend.php`:
  - bbPress topicは日本語かつ巨人/野球文脈のみ、URL/spam語を除外。
  - topic linkは記事下1回だけ、`rel="ugc nofollow"`。
  - `/?page_id=1980` を `/about-yoshilover` へ補正。
  - `opening-pitchers` / 一軍SNS速報をhome data hubへ追加。
  - 重複旧トップ `home-dashboard` は `noindex,follow`。
- `data_site_backlink_injector.py`: page 1（新着）に加え、page 2〜180を日付rotationで遡及。
- `src/tools/internal_link_audit.py`: sitemap再帰crawl + sitemap外target確認、
  orphan / near-orphan / click depth / broken / redirect / canonical / query URLをJSON化。

### validation

- targeted regression: **120 passed**
- `compileall`: PASS
- AST parse: 9 files PASS
- `php -l src/yoshilover-063-frontend.php`: PASS
- `git diff --check` (対象tracked files): PASS
- live書込 / GCP mutation / env / Secret / Scheduler / X: **0**

## authenticated executor runbook

作業treeは他laneの大量dirty差分を含むため、**repo rootの一括build禁止**。
認証実行者はclean temp treeまたは現行production imageへの限定overlayで、次の順に反映する。

1. frontend plugin
   - 対象: `src/yoshilover-063-frontend.php`
   - `wp-frontend-deploy` の現行imageをrollback値として記録してから限定build / Job update / execute。
   - WP cache purge後、最新記事でロシア語topic 0、topic link最大1、`ugc nofollow`、
     header menuが `/about-yoshilover` を向くことを確認。
2. data-site publisher
   - 対象: `config/data_site_player_slugs.json`,
     `src/data_site_template_{cluster,farm,team,salary_value}.py`
   - 現行 `data-site-publisher` imageへ限定overlayし、Job update後に1回execute。
   - `/data/draft` の坂本勇人等がcurrent slugへlinkされ、
     `/data/{日本語名}` と `/data/salary/whitley-26` が消えることを確認。
3. SNS realtime
   - 対象: `src/sns_realtime_topic.py`, `src/sns_realtime_topic_template.py`
   - 現行 `yoshilover-fetcher` imageへ2 fileだけ限定overlay。
   - service update後の自然更新または既存safe pathでpage再生成し、存在しない `/tag/...` 6件が消えることを確認。
4. 過去記事backlink
   - 対象: `src/data_site_backlink_injector.py`
   - `DATA_SITE_BACKLINK_DRY_RUN=1` でsample確認後のみwrite実行。
   - `DATA_SITE_BACKLINK_MAX_PER_PLAYER=20` と日次backfill rotationは維持。
5. 最終監査
   - `python3 -m src.tools.internal_link_audit --workers 4 --timeout 20 --output <report>`
   - acceptance: sitemap broken=0、broken internal target=0、indexable orphan=0、
     spam topic link=0、canonical mismatchの新規増加=0。

rollbackは各laneで記録した直前imageへ戻す。env / Secret / Scheduler / IAM / Xは変更しない。
