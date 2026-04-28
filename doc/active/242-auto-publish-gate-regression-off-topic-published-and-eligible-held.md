# 242 auto-publish gate regression: off-topic published and eligible posts held

- number: 242
- type: incident + investigation + fix
- status: REVIEW_NEEDED
- priority: P0.5
- parent: -
- related: 105 / PUB-004-D, 154, 217, 218, 226, 200, 234
- owner: Codex B(impl) / Claude(audit + dispatch)
- lane: B
- created: 2026-04-28

## incident summary

2026-04-28 JST、auto-publish gate に **両方向 regression** を user が検出:

1. **false positive(対象外通過の疑い、軽度)**: post_id=63844 が publish 済(巨人 vs 広島の見どころ記事)
   - title「巨人―広島戦の見どころ 好調キャベッジと床田攻略に注目」
   - 本文 462 字、巨人 mention ×7、対象内であること自体は確認 ✓
   - ただし本文に「**巨人:則本昂大**」(則本=楽天投手)の **hallucination** あり
   - relevance gate escape ではなく fact / hallucination gate の穴
   - 軽度ブランド毀損 risk

2. **false negative(本来公開対象が止まる、運用 blocker)**: post_id=63841, 63845 が draft で hold
   - 63841: 「巨人二軍スタメン 若手をどう並べたか」(巨人 vs 楽天、二軍、722 字)
   - 63845: 「巨人二軍 3-6 結果のポイント」(巨人 vs 楽天、二軍、549 字)
   - 両方明らかに巨人二軍 farm 記事、自動公開対象
   - guarded-publish 判定で **hard_stop:death_or_grave_incident** で refused
   - 訃報でも重大事故でもない、二軍試合の単純な lineup / 結果記事

## judgment trace evidence(GCS guarded_publish_history.jsonl から)

```json
63844: {"status": "sent", "judgment": "yellow", "publishable": true, "cleanup_required": true, "cleanup_success": true, "hold_reason": null, "is_backlog": false, "freshness_source": "created_at"}
63845: {"status": "refused", "judgment": "hard_stop", "publishable": false, "hold_reason": "hard_stop_death_or_grave_incident", "error": "hard_stop:death_or_grave_incident"}
63841: {"status": "refused", "judgment": "hard_stop", "publishable": false, "hold_reason": "hard_stop_death_or_grave_incident", "error": "hard_stop:death_or_grave_incident,lineup_duplicate_excessive"}
```

## root cause hypothesis(false negative 側)

`src/guarded_publish_evaluator.py:771-781` の `_medical_roster_flag()`:

```python
def _medical_roster_flag(record):
    ...
    if DEATH_OR_GRAVE_INCIDENT_RE.search(combined) or _is_long_term_recovery_story(combined):
        return "death_or_grave_incident"
    if not INJURY_ROSTER_SIGNAL_RE.search(combined):
        return None
    if not _has_primary_source_link(record):
        return "death_or_grave_incident"  # ← escalate path
    return "roster_movement_yellow"
```

→ **INJURY_ROSTER_SIGNAL_RE 発火 + primary_source_link 不在 → 自動的に `death_or_grave_incident` に escalate** される。

63841/63845 は meta.source_url=None(Claude 認証 REST で確認済)。
仮説:本文中の二軍 farm 記事の単語(怪我/離脱/登録抹消系の弱マッチ)が INJURY_ROSTER_SIGNAL_RE に偶然発火 → primary_source_link 不在 → `death_or_grave_incident` に escalate。

related:226 (`subtype_unresolved + cleanup_failed_post_condition` を Yellow 降格) と同方向の問題が **injury signal** でも起きている可能性。

## root cause hypothesis(false positive 側、63844 の hallucination)

