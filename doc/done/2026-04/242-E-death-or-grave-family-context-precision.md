# 242-E DEATH_OR_GRAVE_INCIDENT_RE family-context precision narrow fix

- number: 242-E
- type: incident follow-up / narrow precision correction
- status: **CLOSED**(2026-04-28、image rebuild `c328772` で live 反映、dry-run + boundary fixture verify で narrow 設計通り動作確認)
- priority: P0.5
- parent: 242 / 242-A
- related: 242, 242-A, 242-D, 242-D2, 154 publish-policy
- owner: Codex B(implementation) / Claude(dispatch, accept, push)
- lane: B
- created: 2026-04-28

## purpose

Prevent false positives where `DEATH_OR_GRAVE_INCIDENT_RE` fires on **family-context death**(祖父 / 祖母 / おじいちゃん / おばあちゃん / 父 / 母 / 家族 etc.)which describes a player's grandparent or family member dying — not the player themselves.

This is a correction ticket for the existing `DEATH_OR_GRAVE_INCIDENT_RE` regex behavior. The regex currently matches death keywords without checking whether the subject is the player or a family member. After the 242-A/D/D2 image rebuild went live (`25f176b`), the next guarded-publish tick (19:00:38 JST) refused 2+ valid Giants game-day articles as `hard_stop:death_or_grave_incident` because the article was about a player honoring their deceased grandfather.

## live evidence(image rebuild 後 2026-04-28 JST、Claude live verify)

| post_id | title | family markers | self-death markers | judgment | 結論 |
|---|---|---|---|---|---|
| 63475 | 「巨人スタメン 巨人・ルーキー皆川岳飛、試合の前に亡くなったおじいちゃんに記念…」 | おじいちゃん | なし | hard_stop:death_or_grave_incident | **false positive** |
| 63470 | 「皆川岳飛「天国で見てくれているおじいちゃんに」 実戦で何を見せるか」 | 祖父 / おじいちゃん / 父 | なし | hard_stop:death_or_grave_incident | **false positive** |
| 63638 | 「マタが登録抹消 ２５日に大量援護も…」 | なし | 登録抹消 (INJURY signal) | hard_stop(真陽性、INJURY_ROSTER + source 不在 → escalate)| **正しい hard_stop** |
| 63517 | 「下半身のコンディション不良で登録抹消へ…」 | なし | 登録抹消 (INJURY signal) | hard_stop(同上) | **正しい hard_stop** |
| 63661 | 「De、昇格・復帰でどこを見たいか」 | なし | 復帰系 | escalate(真陽性とは言えないが non-farm/lineup なので 242-A scope 外、現状仕様通り) | 仕様通り |

→ 242-A は意図通り narrow に動作している(farm 系のみ救う、それ以外は escalate 維持)。
→ DEATH_OR_GRAVE_INCIDENT_RE の精度問題が新たに露呈。

## highest priority constraint

**No regression is allowed.**

- Do not weaken the player's actual death / grave injury / long-term injury hard_stop.
- Do not add Gemini / LLM / browser / API calls.
- Do not add multi-pass reasoning, rewrite, or re-generation.
- Use only cheap deterministic checks against fields already present: subtype, title, body, summary, source URL, existing metadata.
- Do not broaden into 242-A / 242-B / 242-D / 242-D2 / 243.
- Do not touch GCP env, Scheduler, Secrets, WP live publish, X live post, RUN_DRAFT_ONLY.
- Do not modify INJURY_ROSTER_SIGNAL_RE, _is_long_term_recovery_story, or 242-A `_medical_roster_flag()` other than the family-context narrow exclusion.

## narrow design lock

**family-context exclusion**:
- if death keywords (`亡くなった` / `逝去` / `死去` / `急逝` / `他界` / `天国` etc.) co-occur with **family-context markers** in the **same sentence or adjacent 1 sentence**, the article is **not a player-self-death case**, and `DEATH_OR_GRAVE_INCIDENT_RE` should NOT escalate to `death_or_grave_incident` hard_stop
- family-context markers (narrow set):
  - `祖父` / `祖母` / `おじいちゃん` / `おばあちゃん` / `お祖父さん` / `お祖母さん`
  - `父` / `母` / `お父さん` / `お母さん`
  - `家族` / `親戚` / `兄` / `弟` / `姉` / `妹` / `息子` / `娘` / `妻` / `奥さん` / `夫`
