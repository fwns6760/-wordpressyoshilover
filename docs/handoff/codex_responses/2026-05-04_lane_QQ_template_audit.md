# 2026-05-04 Lane QQ body template v2 audit

Scope:

- preview first
- production / env / deploy 変更なし
- default OFF の新 flag `ENABLE_BODY_TEMPLATE_V2` を追加
- 既存 publish 記事の rewrite なし
- body template / body renderer / template test のみ

## Step 1. Read-only audit

### 1.1 Target files

| area | files | note |
|---|---|---|
| body template core | `src/rss_fetcher.py` | generic + social + manager + game + farm + notice + recovery の実体 |
| strict postgame text template | `src/postgame_strict_template.py` | plain-text section renderer |
| rendered H3 guard path | `src/rss_fetcher.py::_render_preview_body_html`, `src/rss_fetcher.py::_render_postgame_strict_html` | `ENABLE_H3_COUNT_GUARD` に効く HTML preview |
| quality guard reference | `src/article_quality_guards.py` | Lane OO 既存 forbidden phrase list。今回 meaning 変更なし、整合確認のみ |
| template regression tests | `tests/test_*body_template.py`, `tests/test_build_news_block.py`, `tests/test_live_update_template.py`, `tests/test_postgame_strict_template.py` | OFF regression / ON preview contract |

### 1.2 Current template families

| family | source | current section headers | current H3 count | hardcoded forbidden / weak heading | boilerplate / generic wording |
|---|---|---|---|---|---|
| generic player / general fallback | `src/rss_fetcher.py::_article_section_headings`, `_build_safe_article_fallback` | `【ニュースの整理】` / `【ここに注目】` / `【次の注目】` | 3 | `【ここに注目】` | `整理すると、今回のニュースは3点です。` 系、`押さえておきたい` 系 |
| social | `src/rss_fetcher.py::_build_social_safe_fallback`, `_build_social_strict_prompt`, `_normalize_article_heading` | `【話題の要旨】` / `【発信内容の要約】` / `【文脈と背景】` / `【ファンの関心ポイント】` | 3 | `【発信内容の要約】`, `【文脈と背景】` | `目を引きます`, placeholder family |
| manager / coach | `src/rss_fetcher.py::_build_manager_safe_fallback`, `_build_manager_strict_prompt`, `_normalize_article_heading` | `【発言の要旨】` / `【発言内容】` / `【文脈と背景】` / `【次の注目】` | 3 | `【文脈と背景】` | 背景説明が長くなりやすい |
| game lineup | `src/rss_fetcher.py::_build_lineup_safe_fallback`, `_build_game_strict_prompt` | `【試合概要】` / `【スタメン一覧】` / `【先発投手】` / `【注目ポイント】` | 3 | なし | helper card で `📊 今日のスタメンデータ` / `👀 スタメンの見どころ` が追加 H3 化しうる |
| game postgame | `src/rss_fetcher.py::_build_postgame_safe_fallback`, `_build_game_strict_prompt` | `【試合結果】` / `【ハイライト】` / `【選手成績】` / `【試合展開】` | 3 | なし | helper card で `📊 今日の試合結果` / `👀 勝負の分岐点` が追加 H3 化し、full render では 5 H3 まで増える |
| game pregame | `src/rss_fetcher.py::_build_pregame_safe_fallback`, `_build_game_strict_prompt` | `【変更情報の要旨】` / `【具体的な変更内容】` / `【この変更が意味すること】` | 2 | なし | 既存のままで guard 上は問題なし |
| game live_update | `src/rss_fetcher.py::_build_game_safe_fallback`, `_build_game_strict_prompt` | `【いま起きていること】` / `【流れが動いた場面】` / `【次にどこを見るか】` | 2 | なし | 既存のままで guard 上は問題なし |
| game live_anchor | `src/rss_fetcher.py::_build_game_safe_fallback`, `_build_game_strict_prompt` | `【時点】` / `【現在スコア】` / `【直近のプレー】` / `【ファン視点】` | 3 | なし | `気になります` 系の締めが多い |
| farm result | `src/rss_fetcher.py::_build_farm_safe_fallback`, `_build_farm_strict_prompt` | `【二軍結果・活躍の要旨】` / `【ファームのハイライト】` / `【二軍個別選手成績】` / `【一軍への示唆】` | 3 | なし | `一軍への示唆` が長くなりやすい |
| farm lineup | `src/rss_fetcher.py::_build_farm_lineup_safe_fallback`, `_build_farm_strict_prompt` | `【二軍試合概要】` / `【二軍スタメン一覧】` / `【注目選手】` | 2 | なし | 既存のままで guard 上は問題なし |
| notice | `src/rss_fetcher.py::_build_notice_safe_fallback`, `_build_notice_strict_prompt` | `【公示の要旨】` / `【対象選手の基本情報】` / `【公示の背景】` / `【今後の注目点】` | 3 | なし | `押さえておきたいところです` 系 |
| recovery | `src/rss_fetcher.py::_build_recovery_safe_fallback`, `_build_recovery_strict_prompt` | `【故障・復帰の要旨】` / `【故障の詳細】` / `【リハビリ状況・復帰見通し】` / `【チームへの影響と今後の注目点】` | 3 | なし | `見たいところです` 系 |
| postgame strict renderer | `src/postgame_strict_template.py::render_postgame_strict_body` + `src/rss_fetcher.py::_render_postgame_strict_html` | `【試合結果】` / `【ハイライト】` / `【選手成績】` / `【試合展開】` | 3 | なし | HTML 化すると 4 section 全てが H2/H3 系で出る |

