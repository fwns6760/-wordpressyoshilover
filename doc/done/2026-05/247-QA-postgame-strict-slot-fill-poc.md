---
ticket: 247-QA
title: postgame strict slot-fill POC(LLM 自由作文 → JSON 抽出 + 固定 template に slot-fill、type 別 block 振り分け)
status: READY
owner: Codex B
priority: P0.5
lane: B
ready_for: codex_b_fire
created: 2026-04-29
updated: 2026-04-29 (user 制約 7 件 lock、key_events type 化 + 次戦情報限定 + 文字数 target prompt 不記載)
related: 234-impl-5 (postgame body hardening、CLOSED)、244 (numeric guard、CLOSED)、234-impl-7 (pregame、CLOSED)
---

## 目的

postgame 記事で、スコア・勝敗・日付・対戦相手・投手成績・選手名のハルシネーションを **大幅に減らす**。
LLM に自由本文を書かせる代わりに、source から **facts を JSON 抽出** → 本文は **固定 template に type 別ブロック分配 slot-fill**。

**短文化が目的ではない**。source にある事実だけで余計な作文をせずに必要十分な postgame 本文を作る。
**厚みは render 側のブロック構造で作る**(LLM への文字数目標は与えない、padding 誘発防止)。

## user 制約 7 件 lock

1. LLM には本文を書かせない
2. LLM には source facts を JSON 抽出させる
3. **文字数目標は prompt に入れない**(padding 誘発防止)
4. source facts が少ない場合は review fallback
5. **厚みは render 側のブロック構造で作る**(LLM への指示でなく render の自動結果)
6. **同じ event の二重記載を防ぐため、key_events に type を持たせる**
7. **「次戦への見方」「明日の焦点」などの編集解釈は strict path で禁止**、「次戦情報」のみ

## scope (narrow、postgame 1 subtype のみ)

### 1. 新規 module `src/postgame_strict_template.py`

#### 1-A. JSON schema 定義

```python
POSTGAME_STRICT_REQUIRED_FIELDS = ("game_date", "opponent", "giants_score", "opponent_score", "result")

# key_events 各要素 schema:
KEY_EVENT_TYPES = ("pitching", "batting", "fielding", "comment", "other")

POSTGAME_STRICT_SCHEMA = {
    "game_date": "YYYY-MM-DD or null",
    "opponent": "string or null",
    "giants_score": "number or null",
    "opponent_score": "number or null",
    "result": "win|loss|draw|unknown",
    "starter_name": "string or null",
    "starter_innings": "number|string or null",
    "starter_hits": "number or null",
    "starter_runs": "number or null",
    "key_events": [
        {
            "type": "pitching|batting|fielding|comment|other",
            "text": "source にある事実のみ",
            "evidence": "根拠となる source 断片"
        }
    ],
    "manager_comment": "string or null",
    "next_game_info": {
        "date": "string or null",
        "opponent": "string or null",
        "venue": "string or null",
        "start_time": "string or null"
    },
    "confidence": "high|medium|low",
    "evidence_text": ["string", ...]
}
```

#### 1-B. Gemini prompt(自由作文禁止、JSON 抽出のみ、**文字数 target 0**)

```
あなたは事実抽出の助手です。以下の source から postgame の facts を抽出し、JSON のみを返してください。
本文を書いてはいけません。JSON 以外の文字列を 1 文字も含めないでください。

[制約]
- source に明記されていない値は null にする
- 推測・補完・「明日の焦点」等の編集解釈表現禁止
- 選手名・スコア・日付・対戦相手は source 内の表記そのまま
- 「次戦への見方」「展望」など解釈表現禁止、次戦情報は事実(日付/相手/球場/開始時刻)のみ
- key_events は source からの実引用、各 event は type で分類:
  - pitching: 投球関連(被安打、失点、投球回、奪三振 等)
  - batting: 打撃関連(本塁打、適時打、得点絡み 等)
  - fielding: 守備関連(失策、好守 等)
  - comment: 監督・コーチ・選手コメント
  - other: 上記以外の事実
- evidence は source 内の文(各 fact の根拠)

[SCHEMA]
{schema 定義}

[SOURCE]
{source_text}

[OUTPUT]
JSON only:
```

**禁止**: 文字数目標(500-900 字等)、padding 誘発する目標値、厚み目標、「読み応え」「分かりやすく」等の qualitative 指示。

#### 1-C. validator

```python
def validate_postgame_strict_payload(payload, source_text):
    """schema validation + required facts + evidence_text の source 由来確認 + key_events type 妥当性"""
    # required (game_date, opponent, giants_score, opponent_score, result) 欠損 → review
    # key_events 各要素 type が KEY_EVENT_TYPES 外 → review
    # evidence_text / event.evidence が source 内に存在しない → review
    # confidence=low → review
    # type mismatch (game_date 形式違反等) → review

def has_sufficient_for_render(payload):
    """publish 判定: required facts + (投手 OR 打線 OR コメント OR 次戦情報のいずれか十分) → render OK"""
    # required only → review (publish しない)
    # required + (starter_name AND starter_innings) OR
    #          (key_events に batting type 1 件以上) OR
    #          (manager_comment 非空 OR key_events に comment type) OR
    #          (next_game_info.date AND next_game_info.opponent)
    # のいずれか → render OK
```

#### 1-D. 固定 template renderer(type 別ブロック振り分け、dedupe)