- if family-context co-occurrence is detected → `DEATH_OR_GRAVE_INCIDENT_RE` skip (= no escalate)
- if family-context absent and death keyword present → existing hard_stop behavior 維持(player-self-death suspected)

**boundary cases(必ず test 化)**:
- 「皆川岳飛、亡くなったおじいちゃんに記念ボール」 → family co-occurrence → skip(63475 type)
- 「巨人OBの○○氏が逝去」 → 訃報(player-self / OB-self)→ hard_stop 維持
- 「主力選手が脳梗塞で意識不明、家族が病院へ」 → player-self serious → hard_stop 維持(family marker は文中だが death keyword 主体は player)
- 「○○選手の祖父が亡くなり試合を欠場」 → family death + player absent → 公開可、hard_stop しない

注意:単純な keyword co-occurrence では境界判定が難しい case があるので、以下を許容する:
- 「scope 内で取りこぼす case があっても review/draft に倒す」(safe fallback)
- 「全 case を 100% 自動分類しない」(memory `feedback_template_key_no_full_auto_classification.md` 通り)

## scope (Codex B work)

### detection logic(`src/guarded_publish_evaluator.py` 内に narrow 追加)

1. 既存 `DEATH_OR_GRAVE_INCIDENT_RE` の発火直前で **family-context 共起チェック**を追加
2. 同一文 or 隣接 1 文内に family-context marker と death keyword が共起している場合 → `DEATH_OR_GRAVE_INCIDENT_RE` を **skip**(escalate せず)
3. それ以外は **元の挙動を維持**(player-self-death / grave injury は hard_stop)
4. `_is_long_term_recovery_story` は touch しない
5. `INJURY_ROSTER_SIGNAL_RE` は touch しない
6. 242-A / 242-D / 242-D2 の挙動は touch しない

### tests(必須 fixture、全て pass 必須)

- **63475 type fixture**(family co-occurrence): 「巨人スタメン 皆川岳飛、亡くなったおじいちゃんに記念ボール」 → `death_or_grave_incident` skip(hard_stop_flags に含まれない)
- **63470 type fixture**(family co-occurrence): 「皆川岳飛「天国で見てくれているおじいちゃんに」」 → 同上
- **真陽性維持 fixture (player-self death)**: 「巨人OBの○○氏が逝去」 → `death_or_grave_incident` 維持
- **真陽性維持 fixture (player-self grave injury)**: 「主力選手が脳梗塞で意識不明」「全治半年で重症入院」 → `death_or_grave_incident` 維持
- **境界 fixture (family death, player absent)**: 「○○選手の祖父が亡くなり試合を欠場」 → 公開可、hard_stop しない
- **regression fixture (242-A / 242-D / 242-D2 影響なし)**: 既存 fixture 全て pass(124 baseline 維持)

### baseline(fire-time、prompt 冒頭で再確認)

- tests/test_guarded_publish_evaluator.py + tests/test_guarded_publish_runner.py = `124 collected / 124 passed / 14 subtests passed`(242-D2 `25f176b` 着地後の baseline)
- 完了報告で diff(collect/pass)を出すこと
- 既存 hard_stop / freshness / lineup_dup / cleanup gate / 242-A `_medical_roster_flag()` / 242-D placeholder gate / 242-D2 classifier 挙動 不変
- INJURY_ROSTER_SIGNAL_RE / _is_long_term_recovery_story の発火条件 不変

## write_scope(明示 stage、git add -A 厳禁)

- `src/guarded_publish_evaluator.py`(family-context skip helper の最小追加 + DEATH_OR_GRAVE_INCIDENT_RE 発火点の前段 check)
- `tests/test_guarded_publish_evaluator.py`(fixture 6 種以上)
- `doc/active/242-E-death-or-grave-family-context-precision.md`(本 file、implementation summary 追記)
- `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`(242-E close link 追記)
- `doc/README.md`(242-E row 追加)
- `doc/active/assignments.md`(242-E row 追加)