### 1.3 Forbidden phrase hardcode locations

| phrase / family | repo location | current status |
|---|---|---|
| `【発信内容の要約】` | social heading constants, social strict prompt, social normalization alias | hardcoded |
| `【文脈と背景】` | manager/social heading constants, strict prompts, normalization alias | hardcoded |
| `【ここに注目】` | generic `_article_section_headings`, generic prompt rules | hardcoded |
| `目を引きます` | social safe fallback | hardcoded |
| `整理すると、今回のニュースは3点です。` | generic fallback intro | hardcoded |
| `気になります` 締め | live / farm / social / recovery の一部 closing sentence | hardcoded but user lock 上、今回は全削除ではなく H3/heading 対応優先 |

### 1.4 Current risk summary

1. social / manager の forbidden heading が template 直書きなので、Lane OO の filter を ON にすると review 化が多発する。
2. lineup / postgame / farm / notice / recovery / social / manager / live_anchor / postgame_strict は body section だけで H3 が 3 個、postgame full render は helper card で 5 H3 まで増える。
3. generic `【ここに注目】` は forbidden list には未登録だが、user lock 上は v2 で消しておくべき heading family。
4. `64432` のような subject unresolved / placeholder family は header rename だけでは完治しない。Lane QQ では phrase/H3 を直し、subject recovery は別 lane のままにする。

## Step 2. Rename design

### 2.1 Rename policy

| current | v2 | note |
|---|---|---|
| `【発信内容の要約】` | `【投稿で出ていた内容】` | social 専用 |
| `【文脈と背景】` | `【この話が出た流れ】` | social / manager 専用 |
| `【ここに注目】` | `【今回のポイント】` | generic 3-section family |

### 2.2 Keep / no-rename families

次の family は見出し名は維持し、H3 level だけを調整する。

- lineup: `【先発投手】` を auxiliary 扱い
- postgame: `【選手成績】` を auxiliary 扱い
- farm: `【二軍個別選手成績】` を auxiliary 扱い
- notice: `【公示の背景】` を auxiliary 扱い
- recovery: `【リハビリ状況・復帰見通し】` を auxiliary 扱い
- live_anchor: `【直近のプレー】` を auxiliary 扱い
- postgame helper cards / lineup helper cards / live helper cards は heading text を維持して H4 へ降格

## Step 3. H3 reduction design

### 3.1 Core rule

- flag OFF: current H2/H3 structure を完全維持
- flag ON:
  - structured template の first heading だけ H2
  - main sections は H3
  - auxiliary 1 section は H4
  - target = H3 0-2

### 3.2 Family-by-family v2 render level

| family | H2 | H3 | H4 |
|---|---|---|---|
| social | `【話題の要旨】` | `【投稿で出ていた内容】`, `【ファンの関心ポイント】` | `【この話が出た流れ】` |
| manager | `【発言の要旨】` | `【発言内容】`, `【次の注目】` | `【この話が出た流れ】` |
| lineup | `【試合概要】` | `【スタメン一覧】`, `【注目ポイント】` | `【先発投手】` |
| postgame | `【試合結果】` | `【ハイライト】`, `【試合展開】` | `【選手成績】` |
| farm | `【二軍結果・活躍の要旨】` | `【ファームのハイライト】`, `【一軍への示唆】` | `【二軍個別選手成績】` |
| notice | `【公示の要旨】` | `【対象選手の基本情報】`, `【今後の注目点】` | `【公示の背景】` |
| recovery | `【故障・復帰の要旨】` | `【故障の詳細】`, `【チームへの影響と今後の注目点】` | `【リハビリ状況・復帰見通し】` |
| live_anchor | `【時点】` | `【現在スコア】`, `【ファン視点】` | `【直近のプレー】` |
| generic 3-section | `-` | `【ニュースの整理】`, `【次の注目】` | `【今回のポイント】` |
| pregame / live_update / farm_lineup | current 維持 | current 維持 | 追加降格なし |

### 3.3 Explicit non-goals

- title repair
- subject recovery
- placeholder body cleanup
- publish 済み既存記事の backfill
- Lane OO / PP guard meaning change

## Step 4. Patch plan

1. `src/rss_fetcher.py`
   - `ENABLE_BODY_TEMPLATE_V2` helper を追加
   - heading set / version helper を v1/v2 両対応へ変更
   - social / manager / generic alias rename
   - render level helper を追加し、flag ON の時だけ auxiliary heading を H4 化
   - lineup/postgame/live helper card heading も H4 化
2. `src/postgame_strict_template.py`
   - plain-text section order は据え置き
   - HTML 化は shared renderer 側の H4 化で対応
3. tests
   - OFF regression 維持
   - ON contract: renamed header / H3<=2 / helper card H4

## Step 5. Acceptance for Lane QQ

- `ENABLE_BODY_TEMPLATE_V2=0` では既存 template tests がそのまま通る
- `ENABLE_BODY_TEMPLATE_V2=1` では targeted heading rename が出る
- `ENABLE_BODY_TEMPLATE_V2=1` では structured body H3 count が 2 以下
- `ENABLE_BODY_TEMPLATE_V2=1` でも fact / quote / source citation は増やさない
- deploy / env apply はしない
