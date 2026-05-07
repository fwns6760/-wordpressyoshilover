---
ticket: 250-QA-3
title: fetcher 側 weak generated title review 倒し(PHP weak_title 同等の Python 移植 + narrow phrase list)
status: READY
owner: Codex A
priority: P0(user 手直し負担軽減、即効)
lane: A
ready_for: codex_a_fire
created: 2026-04-29
related: 248-MKT-3a yoshilover_063_is_weak_title (PHP) / 250-QA-1 / post 63952 実例
---

## 背景

post 63952 (4/29 13:51 JST、subtype=manager) で生成 title 「前日コメント整理 ベンチ関連の発言ポイント」が:
- 人名なし、generic
- LLM 自由作文 fallback で生成された
- PHP 側の `yoshilover_063_is_weak_title` (248-MKT-3a) は **front 表示制御のみ**、publish blocked しない
- 結果、generic title の draft が WP に作られて user が手直し or 削除する負担

## 目的

fetcher 側で **生成 title** に対して weak 判定を narrow に追加し、weak なら review 倒し(publish しない)。
**source title は対象外**(source 由来 title は editor 判断、本 ticket は LLM 生成 title のみ対象)。

publish 数より user 手直し削減を優先。

## scope (narrow、最小 diff、2-3 file)

### 1. src/title_validator.py(narrow append)

#### 1-A. weak_generated_title 判定 helper

```python
WEAK_GENERATED_TITLE_PHRASES = (
    "前日コメント整理",
    "ベンチ関連の発言ポイント",
    "実戦で何を見せるか",
    "何を見せるか",
    "注目ポイント",
    "今後に注目",
    "詳しくはこちら",
    "試合の詳細はこちら",
    "結果のポイント",
    "コメント整理",
    "発言ポイント",
)

WEAK_GENERATED_TITLE_STRONG_MARKERS = (
    "巨人", "ジャイアンツ", "選手", "監督", "コーチ", "スタメン", "先発",
    "試合", "登録", "抹消", "復帰", "公示", "番組", "配信",
    # 主要選手名 marker(narrow):
    "戸郷", "山崎", "井上", "岡本", "坂本", "丸", "中田", "梶谷", "浅野",
    # 主要対戦相手 marker:
    "阪神", "中日", "ヤクルト", "広島", "DeNA", "ロッテ", "オリックス",
    "ソフトバンク", "日ハム", "西武", "楽天", "マリナーズ", "ドジャース",
)

def is_weak_generated_title(title: str) -> tuple[bool, str]:
    """生成 title が weak かどうか判定。
    return (is_weak, reason)
    - 12 文字未満 → weak ("title_too_short")
    - blacklist phrase 含む → weak ("blacklist_phrase:<phrase>")
    - 強い marker 1 つも含まない → weak ("no_strong_marker")
    - その他 → not weak
    """
    title = str(title or "").strip()
    if not title:
        return True, "title_empty"
    if len(title) < 12:
        return True, "title_too_short"
    for phrase in WEAK_GENERATED_TITLE_PHRASES:
        if phrase in title:
            return True, f"blacklist_phrase:{phrase}"
    if not any(marker in title for marker in WEAK_GENERATED_TITLE_STRONG_MARKERS):
        return True, "no_strong_marker"
    return False, ""
```

### 2. src/rss_fetcher.py 統合(narrow caller)

生成 title 確定直後(LLM rewritten_title 取得後)、source title でない場合に判定:

```python
from title_validator import is_weak_generated_title

# rewritten_title (LLM 生成) が source title と異なる場合のみ判定
if rewritten_title and rewritten_title != original_title:
    is_weak, weak_reason = is_weak_generated_title(rewritten_title)
    if is_weak:
        logger.warning(json.dumps({
            "event": "weak_generated_title_review",
            "subtype": article_subtype,
            "title": rewritten_title,
            "source_name": source_name,
            "reason": weak_reason,
        }, ensure_ascii=False))
        # 既存 review skip 経路 reuse(247-QA-amend / 250-QA-1 と同 pattern)
        # _log_article_skipped_post_gen_validate 経由
        return None  # or sentinel pattern
```