- 63844 は judgment=yellow + cleanup_success=true で publish 通過。relevance gate は正しく通している
- 本文の「巨人:則本昂大」(則本=楽天投手)は LLM hallucination
- これは relevance gate ではなく **factual / entity-level gate** の問題
- 既存:113-A(HALLUC candidate router、rule-based)/ HALLUC-LANE-002(Gemini 呼び出し型 fact check、PARKED)/ 224(article-body entity-role consistency)
- 63844 タイプは「実在するが所属が違う(則本=楽天 ≠ 巨人)」= entity-role mismatch の variant

## scope split

本 ticket(242)は **incident 記録 + 真因確定 + 即時止血判断 + 修正方針提案** までを scope とする。
具体的な code 修正は子 ticket に分解する:

- **242-A(false negative narrow fix、P0.5)**: 下記「242-A narrow fix design lock」参照。`_medical_roster_flag()` を丸ごと弱めず、farm / farm_lineup / lineup subtype の **63841/63845 型 false positive のみ** を Yellow/repairable に降格。本物の injury/death/recovery/release は hard_stop 維持
- **242-D(body quality placeholder blocker、P0.5)**: `doc/active/242-D-farm-result-placeholder-body-publish-blocker.md` 参照。63845 型の「先発の 投手 / 選手の適時打 / 試合の詳細はこちら」placeholder 連発を subtype 限定 detector で hard_stop / repairable に分岐し、Gemini 補完なしで publish skip に倒す
- **242-B(false positive 抑止、P1)**: 63844 の「実在選手・他球団所属」hallucination を検出する entity-role / roster mismatch detector(224 と統合候補)+ tests
- **242-C(止血、auth executor)**: 63841 / 63845 の手動 publish 判断(user 判断)+ 63844 の修正/draft 戻し判断(user 判断)

## 242-A narrow fix design lock(2026-04-28 user 指示)

### 原則(全 hard_stop 緩和便に共通)

- `death_or_grave_incident` を丸ごと弱めない
- `missing primary source` を丸ごと publish 可にしない
- farm / farm_lineup / lineup など、**63841・63845 型の明確な false positive だけ** Yellow/repairable に降格
- 本物の怪我・訃報・病状・登録抹消・死去系ワードは hard_stop 維持
- 63844 型(巨人記事内に他球団所属の実在選手を混入)は **242-A scope 外**、242-B で別 gate

### 必須テスト(242-A 着地条件)

- 63841 fixture(巨人二軍スタメン、source 不在): publishable or repairable に落ちる
- 63845 fixture(巨人二軍 3-6 楽天 結果、source 不在): publishable or repairable に落ちる
- 本物の injury/death 文(主力選手の重症入院 / 訃報 / 死去): hard_stop のまま
- source なし一般記事(farm でも lineup でもない、generic body): 無条件 publish にならない(= 元の missing source guard 維持)
- 63844 型「巨人記事内に他球団所属の実在選手を混入」: 少なくとも Yellow/hold 候補として検出(= 242-B 起点として、242-A の修正で隠れない)

### live 反映前 verify(authenticated executor 側)

- recent guarded-publish history の dry-run / canary を 242-A 着地前 baseline と比較
- 直近候補(過去 24h 程度)に対して **hard_stop 件数が不自然に減りすぎていないか** 確認
- 63841/63845 相当だけ救えて、危険記事まで通していないことを件数 + sample で目視
- baseline 値と diff を 242-A の verify section に記録

## 242-A implementation summary

- pytest diff: `101 collected / 101 passed` → `106 collected / 106 passed`
- 採用 logic: `_medical_roster_flag()` は `INJURY_ROSTER_SIGNAL_RE` 発火 + primary source link 不在でも、resolved subtype が `farm*` または `lineup` / `lineup_notice` のときだけ `death_or_grave_incident` へ escalate せず `roster_movement_yellow` を返す
- subtype 判定経路: `_evaluate_record()` → `resolve_guarded_publish_subtype(raw_post, record)` → `_medical_roster_flag(record, subtype=resolved_subtype)`
- fixture 5 種:
  - 63841 型: `farm_lineup` + source 不在 + roster signal でも `roster_movement_yellow`
  - 63845 型: `farm` + source 不在 + roster signal でも `roster_movement_yellow`
  - 真陽性維持: `重症/入院`、`死去`、`全治2か月` は `death_or_grave_incident`
  - source なし一般記事 guard 維持: non-farm/lineup subtype の `登録抹消` は従来通り escalate
  - 63844 型 visibility: `巨人:則本昂大` fixture は現状 detector で Yellow 可視のままにして 242-B follow-up を残す