```python
def render_postgame_strict_body(payload):
    """null 項目は section 自体を出さない、空文字埋め禁止、LLM 自由作文 0、type 別 block 振り分け、text/evidence dedupe"""

    # ブロック候補:
    # 1. 試合結果(必須、game_date + opponent + score + result_jp)
    # 2. 試合の分岐点(key_events から type=other or 流れ変動 event)
    # 3. 投手成績(starter_* 揃ってる場合のみ)
    # 4. 打線・得点場面(key_events から type=batting)
    # 5. コメント(manager_comment + key_events から type=comment)
    # 6. 次戦情報(next_game_info、解釈・「見方」禁止、事実のみ)
    
    # 同 event が複数 block に出ないよう text/evidence ベースで dedupe
    # type=pitching の event は 投手成績 block へ、type=batting は 打線 block へ
    # type=other は 試合の分岐点 block へ(scope 不明な event の安全 fallback)
```

**禁止**:
- 「次戦への見方」「明日の焦点」「悔しい一戦」等の感想・編集表現
- LLM 自由作文 0(全 block で payload field を slot-fill のみ)
- null 項目を「未確認」「不明」等で埋める(section 自体を省略)

#### 1-E. feature flag

```python
POSTGAME_STRICT_FEATURE_FLAG_ENV = "POSTGAME_STRICT_TEMPLATE"

def is_strict_enabled() -> bool:
    return os.environ.get(POSTGAME_STRICT_FEATURE_FLAG_ENV, "0").strip() == "1"
```

default OFF、env 未設定で既存自由生成 path 維持。

### 2. src/rss_fetcher.py 統合(narrow、最小 diff、既存 path 0 diff)

postgame Gemini call 該当箇所に narrow if 分岐:

```python
if subtype == "postgame" and _postgame_strict_enabled():
    prompt = _postgame_strict_prompt.format(source_text=source_block)
    raw = _call_gemini(prompt, ...)  # 既存 call、call 数同じ
    payload, parse_reason = _postgame_strict_parse(raw)
    if payload is None:
        log_warning(f"postgame_strict: parse_fail reason={parse_reason}")
        return _existing_review_route(...)  # 既存 review path reuse
    is_valid, errors = _postgame_strict_validate(payload, source_block)
    if not is_valid:
        log_warning(f"postgame_strict: validation_fail errors={errors}")
        return _existing_review_route(...)
    if not _postgame_strict_has_sufficient_for_render(payload):
        log_warning("postgame_strict: insufficient_for_render → review")
        return _existing_review_route(...)
    body_text = _postgame_strict_render(payload)
    # 以降 既存 publish path に流す
else:
    # 既存自由生成 path 完全維持
    pass
```

flag OFF / postgame 以外 / error → 既存 path 完全 fallback。

### 3. tests `tests/test_postgame_strict_template.py`(12 fixture、既存 fixture 不変)

- `test_strict_json_validation_passes_with_required_facts`
- `test_strict_json_validation_fails_when_score_missing` → review
- `test_strict_json_validation_fails_on_invalid_json` → review
- `test_strict_template_renders_only_present_slots`(null section 省略)
- `test_strict_template_does_not_invent_pitcher_when_null`
- `test_strict_template_renders_event_in_correct_block_by_type`(pitching → 投手成績、batting → 打線)
- `test_strict_template_dedupes_event_across_blocks`(同 text/evidence は 1 block のみ)
- `test_strict_evidence_must_exist_in_source`
- `test_strict_confidence_low_routes_to_review`
- `test_strict_required_only_routes_to_review`(投手・打線・コメント・次戦情報なし → review)
- `test_strict_next_game_info_only_facts_no_interpretation`(「見方」「展望」等が renderer 出力に含まれない)
- `test_strict_feature_flag_off_uses_existing_path`(flag OFF で既存 path、0 diff)
- `test_strict_does_not_affect_other_subtypes`(lineup / farm 等不変)

## 不可触

- postgame **以外**の subtype
- src/baseball_numeric_fact_consistency.py / src/body_validator.py / src/fixed_lane_prompt_builder.py
- src/guarded_publish_evaluator.py / src/publish_notice_email_sender.py / src/tools/draft_body_editor.py
- src/article_entity_team_mismatch.py / src/llm_cost_emitter.py
- Gemini call 数 増加 / retry loop 追加
- X API / X 投稿
- env / Secret / Scheduler / Cloud Run 設定変更(`POSTGAME_STRICT_TEMPLATE` env enable は user GO、本 ticket は code 実装のみ)
- WP REST / publish gate / mail UX
- 既存 fixture 1 件も変更しない、追加のみ
- ambient dirty 巻き込み

## デグレ防止 contract

- feature flag default OFF、env 未設定 = 既存挙動完全維持
- flag OFF 時の既存 path に **0 行 diff**
- JSON parse fail / validation fail / sufficient 不足 / confidence=low → 既存 review 倒し path 経由
- postgame 以外の subtype に call 経路 0 変更
- Gemini call 数増加 0(prompt 差し替えのみ)
- false positive(良 JSON を validation で reject)1 件でも疑いがあれば実装止めて Claude に report
- 既存テスト全 pass

## acceptance (3 点 contract)

1. **着地**: 1 commit に新 module + rss_fetcher narrow + tests のみ stage、git add -A 禁止
2. **挙動**: 新規 12 fixture 全 pass、既存 fixture fail 0、flag OFF で既存挙動完全
3. **境界**: postgame 以外 subtype / 244 / 234-impl-* / Gemini call 数 / Cloud Run / Secret すべて不変

## commit message

`247-QA: postgame strict slot-fill POC (JSON extraction + type-aware block render, feature flag default OFF)`

## rollback

- env `POSTGAME_STRICT_TEMPLATE` 未設定(default OFF)で既存 path
- ダメな場合は flag 削除 + strict 関連 code 廃止(別 ticket)

## 完了後の Claude 判断事項

- pytest baseline 確認 + commit accept
- git push
- live deploy: env var enable は **user 判断**(Cloud Run env 変更は user GO 必須)
- まず default OFF で deploy、user GO 後に flag ON で A/B 観察