caller 連携:
- 250-QA-1 で導入した `_ManagerQuoteZeroReviewFallback` sentinel pattern と同 form で `_WeakTitleReviewFallback(reason)` 追加
- 上位 caller で isinstance 判定 → 既存 review skip 経路へ

### 3. tests narrow(既存 fixture 不変、新規 6-8 件追加)

`tests/test_title_validator.py`(or 該当 test file):

- `test_is_weak_generated_title_short_title` (10 文字以下 → True, "title_too_short")
- `test_is_weak_generated_title_blacklist_phrase` (「前日コメント整理」含む → True, "blacklist_phrase")
- `test_is_weak_generated_title_no_strong_marker` (強 marker なし → True, "no_strong_marker")
- `test_is_weak_generated_title_normal_title_passes` (「巨人 vs 阪神 戸郷が好投」→ False)
- `test_is_weak_generated_title_player_name_passes` (「岡本和真 2 安打 1 打点」→ False)
- `test_is_weak_generated_title_empty_returns_weak` (空文字列 → True, "title_empty")

`tests/test_rss_fetcher_*.py`:
- `test_weak_generated_title_routes_to_review` (LLM rewritten title が weak → review sentinel)
- `test_strong_generated_title_renders_normally` (LLM rewritten title が strong → 既存 path)
- `test_source_title_unaffected` (rewritten == original の場合は判定対象外、既存 path)

write_scope (明示 stage、git add -A 厳禁):
- src/title_validator.py
- src/rss_fetcher.py(narrow caller)
- tests/test_title_validator.py(or 該当)
- tests/test_rss_fetcher_*.py(or 該当)

## 不可触

- 既存 `validate_title_candidate` (line 136) 本体 logic touch 禁止(新 helper 追加のみ)
- 既存 weak title 関連 src logic touch 禁止
- src/yoshilover-063-frontend.php (248-MKT-3a の PHP weak_title) touch 禁止(本 ticket は Python 側のみ)
- postgame / lineup / farm / pregame / probable_starter strict path に影響させない
- 247-QA strict template touch 禁止
- 234-impl-* / 244 / 244-followup / 244-B / 244-B-followup touch 禁止
- LLM call 追加 / Gemini retry / 新 LLM
- Cloud Run / Scheduler / Secret / X API / WP REST 設定変更
- 既存記事本文 / WP 既存 post 変更
- 既存 fixture 1 件も変更しない、追加のみ
- ambient dirty 巻き込み

## デグレ防止 contract

- review fallback は 250-QA-1 / 247-QA-amend で実証済 sentinel pattern reuse(新 path 作らない)
- source title 由来は判定対象外(false positive 抑制)
- 強い marker list は **narrow 開始**(本 ticket は最小 list、後段で拡張)
- LLM call 数 0 増(post-gen 判定のみ)
- 既存 caller (rewritten_title なし or source title 同一) は判定通過時 既存挙動維持

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 4 file (or 3 file) のみ stage、git add -A 禁止
2. **挙動**: 新規 fixture 全 pass、既存 fixture fail 0、postgame strict / 既存挙動 完全維持
3. **境界**: 247-QA / 234-impl-* / 244 / Cloud Run / Scheduler / X API / WP REST すべて不変

## commit message

`250-QA-3: fetcher weak generated title review fallback (narrow phrase list, source title untouched)`

## 完了報告 (必須)

- changed files (path + 行数)
- is_weak_generated_title signature + 対象 phrase / marker list
- caller 統合位置(file:line、source title 対象外確認)
- sentinel class 名(_WeakTitleReviewFallback or 同 pattern)
- review fallback 経路(_log_article_skipped_post_gen_validate reuse 確認)
- 新規 fixture pass + 既存 fixture pass
- pytest collect / pass / fail (全体 baseline 比、scope 外既存 fail 1 件は本 ticket 関係なし明記)
- LLM call 数 0 増 確認 (yes/no)
- postgame / lineup / farm strict 不変 確認 (yes/no)
- source title 対象外 確認 (yes/no)
- false positive 候補 0 (yes/no)
- commit hash
- next Claude 判断: push、本 ticket で本日 dispatch 完了