## non-goals(絶対に触らない)

- **Gemini / LLM 追加呼び出し**(call site 増やさない)
- **Codex/Gemini による本文穴埋め / 文章生成 / source-based rewrite**
- Web 検索 / 外部 API
- 重い facts 抽出器 / full fact extractor / NLP module
- 複数 pass 推論 / template registry 構築 / Gemini prompt 全体改修
- 242-A(medical_roster narrow)/ 242-B(entity contamination)/ 242-D(placeholder blocker)/ 242-D2(classifier alignment)/ 243(template contract)への scope 拡大
- env / secret / Cloud Run / Scheduler 変更
- WP publish / X live post / RUN_DRAFT_ONLY
- relevance gate / freshness gate / lineup_dup gate / cleanup_required gate / 242-A `_medical_roster_flag()` / `INJURY_ROSTER_SIGNAL_RE` / `_is_long_term_recovery_story` の発火条件変更
- DEATH_OR_GRAVE_INCIDENT_RE 自体の regex pattern 変更(family-context skip helper を追加するだけ、regex 本体は touch しない)
- 226 (subtype_unresolved) / 241 (mail header) との bundle
- ambient dirty
- subtype 限定対象外への適用拡大

## acceptance(3 点 contract)

1. **着地**: 1 commit に上記 4-6 path を含める(git add -A 禁止、明示 path のみ)
2. **挙動**: pytest 124 baseline + 新規 6 fixture = 130+ collected、全 pass、subtests も全 pass
3. **境界**: 既存 hard_stop / freshness / lineup_dup / cleanup gate / 242-A 挙動 / 242-D placeholder / 242-D2 classifier / regex 発火条件(family-context 部分以外)不変、env / secret / WP / X / Scheduler 不変、LLM call 件数増加なし

## 242-E implementation summary

- pytest diff: `124 collected / 124 passed / 14 subtests passed` → `130 collected / 130 passed / 14 subtests passed`
- 採用 logic: `_medical_roster_flag()` は `DEATH_OR_GRAVE_INCIDENT_RE` 発火時でも `_has_family_context_death_window(title, body_text)` が family death(同一文 or 隣接1文)を高 confidence で検出したときだけ hard-stop を skip し、player-self death / grave injury / long-term recovery は従来通り維持する
- family-context check 経路: `_medical_roster_flag()` → `_has_family_context_death_window()` → `_split_into_sentences()` / `_contains_family_context_marker()` / `_has_self_death_subject()`
- 追加 fixture 数: `6`

## 242-E live verify pending

- TODO(authenticated executor): recent guarded-publish history / dry-run / canary で 63475 / 63470 type が `hard_stop:death_or_grave_incident` を外れることを確認する
- TODO(authenticated executor): player-self death / grave injury / long-term recovery sample が従来通り `death_or_grave_incident` hard-stop のまま残ることを確認する
- TODO(authenticated executor): live verify 結果(image rebuild / tick time / sample post_ids)を本 doc に追記する

## commit 規約

- git add -A 禁止、明示 path のみ stage
- commit message: `242-E: DEATH_OR_GRAVE_INCIDENT_RE family-context precision narrow fix (63475/63470 type) + fixtures`
- push は Claude が後から実行(Codex は commit までで止まる)
- `.git/index.lock` 拒否時は plumbing 3 段 fallback(write-tree / commit-tree / update-ref)

## 完了報告(必須)

- changed files (path 列挙)
- pytest collect/pass diff (before 124 -> after N)
- 採用 logic 1 行(family-context skip 経路 + 既存 DEATH path との連携)
- remaining risk / open question
- 次 Claude 判断事項
- commit hash

## live verify handoff

Claude / authenticated executor handles live verification after Codex commit and push:

- recent guarded-publish history で 63475 / 63470 type 記事が hard_stop ではなくなることを確認
- 真陽性(player-self death / grave injury)が依然 hard_stop されることを確認
- diff sample を本 doc の verify section に記録
- 即時 publish の判断は別途 user 判断(本 ticket scope 外、code 修正のみ)
