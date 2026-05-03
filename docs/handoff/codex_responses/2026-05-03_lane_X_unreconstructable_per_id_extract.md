# 2026-05-03 Lane X unreconstructable per-id extract

作成: 2026-05-03 JST

## scope

- user request: read-only audit only
- repo mutation: this handoff doc only
- code / tests / config / WP write / mail / env / scheduler change: 0
- purpose: Lane T の `24件` を Claude WSL verify 用に per-id へ落とし、blind publish を避けたまま今夜の公開候補抽出を支える

## inputs used

- `docs/handoff/codex_responses/2026-05-03_lane_T_unreconstructable_C24_detailed_audit.md`
- `docs/handoff/codex_responses/2026-05-03_lane_O_injury_return_31_audit_publish.md`
- `/tmp/lane_o_guarded_publish_history.jsonl`
- `/tmp/lane_o_publish_notice_queue.jsonl`
- `/tmp/publish_notice_queue_20260503_audit.jsonl`
- `/tmp/good_draft_rescue_eval_20260503.json`
- `/tmp/good_draft_rescue_runner_dryrun_20260503.json`

## Step 1. Lane T 24件 list 抽出

Lane T の `C24` は、実態として以下の 2 区分に分かれる。

- `C ambiguous / still unreconstructable` = `15`
  - `63093`, `63689`, `63924`, `63946`, `63959`, `63972`, `63973`, `64012`, `64058`, `64070`, `64096`, `64097`, `64208`, `64209`, `64264`
- `D duplicate HOLD` = `9`
  - `63135`, `63197`, `63468`, `63482`, `63841`, `63950`, `64129`, `64131`, `64318`

## Step 2. per-id metadata 集約

注意:

- `latest_hold_reason` は local artifact で回収できた latest row を優先した。
- `keyword hit` は `title / queue subject / local reconstruction` で人間が読めたものだけを書く。全件に付いている `hard_stop_death_or_grave_incident` classifier 自体は、この列には含めない。
- `duplicate_target_post_id` / `duplicate_target_source_url` は、今回の 9 件について **local history 上では全て null / unrecovered**。duplicate target の確定は Claude WSL 側の current public title/link verify が必要。

