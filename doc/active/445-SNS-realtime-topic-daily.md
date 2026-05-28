# 445 SNS リアルタイム話題 (巨人 1軍/2軍/3軍) daily aggregation

## 1. ticket header

- **ticket id**: 445
- **status**: READY (user GO 済 2026-05-28 PM、 Claude 自律実装)
- **owner**: Claude Code
- **lane**: ingest / sns-realtime
- **created**: 2026-05-28
- **priority**: P1
- **github_issue**: #114 (https://github.com/fwns6760/-wordpressyoshilover/issues/114)
- **spec doc**: `mkdocs_docs/spec/sns-realtime-topic.md`

## 2. 目的 (1 line)

Yahoo リアルタイム検索の **巨人専門 1軍/2軍/3軍 版** を、 既存 RSSHub + 既存 Scheduler + 既存 fetcher pipeline に相乗りで実装 (==追加コスト ¥0==)。

## 3. scope (Phase 1.0)

- source = 既存登録済の 巨人専門 / 球団公式 X アカウント 4 件 (`yomiuri_giants` / `TokyoGiants` / `hochi_giants` / `Sanspo_Giants`)
- 取得 = RSSHub `https://rsshub-n5hunzkyna-an.a.run.app/twitter/user/{handle}?limit=30`
- 発火 = 既存 fetcher Scheduler の中で内部 time gate (`hour in {10,13,17,21} and minute < 5`)、 1 日 4 回
- 出力 = WP post 1 件 / 日 (slug = `giants-sns-realtime-{YYYY-MM-DD}`)、 4 fire で同 URL を upsert
- 分類 = 三軍 (`role=='ikusei'` or `育成/三軍/3軍` keyword) / 二軍 (`ファーム/二軍/イースタン` keyword or roster `position` に `二軍/ファーム`) / 一軍 (default)
- トレンド = `config/giants_roster.json` 全 136 名 aliases で言及回数を count、 上位 15 名 (2 回以上のみ) を tag chip で最上部表示
- render = oEmbed `https://publish.twitter.com/oembed` (X 公式、 著作権安全)

Phase 1 では監督 / コーチ言及は **一軍配置を仮定**。 lineup data を使った 1軍 / 2軍 コーチ split は別 ticket (Phase 2)。

## 4. 実装 file (新規)

| file | 内容 |
| --- | --- |
| `src/sns_realtime_topic.py` | main module、 fetch + 分類 + render + WP upsert |
| `src/sns_realtime_topic_classifier.py` | 一軍 / 二軍 / 三軍 分類 + roster alias match |
| `src/sns_realtime_topic_template.py` | jinja template (トレンド + 3 section + 出典) |
| `tests/test_sns_realtime_topic.py` | fetch mock / 分類 / render / upsert mock |
| `tests/test_sns_realtime_topic_classifier.py` | 育成 / ファーム keyword + roster alias match の boundary tests |

新規 Cloud Run Job / Dockerfile / cloudbuild は **作らない**。 既存 `yoshilover-fetcher` service の hourly run に組み込む。

## 5. 触らない範囲

- 既存 article / 既存 subtype の生成 path
- 既存 Cloud Scheduler の cron 式 / enable 状態
- WP frontend display CSS
- X live posting / X API key
- featured_media rule
- 個人 X アカウント (球団 / 専門メディア以外は対象外)
- 野球全般アカウント (`SponichiYakyu` / `nikkansports` / `npb`) は本 subtype では使わない

## 6. tests (新規)

- `test_sns_realtime_topic_classifier.py`
  - 育成 keyword → 三軍
  - ファーム / 二軍 / イースタン keyword → 二軍
  - 選手名 alias で `role=='ikusei'` match → 三軍
  - keyword なし + roster match なし → 一軍 default
- `test_sns_realtime_topic.py`
  - RSSHub fetch mock (1 handle 取得失敗で他 3 handle 継続)
  - トレンド count 2 回未満は除外
  - WP slug 存在チェック → PUT で update (1 日 1 URL fix)
  - section 0 件は H2 ごと非表示

## 7. 受け入れ条件

- [ ] 4 fire 後の 1 日で WP に **1 URL のみ** 作成され、 4 回 update される
- [ ] トレンド section に上位 15 名以下が言及回数 desc で表示
- [ ] 三軍 section に 育成選手 (`role=='ikusei'`) または `育成/三軍/3軍` keyword 投稿のみ
- [ ] 二軍 section に `ファーム/二軍/イースタン` keyword 投稿のみ
- [ ] 一軍 section に default 投稿
- [ ] oEmbed が正しく render され、 X 投稿が embed 表示される
- [ ] Cloud Run / Scheduler / RSSHub の追加課金 ¥0 (24h 観察)

## 8. blockers

なし。 既存 RSSHub Cloud Run + 既存 Scheduler + 既存 roster + 既存 X account list で全部揃っている。

## 9. 関連 ticket

- 関連: 392 (X branding MCP), 411 (X voice persona), 414 (X voice quality framework) — 本 ticket は X 出力ではなく **WP 上の集約記事**、 出力 channel が異なる
- 関連: 444 (data-site per-player) — daily upsert / 1 URL fix 方針は共通

## 10. 実装順序

1. spec doc (本 commit、 done)
2. ticket doc (本 commit、 done)
3. GH Issue 作成
4. README priority board 更新 + assignments.md 更新 (本 commit)
5. mkdocs.yml nav 追加 (本 commit)
6. 実装 (`src/sns_realtime_topic_classifier.py` → `src/sns_realtime_topic.py` → template → tests)
7. fetcher pipeline に hook 追加 (`src/rss_fetcher.py` の hourly entry に time gate + caller 1 行)
8. unit tests pass (`pytest tests/test_sns_realtime_topic*.py`)
9. full pytest baseline pass
10. commit + push (feat/377 branch)
11. fetcher image rebuild + deploy
12. 翌日 4 fire 観察 + 受け入れ条件 verify