## 242-A live verify pending

- TODO(authenticated executor): recent guarded-publish history の dry-run / canary で `death_or_grave_incident` 件数を 242-A 前 baseline と比較する
- TODO(authenticated executor): 63841/63845 相当の `farm` / `farm_lineup` / `lineup` 候補が `hard_stop` ではなく `yellow/repairable` に落ちる sample を確認する
- TODO(authenticated executor): non-farm/lineup の source 不在 + roster signal 記事が従来通り escalate することを sample で再確認する

## first triage(Claude 実施済、本 ticket 起票時点)

- ✓ 63844 / 63845 / 63841 の WP REST 取得済(title / status / categories / body / source / subtype)
- ✓ guarded-publish history GCS ledger から 3 件の judgment trace 取得済
- ✓ `_medical_roster_flag()` の escalate 経路特定済
- ✓ 真因仮説固定(INJURY_ROSTER_SIGNAL_RE + source 不在 → escalate)
- ✓ 224 / 113-A / HALLUC-LANE-002 との関連整理

## close conditions

1. **63844 がなぜ通ったか説明できる**: ✓(judgment=yellow + cleanup_success → publish。relevance gate は正常。本文 hallucination は別軸 → 242-B)
2. **63845/63841 がなぜ止まったか説明できる**: ✓(`_medical_roster_flag()` で INJURY signal + source 不在 → death_or_grave_incident escalate)
3. **必要なら止血、または gate 修正 ticket に分割**: 242-A / 242-B / 242-C で分離
4. **自動公開仕様とのズレを README / assignments / ticket doc に残す**: 本 doc + README 242 row + assignments 242 row(本ticket 内で実施)

## non-goals

- 本 ticket 内での src 修正(242-A / 242-B が担当)
- env mutation
- secret 値表示
- WP publish / X live post の policy 変更
- Cloud Run / Scheduler 変更
- 241 (mail header) との混合(完全分離)

## acceptance(3 点 contract)

1. **着地**: 本 doc + README + assignments の 242 row が 1 commit で landed、242-A / 242-B / 242-C 起票
2. **挙動**: false negative 側は 242-A 着地で 63841 / 63845 相当の eligible farm 記事が gate を通過、false positive 側は 242-B で entity-role mismatch を Yellow 以上で hold
3. **境界**: 既存 hard_stop(injury_death / death_or_grave_incident の真陽性)を緩めない、env / secret 不変、relevance gate / freshness gate / lineup_dup gate 不変

## blocker check on user judgment

止血(242-C)は user 判断:
- (a) 63841 / 63845 を **手動 publish**(2 件だけなら手動で迅速止血、再発防止は 242-A で)
- (b) 63841 / 63845 を **draft 維持**(242-A 修正 landed まで止める、その後 auto-publish 復帰)
- (c) 63844 を **draft 戻し**(則本誤情報の修正 or unpublish、ブランド配慮)
- (d) 63844 を **publish 維持**(誤情報軽度として許容、修正は次の出稿サイクルで)

Claude 推奨:
- (a) + (d):63841/63845 は明らかに公開対象なので user 手動 publish で即時運用復旧、63844 は則本誤情報単一なので修正サイクル待ち(unpublish までは過剰)
- (a) と (d) の組み合わせなら、運用は今夜中に復帰、品質改善は 242-A/B 以降の継続課題に分離できる
