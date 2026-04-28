# 242-D farm_result placeholder body publish blocker

- number: 242-D
- type: incident fix(narrow placeholder detector + publish blocker)
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 242
- related: 242-A, 226, 217, 154 publish-policy, 234 subtype contract
- owner: Codex B(impl) / Claude(dispatch)
- lane: B
- created: 2026-04-28

## background

2026-04-28 incident 第 2 軸:**63845 公開後の本文に placeholder 連発が露出**(Claude/auth executor が status=draft で隔離済)。

63845 本文(全文 549 字、抜粋):
> 📰 巨人公式 / 巨人公式X ⚾ GIANTS FARM WATCH 【二軍】巨人 3-6 楽天 **先発の 投手は5回3失点 9回に 選手の適時打などで** 【二軍】巨人 3-6 楽天**先発の 投手は5回3失点9回に 選手の適時打などで**追い上げるも敗戦。**試合の詳細はこちら**。 📌 関連ポスト ... 【二軍結果・活躍の要旨】 巨人二軍の試合は3-6という結果でした。 💬 このニュース、どう見る？ ...

→ **「先発の 投手」「選手の適時打」「試合の詳細はこちら」が actor / 名前空欄のまま 2 連発**。 source 事実不足で LLM が固有名詞を埋められず、テンプレ穴空き状態のまま publish に通った。

これは relevance gate の問題でも `_medical_roster_flag()` の問題でもなく、**body quality gate の不在**。

## design constraint(2026-04-28 user 明示)

- **publish gate に placeholder body detector を追加**:本文に placeholder 連発が残っていれば publish 前に hard_stop or repairable に倒す
- **Gemini で本文を穴埋め生成しない**:source 事実不足は LLM 呼び出しではなく **publish skip / review 行き**
- **source 不足は draft 維持**:source 確認後の手動修正 / Codex source-based 補正 → 再 publish 判断
- **narrow scope**:farm_result 中心、generic farm にも展開、他 subtype の placeholder 検出は別 ticket
- 良質 farm 記事(actor 名 / イニング / 数値が揃った正常本文)は今まで通り publish

## scope (Codex B work)

### detection logic(`src/guarded_publish_evaluator.py` 内に最小実装)

publish 前 body に以下のいずれかが残っていたら **hard_stop:`farm_result_placeholder_body`** または既存 hard_stop set に類似 flag を新規追加:

#### high-confidence placeholder patterns(必須検出)

1. **空 actor + 動詞 patterns**(actor 名前が空欄のまま動詞続く):
   - `先発の 投手` / `先発の投手` / `先発の\s+投手`(actor 空 + 投手の組合わせ)
   - `選手の 適時打` / `選手の\s*適時打` / `選手の安打` / `選手のホームラン`(actor 空 + 行為)
   - `投手は[\d]+回[\d]+失点` の前に固有名詞がない場合(`先発の 投手は5回3失点` etc)
   - 同一文中 / 直近 2 sentences で **actor 空欄 + 動詞** が **2 回以上連発** したら hard_stop
   - 1 回のみなら repairable または Yellow

2. **filler / placeholder 文末**:
   - `試合の詳細はこちら` / `詳細はこちら` / `詳しくはこちら` 単独で締めくくる(filler-only outro)
   - ただしリンクや関連ポスト見出しと併用は除外(関連リンク block の正常 cue)

3. **空見出し / 空 metadata**:
   - `<h[1-6]>\s*</h[1-6]>`(空タグ)
   - `【\s*】` / `【.{0,3}】`(中身なし or extremely thin タイトル)
   - 空見出しが 1 件でもあれば repairable、2 件以上で hard_stop

#### subtype 限定 + applicability

- 主対象: `farm` / `farm_result` / `farm_lineup` / `lineup` / `lineup_notice` 系(actor 名 / 数字依存度が高い subtype)
- 他 subtype(notice / column / off_field 等)では本検出を **skip**(false positive 防止)
- subtype 取得経路: `_evaluate_record()` → `resolve_guarded_publish_subtype(raw_post, record)`(242-A と同じ helper を再利用)

### tests(必須 fixture、全て pass 必須)

1. **63845 fixture**: 「先発の 投手」「選手の適時打」「試合の詳細はこちら」連発の farm_result body → **hard_stop:`farm_result_placeholder_body`** で refused
2. **良質 farm_result fixture**: actor 名(「先発の 山崎伊織は 5回3失点」「岡本和真の適時打」)+ source URL あり → publish/yellow に通る
3. **空見出し fixture**: `<h2></h2>` 2 件含む farm body → hard_stop
4. **subtype 隔離 fixture**: notice / column subtype に同 placeholder 文があっても本 detector は skip(他 subtype を巻き込まない)
5. **片側のみ filler fixture**: 「試合の詳細はこちら」**1 行だけ**で終わる短い記事 → 既存挙動維持(filler 単独では本 detector は判定しない、別 thin_body gate に任せる)
6. **regression**: 242-A の 5 fixture 全 pass 維持(farm_lineup / farm + source 不在 + roster signal が `roster_movement_yellow` に落ちる)