| class | post_id | latest ts (JST) | recovered title / source | subtype inference | latest hold_reason | latest error detail | duplicate signal | duplicate_target_post_id | duplicate_target_source_url | surfaced keyword hit | notes |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| C | 63093 | `2026-05-03T08:20:39.894312+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | title/source とも復元失敗 |
| D | 63135 | `2026-05-03T08:20:39.894312+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` | null locally | null locally | none surfaced | D bucket; duplicate target 未復元 |
| D | 63197 | `2026-05-03T19:05:39.742769+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` | null locally | null locally | none surfaced | 2026-04-26 に一度 `daily_cap` 行あり、latest は duplicate co-hit |
| D | 63468 | `2026-05-03T19:05:39.742769+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` | null locally | null locally | none surfaced | D bucket; duplicate target 未復元 |
| D | 63482 | `2026-05-03T19:05:39.742769+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` | null locally | null locally | none surfaced | D bucket; duplicate target 未復元 |
| C | 63689 | `2026-05-03T00:15:38.541110+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | title/source とも復元失敗 |
| D | 63841 | `2026-04-28T12:30:35.534155+09:00` | `巨人二軍スタメン 若手をどう並べたか` / queue subject only | `farm_lineup` (doc inference) | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` | null locally | null locally | none surfaced | publish-notice queue に `【公開済】` と `【要確認】` の subject 履歴あり |
| C | 63924 | `2026-05-03T03:15:39.887848+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | older row に `hard_stop_farm_result_placeholder_body` があったが latest は death/grave |
| C | 63946 | `2026-05-03T12:25:39.330058+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | title/source とも復元失敗 |
| D | 63950 | `2026-05-03T14:10:37.184961+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` | null locally | null locally | none surfaced | D bucket; duplicate target 未復元 |
| C | 63959 | `2026-05-03T14:35:39.986483+09:00` | `【5/3予告先発】 ー （甲子園、14:00) 巨人:(2勝2敗、防御率1.90) 阪神:(2勝1敗、防御率5.00)` / `https://twitter.com/sanspo_giants/status/2050430325315264981` | `pregame` / `probable_starter` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | injury/return 系ではなく pregame 系として扱う |
| C | 63972 | `2026-05-03T16:35:37.326877+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | title/source とも復元失敗 |
| C | 63973 | `2026-05-03T16:35:37.326877+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | title/source とも復元失敗 |
| C | 64012 | `2026-05-03T18:05:38.916436+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | title/source とも復元失敗 |
| C | 64058 | `2026-04-29T23:25:37.461461+09:00` | unrecovered | unknown | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | local latest row は 4/29 23:25 JST まで |
| C | 64070 | `2026-05-03T01:10:41.101062+09:00` | `巨人戦 杉内俊哉先発 試合前情報` / source unrecovered | `pregame` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | injury/return 系ではなく pregame 系として扱う |
| C | 64096 | `2026-05-03T14:25:40.315287+09:00` | `投手陣「あんまり良くないっていうのは確か」 ベンチ関連発言` / source unrecovered | `comment` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | none surfaced | coach lexical hit までは断定不可 |
| C | 64097 | `2026-05-03T16:35:37.326877+09:00` | `【4/30公示】 (登録) (抹消)なし` / source unrecovered | `notice` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | `roster` | 公示系だが duplicate は見えていない |
| D | 64129 | `2026-05-03T18:50:39.173956+09:00` | `選手「打撃の神様」 関連発言` / source unrecovered | `comment` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` + `duplicate_title_match_types=exact_title_match,normalized_suffix_title_match` | null locally | null locally | none surfaced | `64131` と同題名。title-match は強いが canonical target は未確定 |
| D | 64131 | `2026-05-03T18:55:37.642971+09:00` | `選手「打撃の神様」 関連発言` / source unrecovered | `comment` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,ranking_list_only,lineup_duplicate_excessive` | `lineup_duplicate_excessive` + `duplicate_title_match_types=exact_title_match,normalized_suffix_title_match` | null locally | null locally | none surfaced | `ranking_list_only` も co-hit。title-match は強いが canonical target は未確定 |
| C | 64208 | `2026-05-03T16:20:36.887468+09:00` | `1軍に合流した 投手 ノックで元気な姿を見せています` / source unrecovered | `notice` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | `return`, `roster` | title だけ見ると fan-important だが source/current status 未確認 |
| C | 64209 | `2026-05-03T16:20:36.887468+09:00` | `(登録) (抹消) ※再登録は11日以降` / source unrecovered | `roster` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | `roster` | 公示系。duplicate は見えていない |
| C | 64264 | `2026-05-03T12:10:39.035340+09:00` | `【5/2公示】 (登録)なし (抹消)なし` / source unrecovered | `notice` | `hard_stop_death_or_grave_incident` | `death_or_grave_incident` | none | n/a | n/a | `roster` | 公示系。duplicate は見えていない |
| D | 64318 | `2026-05-03T11:40:36.493466+09:00` | `投手が１軍に合流` / source unrecovered | `notice` / `一軍合流` (log inference) | `hard_stop_death_or_grave_incident` | `death_or_grave_incident,lineup_duplicate_excessive` | `lineup_duplicate_excessive` | null locally | null locally | `return`, `roster` | title だけ見ると fan-important だが duplicate co-hit のため D 維持 |

## Step 3. Claude WSL verify 指示

### verify contract

- Codex sandbox では WP REST read が不通だったため、current public state 確認は Claude WSL 側で行う。
- 目的は `現在 publish 済か / まだ public に見えない draft か` の切り分けであり、**ここでは publish しない**。
- 想定 code:
  - `200`: public 取得可。`title / date / link` を採取し、`E 既 publish` か `duplicate canonical のヒント` として扱う。
  - `401`: public 取得不可。現時点では draft 維持とみなし、A/C/D の後段判定へ回す。
  - `404` / `5xx`: 想定外。transport or permalink anomaly として HOLD。

### common command pattern

各 ID でまず次を実行する。

```bash
curl -sS -o /tmp/wp_POSTID.json -w 'post_id=POSTID code=%{http_code}\n' \
  "https://yoshilover.com/wp-json/wp/v2/posts/POSTID?_fields=id,date,link,status,title"
