# 444 data-site Phase 1.0 (MVP-mini) 実装計画

## 1. ticket header

- **ticket id**: 444
- **status**: READY (user GO 済 2026-05-28 PM、 Claude 自律実装)
- **owner**: Claude Code
- **lane**: data-site / per-player publisher
- **created**: 2026-05-28
- **priority**: P1
- **github_issue**: PENDING
- **parent**: 443 (DATA-SITE 全体方針)
- **spec doc**: `mkdocs_docs/spec/data-site.md`

## 2. scope — 大手にない data で差別化する metric pack

user 指示 2026-05-28 PM (「大手に乗らないデータとかない?」「データとして弱い」) を反映、 advanced sabermetric (BABIP / wOBA 等) **だけでは足りず**、 ファン視点 + 大手未掲載の specific data を以下 3 段階で追加。

### Phase 1.0 base (deploy 済 2026-05-28 06:00 JST)
- Pillar: 当日試合 placeholder / 直近 5 試合 / season summary (試合/打率/安打/打点/得点/盗塁) / 関連 Topic link
- Cluster: 試合/安打/打率/打点 column + **背番号順 sort**

### Phase 1.0a (即実装、 batting_logs SUM だけで取れる 2 metric)
- **打順別 打率** (1-9 番、 batting_logs.slot_order でグループ化)
  - 例: 吉川尚輝 → 1番 .083 / 8番 .400 (下位で爆発、 大手絶対出さない)
- **vs 各球団 打率** (batting_logs JOIN games で対戦別)
  - 例: 吉川 → 中日 .500 / ヤクルト .111 (相性丸見え、 ファンに刺さる)

### Phase 1.0b (Phase 1.0a 観察後 連続実装、 残り 7 個)
- 球場別 (本拠地 vs ビジター、 games.source_url → 球場抽出)
- イニング別 (序盤/中盤/終盤、 at_bat_details.inning_no)
- 守備機会 + 失策 (defense_opportunities + fielding_logs)
- vs 左右投手 (at_bat_details.current_pitcher → pitcher hand JOIN)
- count split (初球 / 2 strike 後、 at_bat_details.count_*)
- 連続安打/出塁 streak (batting_logs 順次 scan)
- 打席あたり投球数 (at_bat_details 集計)

### Phase 1.0c (BLOCKED、 ticket 445 で先に修復)
- 得点圏打率 (RISP、 at_bat_details.runner_state)
- 走者状況別 (満塁 / 2塁等)
- → at_bat_details.batter_canonical が NULL (raw batter column のみ「吉川」「代打・ 吉川」 形式)、 data-insight lane の取り込み修復必要

### Phase 1.0 全体 (Cluster + Pillar 4 page)

| 階層 | URL | 数 |
|---|---|---|
| **Cluster** | `yoshilover.com/data/` | 1 |
| **Pillar** | `yoshilover.com/data/yoshikawa-naoki/` (吉川尚輝) | 1 |
| Pillar | `yoshilover.com/data/sakamoto-hayato/` (坂本勇人) | 1 |
| Pillar | `yoshilover.com/data/maru-yoshihiro/` (丸佳浩) | 1 |
| **合計** | | **4 page** |

| 階層 | URL | 数 |
|---|---|---|
| **Cluster** | `yoshilover.com/data/` | 1 |
| **Pillar** | `yoshilover.com/data/yoshikawa-naoki/` (吉川尚輝) | 1 |
| Pillar | `yoshilover.com/data/sakamoto-hayato/` (坂本勇人) | 1 |
| Pillar | `yoshilover.com/data/maru-yoshihiro/` (丸佳浩) | 1 |
| **合計** | | **4 page** |

- 頻度: 毎日 6:00 JST、 4 page 同時 upsert
- Topic 階層 (既存記事 ~73,000) は **Phase 1.0 では触らない** (Pillar → 既存 Topic への internal link は出力するが、 Topic 側に back-link 注入は Phase 2 で別途)
- 観察期間: 2-3 週間 (Phase 1.5 拡大判断 前)

### Phase 1.0a 取れる data 例