### baseline(fire-time、prompt 冒頭で再確認)

- tests/test_guarded_publish_evaluator.py + tests/test_guarded_publish_runner.py = `106 collected / 106 passed / 7 subtests passed`(2026-04-28 fire-time rerun baseline)
- 完了報告で diff(collect/pass)を出すこと
- 既存 hard_stop / freshness / lineup_dup / cleanup gate / 242-A の `_medical_roster_flag()` 挙動 不変

### write_scope(明示 stage、git add -A 厳禁)

- `src/guarded_publish_evaluator.py`(detector 追加 + hard_stop set 統合)
- `tests/test_guarded_publish_evaluator.py`(fixture 6 種)
- `tests/test_guarded_publish_runner.py`(必要なら hold_reason / refused error 文言の regression)
- `doc/active/242-D-farm-result-placeholder-body-publish-blocker.md`(本 file、implementation summary 追記)
- `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`(242-D close link 追記)
- `doc/README.md`(242-D row 追加)
- `doc/active/assignments.md`(242-D row 追加)

### non-goals(絶対に触らない)

- **Gemini 本文補完 / 文章生成 / source-based rewrite**(本 ticket では publish blocker のみ、補完は別便)
- env / secret / Cloud Run / Scheduler 変更
- WP publish / X live post / RUN_DRAFT_ONLY
- relevance gate / freshness gate / lineup_dup gate / cleanup_required gate / 242-A `_medical_roster_flag()` の挙動変更
- `INJURY_ROSTER_SIGNAL_RE` / `DEATH_OR_GRAVE_INCIDENT_RE` / `_is_long_term_recovery_story` の発火条件変更
- 226 (subtype_unresolved) との bundle 修正
- ambient dirty(doc/active/206... / doc/done/2026-04/167... / .codex / build/ / logs/ / data/ / docs/handoff/ etc)
- subtype 限定対象外(notice / column / off_field 等)への detector 適用拡大
- 「placeholder 検出 → Gemini に補完依頼」のような fallback 経路の追加

### acceptance(3 点 contract)

1. **着地**: 1 commit に上記 4-7 path を含める(git add -A 禁止、明示 path のみ)
2. **挙動**: pytest 106 baseline + 新規 6 fixture = 112+ collected、全 pass、subtests も全 pass
3. **境界**: 既存 hard_stop / freshness / lineup_dup / cleanup gate / 242-A 挙動 / regex 発火条件 不変、env / secret / WP / X / Scheduler 不変

### commit 規約

- git add -A 禁止、明示 path のみ stage
- commit message: `242-D: farm_result placeholder body publish blocker (63845 type) + 6 fixtures`
- push は Claude が後から実行(Codex は commit までで止まる)
- `.git/index.lock` 拒否時は plumbing 3 段 fallback(write-tree / commit-tree / update-ref)

### 完了報告(必須)

- changed files (path 列挙)
- pytest collect/pass diff (before 106 -> after N)
- 採用 logic 1 行(detector の発火条件 + subtype 限定経路)
- remaining risk / open question
- 次 Claude 判断事項
- commit hash

## 242-D implementation summary

- pytest diff: `106 collected / 106 passed / 7 subtests passed` → `112 collected / 112 passed / 12 subtests passed`
- 採用 logic: `resolve_guarded_publish_subtype()` で解決した subtype が `farm` / `farm_result` / `farm_lineup` / `lineup` / `lineup_notice` のときだけ、空 actor placeholder が同一文または隣接 2 文で 2 hit 以上、または空見出し 2 件以上なら `hard_stop:farm_result_placeholder_body`、単発 cue は `repairable:placeholder_body_repairable`、短い filler-only 締めは skip に倒す
- subtype 判定経路: `_evaluate_record()` → `resolve_guarded_publish_subtype(raw_post, record)` → `_placeholder_body_reason(body_html, _body_text_without_source(record), resolved_subtype)`
- fixture 6 種:
  - 63845 type repeated placeholder farm_result → hard_stop
  - named-actor farm_result → publishable pass
  - double empty heading farm body → hard_stop
  - notice / column subtype isolation → detector skip
  - short filler-only tail → detector skip
  - 242-A medical_roster regression matrix(5 cases) → pass 維持

## 242-D live verify pending

- 242-A + 242-D 着地後に combined verify
- TODO(authenticated executor): 直近 24h の guarded-publish history / dry-run canary を baseline と比較し、`farm_result_placeholder_body` が 63845 type にだけ立つことを確認
- TODO(authenticated executor): 良質 farm_result(named actor + score + source) が publishable のまま通る sample を確認
- TODO(authenticated executor): 242-A の `roster_movement_yellow` sample と本 detector が干渉せず、本物 injury/death hard-stop が維持されることを diff sample で記録