```

`code=200` のときだけ、直後に metadata を見る。

```bash
python3 - <<'PY' /tmp/wp_POSTID.json
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
print("status=", d.get("status"))
print("date=", d.get("date"))
print("link=", d.get("link"))
print("title=", d.get("title", {}).get("rendered"))
PY
```

### 24件 one-by-one curl

```bash
curl -sS -o /tmp/wp_63093.json -w 'post_id=63093 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63093?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63135.json -w 'post_id=63135 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63135?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63197.json -w 'post_id=63197 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63197?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63468.json -w 'post_id=63468 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63468?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63482.json -w 'post_id=63482 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63482?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63689.json -w 'post_id=63689 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63689?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63841.json -w 'post_id=63841 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63841?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63924.json -w 'post_id=63924 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63924?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63946.json -w 'post_id=63946 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63946?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63950.json -w 'post_id=63950 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63950?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63959.json -w 'post_id=63959 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63959?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63972.json -w 'post_id=63972 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63972?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_63973.json -w 'post_id=63973 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/63973?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64012.json -w 'post_id=64012 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64012?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64058.json -w 'post_id=64058 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64058?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64070.json -w 'post_id=64070 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64070?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64096.json -w 'post_id=64096 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64096?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64097.json -w 'post_id=64097 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64097?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64129.json -w 'post_id=64129 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64129?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64131.json -w 'post_id=64131 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64131?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64208.json -w 'post_id=64208 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64208?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64209.json -w 'post_id=64209 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64209?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64264.json -w 'post_id=64264 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64264?_fields=id,date,link,status,title"
curl -sS -o /tmp/wp_64318.json -w 'post_id=64318 code=%{http_code}\n' "https://yoshilover.com/wp-json/wp/v2/posts/64318?_fields=id,date,link,status,title"
```

### expected interpretation

- `code=200`
  - public URL 化済の可能性が高い。
  - `title / date / link` を記録し、`E 既 publish` として扱う。
  - D 行で `200` が返り、かつ別の public post と同題名 / 同 source を示す場合は `D duplicate` を補強できる。
- `code=401`
  - まだ public に読めない状態として扱う。
  - C 行なら `A` または `C` 再判定の対象。
  - D 行なら duplicate HOLD を維持する。
- `code=404` or `5xx`
  - 想定外。post existence / REST exposure / permalink anomaly として HOLD。

## Step 4. post-WSL-verify 区分判定 framework

| class | 条件 | action |
|---|---|---|
| A. fan-important publish candidate | `401` かつ current public 未公開、`injury` または `return` lexical hit があり、`duplicate signal` がなく、title/source が fan-important と読める。`roster` 単独では上げない | publish candidate へ昇格。今夜の公開候補 list に載せる |
| B. real death-grave HOLD | WSL verify で `title` または public `link` から訃報 / 追悼 / grave 系が明示される | HOLD 維持。publish しない |
| C. ambiguous still | `401` のまま、title/source/subtype の復元が弱い、または fan-important と言い切れない | HOLD 維持。追加 reconstruction が要る |
| D. duplicate HOLD | Lane T D bucket 9件、または WSL verify で同題名 / 同 source の canonical public post が見える | HOLD 維持。canonical 側だけ使う |
| E. already published | `200` で public `title / link / date` が取れる | 既対応として除外。二重 publish しない |

### high-priority recheck candidates after WSL verify

user 指定の strict A 条件は `injury/return hit + duplicate なし + 401` なので、local evidence だけで A へ上げ得る最上位は次の 1 件。

- `64208` - `return`, `roster`

roster-only で止まっているため、strict A にはまだ乗せない行:

- `64097`
- `64209`
- `64264`

現時点では D のため A に上げないが、public state の確認価値が高い行:

- `64318` - `return`, `roster`, ただし `lineup_duplicate_excessive` co-hit

## working conclusion

- local evidence だけで tonight publish に進める安全候補は **まだ 0**
- Claude WSL verify で `200/401` を切ったあとにだけ、
  - `E 既 publish` を除外し、
  - strict A 条件に照らして `64208` を再昇格できるかを見る
  - `64097` / `64209` / `64264` は roster-only のため、user が A 条件を広げない限り C 維持で扱う
- D 9件は duplicate target が local で未回収のため、**WSL verify 前の昇格禁止**