| metric | 吉川尚輝 実 sample | 大手 |
|---|---|---|
| 打順別 | 1番 .083 / 2番 .250 / 3番 .167 / 7番 .333 / 8番 **.400** | 出さない |
| vs 球団 | 中日 **.500** / DeNA .250 / ヤクルト .111 / 阪神 .176 / 広島 .167 / ソフトバンク .222 | 出さない |

## 3. 実装 file (新規)

| file | 内容 |
|---|---|
| `src/data_site_publisher.py` | main module、 Cluster 1 + Pillar 3 loop + page generate + WP upsert |
| `src/data_site_template_cluster.py` | Cluster page jinja template (player list + ranking + ItemList JSON-LD) |
| `src/data_site_template_pillar.py` | Pillar page jinja template (data 表 + 関連 Topic link + SportsPlayer JSON-LD) |
| `src/data_site_slug.py` | player name → URL slug (kebab + romaji)、 例: 吉川尚輝 → `yoshikawa-naoki` |
| `src/data_site_query.py` | insight.db 読み出し + WP REST 関連記事 query (Pillar → Topic link 用) |
| `Dockerfile.data_site_publisher` | Cloud Run Job 用 image (root Dockerfile と分離) |
| `cloudbuild_data_site_publisher.yaml` | Cloud Build 設定 |
| `bin/data_site_publisher_entrypoint.sh` | Cloud Run Job entrypoint |
| `tests/test_data_site_publisher.py` | unit tests (Cluster + Pillar template render / WP upsert mock) |
| `tests/test_data_site_slug.py` | slug 変換 (kanji / katakana / 役職 suffix 除去) |
| `tests/test_data_site_template_cluster.py` | Cluster JSON-LD `CollectionPage` + `ItemList` 構造 verify |
| `tests/test_data_site_template_pillar.py` | Pillar JSON-LD `SportsPlayer` + `BreadcrumbList` 構造 verify |
| `config/data_site_phase1_players.json` | Phase 1.0 対象 3 名 list (吉川尚輝 / 坂本勇人 / 丸佳浩、 Phase 1.5 で拡張) |

## 4. WP REST upsert

新 endpoint `POST /wp-json/wp/v2/pages` で **page (post ではない)** として作成。 既存 post (~73,000) は通常 article。 page は固定ページ、 静的 data site にマッチ。

```python
PAGE_PAYLOAD = {
    "title": f"{player_name}（{position}） データ",  # H1 後ろの actual title
    "slug": player_slug,  # e.g. "okamoto-kazuma"
    "content": rendered_html,  # template render 済
    "status": "publish",
    "parent": data_section_parent_id,  # /data/ section の親 page id
    "meta": {
        "_yoast_wpseo_meta-robots-noindex": "0",  # index 解除
        "_yoast_wpseo_canonical": f"https://yoshilover.com/data/{player_slug}/",
    },
}
```

既存 page を slug で find_existing → 存在すれば `PUT /pages/{id}`、 無ければ `POST /pages`。 同 URL 上書き update で 新 URL 作らない。

## 5. data 取得

| 項目 | 取得 path |
|---|---|
| 当日試合結果 | `insight.db` の `game_results` table、 player_id + date=today |
| 直近 5 試合 stats | `insight.db` の `player_game_stats` table、 player_id + order by date desc limit 5 |
| 月間 / season summary | `insight.db` 既存 view (data-insight が更新) |
| vs 他球団 split | `insight.db` の `team_split` table |
| 関連 player 比較 | 同 pos / 同 lineup 内、 同じく `insight.db` |
| 関連記事 link | WP REST `/wp/v2/posts?tags={player_tag_id}&per_page=10` |

## 6. schema.org JSON-LD

```json
{
  "@context": "https://schema.org",
  "@type": "SportsPlayer",
  "name": "岡本和真",
  "nationality": "JP",
  "memberOf": {
    "@type": "SportsTeam",
    "name": "読売ジャイアンツ"
  },
  "jobTitle": "野球選手",
  "athlete": {
    "@type": "Person",
    "name": "岡本和真",
    "image": "https://yoshilover.com/wp-content/uploads/.../okamoto.jpg"
  },
  "url": "https://yoshilover.com/data/okamoto-kazuma/"
}
```

