# 465 DATA-ARTICLE title の発見ドリブン化(機械テンプレ脱却・no-AI維持)

- **種別**: 実装 / **priority**: P2(差別化C・CTR/長尾SEO) / **effort**: M
- **親**: 443 / 設計: `455...md` §16 / §17 Phase2C / GH: #129
- **status**: READY(title rule の確定先行)

## 背景(深掘り 1次source)

データ記事 title は全て機械 f-string(`【巨人データ】{選手}、{指標}{値}で{league}{順位}位（{scope}）`)。**「発見/驚き」を表現できていない**。memory の title rule([[feedback_title_no_ai]] / [[feedback_title_clickable_descriptive]])= 3-token literal・no-AI・末尾truncation禁止 は維持必須。

## ゴール

no-AI rule を**維持したまま**、数値の**対比/驚き**を title に literal で載せる。例:
- 現状: `【巨人データ】吉川尚輝、終盤打率.286でセ3位（直近30日）`
- 改善: `【巨人データ】吉川尚輝、終盤.286は序盤.194の1.5倍 競り合いに強い（直近30日）`
- = source 数値の対比(序盤/終盤・本拠/ビジター差・順位変動)を literal 組み立てで「発見」化。LLM rewrite はしない。

## 対象

- `config/insight_whitelist.json` の `title_format`(case A-D, L113-131)+ 各 publisher の title 組み立て。
- `insight_title_guard`(period suffix)維持。

## やる / やらない

- やる: 対比型 title pattern(case 追加)、driver となる数値の選定ロジック、test。
- やらない: **LLM/AI で title 生成**、煽り誇張(事実から外れる)、末尾 `…` truncation、媒体名混入。

## 成功条件

- 主要角度の title が「発見/対比」を literal で表現、no-AI / 60字以内 / truncation無 を維持。
- title rule の regression test green(既存 title guard を壊さない)。

## 依存

title rule(どの対比を driver にするか case 設計)を確定してから実装。

## 2026-06-03 v1 実装(value-vs-league-mean 対比、ranking 系 renderer)

- **status**: PARTIAL_LIVE_PENDING_DEPLOY → (deploy 後)PARTIAL_LIVE。
- **user 文体決定**: 「数値対比＋断定ラベル(ratio band → 固定辞書、AI生成なし)」。
- **実装**:
  - `src/analysis/insight_contrast_title.py`(新規・純粋・tested 8): `build_contrast_title()`。higher-better=`{metric}{value}はリーグ平均{mean}の{r}倍 {label}`、lower-better(ERA系)=`…を{label}`。gap<1.12倍 / 数値欠落 → `None`(rank f-string fallback)。60字cap・truncation無・LLM不使用。
  - `config/insight_whitelist.json` title_format に `case_e_contrast_higher/lower` + note + examples。
  - `anomaly_article_publisher._render_unified_article` に配線(render時 `cohort_stats.league_mean` + `value` + `_is_higher_better` で対比 title 構築、非該当は従来 rank title)。
- **適用範囲(v1)**: `_render_unified_article` 経由の 3 renderer = zscore_batter / zscore_pitcher / giants_top。
- **prod insight.db 実レンダ検証**(snapshot 2026-06-02): 平山功太 `OPS1.005はリーグ平均0.607の1.7倍 リーグ屈指（直近1ヶ月）`、大城卓三 `OPS0.878…1.4倍 リーグ屈指`、render時 canonical 値で body と整合。
- **test**: contrast 8 + insight/anomaly/data_site regression 0(1541 passed、dup_prevention 3 fail は date 依存の既存 fail、stash で変更前同一 fail を実証)。

## 残(465 follow-up、本 v1 scope 外)

- **split 型対比(序盤/終盤・本拠/ビジター・対左右)**: post エンジンの candidate に split データが無い。出すには split を candidate 生成へ配線する別 scope(大)。
- **非 unified renderer**(hr_pace / 連続多安打 / hero / 好投 / milestone / standings): 各自 title 組み立て。対比可能な軸があれば個別対応。