BreadcrumbList も併記:

```json
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://yoshilover.com/"},
    {"@type": "ListItem", "position": 2, "name": "選手データ", "item": "https://yoshilover.com/data/"},
    {"@type": "ListItem", "position": 3, "name": "岡本和真", "item": "https://yoshilover.com/data/okamoto-kazuma/"}
  ]
}
```

## 7. 触らない範囲 (parent 443 と同)

- 既存 lane / 既存記事 / WP frontend display / featured_media rule / 動画 / 公示

## 8. tests

- `test_data_site_slug.py`: player name → slug 変換 (kanji + katakana + 役職 suffix 除去)
- `test_data_site_publisher.py`: template render 完整性、 schema.org JSON-LD 正しさ、 WP REST upsert 冪等性 (mock)
- `test_data_site_query.py`: insight.db クエリ、 WP REST 関連記事 query (mock)

## 9. deploy

```bash
# build
gcloud builds submit --config=cloudbuild_data_site_publisher.yaml \
  --substitutions=_TAG=phase1-mini-<SHORT_SHA> --project=baseballsite .

# create job (initial)
gcloud run jobs create data-site-publisher \
  --image=asia-northeast1-docker.pkg.dev/.../data-site-publisher:phase1-mini-<SHORT_SHA> \
  --region=asia-northeast1 ...

# create scheduler
gcloud scheduler jobs create http data-site-publisher-daily \
  --location=asia-northeast1 \
  --schedule="0 6 * * *" \
  --time-zone="Asia/Tokyo" \
  --uri="https://asia-northeast1-run.googleapis.com/.../data-site-publisher:run" \
  --http-method=POST \
  --oauth-service-account-email=...
```

## 10. 観察 (Phase 1.0 結果評価)

- Google Search Console submit (1 週間以内)
- 2-3 週間 indexed 確認 (期待: 100% indexed)
- 流入 trend 観察 (まだ少ない、 long-tail で月数 hit 想定)
- 短評 LLM 品質 fb (user 直接確認)
- コスト 実測 (Gemini call 数 + Cloud Run runtime)

## 11. 受け入れ条件 (Phase 1.0)

**Cluster page**:
- [ ] `yoshilover.com/data/` 作成、 H1 = 「巨人選手データ」
- [ ] 3 Pillar への internal link (吉川尚輝 / 坂本勇人 / 丸佳浩)
- [ ] JSON-LD: `CollectionPage` + `ItemList` (3 SportsPlayer entry)
- [ ] `<meta name="robots" content="index, follow">`

**Pillar pages × 3** (吉川尚輝 / 坂本勇人 / 丸佳浩):
- [ ] `/data/yoshikawa-naoki/` / `/data/sakamoto-hayato/` / `/data/maru-yoshihiro/` 作成
- [ ] H1 = 「{player名} ({pos} / 背番号 {jersey})」
- [ ] data section: 当日試合 / 直近 5 試合 / 月間 / season
- [ ] 関連 Topic (既存記事) link 10-20 本/Pillar
- [ ] Cluster への back link 1 (breadcrumb)
- [ ] JSON-LD: `SportsPlayer` + `Person` + `BreadcrumbList`
- [ ] `<meta name="robots" content="index, follow">`
- [ ] featured_media = 該当 player 保存写真 (3 名分 既存保存済 verify 要)

**運用**:
- [ ] daily 6:00 JST upsert で 4 URL 内容更新 (新 URL 増加なし)
- [ ] sitemap.xml に 4 URL 追加、 Search Console submit
- [ ] 2-3 週間後 indexed 確認 + 流入 trend
- [ ] コスト ¥1-2/月 (実測)

## 12. next action

- Claude 自律: 上記 9 file 実装 → tests → commit → push → build → Job create → Scheduler create → 初回 fire (2026-05-29 6:00 JST)
- Phase 1.5 拡大判断は 2026-06-15 頃 user 報告 + GO 待ち
